# -*- coding: utf-8 -*-
"""核心单元自测。运行: python -m unittest tests/test_engine.py -v"""
import sys, os, unittest
# 加入 score-engine 目录（score_engine 包的上级）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from score_engine import registry, models, recognizer, converter, trainer, valley, nn, drift


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
        vec = models.features_to_vector({})
        self.assertEqual(len(vec), models.FEATURE_DIM)

    def test_mock_records_have_value(self):
        recs = models.make_mock_admissions()
        self.assertGreater(len(recs), 0)
        for r in recs[:5]:
            self.assertTrue(0 <= getattr(r, "school_value", -1) <= 1)


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
    def test_find_valley(self):
        recs = models.make_mock_admissions()
        vf = valley.ValleyFinder()
        r = vf.find_valley("QS100", recs)
        self.assertIn("recommended_valley", r)
        rows = r["systems_ranked"]
        costs = [x["competition_cost"] for x in rows]
        self.assertEqual(costs, sorted(costs))  # 已升序


class TestConversion(unittest.TestCase):
    def test_convert(self):
        conv = converter.ScoreConverter()
        res = conv.convert("A-Level: 数学 A*, 物理 A, 雅思 7.0")
        self.assertIn("GAOKAO", res["conversions"])


if __name__ == "__main__":
    unittest.main()


class TestYearDrift(unittest.TestCase):
    """年度漂移识别：换算应随年份变化（核心需求）。"""
    def test_drift_detects_year_change(self):
        recs = models.make_mock_admissions()
        yd = drift.YearDrift.from_records(recs)
        ys = yd.years()
        self.assertGreaterEqual(len(ys), 5)
        # 数据 2019 较易 → 2024 更难，difficulty 应递增
        d = yd.drift_between(min(ys), max(ys))
        self.assertGreater(d, 0.03)

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
        # 更难点应更高价值（门槛更高）
        self.assertGreater(v2, v1)

    def test_scale_for_none_is_one(self):
        yd = drift.YearDrift()
        self.assertEqual(yd.scale_for(None), 1.0)
