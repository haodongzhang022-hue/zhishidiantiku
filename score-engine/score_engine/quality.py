# -*- coding: utf-8 -*-
"""质量鉴定维度 —— 排名 ≠ 真实水平（名不副实识别）。

用户（issue #8 追评）核心关切：QS 排名不一定代表真实水平——
可能"排名高但质量低"。希望鉴定学校实际水平的多维指标：
- 学校规模（在校生/师资）、师生比、学费；
- 论文产出 / 被引 / 专利；
- 就业率、薪资回报；
- 师资分层（顶尖/中坚/不足），并**把不足(负面)也量化**。

本模块把质量维度做成"从分析库(quality_db)多张表 → 质量指数 + 偏差报告"。
口径：
- 每所学校得到一个 **quality_index ∈ [0,1]**（越高=真实质量越高），
  由师生比、师资水平、论文/被引、就业/回报等多维加权，并扣减负面指标。
- 与 QS/THE 排名代表的"名气档位"做对照，输出三类：
  * **实至名归**：排名与质量匹配
  * **名不副实 / 高排名低质量**：排名高但质量指数偏低（用户点名要识别）
  * **被低估 / 高性价比**：排名相对低但真实质量高（价值洼地）
"""
from __future__ import annotations
from typing import Dict, List, Optional, Any
import math


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return min(hi, max(lo, x))


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default


# 各质量子维度的归一化基准（用于把原始量纲映射到 0~1）
# 值越高代表越"好/贵/强"。师生比越低越好，需反转。
QUALITY_BASELINES = {
    "ratio_student_faculty": 30.0,  # 越接近 0 越好（>30 视为差）
    "tuition_intl_usd": 60000.0,    # 学费高不代表质量高，仅作性价比参考
    "papers_yearly": 3000.0,        # 年论文量上限（越多越强）
    "citations": 200000.0,          # 被引上限
    "h_index": 300.0,               # H 指数上限
    "employment_rate": 1.0,         # 就业率（本身就是 0~1）
}


class QualityAnalyzer:
    """从分析库多张表计算质量指数，并输出"排名 vs 质量"偏差报告。

    数据可来自 `score_engine.db.ScoreDB`（quality_db 的三张表），
    也可直接传 dict 列表（便于脱离 DB 复用）。
    """

    def __init__(self,
                 profiles: Optional[List[Dict[str, Any]]] = None,
                 faculties: Optional[List[Dict[str, Any]]] = None,
                 outcomes: Optional[List[Dict[str, Any]]] = None,
                 rankings: Optional[List[Dict[str, Any]]] = None):
        # 按 school_id 建索引，方便查询
        self.profiles = {r["school_id"]: r for r in (profiles or [])}
        self.faculties = {r["school_id"]: r for r in (faculties or [])}
        self.outcomes = {r["school_id"]: r for r in (outcomes or [])}
        self.rankings = rankings or []
        # 取每所学校的最近年份记录
        self.profiles = self._latest(self.profiles)
        self.faculties = self._latest(self.faculties)
        self.outcomes = self._latest(self.outcomes)

    @staticmethod
    def _latest(mapping: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        out = {}
        for sid, rows in mapping.items():
            if not isinstance(rows, list):
                out[sid] = rows
                continue
            if not rows:
                continue
            rows = sorted(rows, key=lambda r: r.get("year") or 0)
            out[sid] = rows[-1]
        return out

    # ---- 质量指数 ----
    def quality_index(self, school_id: str) -> float:
        """计算单校质量指数 [0,1]，可缺失部分维度（缺失不判低）。

        设计原则同引擎主体：**缺失 ≠ 差**。只有存在的数据才参与加权，
        这样没提供论文数据的学校不会被误判为"没水平"。
        """
        p = self.profiles.get(school_id) or {}
        f = self.faculties.get(school_id) or {}
        o = self.outcomes.get(school_id) or {}

        comps = []

        # 1) 师生比（越低越好 → 反转）
        rsr = p.get("ratio_student_faculty")
        if rsr is not None and rsr > 0:
            base = QUALITY_BASELINES["ratio_student_faculty"]
            comps.append(_clip(1.0 - (float(rsr) / base), 0, 1))
        # 2) 师资顶尖占比（越高越好）
        tier_high = f.get("tier_high")
        star = f.get("star_count")
        if tier_high is not None:
            comps.append(_clip(float(tier_high), 0, 1))
        elif star is not None:
            comps.append(_clip(float(star) / 200.0, 0, 1))
        # 3) 师资负面（欠佳占比，越低越好 → 扣分项，反转后加入）
        neg = f.get("negative_ratio")
        if neg is not None:
            comps.append(_clip(1.0 - float(neg), 0, 1))
        # 4) 论文产出（越多越强）
        paper = o.get("papers_yearly") or p.get("papers_yearly")
        if paper is not None:
            comps.append(_clip(float(paper) / QUALITY_BASELINES["papers_yearly"], 0, 1))
        # 5) 被引/学术影响力
        cit = o.get("citations")
        if cit is not None:
            comps.append(_clip(float(cit) / QUALITY_BASELINES["citations"], 0, 1))
        # 6) 就业率 / 就业回报
        emp = o.get("employment_rate") or p.get("employment_rate")
        if emp is not None:
            comps.append(_clip(float(emp), 0, 1))
        # 7) 成果结构：科研 vs 就业的平衡
        if o.get("patents") is not None:
            comps.append(_clip(float(o["patents"]) / 2000.0, 0, 1))

        if not comps:
            return 0.5  # 全缺失 → 中性，不判高不判低
        return round(sum(comps) / len(comps), 3)

    # ---- 排名→名气档位（0~1，越小 rank 越高）----
    def _rank_value(self, school_id: str, year: int = 2024,
                    source: str = "QS") -> Optional[float]:
        """把某年某来源排名映射为 0~1 名气档位（rank=1 → ~1.0）。"""
        for r in self.rankings:
            if (r.get("university_id") == school_id and r.get("year") == year
                    and r.get("source") == source):
                rk = float(r["rank"])
                # rank 1 → ~1.0；rank 1000 → 接近 0；对数压缩
                return _clip(1.0 - (math.log(rk) / math.log(1001.0)), 0, 1)
        return None

    # ---- 学校档案（把分析库三表合并成便于展示的 profile）----
    def school_profile(self, school_id: str) -> Dict[str, Any]:
        p = self.profiles.get(school_id) or {}
        f = self.faculties.get(school_id) or {}
        o = self.outcomes.get(school_id) or {}
        merged = {**p, **f, **o}
        merged["quality_index"] = self.quality_index(school_id)
        merged["school_id"] = school_id
        return merged

    # ---- 偏差 / 名不副实 报告 ----
    def mismatch_report(self, year: int = 2024,
                        source: str = "QS") -> List[Dict[str, Any]]:
        """对全库学校生成"排名 vs 质量"对照，分类并排序。

        用回归法做**同类公平比较**：对"排名越好→质量预期越高"拟合一条参考线，
        再把每所学校的真实质量与该排名的"预期质量"比较，离群者即异常：
          gap > +σ  → 被低估/高性价比（真实水平远超名气）
          gap < -σ  → 名不副实/高排名低质量（名气远超真实水平）
        避免"rank=1 质量永远到不了 1.0"的偏差——把每所学校跟**它排名的正常水平**比。
        """
        school_ids = set(self.profiles) | set(self.faculties) | set(self.outcomes)
        if not school_ids:
            return []
        rows = []
        for sid in school_ids:
            qi = self.quality_index(sid)
            rank = None
            for r in self.rankings:
                if (r.get("university_id") == sid and r.get("year") == year
                        and r.get("source") == source):
                    rank = r.get("rank")
                    break
            rows.append({"school_id": sid, "rank": rank,
                         "quality_index": qi, "logrank": math.log(rank) if rank else None})
        # 用可得的 (logrank, quality) 拟合参考线 quality ≈ a + b*logrank
        pts = [(r["logrank"], r["quality_index"]) for r in rows
               if r["logrank"] is not None]
        a, b, sd = _ols(pts)
        for r in rows:
            qi = r["quality_index"]
            if r["logrank"] is not None:
                expected = a + b * r["logrank"]
                gap = qi - expected
                r["expected_quality"] = round(expected, 3)
            else:
                expected = None
                gap = qi - (a if pts else 0.5)
                r["expected_quality"] = None
            r["gap"] = round(gap, 3)
            r["verdict"] = _verdict(gap, sd)
        rows.sort(key=lambda x: (-(x["quality_index"] or 0), x["rank"] or 9999))
        return rows

    def summary(self, year: int = 2024, source: str = "QS") -> Dict[str, Any]:
        rep = self.mismatch_report(year, source)
        verdicts: Dict[str, int] = {}
        for r in rep:
            verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
        undervalued = [r for r in rep if r["verdict"] == "被低估/高性价比"]
        overrated = [r for r in rep if r["verdict"] == "名不副实/高排名低质量"]
        return {
            "n_schools": len(rep),
            "verdict_counts": verdicts,
            "top_quality": rep[:3],
            "undervalued_leaders": undervalued[:3],
            "overrated": overrated[:3],
        }


def _ols(pts: List[tuple]) -> tuple:
    """最小二乘 y = a + b*x，返回 (a, b, 残差标准差 sd)。pts: [(x,y),...]"""
    if len(pts) < 2:
        if len(pts) == 1:
            return pts[0][1], 0.0, 0.0
        return 0.5, 0.0, 0.0
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    b = sxy / sxx if sxx else 0.0
    a = my - b * mx
    resid = [(p[1] - (a + b * p[0])) for p in pts]
    sd = (sum(x * x for x in resid) / n) ** 0.5
    return a, b, sd


def _verdict(gap: float, sd: float) -> str:
    """根据离群程度给判定。sd=0（样本太少）用固定带。"""
    th = max(0.06, sd)  # 至少 ±0.06，避免全判实至名归
    if gap > th:
        return "被低估/高性价比"
    if gap < -th:
        return "名不副实/高排名低质量"
    return "实至名归"
