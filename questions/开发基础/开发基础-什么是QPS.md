# 题目：什么是 QPS（Queries Per Second）？
- 题目ID：DEV-BASE-0001
- 难度：简单
- 分类：开发基础
- 题型：简答
- 范围：
- owner：zhongguoliandanshidongdong
- 录入时间：2026-09-03

## 题目
请用自己的话解释 QPS 的含义，并给出一个直观示例。

## 答案
QPS（Queries Per Second，每秒查询数）是衡量系统处理能力的指标，
表示一秒钟内能处理完成的请求（查询）数量。例如 QPS = 100，
表示系统平均每秒能处理 100 个请求。

## 解析
QPS 常用于接口/服务的性能评估，与吞吐量（Throughput）、
并发数（Concurrency）共同描述系统容量；压测中常以峰值 QPS 作为容量上限参考。
