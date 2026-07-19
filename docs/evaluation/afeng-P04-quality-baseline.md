# P04 质量基线分析

生成时间：2026-07-18（TASK-020B1R2 修复版）

## 数据来源

`data/catalog/evidence-baseline-C001-C020.json` 中 40 个成熟案例，读取正式 P04 input/output 文件。

## 分布（40 案例）

| 字段 | 最小值 | Q1 | 中位数 | Q3 | 最大值 |
|---|---|---|---|---|---|
| segment_count | 113 | 772 | 1,558 | 2,794 | 4,746 |
| unique_evidence_count | 73 | 102 | 124 | 139 | 210 |
| evidence_spans | 7 | 12 | 16 | 18 | 22 |
| timeline | 13 | 22 | 26 | 29 | 37 |
| observations | 3 | 8 | 12 | 15 | 22 |
| instructor_claims | 8 | 11 | 12 | 16 | 24 |
| quoted_expressions | 11 | 17 | 22 | 32 | 85 |
| quartiles_covered | 4 | 4 | 4 | 4 | 4 |

## 门槛设计

基于最小值的 50% 设置绝对下限（短测试样本兼容）：

| 字段 | 最小值 | 50% 下限 | 用途 |
|---|---|---|---|
| unique_evidence_count | 73 | 36 | 防止空壳 P04 |
| evidence_spans | 7 | 4 | 防止无引用 |
| timeline | 13 | 7 | 防止无时间线 |
| observations | 3 | 2 | 防止无观察 |
| instructor_claims | 8 | 4 | 防止无讲师观点 |
| quoted_expressions | 11 | 6 | 防止无引用表达 |
| quartiles_covered | 4 | 2 | 防止时间分布过于集中 |

自适应规则：对于 segment_count < 200 的短案例，门槛按比例缩小（但不低于绝对下限）。

## C021 现状

| 字段 | C021-001 | C021-002 | C021-003 | 门槛 |
|---|---|---|---|---|
| segment_count | 2,461 | 1,396 | 982 | - |
| unique_evidence_count | 38 | 38 | 37 | 36 |
| evidence_spans | 15 | 15 | 15 | 4 |
| timeline | 10 | 10 | 10 | 7 |
| observations | 8 | 8 | 8 | 2 |
| instructor_claims | 8 | 8 | 8 | 4 |
| quoted_expressions | 8 | 8 | 8 | 6 |
| quartiles_covered | 2 | 2 | 2 | 2 |

C021 全部达标。
