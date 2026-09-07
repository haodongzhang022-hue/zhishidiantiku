# 分数换算引擎使用文档

> 跨体系（AP/A-Level/IB/国内高考等）录取分数换算、深度学习训练与"低分路径"寻优。
> 完整说明见 [score-engine/README.md](../score-engine/README.md)。

## 设计理念
1. **识别（Recognize）**：输入学生成绩文本，自动判断体系并提取关键特征。
2. **统一价值（Unified Value）**：用神经网络把多体系画像回归到一个 0~1 的"可达学校档位"，作为可比锚点。
3. **模糊换算（Convert）**：给定统一价值反推各体系应达到的分数区间（非精确，供策略参考）。
4. **训练/后训练（Train/Retrain）**：基于历年录取数据训练，逐年新增数据可做增量 warm-start 后训练。
5. **门槛洼地（Valley）**：同一所真实大学的多条体系路径中，找相对录取门槛最低（最省力）的一条。
6. **大学与排名分离**：大学档案是静态实体，QS 排名是动态属性（按年份单独记录）。
7. **mask 缺失机制**：缺失信息（如未提供 SAT）不被当作"弱"——缺失维度不参与训练。
8. **LanceDB 双库**：换算库 score_db（大学/排名/门槛/年度）+ 分析库 quality_db（档案/师资含负面/成果）分表管理；无 lancedb 环境自动退化 JSON 存储。
9. **质量鉴定**：排名 ≠ 真实水平。从分析库聚合规模/师生/论文/就业/师资分层得质量指数，识别"名不副实/高排名低质量"与"被低估/高性价比"价值洼地。

## 快速使用（详见 score-engine/README.md）
```bash
cd score-engine
python -m score_engine.demo                                  # 端到端演示
python -m score_engine.cli train --data data/sample_admissions.csv --epochs 150
python -m score_engine.cli convert "高考 652 分，省位次 4200"
python -m score_engine.cli find-valley --school "mit"        # 用 school_id 查 MIT
python -m score_engine.cli find-valley --school "University of Toronto"
python -m score_engine.cli universities --year 2024          # 查看大学档案与排名
python -m score_engine.cli drift --data data/sample_admissions.csv "高考 652 分"  # 年度漂移
python -m score_engine.cli convert "高考 652 分" --year 2024 --data data/sample_admissions.csv
python -m score_engine.cli db --backend json seed        # LanceDB 双库灌库（json 兜底免装包）
python -m score_engine.cli quality --year 2024          # 名不副实/被低估 质量报告
python -m score_engine.cli quality --school eth          # 单校质量档案
python3 ../score-engine/tests/verify_features.py      # 功能达成度核验
```

## 与题库体系维度的关系
题库在 `questions/CATEGORIES.md` 已定义 **AP/AL/IB/国内** 体系白名单（对应 system 字段）。
本引擎与该维度**同源对齐**：识别时复用这些体系代码，将"同一知识点在不同体系考察口径不同"
的自然延伸拓展到**录取门槛口径的跨体系换算**。
