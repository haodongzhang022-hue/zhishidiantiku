# -*- coding: utf-8 -*-
"""门槛洼地寻优 —— 找到"同一学校录取价值下相对最低分的那条体系路径"。

对同一所学校，不同体系录取口径换算成统一价值后，会呈现不同"达成成本"。
"门槛洼地" = 在价值相等的前提下，所需原始分折算成"标准竞争力成本"最低，
即最省力/最容易够到的体系路径，帮申请者找到策略性切入点。

本模块提供：
- value 固定下对每条体系的等效分数；
- 用统一"竞争成本分"做横向比较；
- 返回排序列表 + 推荐"洼地"路径。
"""
from __future__ import annotations
from typing import Dict, List, Optional
import math

from . import registry, models, converter, nn


# 各体系"达成难度的非线性权重"
DIFFICULTY_WEIGHT = {
    "AP": 0.95,     # 科目可多次考、及格线低
    "AL": 1.05,     # 实考压力大、A*要求高
    "IB": 1.10,     # 全人教育、HL+EE 拖累大
    "GAOKAO": 1.00, # 一考定终身但有大量参考
    "SAT": 0.85,
    "TOEFL": 0.5,   # 语言易刷
    "IELTS": 0.5,
}


class ValleyFinder:
    def __init__(self, model: Optional[nn.MLP] = None):
        self.model = model

    def compare_systems(self, value: float,
                        systems: Optional[List[str]] = None) -> List[Dict]:
        """对给定统一价值，计算各体系的等效分数 + 竞争成本，按成本升序。"""
        sys_list = systems or ["AP", "AL", "IB", "GAOKAO", "SAT"]
        rows = []
        for s in sys_list:
            s = registry.normalize_system(s)
            if s == "OTHER":
                continue
            eq = converter._equivalent_score_for_value(value, s, {})
            cost = self._competition_cost(value, s)
            rows.append({
                "system": s,
                "system_name": registry.SYSTEM_NAMES.get(s, s),
                "equivalent": eq,
                "difficulty_weight": DIFFICULTY_WEIGHT.get(s, 1.0),
                "competition_cost": round(cost, 3),
            })
        rows.sort(key=lambda r: r["competition_cost"])
        return rows

    def find_valley(self, school: str,
                    historical: List[registry.AdmissionRecord],
                    year: Optional[int] = None) -> Dict:
        """针对某学校，返回各体系达成度排序，找出"洼地"。

        学校定位支持两种方式：
        - `school` 填大学名（如 "Massachusetts Institute of Technology"）或 school_id（如 "mit"）
        """
        # 过滤该校记录（用 school 名或 school_id 匹配）
        recs = [r for r in historical
                if r.school == school or r.school_id == school]
        if year:
            recs = [r for r in recs if r.year == year]
        if not recs:
            return {"school": school, "error": "无该校历史样本"}

        # 门槛价值估算：用 admitted==1 样本的预测价值分位 p75
        vals = []
        for r in recs:
            if r.admitted:
                if self.model:
                    v = self.model.predict(*models.features_from_record(r))
                else:
                    v = converter._heuristic_value(r.features)
                vals.append(v)
        if not vals:
            vals = [0.6]
        thr = _quantile(sorted(vals), 0.5)

        compare = self.compare_systems(thr)
        return {
            "school": school,
            "school_id": recs[0].school_id if recs else "",
            "year": year,
            "estimated_threshold_value": round(thr, 3),
            "n_admitted": len(vals),
            "systems_ranked": compare,
            "recommended_valley": compare[0],
            "reason": f"在统一价值≈{thr:.2f}口径下，{compare[0]['system']}体系折算竞争成本最低，最易达成",
        }

    def _competition_cost(self, value: float, sys_: str) -> float:
        """把统一价值折算成"达成难度成本"。"""
        w = DIFFICULTY_WEIGHT.get(sys_, 1.0)
        base = value * w
        if sys_ == "GAOKAO":
            base += max(0.0, (value - 0.8)) * 0.5
        if sys_ == "AL":
            base += max(0.0, (value - 0.85)) * 0.6
        if sys_ == "IB":
            base += max(0.0, (value - 0.8)) * 0.8
        return base


def _quantile(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return 0.5
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac
