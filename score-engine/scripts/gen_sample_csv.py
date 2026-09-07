# -*- coding: utf-8 -*-
"""生成示例历年录取 CSV（真实大学 + university_id + 逐年排名 + 随机缺失）。"""
import sys, os, json, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from score_engine import models

def main():
    recs = models.make_mock_admissions()
    out = os.path.join(os.path.dirname(__file__), "..", "data", "sample_admissions.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["school", "university_id", "year", "system",
                         "school_value", "features", "source"])
        for r in recs:
            feat_json = json.dumps(r.features, ensure_ascii=False)
            writer.writerow([r.school, r.university_id, r.year, r.system,
                             r.school_value, feat_json, r.source])
    print(f"生成 {len(recs)} 条 → {out}")

if __name__ == "__main__":
    main()
