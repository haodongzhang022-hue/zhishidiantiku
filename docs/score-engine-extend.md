# 分数换算引擎 · 扩展架构与数据建模（Roadmap）

> 本页承接 [score-engine/README.md](../score-engine/README.md) 与 issue #8 追评中的扩展诉求。

## 已完成（最新状态）

### ✅ 声明式数据管道（真实数据入库的复用机制 · issue #8 最新诉求）
把"如何接入真实数据"从**人肉单次驱动**升级为**声明 + 复用命令**：
- `score_engine/pipeline/MANIFEST.json` —— **声明文件**：每个数据源声明
  「原始文件 → 字段映射 → 目标表位 → 清洗/校验/分类规则 → 溯源」。
- `score_engine/pipeline/rules.py` —— **规则引擎**：清洗/去重/类型规整/自动分类，
  规则登记后即可被声明引用，**加新数据源不改管道主流程**。
- `score_engine/pipeline/ingest.py` + `cli ingest` —— 读声明 + `data_sources/` 原始数据
  自动分类落库，产出质检报告。
- 落库位置由声明约束，目标表不属于对应库会**直接报错**（防放错库/表）。
- `data_sources/` 为真实数据源目录（大学档案 / QS 排名等 + 管理说明），
  每类数据标注 `source` 出处与采集年份，**不把示意数据冒充真实**。

### ✅ 真实数据种子接入（首批）
- `universities.csv`（20 所真实大学公开稳定档案）+ `qs_rankings.csv`
  （QS 2019-2024 官方发布历史）通过 `cli ingest` 落到换算库
  `university` / `university_ranking` 正确表位，`rank→band` 自动分类。

### ✅ 大学与排名分离（核心改进）
- 新增 `score_engine/university.py`：`University`（静态档案）+ `UniversityRanking`（动态排名）。
- 训练样本不再使用 "QS10~QS1000" 排名桶名伪装学校，而是引用真实大学。
- 内置 20 所 QS 世界大学真实档案，含 2019-2024 历年 QS 排名。
- 大学的静态属性（名称/国家/学费/建校年份等）不随排名变化。

### ✅ 缺失值 mask 机制（核心改进）
- 特征 dict 中缺失字段不在其中（None 语义），向量化时填 0.0（sigmoid 中性）。
- 同时生成 mask 向量标记缺失，MLP 训练时**缺失维度不参与反向传播**。
- 不再使用 -1 占位缺失（-1 在 0~1 归一化空间中是误导性信号，会被模型学成"缺失=极弱"）。
- verify_features 确认：缺失 SAT / GPA 不压低学生价值。

### ✅ LanceDB 双库落地（P0 → 已完成）
- 新增 `score_engine/db.py`：`ScoreDB` 统一门面，拆成
  **换算库 score_db**（university / university_ranking / admission_threshold /
  system_calendar）与 **分析库 quality_db**（school_profile / school_faculty /
  school_outcome）两套库、七张表分表管理，减少人工查询。
- 后端优先 **LanceDB**；环境无 `lancedb` 时退化为**纯标准库 JSON 表存储**
  （同一套 schema 与查询 API），CI 免装第三方包也全绿。
- `db seed / tables / query` 子命令打通灌库、列表、按表检索。
- `verify_features` [9]：双库建好、可按 id 查大学/逐年排名/质量档案 7 项断言全过。

### ✅ 质量维度：排名 ≠ 真实水平（P1 → 已完成）
- 新增 `score_engine/quality.py`：从分析库三张表聚合
  **学校规模/师生比/学费/论文/被引/就业 + 师资分层(含负面) → 质量指数 [0,1]**。
- 用回归法对全库学校做**同类公平比较**（每所跟它排名的正常水平比），
  识别离群：**名不副实/高排名低质量** 与 **被低估/高性价比（价值洼地）**。
- `quality` 子命令：全库名不副实报告 / 单校质量档案。
- `verify_features` [10]：ETH(#7)被识别为名不副实等 7 项断言全过。

### 双库结构

```
┌─────────────── 分析库（quality / 分析维度） ───────────────┐
│ table: school_profile       学校档案（规模/师生/学费/论文/就业…）│
│ table: school_faculty       师资档案（分层含负面）          │
│ table: school_outcome       成果/声誉（论文/就业/认证）     │
└────────────────────────────────────────────────────────────┘
┌─────────────── 换算库（score / 录取门槛维度）───────────────┐
│ table: admission_threshold  按 school × system × year      │
│ table: system_calendar      各体系年度漂移系数              │
└────────────────────────────────────────────────────────────┘
```

### 表结构（已在 db.py 落地）

**university（大学档案 · 静态实体）**
| 字段 | 说明 |
|------|------|
| id | 全局唯一（如 MIT / stanford） |
| name_en / name_zh | 中英文名 |
| country / city | 国家/城市 |
| established | 建校年份 |
| is_public | 公立/私立 |
| tuition_intl_usd | 国际生年学费 USD |

**university_ranking（排名 · 动态）**
| 字段 | 说明 |
|------|------|
| university_id | 关联大学 |
| source | QS/THE/USNews/ARWU |
| year | 年份 |
| rank | 当年排名 |

**school_profile（质量鉴定，含负面）**
| 字段 | 说明 |
|------|------|
| school_id | 大学 |
| scale_students / scale_faculty | 在校生/师资 |
| ratio_student_faculty | 师生比 |
| tuition_intl | 学费 |
| papers_yearly / citations | 论文/被引 |
| employment_rate | 就业率 |
| source / year | 出处/采集年 |

**school_faculty（师资分层含负面）**
| 字段 | 说明 |
|------|------|
| school_id | 大学 |
| tier_high / tier_mid / tier_low | 师资分层占比 |
| star_count | 顶尖人数 |
| negative_ratio | 欠佳指标 |
| note | 负面说明 |

**admission_threshold（录取门槛 · 换算库核心）**
| 字段 | 说明 |
|------|------|
| school_id | 大学 |
| year | 年份 |
| system | AP/AL/IB/GAOKAO… |
| raw_score | 当年录取门槛画像 |
| unified_value | 统一价值 |

## 仍在路线图

### P0：全球大学扩展
- 将内置 20 所大学扩展到 QS1000 内的数百所，补充各校历年真实 QS/THE/USNews 排名。
- 为每所大学接入真实规模/学费/论文等静态字段。

### P2：真实数据训练
- 用真实历年录取 CSV 重训 NN，替代当前启发式 + 合成校准。

## 与代码的关系
- `score_engine/university.py` → 大学/排名 分离数据层
- `score_engine/drift.py` → 对应 `system_calendar`
- `score_engine/valley.py` → 对应"门槛洼地"查询
- `score_engine/models.py` / `nn.py` → masked training 支撑
- `score_engine/db.py`、`quality.py` **已完成**；剩余 P0 全球大学扩展 / P2 真实数据训练
