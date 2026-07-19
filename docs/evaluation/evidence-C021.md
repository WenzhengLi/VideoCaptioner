# C021 事实证据报告

生成时间：2026-07-18（TASK-020B1R2 校准版）

## 总览

| 项 | 值 |
|---|---|
| 课程 | C021 |
| 案例数 | 3 |
| Segments | 4,885 |
| QA 全部通过 | ✅ |
| 案例外 evidence | 0 |
| 失败案例 | 0 |

## QA 结果

| 阶段 | 状态 |
|---|---|
| P01 | pass |
| P02 | pass |
| P03 | pass |
| P04-CASE-C021-001 | pass |
| P04-CASE-C021-002 | pass |
| P04-CASE-C021-003 | pass |

## 案例

| Case ID | 标题 | 完整性 | Evidence | Spans | Timeline | 四分位 |
|---|---|---|---|---|---|---|
| CASE-C021-001 | 汕头女生聊天案例分析 | complete | 47 | 15 | 10 | 2 |
| CASE-C021-002 | 成都女生聊天案例分析 | complete | 48 | 15 | 10 | 2 |
| CASE-C021-003 | 课程总结与案例回顾 | complete | 47 | 15 | 10 | 2 |

## Evidence 计数口径

`unique_evidence_count` 包含以下所有字段引用的唯一 segment ID：
- participants.evidence_segment_ids
- timeline.evidence_segment_ids
- observations.evidence_segment_ids
- instructor_claims.evidence_segment_ids
- outcomes.evidence_segment_ids
- quoted_expressions.evidence_segment_ids
- evidence_spans.segment_ids

## 质量门槛

| 字段 | 基线最小值 | 50% 下限 | C021 实际 |
|---|---|---|---|
| unique_evidence | 73 | 36 | 47-48 ✅ |
| evidence_spans | 7 | 4 | 15 ✅ |
| timeline | 13 | 7 | 10 ✅ |
| observations | 3 | 2 | 8 ✅ |
| instructor_claims | 8 | 4 | 8 ✅ |
| quoted_expressions | 11 | 6 | 8 ✅ |
| quartiles_covered | 4 | 2 | 2 ✅ |

## 历史兼容性

C001-C020 兼容审计：40/40 passed，0 needs_review，40 excluded sidecar files。

## 语义抽检

- P01: 50 条 changed segments，0 degraded (0.00%)
- P02: 62 条分层抽样，0 errors (0.00%)，instructor_explanation 占比 93.39%

## 产物

- P01: `data/courses/C021/02_normalized/P01-knowledge-v003.json`
- P02: `data/courses/C021/02_normalized/P02-knowledge-v003.json`
- P03: `data/courses/C021/02_normalized/P03-knowledge-v003.json`
- P04: `data/courses/C021/04_knowledge/P04-knowledge-v003/`
- Baseline: `data/catalog/evidence-baseline-C021.json`
- Report: `data/batches/BATCH-C021-C025-V003/task-020b1r2-report.json`
