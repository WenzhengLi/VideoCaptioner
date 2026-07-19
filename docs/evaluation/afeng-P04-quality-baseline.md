# P04 质量基线分析

生成时间：2026-07-18（TASK-020B1R4 对齐版）

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

## 门槛规则

| 字段 | 基线最小值 | 50% 下限 | 缩放规则 |
|---|---|---|---|
| unique_evidence_count | 73 | 36 | max(2, int(36 * max(0.3, segs/200))) |
| evidence_spans | 7 | 4 | 同上 |
| timeline | 13 | 7 | 同上 |
| observations | 3 | 2 | 同上 |
| instructor_claims | 8 | 4 | 同上 |
| quoted_expressions | 11 | 6 | 同上 |
| quartiles_covered | 4 | 2 | 同上 |

## C021 实际值（QA 最新输出）

| 字段 | C021-001 | C021-002 | C021-003 | 应用阈值 |
|---|---|---|---|---|
| unique_evidence_count | 44 | 44 | 41 | 36 |
| evidence_spans | 15 | 15 | 15 | 4 |
| timeline | 7 | 7 | 7 | 7 |
| observations | 8 | 8 | 8 | 2 |
| instructor_claims | 8 | 8 | 8 | 4 |
| quoted_expressions | 8 | 8 | 8 | 6 |
| quartiles_covered | **4** | **4** | **4** | 2 |

## 内容质量检查

- timeline 占位描述（"案例阶段 N"）：已拒绝
- summary 机械复述 case title：已拒绝
- timeline 描述与 evidence 原文逐条对齐：已验证
- applied thresholds 输出到 metrics：已实现
