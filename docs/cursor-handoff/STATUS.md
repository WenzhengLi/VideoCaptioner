# Cursor Flow 状态

最后更新：2026-07-17 14:40 CST（UTC+8）

## 本轮任务边界

- 事实与证据层到 P04 已完成。
- 阿峰方法层 C001–C015 批量生产与修复已完成。
- 阿峰方法层 C016–C020 已用 `glm-5-2-260617[1M]` 完成生产；20 课聚合报告与离线包 v002.5 已生成；v002.5 已导入 economy 工作 Dataset，36/36 indexing completed，keyword 检索有命中。

## 当前结论

- A–F 已完成。
- C001–C020 baseline 已冻结到 `data/catalog/evidence-baseline-C001-C020.json`。
- 20 课 raw、P01、P02、P03 QA 全部通过。
- 40 个案例 P04 QA 全部通过。
- C016–C020 证据层完成标记为 `complete`，无失败课程和失败案例。
- 阿峰方法层 20 课聚合：36 发布 / 2 人工复核 / 2 拒绝 / 0 程序失败（40 案例）。
- 阿峰方法层 C016–C020：10 发布 / 0 人工复核 / 0 拒绝 / 0 程序失败。
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

## 阿峰方法层（C016–C020）

- 执行器：CC Switch -> Claude Code CLI headless；模型 `glm-5-2-260617[1M]`（不再使用 MiMo）。
- 运行目录：`data/afeng/model-runs/C001-C020-baseline-v002/C016-C020-v002/`。
- 10 案例全部 published，0 失败；C018/CASE-C018-002 经一轮修订后通过，其余首轮通过。
- 发布分类：6 `case_derived_method`、2 `verified_method`、2 `partial_method`。
- 忠实度审查全部 `pass`、`release_allowed=true`，无 invalid evidence、课程外概念或课程观点客观化。
- 历史 mimo 产物原样保留作审计记录，未被复用或覆盖。
- C016–C020 报告：`docs/evaluation/afeng-C016-C020-v002.md/.json`。

## 阿峰方法层 20 课聚合

- 聚合报告：`docs/evaluation/afeng-twenty-course-v002.md/.json`。
- 40 案例、0 失败、`status=complete`；模型 `['mimo-v2.5-pro', 'glm-5-2-260617[1M]']`。
- 36 published / 2 manual_review（C006-001、C008-002）/ 2 rejected（C014-001、C015-001），均沿用十五课历史终态，未强行改写。
- 最终离线包：`data/dify/afeng-release-v002.5/`（36 文档，排除 4）；v002.1–v002.4 未覆盖。

## 下一动作

1. 人工忠实度抽检 C016–C020 发布结果（尤其 2 个 `partial_method`）。
2. 保持 C006-001、C008-002 的人工复核状态；保持 C014-001、C015-001 的拒绝状态，不绕过闸门。
3. Dify 平台与 `afeng-release-v002.5` 在线入库/indexing/keyword 检索已完成（见 `DIFY-STATUS.md`）。
4. 下一生产化轮次：执行 TASK-013～018（canonical ID → v002.6 → 正式语义库 → 同步检索 → 应用 → 终审交接）；embedding 优先验证本地方案，真实不可行时才标记 `external_blocked`。

## 仓库验收

- pytest：255 passed，1 skipped。
- Ruff：全部通过。
- Pyright：0 errors、0 warnings。
