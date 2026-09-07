# -*- coding: utf-8 -*-
"""把内置 QS 历年排名落成"外部原始数据文件" data_sources/rankings/qs_rankings.csv。

数据本身来自内置公开 QS 历史排名（2019-2024），此脚本仅负责把其导出为
管道可消费的原始 CSV。真实运维中该文件应由 QS 官方/公开年鉴更新替换，
管道则通过 MANIFEST.json 读取并自动落库——代码不关心排名怎么来的。
"""
import sys, os, csv
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from score_engine import university as univ_mod

def main():
    ranks = univ_mod.default_rankings()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "data_sources", "rankings", "qs_rankings.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["university_id", "source", "year", "rank"])
        for r in ranks:
            w.writerow([r.university_id, r.source, r.year, r.rank])
    print(f"导出 {len(ranks)} 条 QS 排名 → {os.path.relpath(out)}")

if __name__ == "__main__":
    main()
