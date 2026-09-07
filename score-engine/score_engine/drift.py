# -*- coding: utf-8 -*-
"""年度漂移估计与校准（核心：让换算能识别"每年在变"）。

问题背景：同一所学校的跨体系录取换算**不是固定的**，会随年份浮动
（申请人数、招生政策、学校档次水位变化等）。早期 PR#9 的实现把"统一价值"
当作与年份无关的常量，**无法回答"2019 和 2024 换算结果有何不同"**。

本模块从历年历史录取样本中估计**年度门槛水位指数**（difficulty index），
再用它把某一年份的换算"校准"到当年口径，从而让换算结果带年份、可识别趋势。

口径说明
--------
- 把每条**被录取**记录的统一价值 school_value（0~1）按年份聚合：
  difficulty[year] = 当年录取样本的平均门槛价值。
- 相对基准（历年均值）归一化为 scale[year] = difficulty[year]/base。
- scale[year] > 1 → 该年更难（同样画像需更高价值/更高原始分才够得着）。
- convert(..., year=Y) 会用 scale[Y] 对目标价值做加权，输出"当年口径"的等效分。

示例可测性质
------------
若历史数据里 2024 的门槛逐年高于 2019（学校更难进），则：
    convert(profile, year=2024).GAOKAO > convert(profile, year=2019).GAOKAO
即"换算随年份变化"可被识别。
"""
from __future__ import annotations
from typing import Dict, List, Optional
from . import registry


def _clip(x: float) -> float:
    return min(1.0, max(0.0, x))


class YearDrift:
    """年度门槛水位指数（difficulty）的估计器与校准器。"""

    def __init__(self, difficulty: Optional[Dict[int, float]] = None):
        # difficulty[year] = 当年平均门槛价值
        self.difficulty = dict(difficulty or {})
        self.scale = self._scale_map(self.difficulty)

    @staticmethod
    def _scale_map(diff: Dict[int, float]) -> Dict[int, float]:
        if not diff:
            return {}
        base = sum(diff.values()) / len(diff)
        base = base or 1.0
        return {y: v / base for y, v in diff.items()}

    @classmethod
    def from_records(cls, records: List["registry.AdmissionRecord"]) -> "YearDrift":
        """从历史录取记录估计年度门槛水位指数。

        用当年 admitted 样本的平均 school_value 作为难度水位。
        仅当所有年份覆盖的学校集合可比时该均值才稳健；原型阶段已足够，
        真实使用请用**同一批可比大学**在各年份的被录取样本。
        """
        agg: Dict[int, List[float]] = {}
        for r in records:
            if not getattr(r, "admitted", False):
                continue
            v = getattr(r, "school_value", None)
            if v is None:
                continue
            agg.setdefault(r.year, []).append(float(v))
        diff = {y: sum(vs) / len(vs) for y, vs in agg.items() if vs}
        return cls(diff)

    def scale_for(self, year: Optional[int]) -> float:
        if year is None:
            return 1.0
        return self.scale.get(year, 1.0)

    def apply(self, value: float, year: Optional[int]) -> float:
        """把目标价值按年份校准：scale>1 → 更难，需更高价值。"""
        s = self.scale_for(year)
        return _clip(value * s)

    def years(self) -> List[int]:
        return sorted(self.difficulty)

    def trend(self) -> List[Dict]:
        """年度趋势（便于展示/测试）。"""
        return [{"year": y, "difficulty_index": round(self.difficulty.get(y, 0.0), 4),
                 "scale": round(self.scale_for(y), 4)} for y in self.years()]

    def drift_between(self, y1: int, y2: int) -> float:
        """y2 相对 y1 的漂移幅度（0 表示无漂移）。"""
        s1, s2 = self.scale_for(y1), self.scale_for(y2)
        return round(s2 - s1, 4)

    def to_dict(self):
        return {"difficulty": self.difficulty, "scale": self.scale}

    @classmethod
    def from_dict(cls, d: Dict) -> "YearDrift":
        return cls(d.get("difficulty"))
