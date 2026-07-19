# C021 事实证据报告

生成时间：2026-07-18（TASK-020B1R3 内容真实性版）

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

| Case ID | 标题 | Evidence | 阈值 | Spans | Timeline | 四分位 |
|---|---|---|---|---|---|---|
| CASE-C021-001 | 汕头女生聊天案例分析 | 44 | 36 | 15 | 7 | 2 |
| CASE-C021-002 | 成都女生聊天案例分析 | 44 | 36 | 15 | 7 | 2 |
| CASE-C021-003 | 女生报备与依恋行为聊天案例 | 41 | 36 | 15 | 7 | 2 |

## Timeline 内容（非占位）

### CASE-C021-001
1. 讲师引入案例：今天来讲讲案例
2. 展示微信聊天开场：一月三十号打招呼
3. 分析聊天节奏：打字不花钱、断节奏
4. 讲师解读互动模式：默认可以
5. 关键转折：这是你的幸福
6. 方法应用：约出来见面
7. 案例收尾：好吗？

### CASE-C021-002
1. 讲师过渡到下一个案例
2. 展示聊天记录：成都女生、一七八身高
3. 分析吸引力：crush、喜欢你
4. 讲师解读难度：系数难度一星半
5. 关键分析：七零后爱情长跑
6. 方法总结：在乎你的女生想了解过往
7. 案例收尾

### CASE-C021-003
1. 讲师过渡：好下一个
2. 展示聊天内容：喝醉小龙乱撞
3. 分析约会场景：开心浪漫微醺
4. 讲师解读报备行为
5. 关键分析：依恋模式
6. 方法应用建议
7. 课程收尾：拜拜

## Evidence 计数口径

`unique_evidence_count` = 所有字段引用的唯一 segment ID 总数（含 participants/timeline/observations/instructor_claims/outcomes/quoted_expressions/evidence_spans）

## 产物

- P01: `data/courses/C021/02_normalized/P01-knowledge-v003.json`
- P02: `data/courses/C021/02_normalized/P02-knowledge-v003.json`
- P03: `data/courses/C021/02_normalized/P03-knowledge-v003.json`
- P04: `data/courses/C021/04_knowledge/P04-knowledge-v003/`
- Baseline: `data/catalog/evidence-baseline-C021.json`
- Report: `data/batches/BATCH-C021-C025-V003/task-020b1r3-report.json`
