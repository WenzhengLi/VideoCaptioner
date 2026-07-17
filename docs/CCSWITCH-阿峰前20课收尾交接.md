# CC Switch / Claude Code 交接：完成阿峰前 20 课方法层

你现在接手 `D:\Dev\VideoCaptioner` 项目的“阿峰方法层”收尾任务。你没有此前会话上下文，本文就是
完整上下文和执行要求。请采用 Flow 工作方式持续执行：检查 → 计划 → 执行 → 验证 → 定点修复 →
重新验证 → 报告 → 提交推送。不要停下来询问用户，不要要求用户确认权限；在安全且属于本任务范围
时自行判断并完成。只有确实需要新的外部授权、密钥或不可逆决策时才停止。

## 1. 项目目标与角色边界

- “阿峰”是课程方法复现角色，不是独立情感专家。
- Dify 是后续知识库存储、检索和应用编排平台，不是角色名称。
- 固定流程：课程方法提炼 → 课程忠实度审查 → 发布分类。
- 本链路不做安全审查，不评价课程观点是否科学或正确。
- 所有主要判断必须来自课程 evidence；课程观点使用“按照课程方法”“课程将其解释为”等归属表达。
- 禁止把课程推测升级为客观事实，禁止补充课程外技巧、术语和结果。
- evidence 不足时必须保留不足、人工复核或拒绝，不能为了发布而改写绕过闸门。

## 2. 当前仓库事实

- 工作目录：`D:\Dev\VideoCaptioner`
- 当前分支：`master`
- 当前已推送提交：`35913d4 feat: 完成阿峰十五课方法层验收`
- C001–C020 事实与证据层已完成：20 课、40 案例，raw/P01/P02/P03/P04 QA 全部 pass。
- baseline：`data/catalog/evidence-baseline-C001-C020.json`
- 事实层报告：
  - `docs/evaluation/evidence-C001-C020.md`
  - `docs/evaluation/evidence-C001-C020.json`
- 全量测试基线：251 passed、1 skipped；Ruff pass；Pyright 0 errors。

工作树中可能仍有其他人的未提交修改，例如：

```text
src/course_video_analyzer/knowledge/cli.py
src/course_video_analyzer/knowledge/extraction.py
tests/test_knowledge/test_extraction.py
docs/当前系统事实审计-视频课程与Dify.md
```

这些不属于本次默认提交范围。不得执行 `git add .`、`git commit -a`、`git reset --hard` 或覆盖用户
修改。提交必须使用明确文件列表和 `git commit --only`。

## 3. 已完成的阿峰结果

流水线版本：

```text
pipeline_version: afeng-method-v001
prompt_version: mimo-method-v002
model: mimo-v2.5-pro
executor: CC Switch 配置 → Claude Code CLI headless
```

十五课正式报告：

```text
docs/evaluation/afeng-fifteen-course-v002.md
docs/evaluation/afeng-fifteen-course-v002.json
```

十五课结果：

- 30 案例；
- 26 published；
- 2 manual_review：C006/CASE-C006-001、C008/CASE-C008-002；
- 2 rejected：C014/CASE-C014-001、C015/CASE-C015-001；
- 0 unresolved failure；
- Dify 离线包：`data/dify/afeng-release-v002.4/`，26 文档、排除 4；
- 尚未进行 Dify 在线部署或入库。

已有十五课运行 summary，最终 20 课聚合时必须复用：

```text
data/afeng/model-runs/C003-C006-C010-baseline-v001/c003-v002/model-run-summary.json
data/afeng/model-runs/C003-C006-C010-baseline-v001/c006-v002/model-run-summary.json
data/afeng/model-runs/C003-C006-C010-baseline-v001/c010-v002/model-run-summary.json
data/afeng/model-runs/C003-C006-C007-C010-C012-baseline-C020-v002/new-courses-v002/model-run-summary.json
data/afeng/model-runs/C001-C015-baseline-C020-v002/remaining-ten-v002/model-run-summary.json
data/afeng/model-runs/C001-C015-baseline-C020-v002/repair-v002/model-run-summary.json
```

## 4. 前 20 课正式输入包

已经准备完成：

```text
data/afeng/pilots/C001-C020-baseline-v002/manifest.json
```

验收事实：

- status=ready；
- 40 案例；
- failures=0；
- C001–C015 的 30 个 evidence package 与十五课正式包逐文件 SHA-256 一致，禁止重跑；
- C016–C020 共 10 个新案例；
- 10 个新案例全部使用 knowledge-v003 P04；
- evidence QA pass；
- required evidence coverage=1.0；
- external_payload_safe=true。

此前 C016–C020 运行被用户要求交接时中止，现有部分状态：

```text
run root: data/afeng/model-runs/C001-C020-baseline-v002/C016-C020-v002/
C016/CASE-C016-001: failed
C017/CASE-C017-001: published
C018/CASE-C018-001: running（中止时状态，需恢复或重建 summary）
其余案例尚未完成
```

不要删除这些产物。先检查 run manifest 和失败原因，再使用相同 run-name 恢复；终态 published、
manual_review、rejected 会自动复用。若失败 run 因缓存的非法模型产物无法恢复，使用新的
`C016-C020-repair-v002` run-name 仅补跑失败 case IDs，保留原始失败审计记录。

## 5. 必须完成的任务

### A. 检查环境和工作树

1. `git status --short`，记录但不要清理他人修改。
2. 验证 `.venv\Scripts\python.exe` 可用。
3. 验证 CC Switch 的 Claude 用户配置可用，但禁止打印 API Key、Token 或完整 settings 内容。
4. 检查是否仍有旧的 `run_afeng_pilot_model.py`、Claude 或 Node 孤儿进程；仅终止明确属于
   `C016-C020-v002` 且已失去父任务的孤儿进程。

### B. 恢复并完成 C016–C020

先运行：

```powershell
.\.venv\Scripts\python.exe scripts\run_afeng_pilot_model.py `
  data\afeng\pilots\C001-C020-baseline-v002\manifest.json `
  --run-name C016-C020-v002 `
  --courses C016,C017,C018,C019,C020 `
  --executor cc-switch `
  --model mimo-v2.5-pro `
  --timeout-seconds 900 `
  --max-retries 3 `
  --max-revisions 2 `
  --max-budget-usd 5
```

要求：

- 每个案例由独立、无会话持久化的 Claude Code 模型调用处理，不共享上下文。
- 不因单案例 manual_review/rejected 停止；这两种是合法终态。
- 程序失败必须读取准确原因并定点修复。
- 不对同一输入重复模型调用；优先复用缓存。
- 不手工替模型撰写课程方法内容；修复应沉淀为保守、可复用代码。
- 所有 evidence IDs 必须属于当前 evidence package。
- 最多两轮修订；仍不通过则 manual_review，禁止强行发布。

若存在失败案例：

1. 汇总失败 case IDs 和错误类型；
2. 对可确定性修复的格式问题增加通用代码与测试；
3. 使用新 run-name `C016-C020-repair-v002` 只补跑失败案例；
4. repair summary 中形成终态后，最终聚合器应把旧失败视为已解决；
5. 不覆盖原始失败 run。

### C. 生成 C016–C020 和完整 20 课报告

使用 `scripts/summarize_afeng_model_run.py`。该脚本支持多 summary 聚合，会拒绝重复终态案例，并会
在 repair summary 已有终态时消除旧 summary 的对应失败。

先生成新增五课报告：

```text
docs/evaluation/afeng-C016-C020-v002.md
docs/evaluation/afeng-C016-C020-v002.json
```

再把第 3 节列出的 6 个十五课 summary，加上 C016–C020 主 summary 和可能存在的 repair summary，
聚合成：

```text
docs/evaluation/afeng-twenty-course-v002.md
docs/evaluation/afeng-twenty-course-v002.json
```

验收：

- case_count=40；
- failure_count=0；
- status=complete；
- 每个 course_id/case_id 只出现一次；
- 统计 published/manual_review/rejected；
- 汇总 revision、publication class、tokens、模型耗时和估算成本；
- 人工复核与拒绝案例必须明确列出，不得计入发布。

### D. 构建最终 Dify 离线包

使用 `scripts/build_afeng_dify_bundle.py`，输入完整 20 课所需的所有 run summaries。

- 不覆盖 v002.1、v002.2、v002.3、v002.4。
- 优先使用 `data/dify/afeng-release-v002.5/`；如果已存在且内容不同，自动选择下一个未占用版本。
- 发布器只能收集：status=published、audit pass、release_allowed=true、approved reviewed、
  publication publishable=true 且非 reject、身份字段一致的 Markdown。
- 检查 manifest 文档数、排除数、排除原因、prompt_version 和文件 SHA-256。
- 本任务只生成离线包，不启动 Dify，不声称在线入库。

### E. 审查结果，不绕过闸门

重点检查：

1. C016–C020 是否出现 invalid evidence、课程外概念或课程观点客观化；
2. revision 后是否真正消除审查问题；
3. manual_review/rejected 是否合理；
4. C014/C015 的历史拒绝和 C006/C008 的历史人工复核继续保持，不强行改变；
5. 发布 Markdown 中每个主要判断有 evidence IDs、课程归属表达和时间范围。

如果发现系统性问题，修复 Prompt 或通用代码，使用新版本和新运行目录做定点回归；禁止修改已发布
历史文件来伪造通过。

### F. 文档、测试和 Git

更新：

```text
docs/afeng-method-layer.md
docs/afeng-next-execution-plan.md
docs/cursor-handoff/STATUS.md
```

必须运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pyright
```

预期至少不低于当前基线：251 passed、1 skipped；Ruff pass；Pyright 0 errors。

提交前执行 `git diff` 和 `git status --short`。仅提交本任务明确修改的阿峰代码、测试、报告和上述
文档。禁止混入他人的 `cli.py`、`extraction.py`、`test_extraction.py` 等在途修改，除非你能证明它们
是本次修复必需且已完整审查。

推荐提交信息：

```text
feat: 完成阿峰前20课方法层验收
```

使用明确文件列表执行 `git add -- <files>` 和 `git commit --only ... -- <files>`，然后：

```powershell
git push origin master
```

网络失败时保留本地提交并重试，不得回滚。

## 6. 最终汇报格式

全部完成后一次性汇报：

1. C016–C020 10 案例各状态和修订轮数；
2. 前 20 课 40 案例 published/manual_review/rejected/failed 总数；
3. 所有人工复核和拒绝案例及原因；
4. 程序失败、修复方式和是否增加测试；
5. 完整报告路径；
6. 最终 Dify 离线包路径、文档数和排除数；
7. pytest/Ruff/Pyright 结果；
8. commit hash 和 push 结果；
9. 明确说明：Dify 是否真实在线部署和入库（本任务默认答案应为“否，仅完成离线包”）。

从现在开始直接执行，不要只给计划，不要询问用户，不要输出或记录任何密钥。
