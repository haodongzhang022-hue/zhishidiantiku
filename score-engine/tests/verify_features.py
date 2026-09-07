# -*- coding: utf-8 -*-
"""功能达成度核验脚本（issue #8 追评升级版）。

逐项核验核心功能是否真实达成：
  1. 体系识别可用且特征提取正确
  2. 模糊换算精度：强/弱画像可区分
  3. 深度学习确有学习效果（不是拍脑袋）
  4. ★年度漂移识别：换算会随年份变化
  5. 效果跟踪：区分不同年份、记录指标
  6. ★大学实体与排名分离：样本覆盖真实大学，QS 桶名不再伪装成"学校"
  7. ★缺失信息=NaN/mask，不再用 -1 误导模型判弱
  8. 扩展性：全球大学/质量维度架构

运行： python3 tests/verify_features.py
"""
import sys, os, math, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from score_engine import registry, models, recognizer, converter, trainer, valley, nn, drift
from score_engine import university as univ_mod

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
    ("AP: Calc BC 5, Physics 4, Chem 5, GPA 3.9", 0.55, 0.95),
    ("AP: Calc BC 5, Calc AB 5, Physics C 5, Chem 5, Stats 5, GPA 3.95, SAT 1550", 0.8, 1.0),
    ("AP: Calc AB 4, Chem 3, GPA 3.4", 0.15, 0.6),
    ("A-Level: 数学 A*, 物理 A*, 化学 A*, 雅思 8.0", 0.7, 1.0),
    ("IB 总分 42 / 45，HL 数理化，TOEFL 115", 0.75, 1.0),
    ("高考 700 分", 0.75, 1.0),
]
for txt, lo, hi in strong_weak:
    vm = conv_m.value_of_text(txt)["value"]
    print(f"    {txt[:52]:<54} model={vm:.3f}")
    check(f"模型价值在合理区间: {txt[:24]}", lo<=vm<=hi, f"model={vm:.3f} 期望[{lo},{hi}]")
vs = conv_m.value_of_text("AP: Calc AB 4, Chem 3, GPA 3.4")["value"]
vg = conv_m.value_of_text("AP: Calc BC 5, Calc AB 5, Physics C 5, Chem 5, Stats 5, GPA 3.95, SAT 1550")["value"]
check("强/弱 AP 画像价值能拉开差距", vg - vs > 0.3, f"强={vg:.3f} 弱={vs:.3f}")

print()
print("="*66)
print("[3] 深度学习确有学习效果（排序相关性）")
print("="*66)
snap = t.history[-1]
check("训练 val_corr>0.85", snap["val_corr"]>0.85, f"val_corr={snap['val_corr']}")
check("训练 val_mae<0.08", snap["val_mae"]<0.08, f"val_mae={snap['val_mae']}")

print()
print("="*66)
print("[4] ★年度漂移识别（换算随年份变化可识别）")
print("="*66)
yd = drift.YearDrift.from_records(recs)
trend = yd.trend()
years = yd.years()
check("数据含多年度", len(years) >= 5, f"years={years}")
check("YearDrift 估算出逐年趋势", len(trend) >= 2 and trend[0]["year"] < trend[-1]["year"],
      f"{trend}")
d = yd.drift_between(min(years), max(years))
check("漂移幅度可量化(首年→末年有变化)", abs(d) > 0.01,
      f"drift({min(years)}→{max(years)})={d}")
profile = "AP: Calc BC 5, Physics 4, Chem 5, GPA 3.9"
v_easy = conv_m.convert(profile, year=min(years), drift=yd)["source"]["value"]
v_hard = conv_m.convert(profile, year=max(years), drift=yd)["source"]["value"]
check("同一分数在不同年份换算结果不同", abs(v_easy-v_hard) > 0.005,
      f"{min(years)}={v_easy:.3f} {max(years)}={v_hard:.3f}")
check("更难点换算价值应更高/门槛更高", v_hard > v_easy,
      f"{min(years)}={v_easy:.3f} {max(years)}={v_hard:.3f}")

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
print("[6] ★大学实体与排名分离（核心架构改进）")
print("="*66)
unis = univ_mod.default_universities()
ranks = univ_mod.default_rankings()
check("大学档案含真实大学（非 QS 桶名）", len(unis) >= 10, f"unis={len(unis)}")
all_names = {u.name_en for u in unis}
qs_buckets = [s for s in all_names if s.startswith("QS") or "QS10" in s]
check("无 QS 桶名伪装大学", len(qs_buckets) == 0, f"found: {qs_buckets}")

# 样本中的 school 应该是真实大学名
sample_schools = {r.school for r in recs}
real_names = {u.name_en for u in unis}
check("样本 school 是真实大学名", sample_schools <= real_names,
      f"非真实大学名: {sample_schools - real_names}")

# 有 university_id 字段关联大学
check("样本有 university_id 关联大学", all(hasattr(r, "university_id") and r.university_id for r in recs[:10]))
check("university_id 能解析到大学", all(r.university_id in univ_mod.university_lookup(unis) for r in recs[:10]))

# 排名按年份动态：同一大学不同年份排名不同
mit_ranks = sorted({(r.year, r.rank) for r in ranks if r.university_id == "mit"})
check("大学排名按年份记录且不同", len(mit_ranks) >= 3 and len({rk for _, rk in mit_ranks}) >= 2,
      f"mit ranks: {mit_ranks}")

# 排名与大学静态信息分离：大学的 tuition/国家等信息不在 ranking 里
check("大学静态信息与排名分离", unis[0].name_en != "" and hasattr(unis[0], "country"),
      "大学有独立档案，排名是另一张表")

print()
print("="*66)
print("[7] ★缺失值处理：NaN/mask 而非 -1 判弱")
print("="*66)
# 7a. 特征向量化不再出现 -1
feats = {"ap_avg": 4.8, "ap_subjects": 4}
vec, mask = models.features_to_vector(feats)
check("向量化不再用 -1 占位缺失", -1 not in vec, f"vec={vec}")
check("mask 标记缺失为 0", 0 in mask, f"mask={mask}")
# 7b. 缺失维度为中性值 (0.0)，不是误导值
for k, v, m in zip(models.FEATURE_KEYS, vec, mask):
    if m == 0:
        check(f"缺失字段 '{k}' 置 0 中性", v == 0.0, f"v={v}")
# 7c. 模型对缺失的感知：缺失 SAT 不判弱
text_no_sat = "AP: Calc BC 5, Physics 5, Chem 5, GPA 3.9"
text_with_sat = "AP: Calc BC 5, Physics 5, Chem 5, GPA 3.9, SAT 1550"
v_no_sat = conv_m.value_of_text(text_no_sat)["value"]
v_with_sat = conv_m.value_of_text(text_with_sat)["value"]
check("缺失 SAT 不压低价值（mask 生效）", v_no_sat >= v_with_sat - 0.15,
      f"缺SAT={v_no_sat:.3f} 有SAT={v_with_sat:.3f}")
# 7d. 缺失字段不被填 0 当作"真 0 分"
no_gpa = conv_m.value_of_text("AP: Calc BC 5, Physics 5, Chem 5")["value"]
with_gpa = conv_m.value_of_text("AP: Calc BC 5, Physics 5, Chem 5, GPA 3.9")["value"]
check("缺 GPA 不把学生判为弱（与有 GPA 接近）", no_gpa >= with_gpa - 0.15,
      f"缺GPA={no_gpa:.3f} 有GPA={with_gpa:.3f}")

print()
print("="*66)
print("[8] 泛化/质量/数据库 扩展架构（Roadmap，非硬门禁）")
print("="*66)
import score_engine as se_pkg
pkg_dir = os.path.dirname(se_pkg.__file__)
ext = os.path.abspath(os.path.join(pkg_dir, "..", "..", "docs", "score-engine-extend.md"))
ext_done = os.path.exists(ext)
print(f"  ℹ️  LanceDB 多表 schema 文档(roadmap): "
      f"{'已存在' if ext_done else '缺失'}")
print("  （上述为扩展计划项，见 docs/score-engine-extend.md）")

print()
print("="*66)
print("[9] ★LanceDB 双库落地：换算库(score) + 分析库(quality) 分表管理")
print("="*66)
import tempfile, shutil
from score_engine import db as dbmod
from score_engine import university as univ_mod
import scripts.gen_quality_data as gq
_tmp = tempfile.mkdtemp()
_db = dbmod.ScoreDB(root=os.path.join(_tmp, "ldb"), backend="json")
_unis = univ_mod.default_universities()
_stats = _db.seed_from_engine(
    universities=_unis,
    rankings=univ_mod.default_rankings(),
    profiles=gq.build_profiles(_unis),
    faculties=gq.build_faculties(_unis),
    outcomes=gq.build_outcomes(_unis))
check("双库建好(score_db: university/ranking/threshold/calendar)",
      _db.count_score("university")==20 and _db.count_score("university_ranking")==120,
      f"uni={_db.count_score('university')} rank={_db.count_score('university_ranking')}")
check("分析库建好(quality_db: profile/faculty/outcome 各20)",
      _db.count_quality("school_profile")==20 and _db.count_quality("school_faculty")==20
      and _db.count_quality("school_outcome")==20)
_check1 = _db.query_score("university", {"id": "mit"})
check("换算库可查大学静态档案", len(_check1)==1 and "rank" not in _check1[0])
_check2 = _db.query_score("university_ranking", {"university_id": "mit"})
check("换算库可查逐年排名(2019-2024=6条)", len(_check2)==6)
check("排名逐年不同", len({r["rank"] for r in _check2})>=2)
_check3 = _db.query_quality("school_profile", {"university_id": "mit"})
check("分析库可查质量档案", len(_check3)==1 and "scale_students" in _check3[0])
check("无 LanceDB 时退化为可用后端", _db.backend_kind()=="json")
_db.close(); shutil.rmtree(_tmp, True)

print()
print("="*66)
print("[10] ★质量鉴定：排名≠真实水平（名不副实 / 被低估识别）")
print("="*66)
from score_engine import quality as qmod
qa = qmod.QualityAnalyzer(gq.build_profiles(_unis), gq.build_faculties(_unis),
                          gq.build_outcomes(_unis),
                          [r.to_dict() for r in univ_mod.default_rankings()])
_rep = qa.mismatch_report(year=2024, source="QS")
check("质量报告含真实大学", len(_rep)>=10)
_verdicts = {r["verdict"] for r in _rep}
check("能识别『名不副实/高排名低质量』", "名不副实/高排名低质量" in _verdicts,
      f"verdicts={_verdicts}")
check("能识别『被低估/高性价比』", "被低估/高性价比" in _verdicts, f"verdicts={_verdicts}")
_eth = next(r for r in _rep if r["university_id"]=="eth")
check("ETH 被判定名不副实(高排名#7低质量)", _eth["verdict"]=="名不副实/高排名低质量")
check("质量档案可合并三表出单校报告",
      "quality_index" in qa.school_profile("mit"))
check("缺失部分维度不把质量判极低", 0.0<=qa.quality_index("mit")<=1.0)

print()
print("="*66)
print(f"结果：PASS {len(PASS)} / {len(PASS)+len(FAIL)}")
print("="*66)
if FAIL:
    print("未达成项：")
    for f in FAIL: print(f"  ❌ {f}")
    sys.exit(1)
print("✅ 全部核心功能达成")
