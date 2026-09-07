# -*- coding: utf-8 -*-
"""端到端演示：识别 → 训练 → 换算 → 洼地寻优 → 大学与排名分离。
运行: python -m score_engine.demo
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from . import registry, models, recognizer, converter, trainer, valley, university as univ_mod


def main():
    print("=" * 64)
    print("跨体系分数换算引擎 · 端到端演示")
    print("=" * 64)

    # 0) 大学档案与排名分离
    print("\n[0] 大学实体与排名分离（核心设计）")
    unis = univ_mod.default_universities()
    ranks = univ_mod.default_rankings()
    print(f"  · 大学档案 {len(unis)} 所（静态信息：名称/国家/学费…）")
    print(f"  · 历年排名 {len(ranks)} 条（QS 2019-2024 动态）")
    mit = next(u for u in unis if u.id == "mit")
    print(f"  · 示例: {mit.name_zh} 建校{mit.established} 国家={mit.country}")
    mit_ranks = [(r.year, r.rank) for r in ranks if r.university_id == "mit"]
    print(f"  · {mit.name_en} 历年 QS 排名: {mit_ranks}")
    print("  → 大学信息跟大学走，排名跟年份走，二者分离")

    # 1) 识别
    print("\n[1] 分数识别")
    samples = [
        "AP: Calc BC 5, Physics C 4, Chem 5, GPA 3.92, SAT 1530",
        "A-Level: 数学 A*, 物理 A, 化学 A, 雅思 7.0",
        "IB 总分 38 / 45，HL 数理化，TOEFL 106",
        "高考 652 分，省位次 4200",
    ]
    for s in samples:
        r = recognizer.recognize(s)
        print(f"  · {s[:38]:<38} → {r.system:<8} conf={r.confidence:.2f} "
              f"feats={list(r.features.keys())}")

    # 2) 训练
    print("\n[2] 生成示例历史数据并训练模型")
    recs = models.make_mock_admissions()
    schools = {r.school for r in recs}
    print(f"  · 生成样本 {len(recs)} 条，覆盖 {len(schools)} 所真实大学")
    print(f"  · 样本示例大学: {sorted(schools)[:5]} ...")
    t = trainer.Trainer()
    snap = t.train(recs, epochs=150, verbose=0)
    print(f"  · 训练完成 val_mae={snap['val_mae']:.3f} val_corr={snap['val_corr']:.3f}")

    # 3) 换算
    print("\n[3] 换算一条真实描述")
    conv = converter.ScoreConverter(model=t.model)
    text = "A-Level: 数学 A*, 物理 A, 化学 A, 雅思 7.0"
    res = conv.convert(text)
    print(f"  输入: {text}")
    print(f"  识别={res['source']['system']}  统一价值={res['source']['value']:.3f}")
    if res["source"].get("mask"):
        missing = [k for k, m in zip(models.FEATURE_KEYS, res["source"]["mask"]) if m == 0]
        if missing:
            print(f"  缺失字段(不判弱): {', '.join(missing)}")
    for k, v in res["conversions"].items():
        print(f"    [{k}] {v['kind']}")

    # 4) 洼地寻优（对真实大学）
    print("\n[4] 找 MIT 的低分路径")
    vf = valley.ValleyFinder(model=t.model)
    v = vf.find_valley("mit", recs)   # 用 school_id 查询
    for i, row in enumerate(v["systems_ranked"], 1):
        mark = "  << 洼地" if i == 1 else ""
        print(f"  {i}. {row['system']:<8} 成本={row['competition_cost']:.3f} "
              f"→ {row['equivalent']['kind']}{mark}")
    print(f"  推荐: {v['recommended_valley']['system']}")

    # 5) 效果跟踪展示
    print("\n[5] 效果跟踪")
    for s in t.history:
        print(f"  快照 source={s['source_tag']} samples={s['samples']} "
              f"val_mae={s['val_mae']:.3f} val_corr={s['val_corr']:.3f}")

    print("\n演示完成 ✅")


if __name__ == "__main__":
    main()
