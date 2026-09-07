# -*- coding: utf-8 -*-
"""端到端演示：识别 → 训练 → 换算 → 洼地寻优。
运行: python -m score_engine.demo
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from . import registry, models, recognizer, converter, trainer, valley


def main():
    print("=" * 60)
    print("跨体系分数换算引擎 · 端到端演示")
    print("=" * 60)

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
    print(f"  · 生成样本 {len(recs)} 条")
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
    for k, v in res["conversions"].items():
        print(f"    [{k}] {v['kind']}")

    # 4) 洼地寻优
    print("\n[4] 找 QS50 学校的低分路径")
    vf = valley.ValleyFinder(model=t.model)
    v = vf.find_valley("QS50", recs)
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
