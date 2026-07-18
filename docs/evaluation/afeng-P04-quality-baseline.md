# P04 质量基线分析

生成时间：2026-07-18

## 数据来源

`data/catalog/evidence-baseline-C001-C020.json` 中 40 个成熟案例的 P04 统计。

## 分布

| 字段 | 最小值 | 中位数 | 平均值 | 最大值 |
|---|---|---|---|---|
| unique_evidence_count | 73 | 124 | 124.3 | 210 |
| evidence_spans | 7 | 16 | 15.4 | 22 |
| timeline | 13 | 26 | 25.2 | 37 |
| observations | 3 | 12 | 11.2 | 22 |
| instructor_claims | 8 | 12 | 13.7 | 24 |
| quoted_expressions | 11 | 22 | 26.6 | 85 |

## C021 现状对比

| 字段 | C021-001 | C021-002 | 基线中位数 | 差距 |
|---|---|---|---|---|
| unique_evidence | 4 | 1 | 124 | 严重不足 |
| evidence_spans | 1 | 0 | 16 | 严重不足 |
| timeline | 2 | 1 | 26 | 严重不足 |
| observations | 1 | 1 | 12 | 严重不足 |
| instructor_claims | 1 | 0 | 12 | 严重不足 |
| quoted_expressions | 1 | 0 | 22 | 严重不足 |

## 结论

C021 的 P04 输出远低于成熟案例水平。需要重新生成。

## 保守下限建议

基于最小值分布，建议：
- unique_evidence_count >= 50（成熟最小值 73 的 68%）
- evidence_spans >= 5（成熟最小值 7 的 71%）
- timeline >= 8（成熟最小值 13 的 62%）
- observations >= 2（成熟最小值 3 的 67%）
- instructor_claims >= 5（成熟最小值 8 的 63%）
- quoted_expressions >= 8（成熟最小值 11 的 73%）
