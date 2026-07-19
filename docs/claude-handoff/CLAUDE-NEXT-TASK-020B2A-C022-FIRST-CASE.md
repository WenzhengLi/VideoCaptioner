# Claude 下一步：TASK-020B2A C022 首案例受控生产

## 工作方式改变

这次不要整课批量生成 P04，也不要在最终报告中写 `all_passed=true` 或自行批准进入下一阶段。

任务只完成：

```text
C022 P01
C022 P02
C022 P03
P03 中第一个边界清晰、completeness=complete 的案例 P04
```

完成后提交、推送并停止，交给独立验收。

## Gate 0：开始前检查

确认：

```text
branch: cursor/afeng-canonical-id-dify-bundle
HEAD 与 origin 同步
C021 final report 和三案 P04 QA 均存在且 pass
C022 原始 analysis/timeline/QA 已存在
```

保护现有用户未提交文件。禁止 `git add .`、`commit -a`、reset、rebase、amend 或新建分支。

## Gate 1：P01 与 P02

从 C022 原始 timeline 构建 P01、P02，使用 `knowledge-v003`。

同时生成：

```text
data/batches/BATCH-C021-C025-V003/C022-P01-semantic-sample.json
data/batches/BATCH-C021-C025-V003/C022-P02-semantic-sample.json
```

- P01：至少 50 条 changed segments，区分实质修复、标点规范、neutral、degraded；
- P02：至少 60 条，覆盖 instructor_explanation、actual_chat、board、unknown/marketing；
- expected_role 必须根据文本语义独立判断，不能直接复制 source_role；
- 运行正式 P01/P02 QA。

## Gate 2：P03 案例边界

按 `prompts/knowledge-v003/P03-segment-cases.md` 生成 P03。

逐个检查：

- 新人物、地点、聊天记录或明确“下一个”转场；
- 起止证据前后至少各看 10 个 segments；
- 通用讲解、广告、调试不要强行变成案例；
- cases 与 unassigned 必须完整覆盖且不重叠；
- 标题使用人物/事件型内容，不使用“第一个案例”等泛化标题。

运行正式 P03 QA，并生成边界复核记录。

## Gate 3：只生产一个 P04

从 P03 中选择第一个：

```text
completeness=complete
confidence >= 0.75
起止证据明确
```

仅为该案例构建 P04 input 和 output。禁止继续生成第二个案例。

P04 内容要求：

- timeline 描述必须是证据原文的保守概括；
- 一个 segment 不足时引用连续相邻上下文；
- observation 与 instructor_claim 分离；
- quoted_expression 与 evidence 原文一致；
- outcome 未展示则明确 uncertain；
- evidence 选择来自真实内容节点，不按时间等距抽取。

## Gate 4：生产时同步对齐

生成：

```text
data/batches/BATCH-C021-C025-V003/C022-first-case-semantic-alignment.json
```

对 P04 的全部 timeline、observations、instructor_claims、quoted_expressions、evidence_spans 记录：

```json
{
  "field": "timeline",
  "item_id": "EVT-001",
  "statement": "...",
  "evidence": [{"segment_id": "...", "text": "..."}],
  "alignment_reason": "说明原文如何支持 statement"
}
```

不得自动将所有条目标记 aligned；找不到证据时立即修改 P04。

## Gate 5：验证、报告和提交

运行正式 P01/P02/P03/P04 QA，以及：

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pyright
.\.venv\Scripts\python.exe -m pytest -q
```

生成：

```text
data/catalog/evidence-baseline-C022-pilot.json
docs/evaluation/evidence-C022-first-case.md
data/batches/BATCH-C021-C025-V003/task-020b2a-report.json
```

报告最终状态必须是：

```json
"status": "ready_for_independent_review"
```

不能写 `approved`、`all_passed` 或允许继续整课。

建议提交：

```text
feat: build C022 first-case evidence pilot
```

显式暂存本任务文件，提交并 push，确认 HEAD 与 origin 同步后停止。

## 最终汇报

1. P01/P02 抽检统计；
2. P03 案例数、标题、边界和 unassigned；
3. 被选中的首个案例及选择理由；
4. P04 各字段数量和 applied thresholds；
5. statement/evidence 全量对齐结果；
6. QA 与代码门禁；
7. commit hash 与 push；
8. 明确声明等待独立验收，没有处理第二个案例。
