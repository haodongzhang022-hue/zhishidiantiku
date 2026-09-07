# -*- coding: utf-8 -*-
"""大学实体模型 —— 排名与大学分离。

核心设计原则（对齐 issue #8 追评）：
- **大学是独立实体**：名称、国家、位置、办学层次等是跟随大学的**静态信息**，
  不因 QS 排名变化而变。
- **排名是动态属性**：QS/THE/USNews 每年更新，同一年份不同来源排名也可能不同。
  大学的录取机制（门槛/体系口径）是跟随大学本身的，排名变化时**未必同步变化**。

因此数据模型拆成两层：
1. `University` —— 大学的固有属性（ID/名称/国家/城市/学费等），稳定。
2. `UniversityRanking` —— (university, source, year) → rank，动态、按年记录。

换算引擎的学习对象是**大学实体**（admission_threshold 按 university_id 登记），
而不是"QS100"这种排名桶名。这样才能在信息检索中体现真实大学的意义。
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
import json


# QS 排名参考来源
RANK_SOURCES = ["QS", "THE", "USNews", "ARWU"]


@dataclass
class University:
    """一所真实大学的静态档案（跟学校走，排名变化不影响这些字段）。

    命名注意：避免与"排名桶"混为一谈。University 代表实体，不是排名。
    """
    id: str                # 全局唯一 ID（如 'MIT' / 'stanford' / 'tsinghua'）
    name_en: str           # 英文全名
    name_zh: str = ""      # 中文名（可选）
    country: str = ""      # 国家/地区
    city: str = ""         # 城市（可选）
    established: int = 0   # 建校年份（0 = 未知）
    is_public: Optional[bool] = None  # 公立/私立（None = 未知）
    tuition_intl_usd: Optional[int] = None  # 国际生年学费 USD（None = 未知）
    note: str = ""         # 备注

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "University":
        return cls(
            id=str(d.get("id", "")),
            name_en=str(d.get("name_en", "")),
            name_zh=str(d.get("name_zh", "")),
            country=str(d.get("country", "")),
            city=str(d.get("city", "")),
            established=int(d.get("established", 0) or 0),
            is_public=d.get("is_public"),
            tuition_intl_usd=d.get("tuition_intl_usd"),
            note=str(d.get("note", "")),
        )


@dataclass
class UniversityRanking:
    """大学在某年份/来源的动态排名（QS/THE/USNews…）。

    排名是**动态属性**，每年可能变，因此单独记录。
    大学的录取门槛虽然与排名强相关，但二者不是同步的：
    排名上升/下降可能滞后于录取难度的变化。
    """
    university_id: str      # 关联 University.id
    source: str             # 'QS' / 'THE' / 'USNews' / 'ARWU'
    year: int               # 排名发布年
    rank: int               # 当年排名（数字越小越靠前）
    band: str = ""          # 可选分组（如 'top10' / '100-150'），备用
    note: str = ""

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# 真实大学样本库（示例；P0 用真实世界大学的公开数据填充）
# 这里先给 QS1000 内一批有代表性的真实大学，演示"大学与排名分离"的用法。
# ---------------------------------------------------------------------------
def default_universities() -> List[University]:
    """返回一份内置真实大学档案样本（P0 后由真实数据仓库替代）。

    这里仅作演示与测试：列出的学校基本信息是公开且稳定的，
    不精确到"当年 QS 多少名"——因为排名动态，不硬编入静态档案。
    """
    return [
        University(id="mit", name_en="Massachusetts Institute of Technology",
                   name_zh="麻省理工学院", country="美国", city="Cambridge, MA",
                   established=1861, is_public=False, tuition_intl_usd=57986,
                   note="以理工见长，诺贝尔奖/图灵奖众多"),
        University(id="stanford", name_en="Stanford University",
                   name_zh="斯坦福大学", country="美国", city="Stanford, CA",
                   established=1885, is_public=False, tuition_intl_usd=57693),
        University(id="oxford", name_en="University of Oxford",
                   name_zh="牛津大学", country="英国", city="Oxford",
                   established=1096, is_public=False, tuition_intl_usd=39810),
        University(id="cambridge", name_en="University of Cambridge",
                   name_zh="剑桥大学", country="英国", city="Cambridge",
                   established=1209, is_public=False, tuition_intl_usd=39810),
        University(id="harvard", name_en="Harvard University",
                   name_zh="哈佛大学", country="美国", city="Cambridge, MA",
                   established=1636, is_public=False, tuition_intl_usd=54989),
        University(id="eth", name_en="ETH Zurich",
                   name_zh="苏黎世联邦理工学院", country="瑞士", city="Zurich",
                   established=1855, is_public=True, tuition_intl_usd=1600),
        University(id="nus", name_en="National University of Singapore",
                   name_zh="新加坡国立大学", country="新加坡", city="Singapore",
                   established=1905, is_public=True, tuition_intl_usd=17550),
        University(id="ucb", name_en="University of California, Berkeley",
                   name_zh="加州大学伯克利分校", country="美国", city="Berkeley, CA",
                   established=1868, is_public=True, tuition_intl_usd=44668),
        University(id="yale", name_en="Yale University",
                   name_zh="耶鲁大学", country="美国", city="New Haven, CT",
                   established=1701, is_public=False, tuition_intl_usd=61500),
        University(id="ucl", name_en="University College London",
                   name_zh="伦敦大学学院", country="英国", city="London",
                   established=1826, is_public=False, tuition_intl_usd=38600),
        University(id="pk", name_en="Peking University",
                   name_zh="北京大学", country="中国", city="Beijing",
                   established=1898, is_public=True, tuition_intl_usd=6000),
        University(id="thu", name_en="Tsinghua University",
                   name_zh="清华大学", country="中国", city="Beijing",
                   established=1911, is_public=True, tuition_intl_usd=6000),
        University(id="imperial", name_en="Imperial College London",
                   name_zh="帝国理工学院", country="英国", city="London",
                   established=1907, is_public=False, tuition_intl_usd=42500),
        University(id="uchicago", name_en="University of Chicago",
                   name_zh="芝加哥大学", country="美国", city="Chicago, IL",
                   established=1890, is_public=False, tuition_intl_usd=61500),
        University(id="umich", name_en="University of Michigan, Ann Arbor",
                   name_zh="密歇根大学安娜堡分校", country="美国", city="Ann Arbor, MI",
                   established=1817, is_public=True, tuition_intl_usd=55400),
        University(id="toronto", name_en="University of Toronto",
                   name_zh="多伦多大学", country="加拿大", city="Toronto",
                   established=1827, is_public=True, tuition_intl_usd=58000),
        University(id="princeton", name_en="Princeton University",
                   name_zh="普林斯顿大学", country="美国", city="Princeton, NJ",
                   established=1746, is_public=False, tuition_intl_usd=56100),
        University(id="caltech", name_en="California Institute of Technology",
                   name_zh="加州理工学院", country="美国", city="Pasadena, CA",
                   established=1891, is_public=False, tuition_intl_usd=56400),
        University(id="nw", name_en="Northwestern University",
                   name_zh="西北大学", country="美国", city="Evanston, IL",
                   established=1851, is_public=False, tuition_intl_usd=62100),
        University(id="columbia", name_en="Columbia University",
                   name_zh="哥伦比亚大学", country="美国", city="New York, NY",
                   established=1754, is_public=False, tuition_intl_usd=62100),
    ]


def default_rankings() -> List[UniversityRanking]:
    """生成默认大学的模拟历年 QS 排名（示意用，P0 替换为真实抓取数据）。"""
    # 每所学校的典型 QS rank 范围，2019~2024
    profile = {
        # id: [(2019 rank, 2020 rank, 2021, 2022, 2023, 2024)]
        "mit":    (2, 1, 1, 1, 1, 1),
        "stanford": (2, 2, 2, 3, 5, 2),
        "oxford": (5, 4, 5, 2, 4, 3),
        "cambridge": (6, 7, 7, 3, 2, 2),
        "harvard": (3, 3, 3, 5, 4, 4),
        "eth":    (7, 6, 6, 8, 7, 7),
        "nus":    (11, 11, 11, 11, 8, 8),
        "ucb":    (28, 27, 30, 32, 10, 10),
        "yale":   (15, 17, 17, 14, 16, 16),
        "ucl":    (8, 8, 10, 8, 9, 9),
        "pk":     (30, 22, 23, 18, 12, 14),
        "thu":    (17, 15, 16, 17, 15, 20),
        "imperial": (9, 9, 8, 6, 6, 6),
        "uchicago": (10, 9, 9, 10, 11, 21),
        "umich":  (20, 21, 22, 23, 25, 33),
        "toronto": (28, 29, 25, 26, 21, 21),
        "princeton": (13, 13, 12, 16, 20, 22),
        "caltech": (4, 5, 4, 4, 6, 15),
        "nw":     (34, 31, 29, 30, 32, 43),
        "columbia": (16, 18, 19, 19, 23, 34),
    }
    yrs = [2019, 2020, 2021, 2022, 2023, 2024]
    out = []
    for uid, ranks in profile.items():
        for i, r in enumerate(ranks):
            y = yrs[i]
            # 前 10 给 band
            band = "top10" if r <= 10 else ("top50" if r <= 50 else "50-100")
            out.append(UniversityRanking(university_id=uid, source="QS",
                                         year=y, rank=r, band=band))
    return out


def university_lookup(unis: List[University]) -> Dict[str, University]:
    return {u.id: u for u in unis}
