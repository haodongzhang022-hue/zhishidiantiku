# 知识图谱层 · Graph MVP（L0 知识点 → L1 题目 → L2 场景）

> 对应 Issue #1「解耦题库」核心诉求：把题目从"孤立可评测数据"升级为
> **带目的链、可函数/向量跳转的知识节点**（架构·总师 L0~L13 蓝图的主链打穿段）。

## 为什么做这层
现有的 `questions/` 是一张**扁平题目表**：每题能按分类/范围检索，但"知识点""使用场景"
这些**更上层的目的信息**没有被结构化关联。知识图谱层把题目挂到**最小知识点(L0)**、
再挂到**真实使用场景(L2)**，让用户能：

> 输入现实需求 → 命中 L2 场景 → 跳到 L0 知识点 → 跳到 L1 题目 → 只刷与目的相关的题

这正是"精准刷题 / 带着目的学"的底层结构。

## 层定义（本 MVP 打穿 L0→L1→L2，蓝图更高层 L3~L13 后续演进）
| 层 | 内容 | 节点示例 |
|----|------|----------|
| **L0** | 最小知识点颗粒（"是什么"） | `K.AP-CHEM.electron-config` 电子构型 |
| **L1** | 题目（"怎么考"） | `AP-CHEM-CB-2024-MC-0107`（引用题库 ID） |
| **L2** | 真实使用场景（"用在哪"） | `S.ap-chem-unit1` 备考 AP 化学 Unit1 |

> L1 题目**不复制**题干/答案到图谱（解耦），只登记对 `questions/` 题目 ID 的引用，单向指向，不重复存储。

## 层间双通道跳转（函数 + 向量）
- **函数硬通道（本 MVP 落地）**：`relations` 关系表 `(from → to, type)`，精确、双向可回溯。
  关系类型见下表。
- **向量软通道（预留，LanceDB 依赖就绪后启用，见 G4/G6）**：语义 top-K 模糊命中。当前以
  L0 节点名/关键词做关键字模糊匹配兜底，语义向量化留待 LanceDB/embedding 选型后接入。

| 关系类型 | from | to | 语义 |
|----------|------|----|------|
| `covered_by` | L0 知识点 | L1 题目 | 该知识点被这题考察 |
| `used_in` | L1 题目 | L2 场景 | 这题用于该场景（预留，随向量软通道接入） |
| `requires` | L2 场景 | L0 知识点 | 该场景需要掌握此知识点 |

## 数据存储
- **节点与关系**：`graph/graph-seed.json`（机器可遍历），schema 见文件头注释。
- **图谱范围说明与对账**：`graph/INDEX.md`（人读 + 变更历史，登记 owner/时间）。
- **工具**：`scripts/graph.mjs`（构建 / 检索 / 层间函数跳转）。

## 文件结构
| 文件 | 说明 |
|------|------|
| `graph/graph-seed.json` | L0 知识点节点 + L2 场景节点 + relations（L1 题目以引用 ID 形式挂在 relations 两端） |
| `graph/INDEX.md` | 图谱登记说明 / 变更历史 / 对账 |
| `scripts/graph.mjs` | 构建/查询/跳转 CLI |

## 用法（scripts/graph.mjs）
```bash
node scripts/graph.mjs layers                    # 列出各层节点
node scripts/graph.mjs node k.electron-config    # 查单个节点详情
node scripts/graph.mjs by-scene s.ap-chem-unit1  # 场景→题目（requires + covered_by 回溯）
node scripts/graph.mjs by-kp k.electron-config   # 知识点→题目（covered_by）
node scripts/graph.mjs scene-from-kp <场景关键字> # 输入现实需求→命中场景→出题（精准刷题链路）
node scripts/graph.mjs jump <知识点>             # 知识点→题目→场景 函数跳转全链路
node scripts/graph.mjs stats                     # 图谱规模统计
```

## 校验与门禁
- `node scripts/graph.mjs stats` 可自检 seed 完整性（节点引用、关系两端指向是否都在库内、L1 引用题目 ID 是否存在）。
- 图谱 seed 作为**增强层**，不阻塞 `check.mjs` 题库门禁；图谱自身一致性由 `graph.mjs --check` 守护。
