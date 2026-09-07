# 跨体系分数转化引擎 · Cross-System Score Conversion Engine

> 面向 **QS Top 500 / 1000 高校录取门槛**的跨体系（AP / A-Level / IB / 国内高考 等）分数换算、深度学习训练与"低分路径"寻优引擎。

## 背景问题

同一个学校（同一录取价值）往往存在多条**不同体系的录取口径**：
- AP 体系要求：AP 若干门 4~5 分 + GPA + SAT/托福
- A-Level 体系要求：A\*/A 若干门
- IB 体系要求：总分 34~42 等
- 国内高考体系要求：某省一段线以上 / 位次区间

各体系**分值不可直接精确换算**（本质模糊），且逐年浮动。本引擎：
1. **识别**分数属于哪套体系（score recognition）。
2. **模糊换算**：基于**历年历史录取数据**跨体系对齐价值，而非拍脑袋换算（data-driven fuzzy conversion）。
3. **深度学习训练与后训练**：神经网络建模多体系→"统一录取价值"的映射，支持逐年增量后训练与效果跟踪。
4. **低分路径寻优**：对同一学校/同一价值，找出**相对录取门槛最低**（门槛洼地）的那条体系路径。

## 快速开始

```bash
# 依赖：Python3.8+，无第三方硬依赖（纯标准库实现，numpy 可选加速）
cd score-engine

# 1) 用内置示例数据做一次端到端演示（识别+换算+训练+洼地寻优）
python -m score_engine.demo

# 2) 命令行：训练并保存模型
python -m score_engine.cli train --data data/sample_admissions.csv --epochs 200

# 3) 命令行：换算一条分数
python -m score_engine.cli convert --system AP --score "AP: Calc BC 5, Physics 4, Chem 5" --model models/current.json

# 4) 命令行：查找某学校的最"低分路径"
python -m score_engine.cli find-valley --school "QS100" --model models/current.json

# 5) 年度漂移识别（核心）：同一分数在不同年份换算会变
python -m score_engine.cli drift --data data/sample_admissions.csv "AP: Calc BC 5, Physics 4, Chem 5, GPA 3.9"
python -m score_engine.cli convert "AP: Calc BC 5, Physics 4, Chem 5, GPA 3.9" --year 2024 --data data/sample_admissions.csv

# 6) 功能达成度核验（issue #8 追评：写脚本测试）
python3 tests/verify_features.py
```

## 目录结构
| 路径 | 说明 |
|------|------|
| `score_engine/` | 核心包 |
| `score_engine/registry.py` | 体系白名单 / 分数规范识别（AP/A-Level/IB/国内 等） |
| `score_engine/models.py` | 分数结构体 + 历史录取样本数据模型 |
| `score_engine/recognizer.py` | 分数体系**识别**（pattern + heuristic） |
| `score_engine/converter.py` | **模糊换算**引擎（历史对齐 + 规则 + 神经网络打分） |
| `score_engine/nn.py` | 轻量**神经网络**（纯 Python + 可选 numpy）回归/训练 |
| `score_engine/trainer.py` | **训练 / 后训练 / 效果跟踪**（逐年增量 + 元数据） |
| `score_engine/drift.py` | **年度漂移识别**：从历年样本估计难度水位，让换算随年份变化 |
| `score_engine/valley.py` | **门槛洼地寻优**（同一价值下找相对低分路径） |
| `score_engine/cli.py` | 命令行入口 |
| `score_engine/demo.py` | 端到端演示 |
| `data/sample_admissions.csv` | 示例历年录取样本 |
| `models/` | 训练产物输出目录（gitignore） |

## 概念说明
- **统一录取价值（admission value）**：把不同体系的学生分数换算到一个 0~1 的"录取强度"标尺上，作为可比锚点。每个学校一个门槛值。
- **门槛洼地（valley）**：同一学校的多条体系路径中，**换算成本最低 / 相对最容易达成**的那条。
- **年度漂移（drift）**：门槛不是固定值，会随年份浮动。`YearDrift` 从历年样本估计难度水位，`convert(..., year=Y)` 据此输出当年口径的换算。
- **功能核验**：`tests/verify_features.py` 逐项验证识别/精度/年度漂移/效果跟踪；`docs/score-engine-extend.md` 给出全球大学 + 学校质量 + LanceDB 多表扩展路线。
