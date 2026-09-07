# -*- coding: utf-8 -*-
"""体系白名单 / 分数结构定义。"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, List

# 体系代码与全称
SYSTEM_NAMES = {
    "AP": "Advanced Placement（美国大学先修）",
    "AL": "A-Level（英国普通教育高级水平）",
    "IB": "IB（国际文凭课程）",
    "GAOKAO": "国内高考",
    "SAT": "SAT（美国学术能力评估）",
    "TOEFL": "TOEFL 托福",
    "IELTS": "IELTS 雅思",
    "OTHER": "其他",
}

# 体系 → 分数形态（用于文档 / 识别提示）
SYSTEM_PROFILES: Dict[str, Dict] = {
    "AP": {
        "name": SYSTEM_NAMES["AP"],
        "score_types": ["exam_score", "gpa", "sat", "language"],
        "exam_scale": (1, 5),        # 单科 AP 1~5
        "typical_fields": ["AP", "ap", "advanced placement", "calc", "calculus", "chem", "physics"],
    },
    "AL": {
        "name": SYSTEM_NAMES["AL"],
        "score_types": ["grade", "language"],
        "grade_scale": ["A*", "A", "B", "C", "D", "E", "U"],
        "typical_fields": ["al", "a-level", "alevel", "a level", "caie", "cambridge", "edexcel", "as", "a2"],
    },
    "IB": {
        "name": SYSTEM_NAMES["IB"],
        "score_types": ["total", "language"],
        "total_scale": (24, 45),
        "typical_fields": ["ib", "international baccalaureate", "diploma"],
    },
    "GAOKAO": {
        "name": SYSTEM_NAMES["GAOKAO"],
        "score_types": ["total", "rank"],
        "total_scale": (0, 750),
        "typical_fields": ["gaokao", "高考", "gk", "一本", "一段", "位次", "rank"],
    },
    "SAT": {
        "name": SYSTEM_NAMES["SAT"],
        "score_types": ["total"],
        "total_scale": (400, 1600),
        "typical_fields": ["sat"],
    },
    "TOEFL": {
        "name": SYSTEM_NAMES["TOEFL"],
        "score_types": ["total"],
        "total_scale": (0, 120),
        "typical_fields": ["toefl", "托福", "ibt"],
    },
    "IELTS": {
        "name": SYSTEM_NAMES["IELTS"],
        "score_types": ["total"],
        "total_scale": (1, 9),
        "typical_fields": ["ielts", "雅思"],
    },
    "OTHER": {
        "name": SYSTEM_NAMES["OTHER"],
        "score_types": [],
    },
}

# 体系 → 内部字段名（标准化）
SYSTEM_FIELDS: Dict[str, List[str]] = {
    "AP": ["ap_exams", "gpa", "sat", "toefl", "ielts"],
    "AL": ["al_grades", "ielts", "toefl"],
    "IB": ["ib_total", "toefl", "ielts"],
    "GAOKAO": ["gk_total", "gk_rank", "province"],
    "SAT": ["sat_total"],
    "TOEFL": ["toefl_total"],
    "IELTS": ["ielts_total"],
}

# 语言成绩同效范围（用于去重/合并）
LANGUAGE_LINK = {"TOEFL": (90, 120), "IELTS": (6.0, 9.0)}


@dataclass
class AdmissionRecord:
    """单条历史录取样本。

    设计要点：
    - `school`：学校显示名（可能是真实大学英文名）。
    - `school_id`：大学唯一 ID（关联 University.id）。
      **不再把 "QS100" 这类排名桶名当作 school**，排名与大学分离。
    - `features`：**缺失字段不放入 dict**（等价于 None），
      由特征向量化时用 mask 标记，而不是 -1 占位。

    Attributes
    ----------
    school: 学校显示名（如 "Massachusetts Institute of Technology"）
    school_id: 大学唯一 ID（如 "mit"），用于关联大学静态档案与排名
    year: 年份
    system: 体系代码（AP/AL/IB/GAOKAO...）
    admitted: 是否录取（label）
    features: 体系相关分数特征 dict（缺失字段不在其中）
    source: 数据出处/备注
    school_value: 学校统一录取价值 0~1（可附加）
    """
    school: str
    year: int
    system: str
    admitted: bool
    features: Dict[str, float] = field(default_factory=dict)
    source: str = ""
    school_id: str = ""     # 关联 University.id（新增）

    def to_dict(self):
        return asdict(self)


def normalize_system(raw: str) -> str:
    """把任意写法归一为体系代码。"""
    if not raw:
        return "OTHER"
    r = raw.strip().upper()
    alias = {
        "AP": "AP", "AP课程": "AP", "AP考试": "AP",
        "AL": "AL", "ALEVEL": "AL", "A-LEVEL": "AL", "A_LEVEL": "AL",
        "A LEVEL": "AL", "CAIE": "AL", "EDEXCEL": "AL", "剑桥AL": "AL",
        "IB": "IB", "国际文凭": "IB",
        "GAOKAO": "GAOKAO", "高考": "GAOKAO", "国内高考": "GAOKAO",
        "GK": "GAOKAO", "SAT": "SAT", "TOEFL": "TOEFL", "托福": "TOEFL",
        "IELTS": "IELTS", "雅思": "IELTS",
    }
    # 空格/连字符压缩后匹配
    r2 = r.replace("-", "").replace("_", "").replace(" ", "")
    for k, v in alias.items():
        if k.replace("-", "").replace("_", "").replace(" ", "") == r2:
            return v
    return "OTHER"
