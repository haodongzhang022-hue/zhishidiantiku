# 分数换算引擎 · 扩展架构与数据建模（Roadmap）

> 本页承接 [score-engine/README.md](../score-engine/README.md) 与 issue #8 追评中的扩展诉求，
> 把 PR#9 已交付的"跨体系分数换算引擎"向三个方向扩展：
> **① 全球大学泛化**、**② 学校真实质量鉴定**、**③ LanceDB 数据库化多表管理**。

## 现状与缺口核验结论

已在 `score-engine/tests/verify_features.py` 固化核验。结论：
- ✅ 体系识别、模糊换算、深度学习效果、**年度漂移识别（新增）**、逐年效果跟踪 已达成。
- ❌ **样本仅覆盖 QS 桶名（QS10~QS1000）**，未覆盖真实全球大学。
- ❌ **排名≠真实质量**：尚无学校规模/师生比/学费/论文/就业等质量维度。
- ❌ 尚无高/低水平师资、负面指标的转化。
- ❌ 尚未接入 LanceDB（用户已有）。

## 架构总览：双库 + 多表

把数据拆成两套库，交给 LanceDB / 现有数据库管理，减少人工查询：

```
┌────────────────────────────── 分析库（quality / 分析维度） ─────────────────────────────┐
│ table: school_profile       学校档案（规模/师生/学费/论文/就业…）                        │
│ table: school_faculty       师资档案（按水平分层：顶尖师/一般师/欠佳师 + 负面指标）       │
│ table: school_outcome       成果/声誉（论文产出、就业去向、认证）                         │
└──────────────────────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────── 换算库（score / 录取门槛维度）─────────────────────────────┐
│ table: admission_threshold  按 school × system × year 的录取门槛原始分/统一价值            │
│ table: system_calendar      各体系年度漂移系数（供 YearDrift / convert(year=) 使用）      │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 表结构草案（示意）

**school_profile（学校档案 · 质量鉴定，纳入负面也说明）**
| 字段 | 说明 |
|------|------|
| school_id | 全球唯一（如 QS/泰晤士/WikiData 编号） |
| name_zh / name_en | 中英文名 |
| country / city | 国家/城市 |
| uni_rank | 排名来源 + 年份（QS/THE/USNews/软科） |
| scale_students / scale_faculty | 在校生 / 师资数量 |
| ratio_student_faculty | 师生比（越低资源越充足） |
| tuition_intl | 国际生年学费（折算 USD） |
| endowment | 校产/资金（可选） |
| papers_yearly / citations | 年论文产出 / 被引（反映真实学术水平） |
| employment_rate | 就业率（官方或校友抽样） |
| source / year | 数据出处 / 采集年 |

**school_faculty（师资分层 · 含高低水平与负面）**
| 字段 | 说明 |
|------|------|
| school_id | 学校 |
| tier_high / tier_mid / tier_low | 顶尖/一般/欠佳师资占比（按奖项/论文/职称分层） |
| star_count | 高被引/诺奖等顶尖人数 |
| negative_ratio | 欠佳维度占比（低产出、离职率、师德投诉等负面指标） |
| note | 负面说明（克制、可回溯） |

**admission_threshold（录取门槛 · 换算库核心，供深度学习训练）**
| 字段 | 说明 |
|------|------|
| school_id | 学校 |
| year | 年份（跨年跟踪关键） |
| system | AP/AL/IB/GAOKAO… |
| raw_score | 当年该体系录取门槛原始分画像 |
| unified_value | 统一价值（0~1），作为 label |

**system_calendar（体系年度漂移）**
| 字段 | 说明 |
|------|------|
| year / system / drift_scale | 对应 `YearDrift.scale` 的持久化 |

## 为什么"排名≠真实水平"要单独做质量维度

用户点破：**QS 排名高 ≠ 培养质量高**。
把 `school_profile`（规模/学费/论文/就业）和 `school_faculty`（师资高低/负面）
与 `admission_threshold`（门槛）解耦为独立表后，可以回答三类问题：
1. **门槛洼地**（低分路径）：同一价值下哪条体系最省力 → `admission_threshold` + valley。
2. **性价比/质量**：门槛不高的学校是否质量却好 → 交叉 `school_profile` 的门槛与产出。
3. **风险/负面**：排名高但师生比差 / 欠佳师资占比高的"名不副实"学校 → 负面指标。

## 落地路线（增量，不阻塞现有换算引擎）
- [ ] P0：把 `make_mock_admissions` 的 QS 桶名替换为真实大学（QS1000 内）并补 country 等，提升泛化。
- [ ] P0：接入 LanceDB，建上面 4~5 张表；把 `YearDrift`、`admission_threshold` 落库。
- [ ] P1：新增 `quality.py`，从 school_profile/faculty/outcome 计算"质量指数"（含负面修正）。
- [ ] P1：把质量指数与排名做**偏差报告**（排名高但质量低 / 排名低但质量好的学校）。
- [ ] P2：用真实历年录取 CSV 重训 NN，做真实世界校准（替代当前启发式 + 合成校准）。

## 与代码的关系
- `score_engine/drift.py` → 对应 `system_calendar` 表的算法来源。
- `score_engine/valley.py` → 对应"门槛洼地"查询。
- 新增 `score_engine/quality.py`、`score_engine/db_lancedb.py` 建议放在本仓库后续 PR。
