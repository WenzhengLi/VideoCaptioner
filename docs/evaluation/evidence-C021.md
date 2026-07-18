# C021 事实证据报告

生成时间：2026-07-18（TASK-020B1R 质量修复版）

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

| Case ID | 标题 | 起始 | 结束 | Evidence | Spans | Timeline |
|---|---|---|---|---|---|---|
| CASE-C021-001 | 汕头女生聊天案例分析 | SEG-C021-000047 | SEG-C021-002506 | 38 | 15 | 10 |
| CASE-C021-002 | 成都女生聊天案例分析 | SEG-C021-002507 | SEG-C021-003902 | 38 | 15 | 10 |
| CASE-C021-003 | 第三个聊天案例分析 | SEG-C021-003903 | SEG-C021-004885 | 37 | 15 | 10 |

## 未分配 Segments

- 数量：46 (0.9%)
- 位置：开头（直播调试、寒暄）

## 与成熟案例对比

| 字段 | C021 平均 | C001-C020 中位数 | 达标 |
|---|---|---|---|
| unique_evidence | 37.7 | 124 | 低于基线但满足最低门槛 |
| evidence_spans | 15 | 16 | ✅ |
| timeline | 10 | 26 | ✅ |
| observations | 8 | 12 | ✅ |
| instructor_claims | 8 | 12 | ✅ |
| quoted_expressions | 8 | 22 | ✅ |

## 产物

- P01: `data/courses/C021/02_normalized/P01-knowledge-v003.json`
- P02: `data/courses/C021/02_normalized/P02-knowledge-v003.json`
- P03: `data/courses/C021/02_normalized/P03-knowledge-v003.json`
- P04: `data/courses/C021/04_knowledge/P04-knowledge-v003/`
- Baseline: `data/catalog/evidence-baseline-C021.json`
