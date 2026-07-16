# Cursor Flow 状态

最后更新：2026-07-16 20:10 CST（UTC+8）

## 平台纠错

- 目标产品：**Dify**（非 Tidy）。本地 SQLite 仅回归索引。
- 不启动 Dify；不触碰 cpa。

## 本轮任务边界（仅事实与证据层）

- 唯一任务说明：`docs/CURSOR-NEXT-前20课事实与证据层.md`
- 仅执行到 P04；禁止 P05/P06/finalizer/阿峰方法层

## 当前阶段

- 已完成：任务 A；任务 B 固定集回归；evidence-wave 调度代码
- 进行中：任务 C（hybrid baseline + 高未分配课 v003）；任务 D（C016–C020 视频）
- 待执行：任务 E/F

## 任务 B 结论

- 报告：`docs/evaluation/p03-v002-v003-regression.md/.json`
- 采用：`adopt_v003_hybrid`
- C003：40.4% → 20.9%（采用 v003）
- C008：无变化；C006/C010：无硬退化（软警告）

## 进行中进程

- P03 v003：C012/C015/C002
- `run-batch`：C016–C020（complete-v1，串行）

## 下一动作

1. 写完 `data/catalog/evidence-baseline-C001-C015.json`
2. 仅对边界变化案例重建 P04
3. C016–C020 raw QA 后启动 evidence-wave ThroughStage=P04
