# C022 首案例证据报告

生成时间：2026-07-18

## 总览

| 项 | 值 |
|---|---|
| 课程 | C022 |
| 处理范围 | P01 + P02 + P03 + 首案例 P04 |
| 案例数 | 1（仅首案例） |
| 状态 | **ready_for_independent_review** |

## QA 结果

| 阶段 | 状态 |
|---|---|
| P01 | pass |
| P02 | pass |
| P03 | pass |
| P04-CASE-C022-001 | pass |

## P01 抽检

- 总 segments: 4,429
- Changed: 3,603
- 抽样 50 条: improved=50, neutral=0, degraded=0

## P02 抽检

- 总 segments: 4,429
- 角色分布: instructor_explanation=4,073, board=156, actual_chat=192, unknown=6, marketing=2
- Instructor 占比: 91.96%
- 抽样 53 条: errors=0

## P03 案例

| Case ID | 标题 | 完整性 | 置信度 | 起始 | 结束 |
|---|---|---|---|---|---|
| CASE-C022-001 | 汕头白富美长期跟进案例 | complete | 0.85 | SEG-C022-000011 | SEG-C022-004353 |

- Assigned segments: 4,343
- Unassigned segments: 86（开头调试/寒暄 + 结尾）

## P04 首案例指标

| 字段 | 数量 | 阈值 |
|---|---|---|
| unique_evidence | 38 | 36 |
| evidence_spans | 15 | 4 |
| timeline | 11 | 7 |
| observations | 8 | 2 |
| instructor_claims | 7 | 4 |
| quoted_expressions | 6 | 6 |
| quartiles_covered | 4 | 2 |

## Timeline 摘要

1. 讲师引入案例：这个案例有点长
2. 介绍女生背景：二零二二年一月二十二号，汕头
3. 分析展示价值策略：不是直接告诉妹子有钱
4. 展示约会安排：去看烟花秀
5. 分析靠谱展示面：珠海拍照
6. 讲师定位案例：相对白富美的案例
7. 展示聊天互动：不去酒吧
8. 分析同城约会：在汕头待
9. 分析价格博弈：炒高价格
10. 展示约饭聊天：牛肉火锅还是日料
11. 案例结束

## 声明

- 仅处理了第一个案例，未生成第二个案例 P04
- 未处理 C023–C025
- 等待独立验收后才允许继续
