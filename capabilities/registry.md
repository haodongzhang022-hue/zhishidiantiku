# 能力注册表 · Capability Registry（跨库能力索引）

> 本仓库**可能需要调用 / 可提供给外部**的跨库能力契约登记，统一索引。
> 原则：解耦登记（只登记契约，不内嵌实现）→ 有源即用 / 无源即缺 / 缺口引导。
> 字段与流转规则见 [README.md](README.md)。

## 〇、能力状态取值
- `可用`：能力源存在，可按「来源库+调用入口」匹配调用。
- `缺口`：**应当有**，但当前无源/来源不全，暂不可调（进 [gaps.md](gaps.md) 跟踪 + 引导）。
> 缺口的细分进展（`待获取/建设中/部分可用`）在 [gaps.md](gaps.md) 速览表中登记，本表统一记为 `缺口`。

---

## 一、能力注册表（按域分组）

### A. 分派 / 路由（秘书机制）

> 把"遇到不确定诉求 → 先路由给秘书，不自作主张抛人工"做成可调用的跨库能力。
> 来源库：秘书团（`dongdongxiaozu/zhuanyemishutuan`）。

| 能力代码 | 能力名 | 类型 | 来源库 | 调用入口 | 状态 | owner | 登记时间 |
|----------|--------|------|--------|----------|------|-------|----------|
| `cap.mishu.route` | 秘书·接待路由 | 跨库调用 | `zhuanyemishutuan`(接待) | 未知诉求先 @ 秘书·接待 由其判断分流 | 缺口 | 架构·经理 | 2026-09-07 |
| `cap.mishu.assign` | 秘书·分派编排 | 跨库调用 | `zhuanyemishutuan`(秘书长) | 由接待判定后转派对应秘书/经理/总师 | 缺口 | 架构·经理 | 2026-09-07 |
| `cap.mishu.session` | 秘书·会话/状态管理 | 跨库调用 | `zhuanyemishutuan`(会话管理) | 跨会话状态保持、上下文续接 | 缺口 | 架构·经理 | 2026-09-07 |

> **登记说明**：秘书团能力域存在（CNB NPC 生态），但当前本仓库未见秘书团可被唤醒来分派的实例，
> 属"应有无源/未接入" → 记为 **缺口**，引导见 [gaps.md](gaps.md)。

### B. 协作 / 分工（架构师团队 NPC）

> 把"评审/开发/对齐/测试/哨兵"的角色协作能力做成可调用。
> 来源库：架构师团队仓库（`dongdongxiaozu/dongjiagoushi`）。

| 能力代码 | 能力名 | 类型 | 来源库 | 调用入口 | 状态 | owner | 登记时间 |
|----------|--------|------|--------|----------|------|-------|----------|
| `cap.arch.total` | 架构·总师（设计定稿） | 跨库调用 | `dongjiagoushi/(架构·总师)` | `@dongjiagoushi(架构·总师)` 召唤 | 可用 | 架构·总师 | 2026-09-06 |
| `cap.arch.manager` | 架构·经理（分工调度） | 跨库调用 | `dongjiagoushi/(架构·经理)` | `@dongjiagoushi(架构·经理)` 召唤 | 可用 | 架构·经理 | 2026-09-06 |
| `cap.arch.dev` | 架构·开发（铺题/实现） | 跨库调用 | `dongjiagoushi/(架构·开发)` | `@dongjiagoushi(架构·开发)` 召唤 | 可用 | 架构·开发 | 2026-09-06 |
| `cap.arch.review` | 架构·评审（代码/文档评审） | 跨库调用 | `dongjiagoushi/(架构·评审)` | `@dongjiagoushi(架构·评审)` 召唤 | 可用 | 架构·评审 | 2026-09-06 |
| `cap.arch.test` | 架构·测试（门禁验证） | 跨库调用 | `dongjiagoushi/(架构·测试)` | `@dongjiagoushi(架构·测试)` 召唤 | 可用 | 架构·测试 | 2026-09-06 |
| `cap.arch.align` | 架构·对齐（编号/对账） | 跨库调用 | `dongjiagoushi/(架构·对齐)` | `@dongjiagoushi(架构·对齐)` 召唤 | 可用 | 架构·对齐 | 2026-09-06 |
| `cap.arch.sentinel` | 架构·监控哨兵（进度监督） | 跨库调用 | `dongjiagoushi/(架构·监控哨兵)` | `@dongjiagoushi(架构·监控哨兵)` 召唤 | 可用 | 架构·监控哨兵 | 2026-09-06 |

### C. 评分 / 换算（跨体系分数换算引擎）

> 本仓库自产模块 `score-engine/`，同时**作为可被外部库调用的出口能力**（供给侧）。

| 能力代码 | 能力名 | 类型 | 来源库 | 调用入口 | 状态 | owner | 登记时间 |
|----------|--------|------|--------|----------|------|-------|----------|
| `cap.score.convert` | 跨体系分数识别+换算 | 本地内置 | `score-engine/` | `python -m score_engine.cli convert "…"` | 可用 | 架构·开发 | 2026-09-07 |
| `cap.score.find-valley` | 低分路径/门槛洼地寻优 | 本地内置 | `score-engine/` | `python -m score_engine.cli find-valley --school <id>` | 可用 | 架构·开发 | 2026-09-07 |
| `cap.score.drift` | 年度门槛漂移识别 | 本地内置 | `score-engine/` | `python -m score_engine.cli drift --data <csv> "…"` | 可用 | 架构·开发 | 2026-09-07 |
| `cap.score.quality` | 大学质量鉴定（名不副实/被低估） | 本地内置 | `score-engine/` | `python -m score_engine.cli quality --school <id>` | 可用 | 架构·开发 | 2026-09-07 |
| `cap.score.db-lancedb` | LanceDB 双库读写 | 本地内置 | `score-engine/` | `python -m score_engine.cli db --backend lancedb` | 缺口 | 架构·开发 | 2026-09-07 |

> `cap.score.db-lancedb`：LanceDB 后端存在代码路径，但环境缺 `lancedb` 依赖时退化 JSON 兜底，
> 属"有实现但不全（依赖未铺）" → 记为 **缺口**，引导见 [gaps.md](gaps.md)。

### D. 学习 / 刷题（个人学习进度系统）

> 本仓库自产模块 `scripts/learn.mjs`，供本地使用，也可作为可被调用的能力。

| 能力代码 | 能力名 | 类型 | 来源库 | 调用入口 | 状态 | owner | 登记时间 |
|----------|--------|------|--------|----------|------|-------|----------|
| `cap.learn.progress` | 个人学习进度库（会/不会） | 本地内置 | `scripts/learn.mjs` | `node scripts/learn.mjs progress` | 可用 | 架构·开发 | 2026-09-07 |
| `cap.learn.test` | 知识点掌握测试（出2题判会） | 本地内置 | `scripts/learn.mjs` | `node scripts/learn.mjs test <知识点>` | 可用 | 架构·开发 | 2026-09-07 |
| `cap.learn.quiz` | 弱项补强抽题 | 本地内置 | `scripts/learn.mjs` | `node scripts/learn.mjs quiz` | 可用 | 架构·开发 | 2026-09-07 |

### E. 校验 / 门禁

> 本仓库自产 `scripts/check.mjs`，CI 门禁能力，也可被外部调用来验证题目集。

| 能力代码 | 能力名 | 类型 | 来源库 | 调用入口 | 状态 | owner | 登记时间 |
|----------|--------|------|--------|----------|------|-------|----------|
| `cap.check.questions` | 题目格式强校验（门禁） | 本地内置 | `scripts/check.mjs` | `node scripts/check.mjs` | 可用 | 架构·开发 | 2026-09-06 |
| `cap.check.unittest` | 校验脚本自测 | 本地内置 | `scripts/__tests__/` | `node --test scripts/__tests__` | 可用 | 架构·开发 | 2026-09-06 |

### F. 检索 / 向量 / 知识图谱（蓝图演进）

> 架构·总师蓝图定位的未来能力域，当前**主要作为缺口登记 + 引导增强**。

| 能力代码 | 能力名 | 类型 | 来源库 | 调用入口 | 状态 | owner | 登记时间 |
|----------|--------|------|--------|----------|------|-------|----------|
| `cap.graph.layer` | 14层知识图谱（L0~L13） | 缺口 | 待建 | 蓝图 `docs/arch/00-总览…` 未落代码 | 缺口 | 架构·总师 | 2026-09-06 |
| `cap.graph.vector` | LanceDB 向量检索 | 缺口 | 待接入 | 本仓库未建 LanceDB 库 | 缺口 | 架构·总师 | 2026-09-06 |
| `cap.graph.func` | 函数+向量层间跳转 | 缺口 | 待建 | 蓝图定义，未实现 | 缺口 | 架构·总师 | 2026-09-06 |

---

## 二、变更历史
| 日期 | 操作 | 内容 | 操作人 |
|------|------|------|--------|
| 2026-09-07 | 新建 | 首次建立跨库能力注册与索引机制，登记 分派/协作/评分/学习/校验/图谱 六类能力 + 缺口 | CodeBuddy |
