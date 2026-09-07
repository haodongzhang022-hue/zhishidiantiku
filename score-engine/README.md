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
`university_id` 存唯一 ID（如 "mit"），不再用 "QS100" 这种排名桶名伪装成学校。

### ② 缺失信息 ≠ 弱（NaN/mask 机制）
缺失成绩（如未提供 SAT/托福）**不应被模型当"学生弱"**。
- 特征 dict 中缺失字段**不在其中**（None 语义），不填 -1。
- 向量化时缺失维度填 0（对 sigmoid 中性），同时生成 mask 标记。
- MLP 训练时**缺失维度不参与反向传播**（masked backprop），
  模型不会学到"缺失=弱"。
- 非官方/不确定数据可标注 source 标记，不混入高可信训练样本。

### ③ 排名 ≠ 真实水平（质量鉴定）
QS 排名代表"名气"，不代表真实水平——可能"排名高但质量低"。引擎把质量鉴定做成
独立维度（`quality.py`）：从分析库多张表聚合**学校规模 / 师生比 / 学费 / 论文 / 被引 /
就业 / 师资分层(含负面)**，得质量指数 [0,1]，再与排名做同类回归比较：
- **被低估/高性价比**：真实质量远超其排名名气；
- **名不副实/高排名低质量**：名气远超真实水平（用户点名要识别）。

### ④ 双库入库管理（LanceDB 可选）
数据落地为**两套库分表**，减少人工查询：
- **换算库 score_db**：university / university_ranking / admission_threshold / system_calendar
- **分析库 quality_db**：school_profile / school_faculty / school_outcome
- 后端优先 LanceDB；环境无 `lancedb` 时退化为**纯标准库 JSON 表**（API 一致，CI 免装包）。

### ⑤ 声明式数据管道（真实数据入库的复用机制）
不是"每次由人判断这份数据该放哪张表"，而是把**获取规则 + 入库规则**固化成：
- `pipeline/MANIFEST.json` —— **声明文件**：每个数据源声明"原始文件 → 字段映射 →
  目标表位 → 清洗/校验/分类规则 → 溯源(source/年份)"，作为入库唯一事实来源；
- `pipeline/rules.py` —— **规则引擎**：清洗/去重/类型规整/自动分类规则，注册后即可被声明引用；
- `cli ingest` —— **复用命令**：读声明 + 原始数据 → 自动分类落库 → 质检报告。

数据落到**正确库/表位**由声明文件约束、代码不猜；目标表不属于对应库会直接报错
（守护"别放错库/表"）。补充数据 = `data_sources/` 放文件 + `MANIFEST.json` 登记一条，
即可持续复用、越补越准。详见 [`data_sources/README.md`](data_sources/README.md)。

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

# 4) 找某所真实大学的低分路径（用 university_id 或全名）
python -m score_engine.cli find-valley --school "mit"
python -m score_engine.cli find-valley --school "University of Toronto"

# 5) 年度漂移识别
python -m score_engine.cli drift --data data/sample_admissions.csv "AP: Calc BC 5, Physics 4, Chem 5, GPA 3.9"

# 6) 查看大学档案与排名
python -m score_engine.cli universities --year 2024

# 7) 功能达成度核验
python3 tests/verify_features.py

# 8) LanceDB 双库灌库 / 列表 / 查询（可选 --backend json 走免装包兜底）
python -m score_engine.cli db --backend json seed
python -m score_engine.cli db --backend json tables
python -m score_engine.cli db --backend json query --db score --table university_ranking --university_id mit

# 9) 质量鉴定：名不副实 / 被低估 报告（排名 ≠ 真实水平）
python -m score_engine.cli quality --year 2024
python -m score_engine.cli quality --school eth

# 10) 声明式数据管道：把 data_sources 真实数据按 MANIFEST 自动分类落库
python -m score_engine.cli ingest --backend json --list     # 查看声明一览
python -m score_engine.cli ingest --backend json            # 落库到默认 data_lancedb
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
| `score_engine/db.py` | **LanceDB 双库**（score 换算库 + quality 分析库，可选后端+JSON兜底） |
| `score_engine/quality.py` | **质量鉴定**（规模/师资含负面/论文/就业 → 名不副实报告） |
| `score_engine/cli.py` | 命令行入口 |
| `score_engine/demo.py` | 端到端演示 |
| `scripts/gen_quality_data.py` | 质量示例数据生成（P2 由真实数据替换） |
| `data/sample_admissions.csv` | 示例历年录取样本（真实大学） |
| `pipeline/` | **声明式数据管道**：`MANIFEST.json`(声明) + `rules.py`(规则) + `ingest.py`(引擎) |
| `data_sources/` | **真实数据源目录**：大学档案 / QS 排名等原始数据 + 管理说明 |
| `models/` | 训练产物输出目录（gitignore） |

## 概念说明
- **统一录取价值（admission value）**：把不同体系的学生分数换算到 0~1 的"录取强度"标尺。
- **门槛洼地（valley）**：同一所大学的多条体系路径中，换算成本最低/最容易达成的路径。
- **年度漂移（drift）**：录取门槛随年份浮动，`YearDrift` 从历年样本估计难度水位。
- **mask 缺失机制**：缺失特征不参与训练，避免"缺失=弱"的误判。
- **双库**：score_db（大学/排名/门槛/年度）+ quality_db（档案/师资/成果），LanceDB 或 JSON 兜底。
- **质量指数**：排名 ≠ 真实水平；离群报告识别"名不副实"与"被低估"。
- **功能核验**：`tests/verify_features.py` 逐项验证全部核心功能。
- **声明式数据管道**：`MANIFEST.json` 声明数据源→目标表/字段映射/规则/溯源，`cli ingest` 复用落库，`rules.py` 规则可扩展，持续补充真实数据。
