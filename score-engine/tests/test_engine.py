# -*- coding: utf-8 -*-
"""核心单元自测。运行: python -m unittest tests/test_engine.py -v"""
import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from score_engine import registry, models, recognizer, converter, trainer, valley, nn, drift
from score_engine import quality as qmod
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

    def test_recognize_ap_with_sat_not_overridden(self):
        """AP 申请者带 SAT 不应被误判成 SAT 体系。"""
        r = recognizer.recognize("AP 5门全5，GPA 3.9，SAT 1520")
        self.assertEqual(r.system, "AP")
        self.assertIn("sat", r.features)  # SAT 作为附属分保留

    def test_recognize_ap_chinese_subjects(self):
        """AP 中文科目名应能正确识别并提取特征。"""
        r = recognizer.recognize("AP微积分5 AP化学5 AP物理4")
        self.assertEqual(r.system, "AP")
        self.assertEqual(r.features.get("ap_subjects"), 3.0)
        self.assertAlmostEqual(r.features.get("ap_avg", 0), 4.667, places=2)

    def test_recognize_ap_chinese_with_grade_letters(self):
        """AP 中文科目+等级字母（如物理C）不应误判成 A-Level。"""
        r = recognizer.recognize("AP 微积分BC 5 化学5 物理C 4")
        self.assertEqual(r.system, "AP")
        self.assertEqual(r.features.get("ap_subjects"), 3.0)
        self.assertNotEqual(r.system, "AL")

    def test_recognize_sat_only_still_sat(self):
        """纯 SAT 申请者（无主体学科体系）仍应识别为 SAT。"""
        r = recognizer.recognize("SAT 1520")
        self.assertEqual(r.system, "SAT")
        self.assertEqual(r.features.get("sat"), 1520.0)



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
            self.assertIn(r.university_id, real_ids)
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
    def test_find_valley_by_university_id(self):
        """用 university_id 查询低分路径。"""
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
        self.assertEqual(r["university_id"], "mit")


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


class TestLanceDBDualDB(unittest.TestCase):
    """双库数据层：换算库 + 分析库 分表管理（LanceDB 可选，JSON 兜底）。"""
    def setUp(self):
        import tempfile, shutil
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_seed_and_query_dual_db(self):
        import os
        from score_engine import db, university as u, models, drift as dmod
        root = os.path.join(self.tmp, "ldb")
        dbh = db.ScoreDB(root=root, backend="json")
        unis = u.default_universities()
        ranks = u.default_rankings()
        recs = models.make_mock_admissions(universities=unis, rankings=ranks)
        yd = dmod.YearDrift.from_records(recs)
        import scripts.gen_quality_data as gq
        stats = dbh.seed_from_engine(
            universities=unis, rankings=ranks, records=recs, drift=yd,
            profiles=gq.build_profiles(unis),
            faculties=gq.build_faculties(unis),
            outcomes=gq.build_outcomes(unis))
        self.assertEqual(stats["university"], 20)
        self.assertEqual(stats["university_ranking"], 20 * 6)
        self.assertEqual(stats["school_profile"], 20)
        self.assertEqual(stats["school_faculty"], 20)
        self.assertEqual(stats["school_outcome"], 20)
        # 换算库：大学实体与排名分离，可查
        mit_uni = dbh.query_score("university", {"id": "mit"})
        self.assertEqual(len(mit_uni), 1)
        mit_ranks = dbh.query_score("university_ranking", {"university_id": "mit"})
        self.assertEqual(len(mit_ranks), 6)  # 2019-2024
        # 排名逐年变化
        self.assertNotEqual(mit_ranks[0]["rank"], mit_ranks[-1]["rank"])
        # 大学静态档案不含排名字段
        self.assertNotIn("rank", mit_uni[0])
        # 分析库：质量档案可查
        prof = dbh.query_quality("school_profile", {"university_id": "mit"})
        self.assertEqual(len(prof), 1)
        self.assertIn("scale_students", prof[0])
        dbh.close()

    def test_lancedb_fallback_when_unavailable(self):
        # 即使无 lancedb，也应退化到 json 后端且 API 一致
        import os
        from score_engine import db
        root = os.path.join(self.tmp, "ldb2")
        dbh = db.ScoreDB(root=root)  # 自动探测：本环境无 lancedb → json
        dbh.upsert_quality("school_profile", [{"university_id": "mit", "name": "MIT",
                                                "scale_students": 11500}])
        rows = dbh.query_quality("school_profile", {"university_id": "mit"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "MIT")
        dbh.close()


class TestQualityAnalysis(unittest.TestCase):
    """质量鉴定：排名 ≠ 真实水平，识别名不副实 / 被低估。"""
    def _analyzer(self):
        from score_engine import university as u
        import scripts.gen_quality_data as gq
        unis = u.default_universities()
        return qmod.QualityAnalyzer(
            gq.build_profiles(unis), gq.build_faculties(unis),
            gq.build_outcomes(unis),
            [r.to_dict() for r in u.default_rankings()])

    def test_quality_index_range(self):
        qa = self._analyzer()
        for sid in ["mit", "eth", "umich", "toronto"]:
            qi = qa.quality_index(sid)
            self.assertGreaterEqual(qi, 0.0)
            self.assertLessEqual(qi, 1.0)

    def test_mismatch_report_categories(self):
        qa = self._analyzer()
        rep = qa.mismatch_report(year=2024, source="QS")
        verdicts = {r["verdict"] for r in rep}
        # 三种判定都应出现（能识别"名不副实"与"被低估"）
        self.assertIn("名不副实/高排名低质量", verdicts)
        self.assertIn("被低估/高性价比", verdicts)
        self.assertIn("实至名归", verdicts)
        # ETH 因质量明显低于其高排名 → 名不副实
        eth = next(r for r in rep if r["university_id"] == "eth")
        self.assertEqual(eth["verdict"], "名不副实/高排名低质量")
        self.assertIsNotNone(eth["rank"])

    def test_quality_index_available_even_if_some_missing(self):
        # 缺失部分维度不应把质量判为极低
        qa = self._analyzer()
        qi_full = qa.quality_index("mit")
        # 只给部分维度，质量指数仍应在合理范围
        qa2 = qmod.QualityAnalyzer(
            [{"university_id": "mit", "ratio_student_faculty": 9.7}], [], [], [])
        qi_part = qa2.quality_index("mit")
        self.assertGreaterEqual(qi_part, 0.0)
        self.assertLessEqual(qi_part, 1.0)


class TestDataPipeline(unittest.TestCase):
    """声明式数据管道：真实数据按 MANIFEST 自动分类落库 + 表位守护。"""
    def setUp(self):
        import tempfile, shutil
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_manifest_parses_and_describes(self):
        from score_engine.pipeline import ingest
        desc = ingest.describe()
        self.assertIn("univ_static_20", desc)
        self.assertIn("qs_rank_2019_2024", desc)
        self.assertIn("university", desc)
        self.assertIn("university_ranking", desc)

    def test_ingest_lands_real_data_to_correct_tables(self):
        import os
        from score_engine import db
        from score_engine.pipeline import ingest
        root = os.path.join(self.tmp, "db")
        dbh = db.ScoreDB(root=root, backend="json")
        try:
            report = ingest.run(dbh)
            # 20 所大学 + 120 条 QS 排名落到换算库正确表位
            self.assertEqual(dbh.count_score("university"), 20)
            self.assertEqual(dbh.count_score("university_ranking"), 20 * 6)
            # 字段落位正确
            mit = dbh.query_score("university", {"id": "mit"})
            self.assertEqual(len(mit), 1)
            self.assertEqual(mit[0]["country"], "美国")
            self.assertIsInstance(mit[0]["established"], int)
            self.assertIsInstance(mit[0]["is_public"], bool)
            # band 自动分类
            top = dbh.query_score("university_ranking",
                                  {"university_id": "mit", "rank": 1})
            self.assertEqual(top[0]["band"], "top10")
            # 溯源已打上
            self.assertEqual(report["per_source"][0]["provenance"], "公开稳定档案；源=QS/THE公开资料+学校官网国际生学费(采集口径2024)")
        finally:
            dbh.close()

    def test_ingest_guard_rejects_wrong_table(self):
        # 目标表不属于对应库 → 必须报错（防放错库/表）
        import os, json
        from score_engine import db
        from score_engine.pipeline import ingest
        # 构造一个声明错位的 manifest：quality 库却指向 university（score 表）
        mf = os.path.join(self.tmp, "MANIFEST_bad.json")
        with open(os.path.join(os.path.dirname(ingest.__file__), "MANIFEST.json"),
                  encoding="utf-8") as f:
            m = json.load(f)
        m["sources"] = [{"source_id": "bad", "file": "universities/universities.csv",
                         "format": "csv", "target": {"db": "quality", "table": "university"},
                         "field_map": {"id": "id"}, "rules": []}]
        with open(mf, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False)
        root = os.path.join(self.tmp, "db_bad")
        dbh = db.ScoreDB(root=root, backend="json")
        try:
            with self.assertRaises(ValueError):
                ingest.run(dbh, manifest_path=mf)
        finally:
            dbh.close()
