# 试卷 / 大纲 · 范围登记簿

> **为什么要有"范围"？** 用户要求"为了题不歪，得有个基于试卷或大纲的明确范围"。
> 一个 `范围` = 一道题目声称考察的**出处边界**，可以是：
> - 一份**具体试卷**（AP 真题卷 / 期中期末卷 / 竞赛卷…），或
> - 一段**官方大纲 / 教材章节**（明确知识边界）。

> 范围带唯一编号，题目通过 `- 范围：<编号>` 指向它。这样既能"对账不歪"、
> 又能"按卷/大纲整批铺题"，检索时可按范围过滤。

## 范围登记字段（每条必填）
| 字段 | 说明 |
|------|------|
| 编号 scope_id | **唯一编号**，可被复制精确检索/引用，格式 `学科-来源-年份` |
| 名称 name | 人类可读名称 |
| 类型 type | 试卷 exam / 大纲 syllabus / 教材 textbook |
| 年份 year | 试卷年份或版本年份 |
| 出处 source | 试卷/大纲地址或官方链接（用于区分不同试卷） |
| 学科 subject | 归属顶层分类（须在白名单内） |
| 体系 system | 归属教育体系（AP/AL/IB/国内/其他，须在体系白名单内） |
| 题目量 count | 本范围计划/已入库题量 |
| owner | 负责铺题的负责人 |
| 登记时间 added_at | YYYY-MM-DD |

## 唯一编号约定
- 编号全局唯一，一经登记不改。
- 引用方式：题干文件写 `- 范围：<scope_id>`；PR 描述、检索、批注都直接 `@复制编号`。

---

## 范围登记表

| scope_id | 名称 | 类型 | 年份 | 出处/地址 | 学科 | 体系 | 题目量 | owner | 登记时间 |
|----------|------|------|------|-----------|------|------|--------|-------|----------|

| AP-CHEM-CB-2024 | AP 化学 2024 真题卷（Course&Exam Description 考纲锚定） | exam+syllabus | 2024 | [CB 官方大纲 apcentral.collegeboard.org](https://apcentral.collegeboard.org/courses/ap-chemistry) | AP化学 | AP | 436 题在库（目标 3000） | 架构·开发 | 2026-09-06 |
| AL-CHEM-CIE-2024 | A-Level 化学 CIE(Cambridge) 考纲 2024 | syllabus | 2024 | [CIE 考纲](https://www.cambridgeinternational.org/programmes-and-qualifications/cambridge-advanced/cambridge-international-as-and-a-levels-chemistry-9701/) | AL化学 | AL | 17 题在库（含质谱演示 1 + 扩铺 16） | 架构·开发 | 2026-09-07 |
| IB-CHEM-IBO-2025 | IB DP Chemistry 大纲（2025 首考） | syllabus | 2025 | [IB 官方大纲](https://www.ibo.org/programmes/diploma-programme/curriculum/sciences/chemistry/) | IB化学 | IB | 12 题在库（代表口径题） | 架构·开发 | 2026-09-07 |
| CN-CHEM-RJ-2022 | 国内初中化学 人教版 2022 课标口径（中考） | syllabus+exam | 2022 | 人教版义务教育化学课程标准(2022年版) | 国内化学 | 国内 | 10 题在库（代表口径题） | 架构·开发 | 2026-09-07 |
| DEV-BASE-GEN-2026 | 开发基础通用知识（工程化/性能/方法论，无单一考纲） | textbook | 2026 | 软件工程/研发通用知识集合 | 开发基础 | 其他 | 13 题在库（扩铺 13） | 架构·开发 | 2026-09-07 |
| AL-CHEM-EDEXCEL-2024 | A-Level 化学 Edexcel(培生) 2024 | syllabus | 2024 | Edexcel A-Level Chemistry(9CH0) 大纲 | AL化学 | AL | 待铺（通道登记） | 待分工 | 2026-09-07 |

> 首批优先从 **AP 化学** 出，锚定 College Board 官方《AP Chemistry Course and Exam Description》，
> 见 [AP-Chemistry 范围说明](./AP-Chemistry/README.md)。

## 维护机制
1. **加试卷/大纲**：在 `papers/<学科>/` 建范围说明目录 + 在上表登记一行（owner/时间必填）。
2. **编号去重**：脚本校验 scope_id 在登记表内唯一、且题干引用的编号都存在。
3. **防挡不防堵**：新增走 PR，登记后即放行；改名/下线必须过 PR 并迁移存量引用。
