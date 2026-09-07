# 跨体系分数转化引擎 · Cross-System Score Conversion Engine

> 面向 **QS 全球大学录取门槛**的跨体系（AP / A-Level / IB / 国内高考 等）分数换算、
> 深度学习训练与"低分路径"寻优引擎。

## 设计原则（两大核心）

### ① 大学与排名分离
QS 排名是**动态属性**（每年变化），大学本身是**静态实体**（名称/国家/学费/建校…）。
录取门槛跟随大学本身，与排名非同步。

引擎数据模型分两层：
- `University` —— 大学的固有属性（ID/名称/国家/城市/学费等），稳定不随排名变化。
- `UniversityRanking` —— (university, source, year) → rank，动态按年记录。

训练样本的 `school` 存**真实大学名**（如 "Massachusetts Institute of Technology"），
`school_id` 存唯一 ID（如 "mit"），不再用 "QS100" 这种排名桶名伪装成学校。

### ② 缺失信息 ≠ 弱（NaN/mask 机制）
缺失成绩（如未提供 SAT/托福）**不应被模型当"学生弱"**。
- 特征 dict 中缺失字段**不在其中**（None 语义），不填 -1。
- 向量化时缺失维度填 0（对 sigmoid 中性），同时生成 mask 标记。
- MLP 训练时**缺失维度不参与反向传播**（masked backprop），
  模型不会学到"缺失=弱"。
- 非官方/不确定数据可标注 source 标记，不混入高可信训练样本。

## 快速开始

```bash
# 依赖：Python3.8+，无第三方硬依赖（纯标准库实现）
cd score-engine

# 1) 端到端演示
python -m score_engine.demo

# 2) 训练并保存模型
python -m score_engine.cli train --data data/sample_admissions.csv --epochs 200

# 3) 换算一条分数
python -m score_engine.cli convert "AP: Calc BC 5, Physics 4, Chem 5, GPA 3.9"

# 4) 找某所真实大学的低分路径（用 school_id 或全名）
python -m score_engine.cli find-valley --school "mit"
python -m score_engine.cli find-valley --school "University of Toronto"

# 5) 年度漂移识别
python -m score_engine.cli drift --data data/sample_admissions.csv "AP: Calc BC 5, Physics 4, Chem 5, GPA 3.9"

# 6) 查看大学档案与排名
python -m score_engine.cli universities --year 2024

# 7) 功能达成度核验
python3 tests/verify_features.py
```

## 目录结构
| 路径 | 说明 |
|------|------|
| `score_engine/` | 核心包 |
| `score_engine/registry.py` | 体系白名单 / 录取记录模型 |
| `score_engine/university.py` | **大学实体 + 排名分离**（核心架构） |
| `score_engine/models.py` | 分数结构体 + 特征向量化（mask 缺失） |
| `score_engine/recognizer.py` | 分数体系**识别**（pattern + heuristic） |
| `score_engine/converter.py` | **模糊换算**引擎 |
| `score_engine/nn.py` | 轻量**神经网络**（含 masked backprop） |
| `score_engine/trainer.py` | **训练 / 后训练 / 效果跟踪** |
| `score_engine/drift.py` | **年度漂移识别** |
| `score_engine/valley.py` | **门槛洼地寻优** |
| `score_engine/cli.py` | 命令行入口 |
| `score_engine/demo.py` | 端到端演示 |
| `data/sample_admissions.csv` | 示例历年录取样本（真实大学） |
| `models/` | 训练产物输出目录（gitignore） |

## 概念说明
- **统一录取价值（admission value）**：把不同体系的学生分数换算到 0~1 的"录取强度"标尺。
- **门槛洼地（valley）**：同一所大学的多条体系路径中，换算成本最低/最容易达成的路径。
- **年度漂移（drift）**：录取门槛随年份浮动，`YearDrift` 从历年样本估计难度水位。
- **mask 缺失机制**：缺失特征不参与训练，避免"缺失=弱"的误判。
- **功能核验**：`tests/verify_features.py` 逐项验证全部核心功能。
