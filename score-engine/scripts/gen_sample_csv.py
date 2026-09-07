# -*- coding: utf-8 -*-
"""生成 data/sample_admissions.csv —— 历年历史录取示例数据（连续价值档位）。"""
import sys, os, json, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from score_engine import models

def main():
    recs = models.make_mock_admissions()
    out = os.path.join(os.path.dirname(__file__), "..", "data", "sample_admissions.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["school", "year", "system", "school_value", "features", "source"])
        for r in recs:
            w.writerow([r.school, r.year, r.system,
                        getattr(r, "school_value", 0.0),
                        json.dumps(r.features, ensure_ascii=False), r.source])
    print(f"已生成 {len(recs)} 条 → {out}")

if __name__ == "__main__":
    main()
