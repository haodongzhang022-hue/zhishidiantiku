# -*- coding: utf-8 -*-
"""命令行入口。用法见 README。
"""
from __future__ import annotations
import argparse, sys, os, json, csv

from . import models as _models  # 供 _print_convert 引用

# 让包可直接运行：python -m score_engine.cli
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _load_csv(path: str):
    """从 CSV 加载 AdmissionRecord。

    期望列：school, school_id, year, system, [admitted|school_value],
            features(json)。school_id 可选（缺失则用 school 兜底）。
    """
    from . import registry
    recs = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            features_raw = row.get("features", "{}")
            feat = json.loads(features_raw) if features_raw else {}
            rec = registry.AdmissionRecord(
                school=row.get("school", ""),
                school_id=row.get("school_id", row.get("school", "")),
                year=int(row.get("year", "0")),
                system=registry.normalize_system(row.get("system", "")),
                admitted=row.get("admitted", "1").lower() in ("1", "true", "yes", "admitted"),
                features=feat,
                source=row.get("source", ""),
            )
            if "school_value" in row and row["school_value"]:
                rec.school_value = float(row["school_value"])
            recs.append(rec)
    return recs


def main(argv=None):
    p = argparse.ArgumentParser(prog="score-engine",
                                description="跨体系分数换算引擎")
    sub = p.add_subparsers(dest="cmd", required=True)

    # train
    sp = sub.add_parser("train", help="训练模型")
    sp.add_argument("--data", default=os.path.join("data", "sample_admissions.csv"))
    sp.add_argument("--epochs", type=int, default=250)
    sp.add_argument("--lr", type=float, default=0.3)
    sp.add_argument("--out", default="models/current.json")

    # retrain
    sp = sub.add_parser("retrain", help="增量后训练")
    sp.add_argument("--data")
    sp.add_argument("--epochs", type=int, default=80)
    sp.add_argument("--out", default="models/current.json")

    # convert
    sp = sub.add_parser("convert", help="换算一条分数")
    sp.add_argument("--system", default="")
    sp.add_argument("score")
    sp.add_argument("--model", default="models/current.json")
    sp.add_argument("--year", type=int, help="可选：申请年份，启用年度漂移校准")
    sp.add_argument("--data", default=os.path.join("data", "sample_admissions.csv"),
                    help="用于估计年度漂移的历史样本")

    # valley
    sp = sub.add_parser("find-valley", help="查某学校低分路径")
    sp.add_argument("--school", help="大学名或 school_id，如 MIT/mit")
    sp.add_argument("--data", default=os.path.join("data", "sample_admissions.csv"))
    sp.add_argument("--year", type=int)
    sp.add_argument("--model", default="models/current.json")

    # drift
    sp = sub.add_parser("drift", help="查看某年度门槛漂移 / 或换算随年份变化")
    sp.add_argument("--data", default=os.path.join("data", "sample_admissions.csv"))
    sp.add_argument("score", nargs="?", default="")
    sp.add_argument("--system", default="")
    sp.add_argument("--years", default="2019,2020,2021,2022,2023,2024")
    sp.add_argument("--model", default="models/current.json")

    # compare
    sp = sub.add_parser("compare", help="对比给定价值的各体系成本")
    sp.add_argument("--value", type=float, default=0.6)
    sp.add_argument("--model", default="models/current.json")

    # univs — 列出大学/排名
    sp = sub.add_parser("universities", help="查看大学档案与历年排名")
    sp.add_argument("--year", type=int, default=2024, help="查看某年排名")
    sp.add_argument("--source", default="QS")

    args = p.parse_args(argv)

    if args.cmd == "train":
        from . import registry, models, trainer as trn
        recs = _load_csv(args.data)
        t = trn.Trainer(model_path=args.out)
        t.train(recs, epochs=args.epochs, lr=args.lr)
        t.save(args.out)
        print(f"训练样本 {len(recs)} 条 → {args.out}")
        for s in t.history[-1:]:
            print("  快照:", json.dumps(s, ensure_ascii=False))

    elif args.cmd == "retrain":
        from . import trainer as trn
        recs = _load_csv(args.data)
        t = trn.Trainer(model_path=args.out)
        if os.path.exists(args.out):
            t.load(args.out)
        t.retrain(recs, epochs=args.epochs, lr=0.05)
        t.save(args.out)

    elif args.cmd == "convert":
        from . import converter
        from . import nn, drift as drift_mod
        conv = converter.ScoreConverter()
        if os.path.exists(args.model):
            conv.model = nn.MLP.load(args.model)
        yd = None
        if args.year is not None:
            yd = drift_mod.YearDrift.from_records(_load_csv(args.data))
        res = conv.convert(args.score, system_hint=args.system,
                           year=args.year, drift=yd)
        _print_convert(res)

    elif args.cmd == "drift":
        from . import converter, nn, drift as drift_mod
        from . import registry
        recs = _load_csv(args.data)
        yd = drift_mod.YearDrift.from_records(recs)
        print("年度门槛水位指数（difficulty）趋势：")
        for row in yd.trend():
            print(f"  year={row['year']}  difficulty={row['difficulty_index']:.3f} "
                  f"scale={row['scale']:.3f}")
        if args.score:
            conv = converter.ScoreConverter()
            if os.path.exists(args.model):
                conv.model = nn.MLP.load(args.model)
            years = [int(y) for y in args.years.split(",") if y.strip()]
            print(f"\n分数『{args.score}』在不同年份的换算（GAOKAO 口径）：")
            base = None
            for y in years:
                res = conv.convert(args.score, system_hint=args.system,
                                   year=y, drift=yd)
                v = res["source"]["value"]
                gk = res["conversions"].get("GAOKAO", {}).get("approx_score", None)
                mark = "  <-- 基准"
                if base is not None:
                    mark = "  <-- 更易" if v < base else ("  <-- 更难" if v > base else "  <-- 持平")
                base = v if base is None else base
                print(f"  year={y}: 统一价值={v:.3f}  ≈高考{gk}  {mark}")

    elif args.cmd == "find-valley":
        from . import nn, valley
        recs = _load_csv(args.data)
        m = nn.MLP.load(args.model) if os.path.exists(args.model) else None
        vf = valley.ValleyFinder(model=m)
        r = vf.find_valley(args.school, recs, args.year)
        _print_valley(r)

    elif args.cmd == "compare":
        from . import valley
        vf = valley.ValleyFinder()
        rows = vf.compare_systems(args.value)
        print(f"统一价值 {args.value} 下，各体系竞争成本（升序）：")
        for i, r in enumerate(rows, 1):
            print(f"  {i}. {r['system']:<8} 成本={r['competition_cost']:.3f} "
                  f"等效={r['equivalent']['kind']}")

    elif args.cmd == "universities":
        from . import university as univ_mod
        unis = univ_mod.default_universities()
        ranks = univ_mod.default_rankings()
        print(f"\n大学档案（{len(unis)} 所）：")
        print(f"{'ID':<12} {'英文名':<50} {'国家':<10} {'2024 QS':<8}")
        print("-" * 88)
        for u in sorted(unis, key=lambda x: x.id):
            rk = next((r.rank for r in ranks
                       if r.university_id == u.id and r.year == args.year
                       and r.source == args.source), "-")
            print(f"{u.id:<12} {u.name_en:<50} {u.country:<10} {rk}")
        print(f"\n→ 大学实体（静态）与排名（按年份/来源动态）分离。")
        print(f"→ 查历年排名趋势用 cnb pulls / UniversityRanking 数据结构。")
    return 0


def _print_convert(res):
    src = res["source"]
    print(f"\n识别体系: {src['system']}  confidence={src['confidence']:.2f}")
    print(f"统一录取价值: {src['value']:.3f}")
    if src["features"]:
        print(f"特征: {json.dumps(src['features'], ensure_ascii=False)}")
        # 显示缺失字段
        mask = src.get("mask", [])
        missing = [k for k, m in zip(_models.FEATURE_KEYS, mask) if m == 0]
        if missing:
            print(f"缺失(不判弱): {', '.join(missing)}")
    print("\n各体系等效换算（模糊区间）：")
    for sys_, eq in res["conversions"].items():
        print(f"  [{sys_}] {eq['kind']}")


def _print_valley(r):
    if "error" in r:
        print(r["error"])
        return
    print(f"\n学校: {r['school']}  (id={r['school_id']})  year={r['year']}  "
          f"统一门槛价值≈{r['estimated_threshold_value']}")
    print(f"样本数: {r['n_admitted']}")
    print("\n各体系路径（成本升序，最省力在前 = 洼地）：")
    for i, row in enumerate(r["systems_ranked"], 1):
        mark = "  << 洼地" if i == 1 else ""
        print(f"  {i}. {row['system']:<8} 成本={row['competition_cost']:.3f} "
              f"→ {row['equivalent']['kind']}{mark}")
    print(f"\n推荐路径: {r['recommended_valley']['system']}")
    print(f"理由: {r['reason']}")


if __name__ == "__main__":
    sys.exit(main())
