# TASK-020B2A：C022 P01–P03 与首个完整案例 P04

## 状态

待执行；依赖 C021 最终事实证据基线。

## 目标

验证 C021 已收敛的流程能在 C022 上一次产生内容真实、证据直接对齐的首个案例。该任务不是整课 P04 批处理，只完成 P01、P02、P03，以及 P03 中第一个边界清晰的完整案例 P04。

## 必须完成

1. 复用 C022 已完成的原始视频分析产物，执行 P01、P02、P03；
2. P01 changed segments 抽检至少 50 条，P02 分层抽检至少 60 条；
3. 人工/模型复核 P03 所有案例边界、标题和转场证据；
4. 只选择第一个 `complete` 且 confidence 足够的案例生成 P04；
5. P04 生成时同步建立 timeline 逐条 statement/evidence 原文记录，不允许生成后再补审计；
6. 对该案例全部 timeline、observations、claims、quotes、spans 做语义对齐审计；
7. 运行正式 QA、全量代码门禁，提交并推送后停止，等待独立验收。

## 验收标准

- P01/P02/P03 QA pass；
- P03 案例闭区间与 unassigned 完整覆盖且不重叠；
- 首个案例 P04 结构 QA pass；
- timeline 100% 有直接原文支持；
- observations、claims、quotes、spans 100% 核对，不使用抽样凑数量；
- QA metrics 达到 C021 已冻结的自适应门槛；
- 报告状态使用 `ready_for_independent_review`，不得由生产者自行宣布课程获批；
- 不生成 C022 其他案例 P04，不进入 C023–C025、P05/P06 或 Dify。

## 禁止事项

- 不按固定间隔抽取 evidence；
- 不使用“案例阶段 N”或先写描述再随机补 ID；
- 不让同一份自审报告替代独立验收；
- 不使用 `git add .`、`commit -a`、reset、rebase 或 amend。
