# P02 Classify v002 — 内容来源、知识属性与相关性标注

输入为通过 P01 QA 的 JSON。只做分类，不得再次改写、删除或合并文本。

项目提供了可复用的保守分类基线。优先运行：

```powershell
python -m course_video_analyzer.knowledge.cli classify-p02 <course_id> <p01> <baseline-output>
```

Cursor 应审核 baseline JSON 并写入新的最终输出文件，重点修正“讲师复述实际聊天”“学员复述案例”
以及营销误判，不能为每课重写机械分类程序。最终 `prompt_version` 必须为
`knowledge-v002-p02`。

输入若已经是 P02 baseline JSON，保留全部 P01 字段，只审核新增分类字段，并增加：

```json
"review_metrics": {
  "baseline_segment_count": 0,
  "reviewed_segment_count": 0,
  "classification_change_count": 0,
  "remaining_uncertain_count": 0
}
```

## 完整性约束

1. 每个输入 segment 对应一个输出 segment，顺序和 segment ID 不变。
2. `start_ms`、`end_ms`、`speaker`、`content_type`、`raw_text`、`normalized_text`、
   `edit_notes` 和 P01 `confidence` 必须原样保留。
3. 不总结课程，不拆案例，不推测人物心理，不生成建议。

## 新增分类字段

### source_role

- `instructor_explanation`：讲师解释、评价、示范或复盘。
- `actual_chat`：有明确证据表明是案例中的实际聊天原句。
- `student_question`：学员提问或反馈。
- `board`：课板、PPT、共享屏幕或截图 OCR，但无法进一步确定其内部语义。
- `pdf`：PDF 原文。
- `marketing`：课程推销、联系方式、群宣传或无关广告。
- `unknown`：证据不足。

### epistemic_type

- `observation`：视频、聊天或结果中直接可观察的事实。
- `instructor_claim`：讲师给出的解释、判断、原则或因果说法。
- `quoted_statement`：可明确识别的原话引用。
- `model_inference`：只能通过上下文推断的分类；不得当作事实。
- `unknown`：无法判断。

### relevance

- `core`：案例对话、关键讲解、判断依据或明确结果。
- `supporting`：辅助解释、过渡但仍有知识价值。
- `boilerplate`：寒暄、直播流程、广告、联系方式、重复营销。
- `uncertain`：上下文不足，暂不删除。

## 判断规则

1. `speaker=student` 通常是 `student_question`，但学员复述聊天时可标 `actual_chat`；必须在
   `classification_reasons` 说明证据。
2. `speaker=teacher_a|teacher_b` 通常是 `instructor_explanation`；只有明确引用聊天原话时才是
   `actual_chat` 或 `quoted_statement`。
3. `content_type=board_ocr` 默认 `source_role=board`。OCR 出现聊天句子并不自动证明说话人身份。
4. “对方一定在想什么”“这是测试”等讲师判断标为 `instructor_claim`，不能标 observation。
5. 无法确认时使用 `unknown/uncertain`，不要为了填满分类强行判断。

## 输出 JSON

```json
{
  "schema_version": "1.0",
  "prompt_version": "knowledge-v002-p02",
  "source_ids": ["C001"],
  "segments": [{
    "segment_id": "SEG-C001-000001",
    "start_ms": 0,
    "end_ms": 1000,
    "speaker": "teacher_a",
    "content_type": "speech",
    "raw_text": "",
    "normalized_text": "",
    "edit_notes": [],
    "confidence": 0.9,
    "source_role": "instructor_explanation",
    "epistemic_type": "instructor_claim",
    "relevance": "core",
    "classification_reasons": ["讲师对案例作判断"],
    "classification_confidence": 0.9
  }],
  "uncertainties": [],
  "validation": {
    "input_segment_count": 0,
    "output_segment_count": 0
  },
  "classification_metrics": {
    "source_role_counts": {},
    "epistemic_type_counts": {},
    "relevance_counts": {},
    "uncertain_segment_count": 0
  }
}
```

写入后重新解析 JSON，并确认 P01 字段逐段完全一致、分类枚举合法、计数与实际 segments 一致。
