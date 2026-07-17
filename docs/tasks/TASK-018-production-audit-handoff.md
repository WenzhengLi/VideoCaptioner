# TASK-018：阿峰生产链路终审、备份与运维交接

## 状态

待执行；依赖 TASK-017。若 TASK-015 或 TASK-017 因真实外部 Provider 阻塞，本任务仅执行不依赖该
Provider 的审计、备份脚本和文档部分，并如实标记 `external_blocked`。

## 目标

对 TASK-013～017 的产物做一次独立、可重复的最终核对，冻结可恢复的生产基线，确保后续没有 AI
人工介入时，程序仍能按固定命令完成构建、同步、检索验收、应用验收和故障恢复。

## 必须完成

1. 新增一个只读审计入口，统一检查：
   - 40 案例 = 36 published + 2 manual_review + 2 rejected；
   - v002.6 documents=36、exclusions=4、canonical ID 唯一；
   - lineage、内容 SHA-256、source、time range、evidence IDs 覆盖率 100%；
   - 正式 Dataset 文档数、indexing 状态和正式 map 数量一致；
   - manual_review/rejected 在正式 Dataset 中为 0；
   - Workflow/Chatflow 绑定的是正式 Dataset，不是历史 economy 工作库；
2. 审计命令不得修改 Dify、bundle、map 或历史产物；失败时必须返回非零退出码和机器可读原因；
3. 提供生产备份与恢复说明，至少覆盖：
   - v002.6 immutable bundle；
   - 正式 document map；
   - Dataset/Workflow 标识和非敏感配置；
   - Workflow DSL、Prompt、测试集和验收报告；
   - Dify 官方数据库/volume 的安全备份原则；
4. 恢复流程必须先 dry-run，再允许写入；禁止恢复时产生重复文档；
5. 提供一份不依赖对话上下文的运维手册：启动、健康检查、重建 bundle、同步、轮询 indexing、
   20 问检索、应用验收、备份、恢复、常见故障；
6. 生成最终 Markdown 与 JSON 审计报告，明确区分：代码完成、在线部署、文档入库、索引完成、
   检索通过、应用通过；
7. 运行全量 pytest、Ruff、Pyright，并记录版本、数量、耗时和失败重试结果；
8. 使用显式文件列表提交并推送，不得混入用户已有未提交文件。

## 允许修改

- `scripts/` 中新增生产审计、备份清单或恢复 dry-run 工具；
- `src/course_video_analyzer/knowledge/` 中与只读审计直接相关的代码；
- `tests/test_knowledge/` 及新增相关测试；
- `docs/operations/`；
- `docs/evaluation/afeng-production-*`；
- `docs/tasks/STATUS.md`；
- `docs/cursor-handoff/DIFY-STATUS.md`。

## 禁止事项

- 不重新调用模型生成课程方法；
- 不修改 P01～P04；
- 不覆盖 v002.1～v002.6；
- 不删除 Dataset、Docker volume 或历史工作库；
- 不输出、复制或提交密码、Token、API Key；
- 不停止或修改 `cpa`；
- 不用人工手改数据伪造审计通过。

## 交付内容

- 一键只读审计入口；
- 备份清单和恢复 dry-run；
- 无上下文运维手册；
- Markdown/JSON 最终审计报告；
- 自动化测试与最终提交记录。

## 验收标准

- 审计结果可重复，成功返回 0，任一关键不变量被破坏时返回非零；
- bundle=36、exclusions=4、canonical map=36、remote=36、indexing completed=36；
- exclusion leakage=0、duplicate canonical ID=0、stale map=0；
- 20 问检索和 20 问应用验收报告均可追溯；
- 备份/恢复步骤不依赖当前对话或某个 Agent 的临时记忆；
- 全量 pytest、Ruff、Pyright 通过；
- Git 与远端同步，用户无关脏文件原样保留。
