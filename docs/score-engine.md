# 分数换算引擎使用文档

> 跨体系（AP/A-Level/IB/国内高考等）录取分数换算、深度学习训练与"低分路径"寻优。
> 完整说明见 [score-engine/README.md](../score-engine/README.md)。

## 设计理念
1. **识别（Recognize）**：输入学生成绩文本，自动判断体系并提取关键特征。
2. **统一价值（Unified Value）**：用神经网络把多体系画像回归到一个 0~1 的"可达学校档位"，作为可比锚点。
3. **模糊换算（Convert）**：给定统一价值反推各体系应达到的分数区间（非精确，供策略参考）。
4. **训练/后训练（Train/Retrain）**：基于历年录取数据训练，逐年新增数据可做增量 warm-start 后训练。
5. **门槛洼地（Valley）**：同一学校多条体系路径中，找相对录取门槛最低（最省力）的一条，为申请者提供策略性切入点。

## 快速使用（详见 score-engine/README.md）
```bash
cd score-engine
python -m score_engine.demo                                  # 端到端演示
python -m score_engine.cli train --data data/sample_admissions.csv --epochs 150
python -m score_engine.cli convert "高考 652 分，省位次 4200"
python -m score_engine.cli find-valley --school "QS100" --data data/sample_admissions.csv
```

## 与题库体系维度的关系
题库在 `questions/CATEGORIES.md` 已定义 **AP/AL/IB/国内** 体系白名单（对应 system 字段）。
本引擎与该维度**同源对齐**：识别时复用这些体系代码，将"同一知识点在不同体系考察口径不同"
的自然延伸拓展到**录取门槛口径的跨体系换算**。
