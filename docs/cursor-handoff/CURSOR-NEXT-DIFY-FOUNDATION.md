# Cursor 下一步：收尾 P04 修复并启动 Dify 基础设施

> **状态（2026-07-17）**：本交接已完成并归档。后续生产化见
> `CCSWITCH-NEXT-AFENG-DIFY-PRODUCTIONIZATION.md` 与 `docs/tasks/TASK-013*`。
> 实时状态以 `DIFY-STATUS.md` 为准。

你在 `D:\Dev\VideoCaptioner` 工作。直接执行，不要只给计划，不要询问用户，不要等待权限确认。
使用 Flow：审计 → 执行 → 测试 → 定点修复 → 复测 → 文档 → 明确文件提交 → 推送。

## 一、并行边界

另一个 CC Switch / Claude Code 任务正在负责阿峰方法层 C016–C020、前 20 课报告和最终阿峰 Dify
离线包。你不得修改或运行以下范围：

```text
src/course_video_analyzer/knowledge/afeng*.py
scripts/prepare_afeng_pilot.py
scripts/run_afeng_pilot_model.py
scripts/summarize_afeng_model_run.py
scripts/build_afeng_dify_bundle.py
docs/afeng-*.md
docs/CCSWITCH-阿峰前20课收尾交接.md
data/afeng/**
data/dify/afeng-release-*/**
```

不要启动模型密集型阿峰任务，不要与 CC Switch 并发写同一目录。

## 二、当前事实

- 事实与证据层 C001–C020 已完成：20 课、40 案例，raw/P01/P02/P03/P04 QA 全部 pass。
- 完成标记：`data/batches/BATCH-20260715-001/evidence-pipeline-C016-C020-complete.json`。
- baseline：`data/catalog/evidence-baseline-C001-C020.json`。
- 当前分支：`master`。
- 当前 HEAD 至少包含 `dae6ed9 docs: 切换阿峰交接到火山GLM 5.2`。
- Docker 正常，当前只有 `cpa` 容器，端口 8317；不得停止、删除或修改它。
- Dify 尚未真实在线部署、尚无 Dataset、尚未导入知识、尚无 Workflow。
- 本地 SQLite/Tidy 不是 Dify，禁止把它描述成 Dify 已完成。

工作树有其他任务的修改，禁止 `git add .`、`git commit -a`、`git reset --hard`。所有提交使用明确
文件列表和 `git commit --only`。

## 三、任务 A：收尾 Cursor 遗留的 P04 v003 QA 修复

当前工作树已有以下三处修改：

```text
src/course_video_analyzer/knowledge/cli.py
src/course_video_analyzer/knowledge/extraction.py
tests/test_knowledge/test_extraction.py
```

修改目的：`qa-p04` 支持显式 `--prompt-version`，让 knowledge-v003 P04 QA 不再被 v002 默认值误判。

必须：

1. 审查 diff，确认参数由 CLI 一直传到 `validate_p04_output(expected_prompt_version=...)`。
2. 运行相关单测、Ruff、Pyright。
3. 若实现正确，使用仅包含上述三个文件的独立提交：

```text
fix: support versioned P04 QA
```

4. 不要把其他未提交报告或阿峰文件混入该提交。

## 四、任务 B：真实部署 Dify 基础设施

已有部署骨架：

```text
deploy/dify/README.md
deploy/dify/.env.example
deploy/dify/scripts/bootstrap.ps1
deploy/dify/scripts/up.ps1
deploy/dify/scripts/down.ps1
deploy/dify/scripts/health.ps1
deploy/dify/scripts/backup.ps1
src/course_video_analyzer/knowledge/dify_sync.py
tests/test_knowledge/test_dify_sync.py
```

执行要求：

1. 完整审查部署脚本和同步代码，不假设它们可用。
2. 核对官方 `langgenius/dify` Git tag；优先固定现有文档指定的 `1.15.0`，若官方不存在才选择
   最新稳定非 RC，并同步更新模板和文档。
3. 只使用官方仓库的 `docker/` Compose。
4. 部署根目录使用 `D:\Dev\dify-deploy`，运行数据不得提交到 VideoCaptioner Git。
5. 外部访问端口使用 3080；先检查端口占用。
6. `.env` 中的 SECRET_KEY 等本地必需随机值可以安全生成，但不得输出到聊天、日志或 Git。
7. 未提供的 LLM、embedding、Dify API Key 不得编造。
8. 启动 Dify Compose，等待容器进入可用/healthy；记录实际版本、容器、端口、数据卷和健康状态。
9. 确认 `cpa` 仍正常运行。
10. 运行 `health.ps1`；发现脚本问题则修复并增加可执行验证。
11. 做一次停止/恢复或至少验证脚本的 compose project/path 参数一致，不能误操作其他容器。
12. 不删除 Docker volume，不执行破坏性重置。

如果首次管理员创建必须通过 `/install` 页面人工完成：

- 不向用户发起中途询问；
- 先完成所有不依赖管理员账户的部署、健康检查和代码修复；
- 在最终报告明确写出唯一剩余人工步骤及 URL；
- 不声称 Dataset 或在线入库已完成。

## 五、任务 C：Dify 发布准备，但暂不导入阿峰文档

CC Switch 尚未完成最终前 20 课离线包，因此本次不得导入旧 v002.4 或更早包冒充最终结果。

需要完成：

1. 审查 `dify_sync.py` 和 CLI 是否支持：
   - knowledge ID ↔ Dify document ID 映射；
   - 内容 SHA-256 幂等 create/skip/update；
   - indexing 状态轮询；
   - 明确失败和重试；
   - API Key 仅从环境变量读取；
   - 日志不泄露密钥。
2. 补齐缺失的单元测试和无密钥 dry-run/参数验证。
3. 准备 `.env.example` 或配置说明，但不写真实密钥。
4. 写出最终包到达后的一条同步命令模板，输入目录使用占位：

```text
data/dify/afeng-release-v002.N/documents
```

5. 生成 `docs/cursor-handoff/DIFY-STATUS.md`，严格区分：
   - Docker 部署状态；
   - 管理员初始化状态；
   - Dataset 状态；
   - 文档同步状态；
   - indexing 状态；
   - Workflow/Chatflow 状态；
   - 真实检索验收状态。

## 六、验证与提交

执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pyright
```

已有基线至少为 251 passed、1 skipped。Dify Docker 相关集成验证不能破坏无 Docker 环境下的单测。

建议分两次提交：

1. `fix: support versioned P04 QA`
2. `feat: prepare and verify Dify deployment`

每次都使用明确文件列表和 `git commit --only`。推送 `origin/master`。网络失败时保留本地提交并重试。

## 七、最终汇报

一次性汇报：

1. P04 修复是否提交、commit hash；
2. Dify 实际版本、部署目录、访问 URL；
3. 容器和健康状态；
4. `cpa` 是否仍正常；
5. 管理员、Dataset、文档、indexing、Workflow、真实检索分别是完成还是未完成；
6. Dify 同步代码修复和测试；
7. pytest/Ruff/Pyright；
8. Git commit 与 push；
9. 唯一剩余人工步骤（如有）。

从现在开始执行。禁止输出任何 API Key、Token、密码或 `.env` 实际秘密。
