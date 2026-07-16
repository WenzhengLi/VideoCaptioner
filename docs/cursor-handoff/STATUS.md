# Cursor Flow 状态

最后更新：2026-07-17 01:10 CST（UTC+8）

## 本轮任务边界

- 仅事实与证据层到 P04；未启动 P05/P06、Dify 在线发布或阿峰方法层扩展。

## 当前结论

- A–F 已完成。
- C001–C020 baseline 已冻结到 `data/catalog/evidence-baseline-C001-C020.json`。
- 20 课 raw、P01、P02、P03 QA 全部通过。
- 40 个案例 P04 QA 全部通过。
- C016–C020 完成标记为 `complete`，无失败课程和失败案例。

## C016–C020 结果

- 视频事实层批处理：`succeeded=18, failed=0`。
- Evidence wave：P01–P04 均使用 `knowledge-v003`。
- 课程案例数：C016=1、C017=1、C018=3、C019=2、C020=3。
- 完成标记：`data/batches/BATCH-20260715-001/evidence-pipeline-C016-C020-complete.json`。

## C001–C020 总验收

- baseline policy：`adopt_v003_hybrid`。
- 课程数：20。
- 案例数：40。
- segment 数：80264。
- OCR segment 数：4121。
- P03 assigned + unassigned 覆盖计数一致。
- P04 无案例外 evidence。
- 总失败数：0。
- 报告：`docs/evaluation/evidence-C001-C020.md`、`docs/evaluation/evidence-C001-C020.json`。

## 下一动作

1. 基于冻结 baseline 重新准备五课阿峰方法层正式输入包。
2. 完成五课方法提炼、课程忠实度审查和发布分类。
3. 对五课结果人工抽检并迭代 prompt。
4. 通过发布闸门后，再决定 Dify 在线发布。

## 仓库验收

- pytest：250 passed，1 skipped。
- Ruff：全部通过。
- Pyright：0 errors、0 warnings。
