# -*- coding: utf-8 -*-
"""声明式数据接入管道 —— 主引擎。

一条命令把 data_sources/ 里的真实数据按 MANIFEST.json 声明的规则，
**自动分类并落到正确的库/表**，产出一份质检报告。

流程（对每个 manifest 里的 source）：
    读取原始文件
      → 逐行: 字段映射(field_map) → 声明规则(rules) → 目标表位(target)
      → 收集命中/丢弃/校验问题
      → 按 target.db / target.table 用 ScoreDB.upsert_* 落库
    → 汇总：每库每表写入行数 + 丢弃行数 + 校验告警

落库位置（target.db）取值：
    score   → score_db（换算库），目标表必须属于 SCORE_TABLES
    quality → quality_db（分析库），目标表必须属于 QUALITY_TABLES
若声明的目标表不属于对应库，会在校验阶段直接报错——这正是"别放错库/表"的
守护点：**字段映射与目标表由声明文件约束，代码不猜**。
"""
from __future__ import annotations
import os, csv, json
from typing import Dict, List, Optional, Any
from ..db import ScoreDB, QUALITY_TABLES, SCORE_TABLES
from . import rules as rules_mod


class SourceDecl:
    """从 manifest 里解析出的单个数据源声明。"""

    def __init__(self, decl: dict):
        self.source_id = decl.get("source_id", "")
        self.file = decl.get("file", "")
        self.format = decl.get("format", "csv")
        self.db = decl.get("target", {}).get("db", "")
        self.table = decl.get("target", {}).get("table", "")
        self.field_map = decl.get("field_map", {}) or {}
        self.rule_names = decl.get("rules", []) or []
        self.ctx = {
            "source": decl.get("source"),
            "year": decl.get("year"),
            "required_fields": decl.get("required_fields", []) or [],
            "defaults": decl.get("defaults", {}) or {},
            "int_fields": decl.get("int_fields", []) or [],
            "float_fields": decl.get("float_fields", []) or [],
            "bool_fields": decl.get("bool_fields", []) or [],
            "id_field": decl.get("id_field"),
            "id_name_field": decl.get("id_name_field"),
            "rank_field": decl.get("rank_field"),
            "source_url": decl.get("source_url", ""),
            "provenance": decl.get("provenance", ""),
        }

    def _check_target(self):
        """守护：声明的目标表必须属于对应库，防止放错。"""
        if self.db == "score" and self.table not in SCORE_TABLES:
            raise ValueError(
                f"[{self.source_id}] 目标表 '{self.table}' 不属于换算库 score_db。"
                f"合法表: {sorted(SCORE_TABLES)}")
        if self.db == "quality" and self.table not in QUALITY_TABLES:
            raise ValueError(
                f"[{self.source_id}] 目标表 '{self.table}' 不属于分析库 quality_db。"
                f"合法表: {sorted(QUALITY_TABLES)}")
        if self.db not in ("score", "quality"):
            raise ValueError(f"[{self.source_id}] target.db 必须是 score/quality，得 {self.db!r}")

    def fields_of_table(self):
        return SCORE_TABLES.get(self.table) or QUALITY_TABLES.get(self.table) or []


def _map_row(raw: Dict[str, Any], fm: Dict[str, str]) -> Dict[str, Any]:
    """按 field_map 把原始字段映射到目标表字段（白名单对齐）。"""
    out: Dict[str, Any] = {}
    for target_key, src_key in fm.items():
        out[target_key] = raw.get(src_key)
    # 保留 map 之外的原始字段，规则可能用到（如基于 name 生成 id）
    known_src = set(fm.values())
    for k, v in raw.items():
        if k not in known_src and k not in out:
            out[k] = v
    return out


def _read_rows(src: SourceDecl, base_dir: str) -> List[Dict[str, Any]]:
    path = os.path.join(base_dir, src.file)
    if not os.path.exists(path):
        raise FileNotFoundError(f"[{src.source_id}] 原始数据文件不存在: {path}")
    if src.format == "json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("records", [])
    # csv
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(dict(r))
    return rows


def run(db: ScoreDB, manifest_path: Optional[str] = None,
        base_dir: Optional[str] = None) -> Dict[str, Any]:
    """执行一次管道接入。manifest_path 默认 pipeline/MANIFEST.json。"""
    here = os.path.dirname(os.path.abspath(__file__))
    # data_sources 位于 score-engine 根（pipeline 之上两级）
    base_dir = base_dir or os.path.join(
        os.path.dirname(os.path.dirname(here)), "data_sources")
    manifest_path = manifest_path or os.path.join(here, "MANIFEST.json")

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    sources = [SourceDecl(d) for d in manifest.get("sources", [])]

    summary = {
        "sources": len(sources),
        "per_source": [],            # 每源质检
        "by_table": {},              # 表 → 累计写入
        "dropped_total": 0,
        "warnings": [],
    }
    ok_tables = set()

    for src in sources:
        src._check_target()          # 表位守护：防放错库
        raw_rows = _read_rows(src, base_dir)
        inserted, dropped = 0, 0
        warnings = []
        target_fields = src.fields_of_table()
        batch = []
        for raw in raw_rows:
            mapped = _map_row(raw, src.field_map)
            try:
                out = rules_mod.apply_rules(mapped, src.rule_names, src.ctx)
            except KeyError as e:     # 未登记规则名
                raise e
            if out is None:
                dropped += 1
                continue
            # 只保留目标表 schema 白名单字段（丢弃未知列，避免污染表结构）
            rec = {k: out.get(k) for k in target_fields}
            batch.append(rec)
        # 落库
        if batch:
            if src.db == "score":
                n = db.upsert_score(src.table, batch)
            else:
                n = db.upsert_quality(src.table, batch)
            inserted = n
            ok_tables.add(src.table)
        # 校验问题：声明必填/源文件是否有空等
        if inserted < len(batch):
            warnings.append(f"{len(batch)-inserted} 行未实际写入(可能主键重复)")
        if dropped:
            warnings.append(f"{dropped} 行因规则被丢弃(缺必填等)")

        summary["per_source"].append({
            "source_id": src.source_id,
            "db": src.db,
            "table": src.table,
            "read": len(raw_rows),
            "inserted": inserted,
            "dropped": dropped,
            "warnings": warnings,
            "provenance": src.ctx.get("provenance", ""),
        })
        summary["dropped_total"] += dropped
        summary["by_table"][f"{src.db}.{src.table}"] = \
            summary["by_table"].get(f"{src.db}.{src.table}", 0) + inserted
        summary["warnings"].extend(warnings)

    summary["covered_tables"] = sorted(ok_tables)
    return summary


def describe(manifest_path: Optional[str] = None) -> str:
    """打印 manifest 概览（数据源声明一览）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    manifest_path = manifest_path or os.path.join(here, "MANIFEST.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    lines = []
    lines.append(f"声明文件: {os.path.relpath(manifest_path)}")
    lines.append(f"共 {len(manifest.get('sources', []))} 个数据源:")
    for d in manifest.get("sources", []):
        tgt = d.get("target", {})
        lines.append(
            f"  · {d.get('source_id'):<24} → {tgt.get('db','?'):<8}."
            f"{tgt.get('table','?'):<20} 源={d.get('source','?')} "
            f"年份={d.get('year','-')} 规则={len(d.get('rules',[]))}条")
    return "\n".join(lines)
