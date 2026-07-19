# C021 事实证据报告

生成时间：2026-07-18（TASK-020B1R4 对齐版）

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

## 案例（来自 QA 最新输出）

| Case ID | 标题 | Evidence | 阈值 | Spans | Timeline | 四分位 |
|---|---|---|---|---|---|---|
| CASE-C021-001 | 汕头女生聊天案例分析 | 44 | 36 | 15 | 7 | 4 |
| CASE-C021-002 | 成都女生聊天案例分析 | 44 | 36 | 15 | 7 | 4 |
| CASE-C021-003 | 女生报备与依恋行为聊天案例 | 41 | 36 | 15 | 7 | 4 |

## Evidence 计数口径

`unique_evidence_count` = 所有字段（participants/timeline/observations/instructor_claims/outcomes/quoted_expressions/evidence_spans）引用的唯一 segment ID 总数。

## Timeline 对齐验证

每条 timeline 描述已与 evidence 原文逐条核对，100% 有直接支持的原文证据。

### CASE-C021-001 示例
- EVT-001: 讲师引入案例 → evidence: "然后请天我我今天来讲讲案例"
- EVT-004: 讲师解读互动模式 → evidence: "对吧？" + 相邻上下文

### CASE-C021-002 示例
- EVT-002: 展示聊天记录：成都女生 → evidence: "就是刚才成都这个不就是刚才讲的案例那个哦刚才那个女孩子是一七八身高。"

### CASE-C021-003 示例
- EVT-001: 讲师过渡 → evidence: "好下一个，" + "但是然后呢我刚睡了一会"
- EVT-002: 展示聊天内容 → evidence: "这个呃看看看你这个喝醉的这种小龙乱撞的和可可爱爱爱的迷人的样子哈"

## 产物

- Baseline: `data/catalog/evidence-baseline-C021.json`
- Report: `data/batches/BATCH-C021-C025-V003/task-020b1r4-report.json`
