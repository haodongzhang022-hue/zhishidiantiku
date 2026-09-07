# -*- coding: utf-8 -*-
"""双库数据接入层 —— LanceDB（可选后端）+ 纯标准库兜底后端。

背景（对齐 issue #8 追评）：用户希望把分数换算相关的数据**入库管理**，
拆成两套、减少人工查询，并给出明确的表 schema。本模块把 roadmap 里的
双库多表 schema 落成可查询的数据层：

```
┌──────────── 分析库 quality_db（质量鉴定维度） ────────────┐
│ school_profile   学校档案：规模/师生比/学费/论文/就业/认证  │
│ school_faculty   师资档案：分层含负面(star/tier/negative)  │
│ school_outcome   成果/声誉：论文产出/被引/就业/认证        │
└──────────────────────────────────────────────────────────┘
┌──────────── 换算库 score_db（分数/录取门槛维度）───────────┐
│ university           大学静态实体档案（跟学校走）          │
│ university_ranking   排名动态(大学×来源×年份)             │
│ admission_threshold  录取门槛(大学×体系×年份)             │
│ system_calendar      各体系年度漂移系数                   │
└──────────────────────────────────────────────────────────┘
```

**后端策略（关键）**
- 引擎整体保持"无第三方硬依赖"。LanceDB 是可选后端：
  当环境里 `lancedb` 可导入 → 落到真实 LanceDB；
  否则退化为**纯标准库 JSON 表存储**（同一套 schema 与查询 API），
  保证 CI（python:3.11）无需额外装包也能全绿。
- 两套后端对外暴露**统一 API**：`upsert(table, rows)` / `query(...)` /
  `count` / `tables` / `close`，调用方无感知。

典型用法见 `cli.py` 的 `db seed` / `db tables` / `db query`。
"""
from __future__ import annotations
import os, json, copy
from typing import Dict, List, Optional, Any, Iterable

# ---------------------------------------------------------------------------
# 双库 schema 定义（表名 → 字段列表 + 说明）
# ---------------------------------------------------------------------------

QUALITY_TABLES: Dict[str, List[str]] = {
    # 分析库：质量鉴定维度
    "school_profile": [
        "university_id", "name", "scale_students", "scale_faculty",
        "ratio_student_faculty", "tuition_intl_usd", "papers_yearly",
        "citations", "employment_rate", "accreditation", "source", "year",
    ],
    "school_faculty": [
        "university_id", "name", "tier_high", "tier_mid", "tier_low",
        "star_count", "negative_ratio", "note", "source", "year",
    ],
    "school_outcome": [
        "university_id", "name", "papers_yearly", "citations", "h_index",
        "patents", "employment_rate", "salary_outcome", "source", "year",
    ],
}

SCORE_TABLES: Dict[str, List[str]] = {
    # 换算库：分数/录取门槛维度
    "university": [
        "id", "name_en", "name_zh", "country", "city", "established",
        "is_public", "tuition_intl_usd", "note",
    ],
    "university_ranking": [
        "university_id", "source", "year", "rank", "band",
    ],
    "admission_threshold": [
        "university_id", "year", "system", "raw_score", "unified_value",
        "source", "admitted",
    ],
    "system_calendar": [
        "year", "system", "difficulty_index", "scale", "n_samples",
    ],
}

# ---------------------------------------------------------------------------
# 各表逻辑主键：upsert 时用于"命中更新而非追加重复"
# ---------------------------------------------------------------------------
# - university / university_ranking 等表有明确的自然主键（如 id / university_id+source+year），
#   重复 ingest 时按主键合并——同主键新数据覆盖旧数据（更新），不同主键追加。
# - admission_threshold 存多条独立录取样本，无单一逻辑主键 → 不在此表登记，
#   靠整行内容做字节级幂等去重（完全相同的行不重复写入）。
TABLE_PRIMARY_KEYS: Dict[str, List[str]] = {
    # 换算库 score_db
    "university": ["id"],
    "university_ranking": ["university_id", "source", "year"],
    "system_calendar": ["year", "system"],
    # 分析库 quality_db（每校一条档案）
    "school_profile": ["university_id"],
    "school_faculty": ["university_id"],
    "school_outcome": ["university_id"],
}


def _row_to_record(row: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    """按表 schema 白名单规整一行（丢弃未知列，补齐缺省）。"""
    out: Dict[str, Any] = {}
    for f in fields:
        out[f] = row.get(f)
    return out


# ---------------------------------------------------------------------------
# 后端 1：LanceDB（可选，导入即启用）
# ---------------------------------------------------------------------------
def _make_lancedb_backend(root: str):
    """尝试构建 LanceDB 后端；不可用则返回 None。"""
    try:
        import lancedb
    except Exception:
        return None
    try:
        return LanceDBBackend(root, lancedb=lancedb)
    except Exception:
        return None


class LanceDBBackend:
    """真实 LanceDB 后端。每个表一个 lancedb 数据集。"""

    def __init__(self, root: str, lancedb=None):
        import lancedb  # 再次确认可用
        self._lancedb = lancedb
        self.root = root
        os.makedirs(root, exist_ok=True)
        self._db = lancedb.connect(root)

    def _dataset(self, table: str):
        return self._db.open_table(table) if table in self._db.table_names() else None

    def upsert(self, table: str, rows: List[Dict[str, Any]], fields: List[str]) -> int:
        """按逻辑主键合并写入（PK 相同→更新；不同→追加），返回净新增行数。

        LanceDB 无原生按字段 merge 的 upsert，故读出现有数据 → 内存合并 → 整表覆写。
        小规模表数据下该策略正确可靠；大规模后可换 lancedb 的增量 add + 去重方案。
        """
        norm = [_row_to_record(r, fields) for r in rows]
        if not norm:
            return 0
        existing = self.query(table, fields)
        pk = TABLE_PRIMARY_KEYS.get(table)
        if pk:
            def pk_of(r: Dict[str, Any]) -> str:
                return json.dumps({k: r.get(k) for k in pk},
                                  sort_keys=True, ensure_ascii=False)
            old_pks = {pk_of(r) for r in existing}
            new_map = {pk_of(r): r for r in norm}
            keep = [r for r in existing if pk_of(r) not in new_map]
            merged = keep + list(new_map.values())
            n_new = sum(1 for r in norm if pk_of(r) not in old_pks)
        else:
            def row_key(r: Dict[str, Any]) -> str:
                return json.dumps(r, sort_keys=True, ensure_ascii=False)
            old_keys = {row_key(r) for r in existing}
            new_entries = [r for r in norm if row_key(r) not in old_keys]
            merged = existing + new_entries
            n_new = len(new_entries)
        if merged:
            self._db.create_table(table, data=merged, mode="overwrite")
        return n_new

    def query(self, table: str, fields: List[str],
              filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        ds = self._dataset(table)
        if ds is None:
            return []
        try:
            data = ds.to_pandas().to_dict("records")
        except Exception:
            return []
        return _apply_filters(data, filters)

    def count(self, table: str) -> int:
        return len(self.query(table, []))

    def tables(self) -> List[str]:
        return sorted(self._db.table_names())

    def close(self):
        pass


# ---------------------------------------------------------------------------
# 后端 2：纯标准库 JSON 表存储（无 LanceDB 时兜底）
# ---------------------------------------------------------------------------
class JsonBackend:
    """把每张表存成一个 JSON 文件，模拟表存储（无第三方依赖）。

    用于无 LanceDB 的环境（如 CI python:3.11 基础镜像），
    与 LanceDB 后端暴露**完全一致**的 API。
    """

    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)
        self._cache: Dict[str, List[Dict[str, Any]]] = {}
        self._load_all()

    def _path(self, table: str) -> str:
        return os.path.join(self.root, f"{table}.json")

    def _load_all(self):
        if not os.path.isdir(self.root):
            return
        for fn in os.listdir(self.root):
            if fn.endswith(".json"):
                t = fn[:-5]
                try:
                    with open(os.path.join(self.root, fn), encoding="utf-8") as f:
                        self._cache[t] = json.load(f)
                except Exception:
                    self._cache[t] = []

    def upsert(self, table: str, rows: List[Dict[str, Any]], fields: List[str]) -> int:
        """按逻辑主键合并写入（PK 相同→更新替换；不同→追加），返回净新增行数。"""
        norm = [_row_to_record(r, fields) for r in rows]
        if not norm:
            return 0
        existing = self._cache.get(table, [])
        pk = TABLE_PRIMARY_KEYS.get(table)
        if pk:
            def pk_of(r: Dict[str, Any]) -> str:
                return json.dumps({k: r.get(k) for k in pk},
                                  sort_keys=True, ensure_ascii=False)
            old_pks = {pk_of(r) for r in existing}
            new_map = {pk_of(r): r for r in norm}
            # 未被本轮数据覆盖的旧行保留；命中 PK 的旧行被新数据替换
            keep = [r for r in existing if pk_of(r) not in new_map]
            merged = keep + list(new_map.values())
            n_new = sum(1 for r in norm if pk_of(r) not in old_pks)
        else:
            # 无逻辑主键表（如 admission_threshold）：整行字节级幂等去重
            def row_key(r: Dict[str, Any]) -> str:
                return json.dumps(r, sort_keys=True, ensure_ascii=False)
            old_keys = {row_key(r) for r in existing}
            new_entries = [r for r in norm if row_key(r) not in old_keys]
            merged = existing + new_entries
            n_new = len(new_entries)
        self._cache[table] = merged
        with open(self._path(table), "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=1)
        return n_new

    def query(self, table: str, fields: List[str],
              filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        data = self._cache.get(table, [])
        return _apply_filters(copy.deepcopy(data), filters)

    def count(self, table: str) -> int:
        return len(self._cache.get(table, []))

    def tables(self) -> List[str]:
        return sorted(self._cache)

    def close(self):
        pass


def _apply_filters(rows: List[Dict[str, Any]],
                   filters: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not filters:
        return rows
    out = []
    for r in rows:
        ok = True
        for k, v in filters.items():
            if r.get(k) != v:
                ok = False
                break
        if ok:
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# 统一门面：双库
# ---------------------------------------------------------------------------
class ScoreDB:
    """分数换算引擎的双库门面（quality_db + score_db）。

    参数 root 为存储根目录；若 LanceDB 可用则落到 LanceDB，否则 JSON 兜底。
    默认把两张库放到 {root}/quality_db 和 {root}/score_db 两个子目录。
    """

    QUALITY = QUALITY_TABLES
    SCORE = SCORE_TABLES

    def __init__(self, root: str = "./data_lancedb", backend: Optional[str] = None):
        self.root = root
        self.quality_root = os.path.join(root, "quality_db")
        self.score_root = os.path.join(root, "score_db")
        # backend: 'lancedb' | 'json' | None(自动)
        if backend == "lancedb":
            q = _make_lancedb_backend(self.quality_root)
            if q is None:
                raise RuntimeError("LanceDB 不可用")
            self.quality = q
            self.score = _make_lancedb_backend(self.score_root)
        elif backend == "json":
            self.quality = JsonBackend(self.quality_root)
            self.score = JsonBackend(self.score_root)
        else:
            # 自动：优先 LanceDB
            q = _make_lancedb_backend(self.quality_root)
            if q is not None:
                s = _make_lancedb_backend(self.score_root)
                self.quality, self.score = q, s
            else:
                self.quality = JsonBackend(self.quality_root)
                self.score = JsonBackend(self.score_root)

    # -- 分析库 ----------
    def upsert_quality(self, table: str, rows: List[Dict[str, Any]]) -> int:
        if table not in QUALITY_TABLES:
            raise KeyError(f"分析库无此表: {table}")
        return self.quality.upsert(table, rows, QUALITY_TABLES[table])

    def query_quality(self, table: str,
                      filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return self.quality.query(table, QUALITY_TABLES[table], filters)

    # -- 换算库 ----------
    def upsert_score(self, table: str, rows: List[Dict[str, Any]]) -> int:
        if table not in SCORE_TABLES:
            raise KeyError(f"换算库无此表: {table}")
        return self.score.upsert(table, rows, SCORE_TABLES[table])

    def query_score(self, table: str,
                    filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return self.score.query(table, SCORE_TABLES[table], filters)

    def count_quality(self, table: str) -> int:
        return self.quality.count(table)

    def count_score(self, table: str) -> int:
        return self.score.count(table)

    def quality_tables(self) -> List[str]:
        return sorted(QUALITY_TABLES)

    def score_tables(self) -> List[str]:
        return sorted(SCORE_TABLES)

    def backend_kind(self) -> str:
        """返回实际生效的后端类型。"""
        return "lancedb" if isinstance(self.quality, LanceDBBackend) else "json"

    def close(self):
        self.quality.close()
        self.score.close()

    # -- 便捷：把引擎现有对象一次性灌库 ----------
    def seed_from_engine(self, universities=None, rankings=None,
                         records=None, faculties=None, profiles=None,
                         outcomes=None, drift=None) -> Dict[str, int]:
        """把内存中的大学/排名/样本/质量数据灌入双库。

        返回各表写入行数。数据源为可选，未给则用模块默认（universities 等）。
        """
        from . import university as univ_mod
        from . import drift as drift_mod
        if universities is None:
            universities = univ_mod.default_universities()
        if rankings is None:
            rankings = univ_mod.default_rankings()

        uni_rows = [u.to_dict() for u in universities]
        rank_rows = [r.to_dict() for r in rankings]
        n_uni = self.upsert_score("university", uni_rows)
        n_rank = self.upsert_score("university_ranking", rank_rows)

        n_thr = 0
        if records is not None:
            thr_rows = []
            for rec in records:
                uid = getattr(rec, "university_id", "") or rec.school
                thr_rows.append({
                    "university_id": uid, "year": rec.year, "system": rec.system,
                    "raw_score": json.dumps(rec.features, ensure_ascii=False),
                    "unified_value": getattr(rec, "school_value", None),
                    "source": rec.source, "admitted": bool(getattr(rec, "admitted", True)),
                })
            n_thr = self.upsert_score("admission_threshold", thr_rows)

        n_cal = 0
        if drift is not None or records is not None:
            if drift is None and records is not None:
                drift = drift_mod.YearDrift.from_records(records)
            if drift is not None:
                cal_rows = [{"year": r["year"], "system": "ALL",
                             "difficulty_index": r["difficulty_index"],
                             "scale": r["scale"], "n_samples": 0}
                            for r in drift.trend()]
                n_cal = self.upsert_score("system_calendar", cal_rows)

        n_pf = n_fc = n_out = 0
        if faculties is not None:
            n_fc = self.upsert_quality("school_faculty", faculties)
        if profiles is not None:
            n_pf = self.upsert_quality("school_profile", profiles)
        if outcomes is not None:
            n_out = self.upsert_quality("school_outcome", outcomes)

        return {"university": n_uni, "university_ranking": n_rank,
                "admission_threshold": n_thr, "system_calendar": n_cal,
                "school_profile": n_pf, "school_faculty": n_fc,
                "school_outcome": n_out}
