# Claude 下一步：TASK-018 生产终审、备份与运维交接

> 本文件是 2026-07-18 的最新交接，优先级高于目录内所有旧 Claude/Cursor 计划。旧文件中的“继续外部 embedding 迁移”“创建 v2 Dataset”“TASK-017 未完成”等内容全部作废。

## 唯一目标

完成 `docs/tasks/TASK-018-production-audit-handoff.md`：对已上线的阿峰 Dify 生产链路做只读终审，形成可恢复基线、备份/恢复 dry-run、无上下文运维手册、最终报告，并通过全量质量门禁后显式提交和推送。

模型方案已经冻结：

```text
LLM: 外部 DeepSeek，应用使用 deepseek-chat
Embedding: 本地 Ollama bge-m3
正式 Dataset: 阿峰课程方法库-研究版-v1（high_quality，36 docs）
应用: 阿峰（advanced-chat，已发布）
```

禁止再安装、测试或迁移其他本地生成模型、外部 embedding、视觉 embedding 或 v2 Dataset。

## 当前真实基线

```text
branch: cursor/afeng-canonical-id-dify-bundle
HEAD: 73d5131
ahead of origin: 1 commit

v002.6 immutable bundle: 36 published + 4 excluded
aggregate: 40 cases = 36 published + 2 manual_review + 2 rejected
formal map: data/dify/document-map-v1.json，36 canonical keys
formal retrieval: hybrid Top-5 18/20（90%，document-level dedup）
Afeng app acceptance: 20/20（100%）
C019 smoke citation validation: valid=true
```

运行配置从以下本机文件安全读取，任何值不得输出或提交：

```text
D:\Dev\dify-deploy\secrets\admin.env
D:\Dev\dify-deploy\secrets\dify-runtime.env
```

## 第 0 步：先收口 TASK-017，禁止覆盖

当前 TASK-017 的已验收改动尚未提交。先只读复核，再使用显式文件列表提交；不得重新设计 Workflow，也不得重跑模型生成课程内容。

允许纳入 TASK-017 收口提交的文件：

```text
deploy/dify/workflows/afeng-chatflow.yml
docs/tasks/STATUS.md
docs/tasks/TASK-017-afeng-dify-application.md
docs/deployment/afeng-dify-operations.md
docs/evaluation/afeng-app-acceptance.md
scripts/deploy_afeng_dify_app.py
scripts/prepare_afeng_app_index.py
scripts/run_afeng_app_acceptance.py
scripts/run_afeng_retrieval_test.py
scripts/validate_afeng_citations.py
docs/claude-handoff/CLAUDE-NEXT-TASK-018-FINAL-AUDIT.md
```

提交前至少执行：

```powershell
.\.venv\Scripts\python.exe -m py_compile `
  scripts\deploy_afeng_dify_app.py `
  scripts\prepare_afeng_app_index.py `
  scripts\run_afeng_app_acceptance.py `
  scripts\run_afeng_retrieval_test.py `
  scripts\validate_afeng_citations.py
git diff --check
```

建议提交信息：

```text
feat: deploy and validate Afeng Dify application
```

提交后才进入 TASK-018。不要使用 `git add .`、`git commit -a`、reset、rebase 或新建分支。

## 受保护文件

以下为用户历史/其他 Agent 文件，必须原样保留，不恢复、不删除、不暂存、不提交：

```text
.claude/
docs/evaluation/afeng-five-course-v002.md
docs/evaluation/evidence-C001-C020.md
docs/当前系统事实审计-视频课程与Dify.md
docs/cursor-handoff/CURSOR-NEXT-AFENG-V0026-PRODUCTION.md
docs/claude-handoff/CLAUDE-NEXT-DIFY-PRODUCTION-COMPLETION.md
docs/claude-handoff/CLAUDE-NEXT-EXTERNAL-MODEL-MIGRATION.md
```

## Gate A：增强一键只读生产审计

以 `scripts/audit_afeng_production.py` 为入口扩展，不得在审计期间写入 Dify、bundle、map 或应用。

必须检查并输出机器可读结果：

1. aggregate 为 40 cases，精确等于 36 published + 2 manual_review + 2 rejected；
2. v002.6 manifest 为 36 documents + 4 exclusions；canonical ID 唯一且格式正确；
3. 每篇文档真实存在，内容 SHA-256 与 manifest 一致；缺文件也必须 FAIL；
4. lineage、source、source time range、evidence IDs 覆盖率均为 100%；
5. `document-map-v1.json` 为 36 个 canonical key，无旧键、SMOKE、重复、stale 条目；
6. map 绑定的 Dataset 与正式 Dataset 一致；远端 document count=36；
7. 远端 36 篇 indexing 全部 completed；远端文档名集合与 map canonical key 集合完全相等；
8. manual_review/rejected 远端泄漏为 0；
9. Dataset 为 high_quality，embedding 精确为 Ollama `bge-m3`；
10. “阿峰”应用存在且已发布，实际 Workflow 绑定正式 Dataset，不是旧 economy Dataset；
11. DeepSeek LLM 节点存在，Workflow 中受控引用目录节点存在；
12. 检索报告可追溯且为 18/20；应用报告可追溯且为 20/20；
13. 任何关键检查失败时退出码非零，报告不得用 SKIP/PARTIAL 冒充 PASS。

不得在 JSON/Markdown 报告中输出 API Key、密码、Provider Key。Dataset/App ID 如无必要只报告匹配布尔值或脱敏摘要。

## Gate B：审计自动化测试

为审计器补单元测试，建议放在：

```text
tests/test_knowledge/test_afeng_production_audit.py
```

至少覆盖：

- 正常 36/4 基线通过；
- manifest 文档缺失或 hash 错误时失败；
- 非 canonical map key、map 数量错误、dataset_id 错绑时失败；
- remote 文档缺失、重复、indexing 未完成时失败；
- exclusion leakage 时失败；
- Workflow 绑定旧 Dataset 或缺少引用节点时失败；
- 报告不含 secret 值；
- 任一关键 section FAIL 时进程返回非零。

测试使用 mock/fixture，不依赖真实 Dify；真实在线审计单独执行。

## Gate C：备份清单与恢复 dry-run

新增非破坏性工具，例如：

```text
scripts/build_afeng_backup_manifest.py
scripts/dry_run_afeng_restore.py
```

备份 manifest 至少记录路径、大小、SHA-256、用途和生成时间：

- v002.6 immutable bundle + manifest；
- v002.7 检索版文档；
- formal document map；
- Workflow DSL 和完整 Prompt；
- 冻结检索测试集；
- 18/20 检索报告；
- 20/20 应用报告；
- 部署、引用校验和验收脚本；
- Dify 非敏感版本/配置摘要。

恢复 dry-run 必须：

1. 默认只读，禁止调用 create/update/delete；
2. 先验证 bundle/map/dataset 绑定；
3. 计算 create/update/skip 计划；当前生产基线应为 `create=0, update=0, skip=36`；
4. 检测重复 canonical ID、stale map、错误 Dataset 绑定并拒绝继续；
5. 说明 Dify 官方数据库和 Docker volume 的停写/一致性备份原则，但本任务不得删除 volume，也不得执行破坏性恢复。

## Gate D：无上下文运维手册

在 `docs/operations/` 新增最终手册，不能只引用对话或旧 handoff。至少覆盖：

- 当前架构和模型职责：DeepSeek 生成、Ollama/bge-m3 embedding；
- Dify/Docker/Ollama 启动与健康检查；
- secrets 位置与安全边界；
- bundle 校验和正式 map 校验；
- 只读生产审计；
- 幂等同步和 indexing 轮询；
- 20 问检索验收；
- 应用部署、C019 smoke、20 问应用验收；
- 备份 manifest；
- 恢复 dry-run；
- 常见故障：Dify 不可达、Ollama 不可达、DeepSeek 错误、索引未完成、segment UUID 引用、Dataset 错绑、检索回退；
- 回滚到上一个已验收 DSL 的步骤。

同步更新 `docs/cursor-handoff/DIFY-STATUS.md`，删除其中“缺 LLM”“应用未创建”“semantic 未完成”等过期事实。

## Gate E：真实终审与报告

加载本机 runtime secret，但以 `document-map-v1.json` 中的正式 Dataset 为准，执行真实只读审计，输出：

```text
data/dify/afeng-production-final-audit.json   # runtime，可 gitignore
docs/evaluation/afeng-production-final-audit.md
```

Markdown 和 JSON 必须明确区分：

- code_complete
- provider_ready
- dataset_created
- documents_ingested
- indexing_completed
- retrieval_passed
- app_deployed
- app_acceptance_passed
- backup_manifest_ready
- restore_dry_run_passed

最终在线不变量：

```text
bundle=36
exclusions=4
canonical map=36
remote documents=36
indexing completed=36
duplicate canonical=0
stale map=0
exclusion leakage=0
retrieval=18/20
application=20/20
```

## Gate F：全量质量门禁

记录工具版本、测试数量、耗时和首次/重试结果：

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pyright
.\.venv\Scripts\python.exe -m pytest -q
```

如果失败，只修复与本任务或当前未提交 TASK-017 改动直接相关的问题；不得顺手格式化或改写用户受保护文件。

## Gate G：显式提交与推送

TASK-018 只暂存本任务允许范围内的文件。提交前执行：

```powershell
git diff --cached --name-only
git diff --cached --check
```

确认没有受保护文件后提交，建议信息：

```text
docs: complete Afeng production audit and operations handoff
```

然后推送当前分支，不新建分支、不 rebase。若推送失败，如实报告，不得改写历史。

## 禁止事项

- 不重新生成、改写或覆盖 v002.6；
- 不调用模型重做课程方法；
- 不创建 v2 Dataset，不迁移 embedding；
- 不修改或删除旧 economy Dataset、正式 Dataset、实验 Dataset、Docker volume；
- 不停止或修改 `cpa`；
- 不输出或提交任何 secret；
- 不以 dry-run、脚本存在或旧报告冒充真实在线通过；
- 不用人工改 JSON 伪造 PASS；
- 不使用 `git add .`、`commit -a`、reset、rebase。

## 最终汇报格式

1. TASK-017 收口 commit/push；
2. TASK-018 commit/push；
3. 生产审计各 section 的 PASS/FAIL；
4. bundle/map/remote/indexing/exclusion 精确数量；
5. 检索 18/20 与应用 20/20 的报告路径；
6. 备份 manifest 和恢复 dry-run 结果；
7. Ruff/Pyright/Pytest 的版本、数量、耗时；
8. 工作区受保护文件仍未暂存的证明；
9. 剩余阻塞；没有则明确写“无”。
