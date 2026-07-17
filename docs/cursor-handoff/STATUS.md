# Cursor Flow 状态

最后更新：2026-07-17 09:10 CST（UTC+8）

## 本轮任务边界

- 事实与证据层到 P04 已完成。
- 阿峰方法层 C001–C015 批量生产与修复已完成；未做 Dify 在线发布。

## 当前结论

- A–F 已完成。
- C001–C020 baseline 已冻结到 `data/catalog/evidence-baseline-C001-C020.json`。
- 20 课 raw、P01、P02、P03 QA 全部通过。
- 40 个案例 P04 QA 全部通过。
- C016–C020 完成标记为 `complete`，无失败课程和失败案例。
- 阿峰五课：7 发布 / 1 人工复核。
- 阿峰十五课（修复后）：26 发布 / 2 人工复核 / 2 拒绝 / 0 程序失败。

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

## 阿峰方法层（C001–C015）

- 其余十课原始跑次：`remaining-ten-v002`（2 例程序失败后已修复）。
- 修复跑次：`repair-v002`（C002-002 发布；C008-002 人工复核）。
- 合并报告：`docs/evaluation/afeng-remaining-ten-repaired-v002.md`。
- 十五课合并报告：`docs/evaluation/afeng-fifteen-course-v002.md`。
- 离线发布包：`data/dify/afeng-release-v002.4/`（26 文档，排除 4）。

## 下一动作

1. 人工忠实度抽检十五课发布结果。
2. 复核 C006-001、C008-002；确认 C014-001、C015-001 拒绝是否合理。
3. 使用同一 `mimo-method-v002` 扩展 C016–C020。
4. 用 `afeng-release-v002.4` 做离线验收；Dify 在线部署后再做检索验收。

## 仓库验收

- pytest：250 passed，1 skipped。
- Ruff：全部通过。
- Pyright：0 errors、0 warnings。
