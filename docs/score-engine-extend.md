# 分数换算引擎 · 扩展架构与数据建模（Roadmap）

> 本页承接 [score-engine/README.md](../score-engine/README.md) 与 issue #8 追评中的扩展诉求。

## 已完成（最新状态）

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

## 仍在路线图

### P0：全球大学扩展
- 将内置 20 所大学扩展到 QS1000 内的数百所，补充各校历年真实 QS/THE/USNews 排名。
- 为每所大学接入真实规模/学费/论文等静态字段。

### P0：接入 LanceDB 双库多表
把数据拆成两套库：

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

### 表结构草案

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

### P1：质量维度
- 新增 `quality.py`：从 school_profile/faculty/outcome 计算"质量指数"。
- 做"排名 vs 质量"偏差报告（排名高但质量低 = 名不副实）。

### P2：真实数据训练
- 用真实历年录取 CSV 重训 NN，替代当前启发式 + 合成校准。

## 与代码的关系
- `score_engine/university.py` → 大学/排名 分离数据层
- `score_engine/drift.py` → 对应 `system_calendar`
- `score_engine/valley.py` → 对应"门槛洼地"查询
- `score_engine/models.py` / `nn.py` → masked training 支撑
- 新增 `quality.py`、`db_lancedb.py` 建议放后续 PR
