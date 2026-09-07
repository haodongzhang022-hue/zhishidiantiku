# -*- coding: utf-8 -*-
"""核心单元自测。运行: python -m unittest tests/test_engine.py -v"""
import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from score_engine import registry, models, recognizer, converter, trainer, valley, nn, drift
from score_engine import university as univ_mod


class TestRecognizer(unittest.TestCase):
    def test_recognize_ap(self):
        r = recognizer.recognize("AP: Calc BC 5, Physics 4, Chem 5, GPA 3.9")
        self.assertEqual(r.system, "AP")
        self.assertIn("ap_avg", r.features)

    def test_recognize_al(self):
        r = recognizer.recognize("A-Level: 数学 A*, 物理 A, 化学 A, 雅思 7.0")
        self.assertEqual(r.system, "AL")
        self.assertAlmostEqual(r.features.get("al_avg", 0), 4.333, places=2)

    def test_recognize_ib(self):
        r = recognizer.recognize("IB 总分 38 / 45，HL 数理化，TOEFL 106")
        self.assertEqual(r.system, "IB")
        self.assertEqual(r.features.get("ib_total"), 38.0)

    def test_recognize_gaokao(self):
        r = recognizer.recognize("高考 652 分，省位次 4200")
        self.assertEqual(r.system, "GAOKAO")
        self.assertEqual(r.features.get("gk_total"), 652.0)

    def test_empty(self):
        r = recognizer.recognize("")
        self.assertEqual(r.system, "OTHER")


class TestRegistry(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(registry.normalize_system("A-Level"), "AL")
        self.assertEqual(registry.normalize_system("高考"), "GAOKAO")
        self.assertEqual(registry.normalize_system("IB"), "IB")


class TestModels(unittest.TestCase):
    def test_vector_dim(self):
        vec, mask = models.features_to_vector({})
        self.assertEqual(len(vec), models.FEATURE_DIM)
        self.assertEqual(len(mask), models.FEATURE_DIM)

    def test_no_minus_one_missing(self):
        """缺失不用 -1，用 mask 标记。"""
        vec, mask = models.features_to_vector({"ap_avg": 4.8})
        self.assertNotIn(-1, vec)
        # 缺字段的 mask 应标 0
        for k, m in zip(models.FEATURE_KEYS, mask):
            if k not in ("ap_avg",):
                self.assertEqual(m, 0, f"{k} should be masked")
        self.assertEqual(mask[0], 1, "ap_avg should be present")

    def test_mock_records_have_real_schools(self):
        """样本应使用真实大学而非 QS 桶名。"""
        recs = models.make_mock_admissions()
        self.assertGreater(len(recs), 0)
        unis = univ_mod.default_universities()
        real_ids = {u.id for u in unis}
        for r in recs[:10]:
            self.assertIn(r.school_id, real_ids)
            self.assertTrue(r.school)
            self.assertTrue(0 <= getattr(r, "school_value", -1) <= 1)

    def test_no_qs_bucket_in_schools(self):
        recs = models.make_mock_admissions()
        schools = {r.school for r in recs}
        self.assertFalse(any(s.startswith("QS") for s in schools),
                         f"Found QS buckets: {[s for s in schools if s.startswith('QS')]}")


class TestUniversity(unittest.TestCase):
    def test_university_ranking_separation(self):
        """大学实体与排名分离。"""
        unis = univ_mod.default_universities()
        ranks = univ_mod.default_rankings()
        self.assertGreaterEqual(len(unis), 10)
        self.assertGreaterEqual(len(ranks), 20)
        # 排名是独立的 UniversityRanking 记录
        self.assertTrue(all(hasattr(r, "year") and hasattr(r, "rank") for r in ranks))
        # 大学静态档案不包含年份排名
        self.assertFalse(any(hasattr(u, "rank") for u in unis))

    def test_ranking_changes_by_year(self):
        """同一大学不同年份排名应记录且可能变化。"""
        ranks = univ_mod.default_rankings()
        stanford_ranks = [r for r in ranks if r.university_id == "stanford"]
        self.assertGreaterEqual(len(stanford_ranks), 3)
        # 至少有一所大学排名在年份间有变化
        has_change = False
        for uid in {r.university_id for r in ranks}:
            yr_ranks = sorted({(r.year, r.rank) for r in ranks if r.university_id == uid})
            if len({rk for _, rk in yr_ranks}) > 1:
                has_change = True
                break
        self.assertTrue(has_change, "At least one university should have rank change across years")


class TestTrainer(unittest.TestCase):
    def test_train_and_retrain(self):
        recs = models.make_mock_admissions()
        t = trainer.Trainer()
        snap = t.train(recs, epochs=80, verbose=0)
        self.assertGreater(snap["val_corr"], 0.5)
        # 增量后训练
        t2 = trainer.Trainer(model_path="models/_test_model.json")
        t2.model = t.model
        t2.retrain(recs[:30], epochs=10, verbose=0)
        self.assertGreaterEqual(len(t2.history), 1)


class TestValley(unittest.TestCase):
    def test_find_valley_by_school_id(self):
        """用 school_id 查询低分路径。"""
        recs = models.make_mock_admissions()
        vf = valley.ValleyFinder()
        r = vf.find_valley("mit", recs)
        self.assertIn("recommended_valley", r)
        rows = r["systems_ranked"]
        costs = [x["competition_cost"] for x in rows]
        self.assertEqual(costs, sorted(costs))  # 已升序

    def test_find_valley_by_school_name(self):
        recs = models.make_mock_admissions()
        vf = valley.ValleyFinder()
        r = vf.find_valley("Massachusetts Institute of Technology", recs)
        self.assertNotIn("error", r)
        self.assertEqual(r["school_id"], "mit")


class TestConversion(unittest.TestCase):
    def test_convert(self):
        conv = converter.ScoreConverter()
        res = conv.convert("A-Level: 数学 A*, 物理 A, 雅思 7.0")
        self.assertIn("GAOKAO", res["conversions"])

    def test_missing_field_not_penalized(self):
        """缺失字段不应压低价值（核心改进）。"""
        recs = models.make_mock_admissions()
        t = trainer.Trainer()
        t.train(recs, epochs=200, verbose=0)
        conv = converter.ScoreConverter(model=t.model)
        # 有 SAT vs 缺 SAT
        v_no = conv.value_of_text("AP: Calc BC 5, Physics 5, Chem 5, GPA 3.9")["value"]
        v_yes = conv.value_of_text("AP: Calc BC 5, Physics 5, Chem 5, GPA 3.9, SAT 1550")["value"]
        # 缺 SAT 不应该显著压低价值
        self.assertGreaterEqual(v_no, v_yes - 0.15)


class TestYearDrift(unittest.TestCase):
    """年度漂移识别：换算应随年份变化（核心需求）。"""
    def test_drift_detects_year_change(self):
        recs = models.make_mock_admissions()
        yd = drift.YearDrift.from_records(recs)
        ys = yd.years()
        self.assertGreaterEqual(len(ys), 5)
        d = yd.drift_between(min(ys), max(ys))
        self.assertGreater(abs(d), 0.01)

    def test_convert_year_aware(self):
        recs = models.make_mock_admissions()
        yd = drift.YearDrift.from_records(recs)
        t = trainer.Trainer()
        t.train(recs, epochs=120, verbose=0)
        conv = converter.ScoreConverter(model=t.model)
        y1, y2 = min(yd.years()), max(yd.years())
        v1 = conv.convert("AP: Calc BC 5, Physics 4, Chem 5, GPA 3.9",
                          year=y1, drift=yd)["source"]["value"]
        v2 = conv.convert("AP: Calc BC 5, Physics 4, Chem 5, GPA 3.9",
                          year=y2, drift=yd)["source"]["value"]
        self.assertGreater(abs(v2 - v1), 0.001)

    def test_scale_for_none_is_one(self):
        yd = drift.YearDrift()
        self.assertEqual(yd.scale_for(None), 1.0)


if __name__ == "__main__":
    unittest.main()
