# P04 质量基线分析

## 历史基线

C001–C020 共 40 个正式案例，读取 catalog 指定版本的 P04 input/output。

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

## 自适应门槛

| 字段 | 长案例基础门槛 | 短案例缩放 |
|---|---|---|
| unique evidence | 36 | `max(2, int(36 * max(0.3, segments/200)))` |
| evidence spans | 4 | 同一缩放规则 |
| timeline | 7 | 同一缩放规则 |
| observations | 2 | 同一缩放规则 |
| instructor claims | 4 | 同一缩放规则 |
| quoted expressions | 6 | 同一缩放规则 |
| quartiles covered | 2 | 不缩放 |

## C021 应用结果

| Case | Evidence | Required | Spans | Timeline | Quartiles |
|---|---|---|---|---|---|
| CASE-C021-001 | 50 | 36 | 15 | 7 | 4 |
| CASE-C021-002 | 54 | 36 | 15 | 7 | 4 |
| CASE-C021-003 | 45 | 36 | 15 | 7 | 4 |

门槛由 `validate_p04_output()` 计算并写入 QA metrics；报告不维护第二套手写值。
