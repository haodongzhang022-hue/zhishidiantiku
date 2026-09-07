# 数据源（data_sources）· 真实数据接入说明

> 本目录是 **真实数据的唯一入库入口**。配合 `score_engine/pipeline/MANIFEST.json` 声明文件，
> 由管道（`cli ingest`）自动分类并落到**正确的库/表位**，避免"每份数据都要人肉判断放哪"。

## 为什么要有它（issue #8 最新诉求）

过去补充数据是**单次驱动**：每次都要重新识别"这份数据从哪来、该按什么规则存进
哪张库哪张表"。既不专业也不可持续。现在我们用**声明 + 复用命令**固化规则：

```
数据源原始文件  ──►  MANIFEST.json(声明：字段映射/目标表/清洗校验/溯源)
> 实际路径: score_engine/pipeline/MANIFEST.json
                       │
                       ▼  cli ingest（复用，不改代码）
                   ScoreDB 落库（score 换算库 / quality 分析库）
                       │
                       ▼
                   质检报告（每表写入/丢弃/告警）
```

## 目录约定

| 子目录 | 内容 |
|--------|------|
| `universities/` | 大学静态档案源（公开稳定信息 + 采集口径年份） |
| `rankings/` | QS 等历年排名源（来源/年份可追溯） |
| `admissions/` | 历年录取门槛样本（真实录取 CSV，P2 待铺） |
| `quality/` | 质量鉴定数据（规模/师资/论文/就业，真实源待接） |

## 如何补充一类真实数据（三步，之后可复用）

1. **放原始文件**：把新数据存成 `data_sources/<类别>/<文件名>.csv|json`。
2. **登记声明**：在 `score_engine/pipeline/MANIFEST.json` 的 `sources` 里加一条，声明：
   - `file` 原始文件路径；`target` 目标库/表（`score` 或 `quality`）；
   - `field_map` 源字段 → 表字段映射；
   - `rules` 清洗/校验/分类规则（在 `pipeline/rules.py` 登记，见下）；
   - `source` / `provenance` 溯源标记（出处 + 采集年份）。
3. **跑管道落库**：
   ```bash
   cd score-engine
   python -m score_engine.cli ingest --backend json            # 全量落库
   python -m score_engine.cli ingest --backend json --dry-run  # 先看会写进哪、不落库
   ```

## 规则如何复用（规则引擎在 score_engine/pipeline/rules.py）

规则是**纯函数**，登记进 `RULES` 表后即可在 MANIFEST 里用名字引用，
**加新数据源不需要改管道主流程**。内置规则：
- `drop_if_missing` 必填字段缺失则丢弃该行
- `strip_strings` / `to_int_fields` / `to_float_fields` 清洗与类型规整
- `ensure_id` 主键缺省则按名称生成 slug id
- `set_band_from_rank` 排名→档位分组（自动分类）
- `tag_source` 打溯源标记（source/年份）
- `fill_defaults` 填充声明的默认值

> 需要新规则？在 `score_engine/pipeline/rules.py` 加一个 `fn(row, ctx)->row`，注册到 `RULES`，
> 再在 MANIFEST 里引用即可。

## 真实数据的边界（诚实声明）

- `universities/` 为**公开可核查的稳定事实**（建校年/国家/公立私立/官网学费），
  标注 `source`（QS/THE 公开档案、校官网）与采集口径年份 2024。
- `rankings/qs_rankings.csv` 为 QS 世界排名 2019-2024 官方发布历史。
- 录取门槛样本与质量细分维度（师资分层/论文/就业等）目前仍是**示意/待真实源替换**，
  本管道已为其预留 `admissions/`、`quality/` 目录位，接入真实 CSV 后即可自动落库。
- **不把示意数据冒充真实**：凡未经真实源核实的数据源一律不登记进本目录。
