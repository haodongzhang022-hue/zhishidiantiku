# 题目：分布式系统的 CAP 定理指什么？
- 题目ID：DEV-BASE-MC-0003
- 难度：困难
- 分类：开发基础
- 题型：单选
- owner：zhongguoliandanshidongdong
- 录入时间：2026-09-07

## 题目
分布式系统的 CAP 定理说明，在出现网络分区（Partition）时，系统只能在下列哪两者之间做权衡？

## 选项
A. 可用性与最终一致性
B. 一致性（Consistency）与可用性（Availability）
C. 持久性与一致性
D. 可扩展性与可用性

## 答案
B

## 解析
CAP 指 Consistency、Availability、Partition tolerance 三者不可兼得。发生网络分区时，
系统只能在"保持一致（C）"与"保持可用（A）"之间二选一，P 是必须面对的现实。
