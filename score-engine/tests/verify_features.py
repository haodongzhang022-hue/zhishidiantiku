# -*- coding: utf-8 -*-
"""功能达成度核验脚本（issue #8 追评）。
针对 PR#9 交付的"跨体系分数换算引擎"逐项核验核心功能是否真实达成：
  1. 体系识别可用且特征提取正确
  2. 模糊换算精度：同一档位的不同体系应给出可比、不越界的价值；强/弱画像要能区分
  3. 深度学习确有学习效果（不是拍脑袋）
  4. ★年度漂移识别：换算会随年份变化，引擎须能识别并量化这种变化
  5. 效果跟踪：能区分不同年份数据、记录指标并做对比
  6. 扩展性：全球大学/质量维度的架构是否已立起来
运行： python3 tests/verify_features.py
"""
import sys, os, math, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from score_engine import registry, models, recognizer, converter, trainer, valley, nn, drift

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅ PASS' if cond else '❌ FAIL'}  {name}" + (f"\n        ↳ {detail}" if detail and not cond else ""))

print("="*66)
print("[1] 体系识别 & 特征提取")
print("="*66)
r = recognizer.recognize("AP: Calc BC 5, Physics 4, Chem 5, GPA 3.9")
check("AP 识别正确", r.system=="AP", f"got {r.system}")
check("AP 提取到 ap_avg", "ap_avg" in r.features)
check("AP ap_avg 值合理", 3<=r.features.get("ap_avg",0)<=5, f"got {r.features.get('ap_avg')}")
check("AL 识别正确", recognizer.recognize("A-Level: 数学 A*, 物理 A, 化学 A, 雅思 7.0").system=="AL")
check("IB 识别正确", recognizer.recognize("IB 总分 38 / 45，HL 数理化，TOEFL 106").system=="IB")
check("高考 识别正确", recognizer.recognize("高考 652 分，省位次 4200").system=="GAOKAO")

print()
print("="*66)
print("[2] 换算精度 & 跨体系一致性（能区分强弱、不越界）")
print("="*66)
recs = models.make_mock_admissions()
t = trainer.Trainer(); t.train(recs, epochs=500, verbose=0)
conv_m = converter.ScoreConverter(model=t.model)
strong_weak = [
    # (描述, 期望区间)
    ("AP: Calc BC 5, Physics 4, Chem 5, GPA 3.9", 0.6, 0.9),
    ("AP: Calc BC 5, Calc AB 5, Physics C 5, Chem 5, Stats 5, GPA 3.95, SAT 1550", 0.8, 1.0),
    ("AP: Calc AB 4, Chem 3, GPA 3.4", 0.15, 0.5),          # 弱画像应显著更低
    ("A-Level: 数学 A*, 物理 A*, 化学 A*, 雅思 8.0", 0.7, 1.0),
    ("IB 总分 42 / 45，HL 数理化，TOEFL 115", 0.75, 1.0),
    ("高考 700 分", 0.75, 1.0),
]
for txt, lo, hi in strong_weak:
    vm = conv_m.value_of_text(txt)["value"]
    print(f"    {txt[:52]:<54} model={vm:.3f}")
    check(f"模型价值在合理区间: {txt[:24]}", lo<=vm<=hi, f"model={vm:.3f} 期望[{lo},{hi}]")
# 弱画像必须显著低于强画像（能区分精度）
vs = conv_m.value_of_text("AP: Calc AB 4, Chem 3, GPA 3.4")["value"]
vg = conv_m.value_of_text("AP: Calc BC 5, Calc AB 5, Physics C 5, Chem 5, Stats 5, GPA 3.95, SAT 1550")["value"]
check("强/弱 AP 画像价值能拉开差距", vg - vs > 0.3, f"强={vg:.3f} 弱={vs:.3f}")

print()
print("="*66)
print("[3] 深度学习确有学习效果（排序相关性）")
print("="*66)
snap = t.history[-1]
check("训练 val_corr>0.9", snap["val_corr"]>0.9, f"val_corr={snap['val_corr']}")
check("训练 val_mae<0.1", snap["val_mae"]<0.1, f"val_mae={snap['val_mae']}")

print()
print("="*66)
print("[4] ★年度漂移识别（换算随年份变化可识别）")
print("="*66)
# 数据里 2019 较易 → 2024 更难（school_value 逐年抬升）
yd = drift.YearDrift.from_records(recs)
trend = yd.trend()
years = yd.years()
check("数据含多年度", len(years) >= 5, f"years={years}")
check("YearDrift 估算出逐年趋势", len(trend) >= 2 and trend[0]["year"] < trend[-1]["year"],
      f"{trend}")
d = yd.drift_between(min(years), max(years))
check("漂移幅度可量化(2019→2024 有变化)", abs(d) > 0.03,
      f"drift(2019→2024)={d}")
# 同一条分数，换算结果随年份不同（更难年份 → 等效价值更高 → 更高门槛）
profile = "AP: Calc BC 5, Physics 4, Chem 5, GPA 3.9"
v_easy = conv_m.convert(profile, year=min(years), drift=yd)["source"]["value"]
v_hard = conv_m.convert(profile, year=max(years), drift=yd)["source"]["value"]
check("同一分数在不同年份换算结果不同(2019≠2024)", abs(v_easy-v_hard) > 0.01,
      f"2019={v_easy:.3f} 2024={v_hard:.3f}")
check("更难点(2024)换算价值应更高/门槛更高", v_hard > v_easy,
      f"2019={v_easy:.3f} 2024={v_hard:.3f}")

print()
print("="*66)
print("[5] 效果跟踪：能区分不同年份数据并记录指标")
print("="*66)
t2 = trainer.Trainer(model_path="models/_verify_tmp.json"); t2.model = t.model
y19 = [r for r in recs if r.year==2019]; y24=[r for r in recs if r.year==2024]
t2.retrain(y19, epochs=10, verbose=0, source_tag="year2019")
t2.retrain(y24, epochs=10, verbose=0, source_tag="year2024")
tags = {h["source_tag"] for h in t2.history}
check("快照区分不同年份(year2019/year2024)", {"year2019","year2024"}<=tags, f"tags={tags}")
try: os.remove("models/_verify_tmp.json")
except Exception: pass

print()
print("="*66)
print("[6] 泛化/质量/数据库 扩展架构（Roadmap，非本次硬门禁）")
print("="*66)
import score_engine as se_pkg
pkg_dir = os.path.dirname(se_pkg.__file__)
ext = os.path.abspath(os.path.join(pkg_dir, "..", "..", "docs", "score-engine-extend.md"))
ext_done = os.path.exists(ext)
print(f"  ℹ️  样本覆盖真实大学名(泛化到全球大学): "
      f"{'是' if any(not s.startswith('QS') for s in {r.school for r in recs}) else '否→待P0(roadmap)'}")
print(f"  ℹ️  LanceDB 多表 schema 文档(roadmap): "
      f"{'已存在' if ext_done else '缺失'}")
print("  （上述为扩展计划项，未纳入本次硬门禁；见 docs/score-engine-extend.md）")

print()
print("="*66)
print(f"结果：PASS {len(PASS)} / {len(PASS)+len(FAIL)}")
print("="*66)
if FAIL:
    print("未达成项（可接受范围外的缺口）：")
    for f in FAIL: print(f"  ❌ {f}")
    sys.exit(1)
print("✅ 全部核心功能达成")
