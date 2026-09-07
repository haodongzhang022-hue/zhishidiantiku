# -*- coding: utf-8 -*-
"""跨体系模糊换算引擎。

核心思想：
1. 所有体系分数先**识别 + 特征化**，投影到定长特征向量。
2. 用训练好的 **MLP** 将特征向量映射到 0~1 的"统一录取价值"。
3. "换算" = 在统一价值下做反向近似——给定一个体系的分数，求"同等价值"在另一体系的等价门槛。

也提供轻量、无需训练的历史对齐表方法（可选），供冷启动。
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import math

from . import registry, models, nn


class ScoreConverter:
    """把一条原始分数文本换算成各体系的"等价分数区间"。"""

    def __init__(self, model: Optional[nn.MLP] = None,
                 feature_fn=None):
        self.model = model
        self.feature_fn = feature_fn or models.features_to_vector

    # ---------- 识别 + 单价值 ----------
    def value_of_text(self, text: str, system_hint: str = "",
                     year: Optional[int] = None,
                     drift: Optional["YearDrift"] = None) -> Dict:
        """识别 + 返回 (system, confidence, features, value, year, drift)。

        参数
        ----
        year : 可选。给定申请年份，用年度漂移校准价值（识别逐年变化）。
        drift: 可选。由历史样本构建的 YearDrift 估计器；None 且给 year 时自动按
               (system, year) 无法细分则退化为不漂移（由上层传入 drift 更可靠）。
        """
        from . import recognizer, drift as drift_mod
        # 若给了体系提示，优先
        sys_ = registry.normalize_system(system_hint)
        if sys_ == "OTHER":
            r = recognizer.recognize(text)
            sys_ = r.system
            feats = r.features
            conf = r.confidence
        else:
            r = recognizer.recognize(text)
            feats = r.features or {}
            conf = r.confidence
        vec = self.feature_fn(feats)
        if self.model:
            value = self.model.predict(vec)
        else:
            value = _heuristic_value(feats)
        value = max(0.0, min(1.0, value))
        # 年度校准：同一年画像换算价值在"更难年份"应更高（需更强才够得着）
        applied_drift = None
        if year is not None and drift is not None:
            value = drift.apply(value, year)
            applied_drift = drift.scale_for(year)
        return {
            "system": sys_, "confidence": conf,
            "features": feats, "vector": vec, "value": value,
            "year": year, "drift_scale": applied_drift,
        }

    # ---------- 换算 ----------
    def convert(self, text: str, target_systems: Optional[List[str]] = None,
                system_hint: str = "", year: Optional[int] = None,
                drift: Optional["YearDrift"] = None) -> Dict:
        """换算：把输入文本分数映射到各目标体系的"等价门槛区间"。

        新增 year/drift：给定年份时换算结果随年份浮动，用于识别"逐年变化"。
        返回 { 源信息, 各体系: {等价分数范围, 说明} }
        """
        src = self.value_of_text(text, system_hint, year=year, drift=drift)
        val = src["value"]
        result = {"source": src, "conversions": {}}
        targets = target_systems or ["AP", "AL", "IB", "GAOKAO", "SAT"]
        for t in targets:
            t = registry.normalize_system(t)
            if t == "OTHER":
                continue
            eq = _equivalent_score_for_value(val, t, src["features"])
            result["conversions"][t] = eq
        return result

    # ---------- 批量数据入口 ----------
    def value_of_record(self, rec: registry.AdmissionRecord) -> float:
        vec = models.features_from_record(rec)
        if self.model:
            return self.model.predict(vec)
        return _heuristic_value(rec.features)


def _equivalent_score_for_value(value: float, target_system: str,
                                src_feats: Dict[str, float]) -> Dict:
    """给定统一价值 0~1，反推某体系需要达到的大致分数区间。"""
    import copy
    base = dict(src_feats)
    if target_system == "AP":
        # AP 主要看均分 + 门数。粗略反解
        need_avg = 3.0 + value * 2.0       # 与训练数据尺度一致
        need_n = max(1, int(round(1 + value * 5)))
        return {
            "kind": "AP 均分≈%.1f/5, %d门 AP 课" % (need_avg, need_n),
            "range": "AP 均分%.1f/5 / %d门" % (need_avg, need_n),
            "approx_score": round(need_avg, 1),
            "note": "同校门槛洼地对比口径：AP 单科及门数组合等效换算"
        }
    if target_system == "AL":
        need_avg = 2.2 + value * 2.8        # 与训练数据尺度一致
        need_n = max(1, int(round(1 + value * 4)))
        letter = _al_value_letter(need_avg)
        return {
            "kind": "A-Level %s（%d门，均分≈%.2f/5）" % (letter, need_n, need_avg),
            "range": "%s×%d门" % (letter, need_n),
            "approx_score": round(need_avg, 1),
            "note": "AL 字母：A*=5, A=4, B=3"
        }
    if target_system == "IB":
        need_ib = 24 + value * 21.0        # 与训练数据尺度一致
        return {
            "kind": "IB 总分≈%.0f/45" % need_ib,
            "range": "%.0f/45" % need_ib,
            "approx_score": round(need_ib, 1),
            "note": "IB 需含 HL 科目及 TOK/EE 组合"
        }
    if target_system == "GAOKAO":
        need_gk = 350 + value * 400.0       # 与训练数据尺度一致
        return {
            "kind": "高考≈%.0f/750" % need_gk,
            "range": "%.0f~%.0f/750" % (max(300, need_gk - 20), min(750, need_gk + 20)),
            "approx_score": round(need_gk, 1),
            "note": "高考分随省份/文理/位次浮动，粗口径"
        }
    if target_system == "SAT":
        need_sat = 1200 + value * 400.0    # 与训练数据尺度一致
        return {
            "kind": "SAT≈%.0f/1600" % need_sat,
            "range": "%.0f/1600" % need_sat,
            "approx_score": round(need_sat, 1),
            "note": ""
        }
    if target_system == "TOEFL":
        need = 70 + value * 50.0
        return {"kind": "TOEFL≈%.0f/120" % need, "range": "%.0f/120" % need,
                "approx_score": round(need, 1), "note": "语言维度，非学科门槛"}
    if target_system == "IELTS":
        need = 5.5 + value * 3.5
        return {"kind": "IELTS≈%.1f/9" % need, "range": "%.1f/9" % need,
                "approx_score": round(need, 1), "note": "语言维度，非学科门槛"}
    return {"kind": "N/A", "range": "", "approx_score": 0, "note": ""}


def _al_value_letter(avg: float) -> str:
    if avg >= 4.6:
        return "A*"
    if avg >= 4.0:
        return "A"
    if avg >= 3.2:
        return "B"
    if avg >= 2.4:
        return "C"
    if avg >= 1.6:
        return "D"
    return "E"


def _heuristic_value(feats: Dict[str, float]) -> float:
    """无模型时的启发式估算（冷启动/兜底）。"""
    vals = []
    if "ap_avg" in feats:
        vals.append((feats["ap_avg"] - 3) / 2.0)
    if "ap_subjects" in feats:
        vals.append(min(1.0, feats["ap_subjects"] / 6.0) * 0.5)
    if "al_avg" in feats:
        vals.append((feats["al_avg"] - 2) / 3.0)
    if "ib_total" in feats:
        vals.append((feats["ib_total"] - 24) / 21.0)
    if "gk_total" in feats:
        vals.append((feats["gk_total"] - 300) / 450.0)
    if "sat" in feats:
        vals.append((feats["sat"] - 1000) / 600.0)
    if "gpa" in feats:
        vals.append((feats["gpa"] - 2.5) / 1.5)
    if "toefl" in feats:
        vals.append((feats["toefl"] - 60) / 60.0)
    if not vals:
        return 0.3
    v = sum(vals) / len(vals)
    return max(0.0, min(1.0, v))
