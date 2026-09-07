# -*- coding: utf-8 -*-
"""特征向量化 / 数据样本模型。

把不同体系（AP/AL/IB/GAOKAO/SAT/TOEFL/IELTS）的原始分数特征
统一投影到一个定长的"录取价值特征向量"，供 MLP 学习。

本引擎学的是「一套学生画像 → 可达学校档位(0~1)」的连续回归，
输出即"统一录取价值"——等价于该校的录取门槛值。

**缺失值处理（重要设计）**：
- 不再用 -1 占位缺失。缺失不是"很弱的信号"，它可能是学生没提供该维度
  或该维度不适用于当前体系。用 -1 会让模型误学成"缺失 = 极弱"。
- 现在用 `None` 表示缺失，vectorize 时缺失维度填 0（对 sigmoid 中性），
  同时输出 `mask` 向量标记缺失维度。NN 训练时**缺失维度不参与反向传播**，
  因此模型学到"缺失 ≠ 弱"，只是"没有信号"。
"""
from __future__ import annotations
import random
from typing import Dict, List, Optional, Tuple
from . import registry

# 特征向量定义
# 注意：min/max 用于归一化，缺失不填 min 也不填 max，
# 由调用方（features_to_vector）处理为 mask。
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


def features_to_vector(feats: Dict[str, float],
                       with_mask: bool = True) -> Tuple[List[float], List[int]]:
    """把特征 dict 转成归一化向量 + mask。

    缺失（None / 不存在）→ 填 0.0（对 sigmoid 中性），mask=0 标记缺失。
    存在 → 归一化到 [0,1]，mask=1。

    Returns:
        (vector, mask) — with_mask=True 时返回 tuple；False 仅返回 vector。
    """
    vec = []
    mask = []
    for k in FEATURE_KEYS:
        v = feats.get(k)
        if v is None:
            vec.append(0.0)   # 中性值：对 sigmoid(0)=0.5，不带偏置
            mask.append(0)    # 0 = 该维度缺失，不参与训练
            continue
        lo, hi = FEATURE_SCHEMA[k]["min"], FEATURE_SCHEMA[k]["max"]
        if hi == lo:
            vec.append(0.0)
            mask.append(1)
            continue
        # 范围外的值也做 clip（防止异常）
        x = (float(v) - lo) / (hi - lo)
        x = min(1.0, max(0.0, x))
        vec.append(x)
        mask.append(1)
    if with_mask:
        return vec, mask
    return vec


def features_from_record(rec: registry.AdmissionRecord) -> Tuple[List[float], List[int]]:
    return features_to_vector(rec.features)


def value_of_record(rec: registry.AdmissionRecord) -> float:
    """样本对应的"可达学校档位"(0~1)。admitted 时取 school_value，未录取给 0。"""
    sv = getattr(rec, "school_value", None)
    if sv is not None:
        return min(1.0, max(0.0, float(sv)))
    return 0.0


def make_mock_admissions(seed: int = 42,
                         universities: Optional[list] = None,
                         rankings: Optional[list] = None):
    """生成历年示例，按**真实大学实体**而非 QS 桶名。

    设计要点（对齐 issue #8）：
    1. **大学实体与排名分离**：每所大学有一个稳定的 university_id，
       排名随年份记录在 UniversityRanking 中。
    2. 训练样本的 school 字段填写**真实大学**（不再是 'QS100' 桶）。
    3. 每所大学的"统一录取价值"由该大学的整体录取难度决定，
       **不完全等于 QS 排名**（有的排名高但门槛低，即"洼地"）。
    4. AP 画像保留随机缺失（让模型学"缺失≠弱"），缺的语言成绩在 mask 中标为 0。
    """
    from . import university as univ_mod

    if universities is None:
        universities = univ_mod.default_universities()
    if rankings is None:
        rankings = univ_mod.default_rankings()
    univ_by_id = univ_mod.university_lookup(universities)
    rank_by_uid_year = {(r.university_id, r.year): r.rank for r in rankings}

    # 每所大学的"基础录取难度"（0~1，越接近 1 越难进）
    # 这个值与 QS 排名强相关但不等同——就是用户指出的"排名高但门槛未必最高"
    base_difficulty = {
        # 以 2024 QS 排名为锚点，加入"排名/门槛不一致"以体现真实差异。
        # 故意把档位拉开，让统一价值有足够区分度（0.45~0.95）。
        "mit": 0.95, "stanford": 0.92, "oxford": 0.90, "cambridge": 0.90,
        "harvard": 0.94, "eth": 0.86, "nus": 0.78, "ucb": 0.84,
        "yale": 0.88, "ucl": 0.70, "pk": 0.76, "thu": 0.78,
        "imperial": 0.84, "uchicago": 0.86, "umich": 0.55,
        "toronto": 0.50, "princeton": 0.92, "caltech": 0.93,
        "nw": 0.52, "columbia": 0.86,
    }

    rng = random.Random(seed)
    records = []
    years = [2019, 2020, 2021, 2022, 2023, 2024]
    # 逐年全球申请竞争加重的因子：2019 = 0.96 → 2024 = 1.05
    year_factor = {years[i]: 0.96 + 0.018 * i for i in range(len(years))}

    for univ in universities:
        uid = univ.id
        base_d = base_difficulty.get(uid, 0.60)  # 默认中低难度
        for year in years:
            # 年度难度 = 基础难度 × 年份竞争因子 × 该校排名在该年的额外调整
            # 排名越好 → 额外微升（但非线性的，不过度放大）
            rk = rank_by_uid_year.get((uid, year), 100)
            # rank 越大越靠后，难度因子在 0.95~1.05 之间微调
            rank_adj = 0.95 + max(0.0, min(0.10, (100 - rk) / 100.0 * 0.10))
            t = min(0.99, max(0.05, base_d * year_factor[year] * rank_adj))
            for sys_ in ["AP", "AL", "IB", "GAOKAO"]:
                for _ in range(3):  # 每所大学每体系每年 3 条
                    feat = synthesize_feature(sys_, t, rng, year)
                    rec = registry.AdmissionRecord(
                        school=univ.name_en,      # 存真实大学英文名
                        university_id=uid,            # 存大学唯一 ID
                        year=year, system=sys_,
                        admitted=True, features=feat,
                        source="synthetic-demo")
                    rec.school_value = round(t, 3)
                    records.append(rec)
    return records


def synthesize_feature(sys_: str, tier: float, rng, year: int = None) -> Dict[str, float]:
    """按可达档位 tier(0~1) 生成对应体系的一整套分数。

    与 recognizer 取数口径一致。
    关键：**缺失字段不放进 dict**（即 None 语义），
    而不是放 -1 之类的占位值。
    """
    if sys_ == "AP":
        n = rng.choice([3, 3, 4, 4, 5, 5, 6])
        base_p5 = 0.15 + tier * 0.80
        scores = []
        for _ in range(n):
            if rng.random() < base_p5:
                scores.append(5)
            else:
                scores.append(rng.choice([3, 4]) if rng.random() < 0.5 else 4)
        ap_avg = sum(scores) / len(scores)
        top_ratio = sum(1 for s in scores if s == 5) / len(scores)
        feat = {"ap_avg": round(ap_avg, 2), "ap_subjects": float(n),
                "ap_top_ratio": round(top_ratio, 3)}
        # 随机缺失：模型需学会"缺失≠弱"。只对存在的字段才有 key。
        if rng.random() > 0.25:
            feat["gpa"] = round(min(4.0, max(3.0, 3.0 + tier * 0.9 + rng.gauss(0, 0.05))), 2)
        if rng.random() > 0.35:
            feat["sat"] = float(min(1600, max(1200, int(1200 + tier * 400 + rng.gauss(0, 25)))))
        if rng.random() > 0.35:
            feat["toefl"] = float(min(120, max(80, int(85 + tier * 35 + rng.gauss(0, 5)))))
        return feat
    if sys_ == "AL":
        al_avg = min(5.0, max(2.0, 2.2 + tier * 2.8 + rng.gauss(0, 0.15)))
        n = max(3, min(5, int(round(1 + tier * 4))))
        feat = {"al_avg": round(al_avg, 2), "al_subjects": n,
                "al_top_ratio": round(min(1, max(0, tier * 0.9 + rng.gauss(0, 0.1))), 3)}
        if rng.random() > 0.3:
            feat["ielts"] = round(min(9.0, max(5.5, 6.0 + tier * 3.0 + rng.gauss(0, 0.2))), 1)
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
