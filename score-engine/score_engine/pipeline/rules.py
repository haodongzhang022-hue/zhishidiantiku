# -*- coding: utf-8 -*-
"""数据管道规则引擎（声明式）。

Manifest 中每个数据源可用 `rules` 字段声明一组规则（字符串名），
管道在 ingest 时逐条应用到该源的每条原始记录上，完成
**清洗 / 校验 / 分类 / 去重 / 溯源**。

规则均为纯函数，签名统一为 ``fn(row: dict, ctx: dict) -> dict``，
其中 ctx 携带 manifest 里该 source 的静态上下文（如 source 名、year、默认值）。

规则注册表 RULES：名字 → 函数。新规则在此登记后即可在 MANIFEST.json 里引用，
**无需改动 ingest 主流程**——这保证了"加新数据源 = 只改声明文件"的复用能力。
"""
from __future__ import annotations
from typing import Dict, Callable, List
import json


# ---------------------------------------------------------------------------
# 规则函数（row: 单条原始记录；ctx: 该 source 的静态上下文）
# ---------------------------------------------------------------------------

def drop_if_missing(row: dict, ctx: dict) -> dict:
    """必填字段缺失 → 该行判为无效（返回 None 表示丢弃）。"""
    for f in ctx.get("required_fields", []):
        v = row.get(f)
        if v is None or str(v).strip() == "":
            return None
    return row


def fill_defaults(row: dict, ctx: dict) -> dict:
    """为声明里列出的缺省字段填充默认值（清洗空值）。"""
    for f, val in (ctx.get("defaults", {}) or {}).items():
        if row.get(f) is None or str(row.get(f)).strip() == "":
            row[f] = val
    return row


def to_int_fields(row: dict, ctx: dict) -> dict:
    """把指定字段转 int；失败保持原样或按 fallback。"""
    for f in ctx.get("int_fields", []):
        v = row.get(f)
        if v is None or str(v).strip() == "":
            continue
        try:
            row[f] = int(float(str(v).replace(",", "")))
        except Exception:
            pass
    return row


def to_float_fields(row: dict, ctx: dict) -> dict:
    """把指定字段转 float。"""
    for f in ctx.get("float_fields", []):
        v = row.get(f)
        if v is None or str(v).strip() == "":
            continue
        try:
            row[f] = float(str(v).replace(",", ""))
        except Exception:
            pass
    return row


def to_bool_fields(row: dict, ctx: dict) -> dict:
    """把指定字段转 bool（兼容 True/False/0/1/yes/no/是/否 等写法）。"""
    for f in ctx.get("bool_fields", []):
        v = row.get(f)
        if v is None or str(v).strip() == "":
            continue
        s = str(v).strip().lower()
        row[f] = s in ("1", "true", "yes", "是", "y", "public")
    return row


def strip_strings(row: dict, ctx: dict) -> dict:
    """去除字符串字段首尾空白。"""
    for k, v in row.items():
        if isinstance(v, str):
            row[k] = v.strip()
    return row


def ensure_id(row: dict, ctx: dict) -> dict:
    """保证目标主键字段存在且唯一稳定：缺省则由 name 生成 slug 型 id。"""
    id_field = ctx.get("id_field", "id")
    name_field = ctx.get("id_name_field", "name_en")
    if not row.get(id_field) and row.get(name_field):
        row[id_field] = _slugify(str(row[name_field]))
    return row


def set_band_from_rank(row: dict, ctx: dict) -> dict:
    """按排名自动给 band 分组（排名→档位，声明式分类规则）。"""
    rk = row.get(ctx.get("rank_field", "rank"))
    if rk is None:
        return row
    try:
        rk = int(rk)
    except Exception:
        return row
    if rk <= 10:
        row["band"] = "top10"
    elif rk <= 50:
        row["band"] = "top50"
    elif rk <= 100:
        row["band"] = "top100"
    elif rk <= 500:
        row["band"] = "top500"
    elif rk <= 1000:
        row["band"] = "top1000"
    else:
        row["band"] = "1000+"
    return row


def tag_source(row: dict, ctx: dict) -> dict:
    """给行打溯源标记（source / 数据年份）。"""
    if ctx.get("source"):
        row["source"] = ctx["source"]
    if ctx.get("year") is not None:
        row["year"] = ctx["year"]
    if ctx.get("as_quality") and not row.get("_quality_flag"):
        row["_quality_flag"] = True
    return row


def _slugify(s: str) -> str:
    out = []
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
    s2 = "".join(out)
    return s2[:40] if s2 else "item"


# ---------------------------------------------------------------------------
# 注册表：名字 → 函数
# ---------------------------------------------------------------------------
RULES: Dict[str, Callable[[dict, dict], dict]] = {
    "drop_if_missing": drop_if_missing,
    "fill_defaults": fill_defaults,
    "to_int_fields": to_int_fields,
    "to_float_fields": to_float_fields,
    "strip_strings": strip_strings,
    "ensure_id": ensure_id,
    "set_band_from_rank": set_band_from_rank,
    "tag_source": tag_source,
    "to_bool_fields": to_bool_fields,
}


def apply_rules(row: dict, rule_names: List[str], ctx: dict) -> dict:
    """按顺序把 manifest 声明的规则应用到一行；返回 None 表示该行被丢弃。"""
    for name in rule_names or []:
        fn = RULES.get(name)
        if fn is None:
            raise KeyError(f"未知规则: {name}（请在 pipeline/rules.py 登记）")
        row = fn(row, ctx)
        if row is None:   # 规则判定丢弃
            return None
    return row
