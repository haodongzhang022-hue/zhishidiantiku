# -*- coding: utf-8 -*-
"""特征向量化 / 数据样本模型。

把不同体系（AP/AL/IB/GAOKAO/SAT/TOEFL/IELTS）的原始分数特征
统一投影到一个定长的"录取价值特征向量"，供 MLP 学习。

本引擎学的是「一套学生画像 → 可达学校档位(0~1)」的连续回归，
输出即"统一录取价值"——等价于该校的录取门槛值。
"""
from __future__ import annotations
import random
from typing import Dict, List, Optional
from . import registry

# 特征向量定义
FEATURE_SCHEMA = {
    "ap_avg":       {"min": 0, "max": 5, "src": "AP"},
    "ap_subjects":  {"min": 0, "max": 6, "src": "AP"},
    "ap_top_ratio": {"min": 0, "max": 1, "src": "AP"},
    "gpa":          {"min": 0, "max": 4, "src": "AP"},
    "al_avg":       {"min": 0, "max": 5, "src": "AL"},
    "al_subjects":  {"min": 0, "max": 5, "src": "AL"},
    "al_top_ratio": {"min": 0, "max": 1, "src": "AL"},
    "ib_total":     {"min": 24, "max": 45, "src": "IB"},
    "gk_total":     {"min": 0, "max": 750, "src": "GAOKAO"},
    "sat":          {"min": 400, "max": 1600, "src": "SAT"},
    "toefl":        {"min": 0, "max": 120, "src": "TOEFL"},
    "ielts":        {"min": 0, "max": 9, "src": "IELTS"},
    "province_enc": {"min": 0, "max": 1, "src": "GAOKAO"},
}
FEATURE_KEYS = list(FEATURE_SCHEMA.keys())
FEATURE_DIM = len(FEATURE_KEYS)


def features_to_vector(feats: Dict[str, float]) -> List[float]:
    vec = []
    for k in FEATURE_KEYS:
        v = feats.get(k)
        if v is None:
            vec.append(-1.0)      # 缺失，-1 占位
            continue
        lo, hi = FEATURE_SCHEMA[k]["min"], FEATURE_SCHEMA[k]["max"]
        if hi == lo:
            vec.append(0.0)
            continue
        x = (v - lo) / (hi - lo)
        x = min(1.0, max(0.0, x))
        vec.append(x)
    return vec


def features_from_record(rec: registry.AdmissionRecord) -> List[float]:
    return features_to_vector(rec.features)


def value_of_record(rec: registry.AdmissionRecord) -> float:
    """样本对应的"可达学校档位"(0~1)。admitted 时取 school_value，未录取给 0。"""
    sv = getattr(rec, "school_value", None)
    if sv is not None:
        return min(1.0, max(0.0, float(sv)))
    return 0.0


def make_mock_admissions(seed: int = 42) -> List[registry.AdmissionRecord]:
    """生成历年示例：每个"学生画像"被标注其可达学校档位（连续 0~1）。

    档位越高，各体系原始分越高（按各自体系的反算映射）。

    相比最初原型做了两处关键增强：
    1. **年度漂移**：同一学校门槛价值随年份单调爬升（2019 易 → 2024 难），
       使"换算逐年变化"这一核心需求有真实可学的数据基础（供 YearDrift 识别）。
    2. **AP 门数与强度解耦**：真实 AP 申请者门数 3~6 门均可，门数不再强绑档位，
       避免模型把"3 门 AP"一律判成低档（修复对强 AP 画像的欠预测）。
    """
    school_tiers = [
        ("QS10 名校", 0.92), ("QS50", 0.78), ("QS100", 0.66),
        ("QS200", 0.55), ("QS500", 0.42), ("QS1000", 0.30),
    ]
    rng = random.Random(seed)
    records = []
    years = [2019, 2020, 2021, 2022, 2023, 2024]
    # 逐年难度的相对抬升：2019 = 0.94 → 2024 = 1.06（同一学校更难进）
    year_factor = {years[i]: 0.94 + 0.024 * i for i in range(len(years))}
    for school, tier in school_tiers:
        for year in years:
            # 门槛 = 基础档位 × 年度难度因子 × 微小噪声
            t = min(0.98, max(0.05, tier * year_factor[year] * (1.0 + 0.01 * rng.random())))
            for sys_ in ["AP", "AL", "IB", "GAOKAO"]:
                n_profiles = 4
                for _ in range(n_profiles):
                    feat = synthesize_feature(sys_, t, rng, year)
                    rec = registry.AdmissionRecord(
                        school=school, year=year, system=sys_,
                        admitted=True, features=feat,
                        source="synthetic-demo")
                    rec.school_value = round(t, 3)
                    records.append(rec)
    return records


def synthesize_feature(sys_: str, tier: float, rng, year: int = None) -> Dict[str, float]:
    """按可达档位 tier(0~1) 生成对应体系的一整套分数。

    year 目前仅占位，便于后续按年度微调原始分尺度；档位已含年度因子。
    """
    if sys_ == "AP":
        # 让合成画像与 recognizer 的取数口径一致：
        # 先按档位决定每门 AP 的得分(3~5)，再聚合出 ap_avg / ap_top_ratio，
        # 使"均分/满分比例 → 价值"的映射在真实识别输入上也成立。
        n = rng.choice([3, 3, 4, 4, 5, 5, 6])          # 门数独立于档位
        # 分数分布：tier 越高，出现 5 的概率越大
        base_p5 = 0.15 + tier * 0.80
        scores = []
        for _ in range(n):
            r5 = rng.random()
            if r5 < base_p5:
                scores.append(5)
            else:
                scores.append(rng.choice([3, 4]) if rng.random() < 0.5 else 4)
        ap_avg = sum(scores) / len(scores)
        top_ratio = sum(1 for s in scores if s == 5) / len(scores)
        feat = {"ap_avg": round(ap_avg, 2), "ap_subjects": float(n),
                "ap_top_ratio": round(top_ratio, 3)}
        # 可选字段：真实画像常缺 SAT/TOEFL/GPA（文本未必全部给），
        # 随机缺失，让模型学到"缺失≠弱"，避免把缺语言分判成低档
        if rng.random() > 0.25:
            feat["gpa"] = round(min(4.0, max(3.0, 3.0 + tier*0.9 + rng.gauss(0, 0.05))), 2)
        if rng.random() > 0.35:
            feat["sat"] = float(min(1600, max(1200, int(1200 + tier*400 + rng.gauss(0, 25)))))
        if rng.random() > 0.35:
            feat["toefl"] = float(min(120, max(80, int(85 + tier*35 + rng.gauss(0, 5)))))
        return feat
    if sys_ == "AL":
        al_avg = min(5.0, max(2.0, 2.2 + tier * 2.8 + rng.gauss(0, 0.15)))
        n = max(3, min(5, int(round(1 + tier * 4))))
        feat = {"al_avg": round(al_avg, 2), "al_subjects": n,
                "al_top_ratio": round(min(1, max(0, tier * 0.9 + rng.gauss(0, 0.1))), 3)}
        if rng.random() > 0.3:
            feat["ielts"] = round(min(9.0, max(5.5, 6.0 + tier*3.0 + rng.gauss(0, 0.2))), 1)
        return feat
    if sys_ == "IB":
        ib = min(45, max(24, int(round(24 + tier * 21)) + (1 if rng.random() > 0.5 else 0)))
        feat = {"ib_total": float(ib)}
        if rng.random() > 0.3:
            feat["toefl"] = float(min(120, max(80, int(85 + tier * 35))))
        return feat
    if sys_ == "GAOKAO":
        gk = min(750, max(300, int(350 + tier * 400 + rng.gauss(0, 15))))
        return {"gk_total": float(gk)}
    return {}

