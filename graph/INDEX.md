# 知识图谱登记 · Graph INDEX

> 图谱 L0/L2 节点与关系的关系登记说明 + 变更历史（配合 `graph/graph-seed.json` 使用）。
> L1 题目节点由题目文件自动发现（无需在此登记），见 [README.md](README.md)。

## 登记字段（graph-seed.json）
| 字段 | 说明 |
|------|------|
| `l0` | L0 最小知识点节点：id（`K.<体系>.<topic>`）→ {name, topic} |
| `l2` | L2 使用场景节点：id（`S.<slug>`）→ {name, desc} |
| `relations` | 层间关系：{from, to, type}。type：`requires`(L2→L0，手工登记)；`covered_by`(L0→L1，由题目 `知识点` 字段自动生成) |

## 关系类型
| type | from | to | 来源 |
|------|------|----|------|
| `covered_by` | L0 知识点 | L1 题目 | 自动（题目文件 `- 知识点:` 字段） |
| `requires` | L2 场景 | L0 知识点 | 手工 seed |

## 维护机制
1. **新增 L0 知识点**：在 `graph-seed.json` 的 `l0` 加一条；把覆盖它的题目补上 `- 知识点：<该id>` 字段（一条知识点至少挂 1 题才能被场景检索到）。
2. **新增 L2 场景**：在 `l2` 加场景；在 `relations` 里登记它 `requires` 哪些 L0 知识点。
3. **校验**：`node scripts/graph.mjs --check` 自检 seed 引用一致（关系两端节点存在）。
4. **防失序**：L0 知识点 id 一经登记不改；改名须同步题目 `知识点` 字段 + PR 留痕。

## 当前规模（对账）
> 更新日期：2026-09-08　来源：`node scripts/graph.mjs stats`
- L0 知识点：17（AP 化学 Unit1~9 主知识点）
- L2 场景：3（AP 化学考试 / 大学预修 / 化学竞赛）
- L1 题目（已挂知识点）：139 / 全库 488
- relations（requires seed）：26

## 变更历史
| 日期 | 操作 | 内容 | 操作人 |
|------|------|------|--------|
| 2026-09-08 | 新建 | L0→L1→L2 图谱主链落地：graph-seed.json（17 L0 + 3 L2 + 26 requires）+ scripts/graph.mjs；为 AP 化学 139 题补 `知识点` 标注打通 covered_by | CodeBuddy |
