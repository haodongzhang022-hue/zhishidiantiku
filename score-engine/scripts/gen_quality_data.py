# -*- coding: utf-8 -*-
"""为内置真实大学生成质量鉴定数据（school_profile/faculty/outcome）。

这些是**示意/演示数据**，用于打通"分析库多表 → 质量指数 → 名不副实报告"
整条链路。P2 阶段用各校真实公开数据（USNews/THE 年鉴、学校年报）替换。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from score_engine import university as univ_mod

# university_id -> (在校生, 师资, 师生比, 学费USD, 年论文, 被引, 就业率, 
#               顶尖师资占比tier_high, star_count, 负面占比negative_ratio)
# 注：故意让"排名"与"质量"错位，演示名不副实 / 被低估。
QUAL = {
    "mit":    (11500, 1180, 9.7, 57986, 32000, 220000, 0.94, 0.45, 210, 0.05),
    "stanford":(15500, 2020, 7.7, 57693, 29000, 260000, 0.93, 0.40, 195, 0.06),
    "oxford": (24000, 1600, 15.0, 39810, 18000, 240000, 0.92, 0.38, 160, 0.08),
    "cambridge":(20000, 1650, 12.1, 39810, 17000, 230000, 0.93, 0.40, 170, 0.07),
    "harvard":(21000, 2100, 10.0, 54989, 26000, 280000, 0.95, 0.42, 200, 0.05),
    "eth":    (24000, 540, 44.4, 1600, 16000, 140000, 0.95, 0.35, 90, 0.06),
    "nus":    (35000, 2600, 13.5, 17550, 25000, 160000, 0.92, 0.32, 110, 0.10),
    "ucb":    (43000, 2500, 17.2, 44668, 20000, 230000, 0.92, 0.36, 150, 0.09),
    "yale":   (13500, 1400, 9.6, 61500, 11000, 180000, 0.94, 0.38, 130, 0.06),
    "ucl":    (42000, 4500, 9.3, 38600, 23000, 190000, 0.91, 0.33, 120, 0.12),
    "pk":     (45000, 3400, 13.2, 6000, 15000, 130000, 0.95, 0.28, 90, 0.14),
    "thu":    (48000, 3300, 14.5, 6000, 17000, 150000, 0.96, 0.30, 100, 0.12),
    "imperial":(19000, 3200, 5.9, 42500, 15000, 140000, 0.93, 0.37, 110, 0.07),
    "uchicago":(17000, 2300, 7.4, 61500, 9000, 120000, 0.90, 0.35, 95, 0.10),
    "umich":  (49000, 6800, 7.2, 55400, 16000, 180000, 0.91, 0.31, 110, 0.11),
    "toronto":(70000, 11000, 6.4, 58000, 22000, 220000, 0.91, 0.34, 140, 0.12),
    "princeton":(8300, 1300, 6.4, 56100, 8000, 110000, 0.95, 0.42, 90, 0.05),
    "caltech":(2200, 300, 7.3, 56400, 8000, 100000, 0.94, 0.48, 70, 0.05),
    "nw":    (22000, 1800, 12.2, 62100, 12000, 130000, 0.93, 0.34, 100, 0.10),
    "columbia":(33000, 4100, 8.0, 62100, 16000, 160000, 0.92, 0.36, 130, 0.11),
}


def build_profiles(unis):
    rows = []
    for u in unis:
        if u.id not in QUAL:
            continue
        (students, fac, rsr, tuition, papers, cit, emp,
         tier_high, star, neg) = QUAL[u.id]
        rows.append({
            "university_id": u.id, "name": u.name_en,
            "scale_students": students, "scale_faculty": fac,
            "ratio_student_faculty": rsr, "tuition_intl_usd": tuition,
            "papers_yearly": papers, "citations": cit,
            "employment_rate": emp, "accreditation": u.country,
            "source": "demo-public", "year": 2024,
        })
    return rows


def build_faculties(unis):
    rows = []
    for u in unis:
        if u.id not in QUAL:
            continue
        (_, _, _, _, _, _, _, tier_high, star, neg) = QUAL[u.id]
        rows.append({
            "university_id": u.id, "name": u.name_en,
            "tier_high": tier_high, "tier_mid": round(1.0 - tier_high - neg, 3),
            "tier_low": round(neg * 0.5, 3),
            "star_count": star, "negative_ratio": neg,
            "note": "负面占比越低越健康", "source": "demo-public", "year": 2024,
        })
    return rows


def build_outcomes(unis):
    rows = []
    for u in unis:
        if u.id not in QUAL:
            continue
        (_, _, _, _, papers, cit, emp, _, _, _) = QUAL[u.id]
        rows.append({
            "university_id": u.id, "name": u.name_en,
            "papers_yearly": papers, "citations": cit,
            "h_index": round(cit ** 0.45), "patents": round(papers * 0.08),
            "employment_rate": emp, "salary_outcome": 0.8 + (emp - 0.9) * 2,
            "source": "demo-public", "year": 2024,
        })
    return rows


def main():
    unis = univ_mod.default_universities()
    rows = {"profiles": build_profiles(unis), "faculties": build_faculties(unis),
            "outcomes": build_outcomes(unis)}
    print(f"生成质量数据：{len(rows['profiles'])} 校 profile / "
          f"{len(rows['faculties'])} 校 faculty / {len(rows['outcomes'])} 校 outcome")
    return rows


if __name__ == "__main__":
    main()
