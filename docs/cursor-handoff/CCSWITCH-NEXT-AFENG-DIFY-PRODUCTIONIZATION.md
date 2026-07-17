# CC Switch / Claude Code 历史交接：阿峰知识库生产化 TASK-013～TASK-017

> 本文件保留作历史记录，不再作为最新执行入口。最新事实、TASK-018 和正式 Dataset 隔离要求见：
> `docs/cursor-handoff/CURSOR-NEXT-AFENG-V0026-PRODUCTION.md`。

你现在接手 `D:\Dev\VideoCaptioner` 的阿峰知识库生产化任务。你没有此前会话上下文；本文和本文列出的
任务文件就是完整上下文。使用 Flow 持续执行：审计 → 计划 → 实现 → 测试 → 定点修复 → 复测 →
文档 → 明确文件提交 → 推送。不要只给计划，也不要重复已经完成的前 20 课模型生产。

## 一、必须先读取

按顺序完整阅读：

```text
docs/tasks/README.md
docs/tasks/STATUS.md
docs/tasks/TASK-013-afeng-stable-identity.md
docs/tasks/TASK-014-afeng-v0026-review.md
docs/tasks/TASK-015-dify-indexing-readiness.md
docs/tasks/TASK-016-dify-sync-retrieval.md
docs/tasks/TASK-017-afeng-dify-application.md
docs/afeng-method-layer.md
docs/afeng-next-execution-plan.md
docs/cursor-handoff/DIFY-STATUS.md
docs/evaluation/afeng-twenty-course-v002.md
docs/evaluation/afeng-twenty-course-v002.json
```

每完成一个任务，必须更新 `docs/tasks/STATUS.md` 和相关状态文档。严格按
TASK-013 → 014 → 015 → 016 → 017 顺序执行，不跳过前置验收。

## 二、当前真实状态

仓库：

```text
workspace: D:\Dev\VideoCaptioner
branch: master
current completed commit: cddf315 docs: 规划阿峰知识库生产化任务
（含前置 bc3f032 Dify 初始化与 v002.5 同步）
remote: origin/master
```

事实与证据层：

- C001–C020 已完成；
- 20 课、40 案例；
- raw/P01/P02/P03/P04 QA 全部 pass；
- baseline：`data/catalog/evidence-baseline-C001-C020.json`。

阿峰方法层：

- 40 案例；
- 36 published；
- 2 manual_review：C006/CASE-C006-001、C008/CASE-C008-002；
- 2 rejected：C014/CASE-C014-001、C015/CASE-C015-001；
- 0 failed；
- C001–C015 使用 `mimo-v2.5-pro`；
- C016–C020 使用 `glm-5-2-260617[1M]`；
- 当前报告：`docs/evaluation/afeng-twenty-course-v002.md/.json`；
- 当前离线包：`data/dify/afeng-release-v002.5/`，36 文档、排除 4；
- v002.5 **已正式导入** Dify（economy，indexing 36/36 completed；keyword 有命中）；后续以 v002.6 canonical 迁移/更新为准。

仓库验证基线：

```text
pytest: 255 passed, 1 skipped
Ruff: pass
Pyright: 0 errors, 0 warnings
```

Dify：

- 官方 Dify 1.15.0 已在 `http://127.0.0.1:3080` 运行；
- Docker 容器健康；
- `cpa` 位于 8317，禁止停止、删除或修改；
- 管理员、Dataset「阿峰课程方法库-研究版」、Dataset API Key 已完成；
- `afeng-release-v002.5` 36 文档已导入且 indexing completed；历史 SMOKE 已从 map 清除；
- 当前无 embedding，semantic/`high_quality` 不可用；
- keyword retrieve 对正式库有命中；
- Chatflow DSL 已准备，控制台可回答应用未创建（缺 LLM）；
- 本地密钥仅在 `D:\Dev\dify-deploy\secrets\`（及兼容旧文件），禁止打印或提交。

## 三、本轮审查发现的必须修复问题

### 1. knowledge ID 不是系统稳定标识

v002.5 的 36 个文档中，统一 canonical ID 数量为 0。现有 ID 包含中文、英文、哈希和不同格式。
`afeng_pipeline.py` 先生成 canonical ID，但随后执行 `manifest.knowledge_id = draft.knowledge_id`，让模型
重新控制远端幂等主键。相同案例重新运行可能在 Dify 中 create duplicate。

必须改为程序控制：

```text
AFENG-{course_id}-{case_id}
示例：AFENG-C007-CASE-C007-001
```

### 2. 缺少逐文档模型和运行血缘

v002.5 manifest 的 36 个文档都没有 `model` 字段，不能直接判断文档来自 MiMo 还是 GLM。必须增加
model、run token/run ID、input hash、source summary 等字段，并同步进入 Markdown metadata、bundle
manifest 和 Dify document map。

### 3. Dify indexing 模式不一致

正式 Dataset 当前是 economy，但 `create_dataset` / `create_document_by_text` 把 high_quality 写死。
当前又没有 embedding，因此不能直接把 v002.5/v002.6 当作可用语义知识库导入。必须让模式显式可配，
并在同步前验证 Dataset/文档模式一致。

### 4. 仍需内容抽检

C016–C020 的 10 个案例确定性 QA 全部通过，但生成和忠实度审查使用同一个 GLM，程序闸门不能替代
语义人工复核。尤其检查：C018-002、C018-003、C019-001、C020-002、C020-003，以及历史的
C006-001、C008-002、C014-001、C015-001。

## 四、执行规则

1. 使用 CC Switch 当前火山 Coding Pro 配置时，Agent 模型显式使用
   `glm-5-2-260617[1M]`；
2. TASK-013/014 不允许重新调用模型生成 40 个案例；必须复用现有终态并确定性迁移；
3. 不覆盖 `data/dify/afeng-release-v002.1`～`v002.5`；新包固定使用 v002.6；
4. 不把 manual_review/rejected 改成 published；
5. 不修改 P01–P04；
6. 不使用 CC Switch Token 作为 Dify embedding/LLM Token；
7. 不编造 embedding、LLM、Dify API Key 或管理员密码；
8. 不输出或记录任何密钥；
9. 不删除 Docker volume；
10. 不停止 `cpa`；
11. 真实索引和检索未通过前，不宣称知识库完成；
12. Workflow 未真实创建和验收前，不宣称“阿峰应用”完成。

## 五、工作树与 Git 边界

开工必须运行：

```powershell
git status --short
git log -5 --oneline
```

当前可能存在不属于本任务的工作树内容：

```text
.claude/
docs/evaluation/afeng-five-course-v002.md
docs/evaluation/evidence-C001-C020.md
docs/cursor-handoff/CURSOR-NEXT-DIFY-FOUNDATION.md
docs/当前系统事实审计-视频课程与Dify.md
```

保留这些内容，不要随意删除、恢复或混入提交。禁止：

```text
git add .
git commit -a
git reset --hard
git checkout -- <user files>
```

每个 TASK 独立提交，使用明确文件列表和 `git commit --only`。推荐提交：

```text
TASK-013: feat: stabilize Afeng knowledge identity
TASK-014: feat: build Afeng release v002.6
TASK-015: feat: make Dify indexing mode explicit
TASK-016: feat: sync and validate Afeng Dify knowledge
TASK-017: feat: add Afeng Dify application workflow
```

每个通过验收的提交都推送 `origin master`。网络失败保留本地提交并重试，不回滚。

## 六、测试要求

每个任务至少运行目标测试；每个可提交阶段必须运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pyright
```

不得低于当前基线。Dify 相关任务还必须执行真实 health、dry-run、indexing 和 retrieve 验收，不能只跑
mock 单测。

## 七、外部阻塞处理

TASK-015/017 可能缺少 embedding 或 Dify LLM 供应商密钥。处理规则：

1. 先完成所有不依赖密钥的代码、测试、配置模板、部署检查和文档；
2. 检查本机是否已有合法配置，但不得显示密钥；
3. 没有配置时，把任务标记为 `external_blocked`，准确写明需要哪类配置和控制台位置；
4. 不得用假密钥、CC Switch Token 或 economy 冒充 high_quality；
5. TASK-015 未达到正式 Dataset 可用状态时，不执行 TASK-016；
6. TASK-016 未通过时，不执行 TASK-017。

这类真实外部依赖是唯一允许暂停的原因。不要因普通测试失败、代码问题或长时间任务向用户提问。

## 八、最终汇报

每个任务完成后记录：

- 修改文件；
- 核心设计；
- 测试结果；
- 真实外部状态；
- commit hash 和 push 结果；
- 下一任务是否满足 Definition of Ready。

全部可执行任务完成后一次性汇报：

1. canonical ID 和模型血缘是否覆盖 40 案例；
2. v002.6 文档数、排除数、hash/dry-run 结果；
3. 重点案例审查结论和仍需真人确认项；
4. 正式 Dataset 名称、模式和 embedding 状态；
5. Dify create/update/skip/failed/indexing 数量；
6. 20 问检索验收结果；
7. Workflow/Chatflow 状态和 DSL；
8. pytest/Ruff/Pyright；
9. 所有提交和 push；
10. 明确区分“代码准备完成”“Dify 平台在线”“正式文档入库”“索引完成”“检索通过”“应用完成”。

现在开始：完整阅读任务文件，审查工作树，然后从 TASK-013 直接执行。除真实外部密钥阻塞外，不要
只给计划、不要询问用户、不要等待权限确认。
