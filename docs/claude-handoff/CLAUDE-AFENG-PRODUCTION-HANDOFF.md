# Claude Code 独立交接：阿峰 v002.6、Dify 知识库与生产验收

## 0. 你的任务

你正在接手一个没有此前会话上下文的本地项目：

```text
D:\Dev\VideoCaptioner
```

不要依赖聊天历史，本文件就是完整入口。请先审计当前 Git、代码、测试、离线产物和 Dify 真实状态，
然后从第一个未完成任务继续执行：

```text
TASK-013 收尾验收
→ TASK-014 构建不可变 v002.6
→ TASK-015 正式 high_quality Dataset 与 embedding
→ TASK-016 同步、索引和检索验收
→ TASK-017 “阿峰”应用
→ TASK-018 生产终审、备份与运维交接
```

使用持续执行方式：审计 → 实现 → 目标测试 → 修正 → 全量测试 → 文档 → 显式文件提交 → push →
下一任务。不要只输出计划，不要因为普通错误、长耗时或权限确认停下来。

## 1. 必须先完整阅读

按顺序读取：

```text
docs/claude-handoff/CLAUDE-AFENG-PRODUCTION-HANDOFF.md
docs/audit/TASK-013-READONLY-AUDIT.md
docs/tasks/README.md
docs/tasks/STATUS.md
docs/tasks/TASK-013-afeng-stable-identity.md
docs/tasks/TASK-014-afeng-v0026-review.md
docs/tasks/TASK-015-dify-indexing-readiness.md
docs/tasks/TASK-016-dify-sync-retrieval.md
docs/tasks/TASK-017-afeng-dify-application.md
docs/tasks/TASK-018-production-audit-handoff.md
docs/afeng-method-layer.md
docs/afeng-next-execution-plan.md
docs/cursor-handoff/DIFY-STATUS.md
docs/evaluation/afeng-twenty-course-v002.md
docs/evaluation/afeng-twenty-course-v002.json
data/dify/afeng-release-v002.5/manifest.json
```

如果文档与真实代码、Git 或 Dify API 状态冲突，以可重复验证的真实状态为准，并修正文档。

## 2. 当前 Git 快照

交接编写时的状态：

```text
branch: cursor/afeng-canonical-id-dify-bundle
HEAD: 2b2cf70 feat: 稳定阿峰 canonical ID 并完善 Dify 发布包校验
origin/master: 765070b docs: 验收后清理 Dify 状态并加固冒烟检索
HEAD 相对 origin/master: ahead 1
```

`2b2cf70` 是 Cursor 遗留的 TASK-013 实现提交，尚未推送。不要丢弃、重置或重新从 master 实现。

开工必须运行：

```powershell
git status --short --branch
git log -8 --oneline --decorate
git rev-list --left-right --count origin/master...HEAD
git show --stat --oneline 2b2cf70
git diff --check
```

交接时存在以下未提交内容：

```text
docs/tasks/TASK-013-afeng-stable-identity.md
docs/tasks/STATUS.md
scripts/verify_afeng_release_bundle.py
src/course_video_analyzer/knowledge/afeng_pipeline.py
docs/cursor-handoff/CCSWITCH-NEXT-AFENG-DIFY-PRODUCTIONIZATION.md
docs/claude-handoff/CLAUDE-AFENG-PRODUCTION-HANDOFF.md
```

其中 TASK-013 文档、状态、类型注解和未使用 import 修正是 Cursor 提交后的收尾，必须审查后保留，
不要直接恢复。

以下文件/目录可能是用户原有内容或其他会话产物，必须保留，除非任务明确需要，否则不要提交：

```text
.claude/
docs/evaluation/afeng-five-course-v002.md
docs/evaluation/evidence-C001-C020.md
docs/当前系统事实审计-视频课程与Dify.md
```

`docs/audit/TASK-013-READONLY-AUDIT.md` 是只读审查证据。先验证其发现，再决定是否作为 TASK-013
收尾交付提交，不得把报告结论当成无需复核的事实。

严格禁止：

```text
git add .
git commit -a
git reset --hard
git checkout -- <用户文件>
git clean -fd
```

每个任务使用明确文件列表；提交前检查：

```powershell
git diff --cached --name-only
git diff --cached --check
```

## 3. 产品目标和角色边界

系统流程：

```text
视频课程
→ ASR / 说话人 / OCR / 时间轴
→ 事实证据 P01～P04
→ 阿峰课程方法提炼
→ 课程忠实度审查
→ 发布分类
→ Dify 知识库
→ “阿峰”课程方法应用
```

“阿峰”是课程方法复现角色；Dify 是知识库和应用平台，不是角色名称。

当前方法层只做：

```text
课程方法提炼
→ 课程忠实度审查
→ 发布分类
```

不要新增独立安全审查闸门。所有分析、策略和回复必须来自课程证据；不使用外部心理学、社会学或个人
经验纠正课程；课程未覆盖时返回证据不足；课程观点表达为“按照课程方法”或“课程将其解释为”；不得
把课程推测升级为客观事实。

## 4. 已完成的事实证据层

```text
课程: 20
案例: 40
segments: 80,264
OCR segments: 4,121
raw/P01/P02/P03/P04 QA: 全部通过
P04 案例外 evidence: 0
baseline: data/catalog/evidence-baseline-C001-C020.json
```

报告：

```text
docs/evaluation/evidence-C001-C020.md
docs/evaluation/evidence-C001-C020.json
```

不要重跑 ASR/OCR，不修改 P01～P04，不重新生成前 20 课。

## 5. 已完成的阿峰方法层

```text
pipeline_version: afeng-method-v001
prompt_version: mimo-method-v002
C001～C015 model: mimo-v2.5-pro
C016～C020 model: glm-5-2-260617[1M]
```

最终状态：

```text
40 cases
36 published
2 manual_review:
  C006/CASE-C006-001
  C008/CASE-C008-002
2 rejected:
  C014/CASE-C014-001
  C015/CASE-C015-001
0 failed
```

历史离线包：

```text
data/dify/afeng-release-v002.5/
documents=36
exclusions=4
```

v002.1～v002.5 都是历史不可变产物，禁止覆盖。

## 6. Dify 当前真实状态

```text
official Dify: 1.15.0
deploy root: D:\Dev\dify-deploy
URL: http://127.0.0.1:3080
working Dataset: 阿峰课程方法库-研究版
mode: economy
documents: 36
indexing: 36/36 completed
keyword retrieval: 有真实命中
semantic/high_quality retrieval: 当前不可用，未配置 embedding Provider
LLM Provider: 当前未配置
```

Dify 容器当前运行；`dify-api-1`、Postgres 等健康。`cpa` 运行在 8317，禁止停止、删除或修改。

凭据只位于：

```text
D:\Dev\dify-deploy\secrets\admin.env
D:\Dev\dify-deploy\secrets\dify-runtime.env
```

脚本可以安全加载，但禁止打印、复制、提交或写入 Prompt。不得把 Claude Code、CC Switch、Cursor 的
Token 当作 Dify embedding/LLM Token。

已有 economy Dataset 是历史/工作库，必须保留，不删除、不清空、不冒充最终语义库。

正式目标：

```text
Dataset: 阿峰课程方法库-研究版-v1
mode: high_quality
bundle: only data/dify/afeng-release-v002.6/
document map: 与旧工作库完全隔离
```

## 7. TASK-013 当前状态和必须先处理的问题

Cursor 提交 `2b2cf70` 已实现：

- `AFENG-{course_id}-{case_id}` canonical ID；
- draft/audit/publication/manifest/bundle 的 ID 归一；
- bundle 血缘字段；
- Dify metadata 以 course+case 计算 canonical ID；
- bundle 校验脚本和相关测试。

Cursor 声称当时验证：

```text
pytest: 263 passed, 1 skipped
Ruff: pass
Pyright: 0 errors
```

Claude 必须重新运行验证，不要只相信说明。

独立只读审查发现：当前 `data/dify/document-map.json` 的 36 个键仍是历史非 canonical ID，canonical
键数量为 0。如果拿 v002.6 对旧 map/旧 Dataset 直接同步，会走 create 并产生 36 个重复文档。

处理原则：

1. TASK-014 可以先做，因为它是离线构建且禁止真实导入；
2. TASK-015/016 前必须消除重复风险；
3. 推荐正式 v1 Dataset 使用独立新 map，旧 economy Dataset 和旧 map 保留为历史；
4. 如果选择更新旧 Dataset，必须先提供经过测试的一次性 map canonical 迁移，证明 update/skip，
   绝不能直接 create 36；
5. 不允许通过删除旧 Dataset 掩盖问题。

TASK-013 收尾动作：

1. 审查 `2b2cf70` 和未提交差异；
2. 复核 `docs/audit/TASK-013-READONLY-AUDIT.md`；
3. 运行目标测试、全量 pytest、Ruff、Pyright；
4. 修正文档与实现不一致；
5. 用显式文件列表提交收尾；
6. push 当前分支；
7. 确认 TASK-014 Definition of Ready。

## 8. TASK-014：构建不可变 v002.6

不调用任何模型，确定性复用现有 40 案例终态，生成：

```text
data/dify/afeng-release-v002.6/
```

必须保持：

```text
40 cases
36 published
2 manual_review
2 rejected
0 failures
```

要求：

1. 36 篇发布文档、4 个 exclusion；
2. canonical ID 唯一；
3. `model`、`run_token/run_id`、`input_hash`、`content_sha256`、`source_summary`、
   `pipeline_version`、`prompt_version` 覆盖 100%；
4. Markdown frontmatter、manifest 和内容 hash 一致；
5. dry-run 不操作 Dify，结果应为 36 个唯一计划项、0 duplicate；
6. 不覆盖 v002.5。

生成 9 个重点案例审查包：

```text
C018-002
C018-003
C019-001
C020-002
C020-003
C006-001
C008-002
C014-001
C015-001
```

机器审查必须保留 `human_confirmation_required`，不能冒充真人确认。

## 9. TASK-015：正式 Dataset 和 embedding

先以 Dify 1.15.0 的真实插件/Provider 能力为准检查本地 embedding 接入，不能凭印象配置。

用户偏好用磁盘和本机计算换取长期调用成本，因此优先验证本地 embedding。候选优先评估：

```text
BAAI/bge-m3
```

根据 Dify 实际支持情况评估 Ollama、Xinference 或 OpenAI-compatible embedding。必须完成真实健康检查、
一次真实 embedding 调用和小样本语义检索，才能声称可用。

还必须：

- 移除同步代码对 indexing technique 的隐藏硬编码；
- CLI 显式支持 economy/high_quality 并在同步前校验；
- 正式 Dataset 使用独立 map；
- 不改已有 economy 工作库；
- 不改 `cpa`；
- 不泄露凭据。

只有本地方案经真实证据确认不可行，且没有合法外部 Provider 时，才允许标记 `external_blocked`。
暂停前必须完成所有不依赖 Provider 的代码、测试、探测和文档。

## 10. TASK-016：同步、索引和检索验收

只在正式 high_quality Dataset 真实可用后执行。

要求：

```text
source: data/dify/afeng-release-v002.6/documents
target: 阿峰课程方法库-研究版-v1
formal map: 36 canonical IDs
```

空正式库首次同步预期：

```text
create=36
failed=0
duplicate=0
indexing completed=36
```

第二次不改内容同步：

```text
skip=36
```

使用测试副本验证 changed content → update，不修改 immutable v002.6。

至少执行 20 个真实检索问题，覆盖课程、案例、方法、条件、限制、话术、时间戳和 evidence。建议目标：

```text
correct source in Top-5 >= 90%
metadata completeness = 100%
evidence ID coverage = 100%
timestamp/source traceability = 100%
manual_review/rejected retrieval = 0
```

生成 JSON 和 Markdown 报告。接口能访问不等于检索通过。

## 11. TASK-017：“阿峰”应用

只在 TASK-016 检索验收通过后执行。

流程：

```text
用户问题
→ 正式 Dataset 检索
→ 证据整理
→ 课程方法组织
→ 引用校验
→ 输出
```

输出必须区分：

```text
课程原话
课程总结
课程方法直接改写
跨课程组合
证据不足
```

每个主要判断必须包含：

```text
knowledge_id
course_id
case_id
time_range
evidence_ids
```

最终输出前必须校验引用关系。ID 不存在、证据不属于命中文档、时间范围缺失或证据不支持结论时，
不得发布该结论。

如果没有合法 Dify LLM Provider，完成 DSL、Prompt、JSON Schema、变量、20 问测试集、引用校验器、
导入和恢复文档，再如实标记 `external_blocked`；不得复制 Claude Code Token。

## 12. TASK-018：生产终审和运维交接

新增可重复、只读的最终审计入口，至少检查：

```text
cases=40
published=36
manual_review=2
rejected=2
bundle documents=36
bundle exclusions=4
published canonical IDs=36 unique
formal map=36
formal remote documents=36
indexing completed=36
exclusion leakage=0
duplicate canonical ID=0
stale map=0
```

审计失败必须返回非零和机器可读原因。补齐备份清单、恢复 dry-run、无上下文运维手册、最终 Markdown/
JSON 报告。后期没有 AI 介入时，程序也必须能按固定命令完成构建、同步、索引轮询、检索验收、应用
验收、备份和恢复。

## 13. 测试要求

每个任务先跑目标测试，每个可提交阶段必须运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pyright
```

Dify 任务还必须运行真实 Docker health、Dataset API、indexing 和 retrieve，不得只跑 mock。

失败处理：完整读取错误 → 定点修复 → 目标复测 → 全量复测。普通失败不是向用户提问的理由。

## 14. 提交和推送

建议每个任务独立提交：

```text
TASK-013: fix: finalize Afeng canonical identity handoff
TASK-014: feat: build Afeng release v002.6
TASK-015: feat: prepare high-quality Dify indexing
TASK-016: feat: sync and validate Afeng knowledge retrieval
TASK-017: feat: add Afeng Dify application
TASK-018: docs: finalize Afeng production operations handoff
```

只提交任务明确修改的文件。每个通过验收的提交推送当前分支；不要擅自 force push，不要把分支合并到
master，除非用户另行要求。

## 15. 允许暂停的唯一情况

仅允许：

1. 本地 embedding 接入经真实验证不可行，且无合法外部 embedding Provider；
2. 没有合法 Dify LLM Provider；
3. 外部网络/服务故障经多轮诊断仍无法恢复。

暂停前必须完成全部不依赖该外部条件的实现、测试、提交和文档，并写清：已完成内容、真实证据、唯一
阻塞、用户只需完成的一步、恢复命令。不要因权限弹窗、普通测试失败、耗时较长或上下文不足停顿。

## 16. 最终汇报

一次性汇报：

1. TASK-013～018 状态、commit、push；
2. canonical ID、lineage、hash 覆盖率；
3. v002.6 文档、排除项和 9 个审查包；
4. economy 工作库与 high_quality 正式库的隔离；
5. embedding Provider、模型和真实检索证据；
6. create/update/skip/failed/indexing 数量；
7. 20 问检索指标；
8. 阿峰应用、引用校验和 20 问应用指标；
9. 最终审计、备份、恢复和运维手册；
10. pytest/Ruff/Pyright；
11. 仍需真人确认或外部 Provider 的项目；
12. 明确区分代码完成、在线部署、入库完成、索引完成、检索通过和应用通过。

现在开始：读取全部指定文件，审计 `2b2cf70` 和未提交差异，完成 TASK-013 收尾后继续 TASK-014。
不要只回复计划。
