# P01 Normalize v002 — 完整保留前提下的实际规范化

你负责清理课程转写稿。目标不是缩短文本，而是在逐段完整保留证据的前提下，让
`normalized_text` 真正可读、可用于后续案例拆分。

项目已经提供可复用的确定性实现。优先运行以下命令生成完整基线，再检查上下文相关错字和
规则例外，不要为每课重新编写一次性脚本：

```powershell
python -m course_video_analyzer.knowledge.cli normalize-p01 <course_id> <input> <output> `
  --prompt-version knowledge-v002-p01
```

若输出路径已经存在，不得覆盖；先验证现有结果或由外层调度器创建新版本路径。

## 不可违反的完整性约束

1. 每个输入时间段必须对应一个输出 segment，顺序、`start_ms`、`end_ms` 不得改变。
2. `raw_text` 必须逐字保存输入正文，禁止修正、删减或覆盖。
3. 不总结、不合并时间段、不删除口语内容、不新增原文没有的事实。
4. 听不清或无法判断时保留原文；不能靠想象补齐。

## normalized_text 必须执行的工作

1. 将明显的 ASCII 句末标点规范为中文标点，例如 `,`→`，`、`.`→`。`、`?`→`？`、`!`→`！`。
2. 修复明确的错别字、同音字和断句问题；必须能由相邻上下文支持。
3. 对明显的识别性重复、卡顿或断裂进行可读化，例如无语义的“就就”“然后然后”；如果重复
   可能是强调，则保留并写入不确定项。
4. 保留粗口、语气词、重复观点和课程原始表达，不进行价值美化。
5. 即使正文无需修改，也要检查标点；不能让全课 `changed_segment_count` 为 0，除非输入本身已
   全部规范，并在 `quality_metrics` 中说明证据。

## 角色与来源

- 原标签“导师”确定映射为 `teacher_a`，“学员”映射为 `student`；这是确定性映射，不得加入
  `uncertainties`，也不必为每段重复写 `edit_notes`。
- 不能确定具体人物时使用 `unknown`。
- `课板[...]` 使用 `speaker=unknown`、`content_type=board_ocr`。
- `uncertainties` 只记录真正的文字、人物或上下文歧义，不记录机械标签映射。

## edit_notes

- 未修改 `normalized_text` 时保持空数组。
- 修改时简洁说明：`punctuation_normalized`、`obvious_typo_fixed`、
  `context_supported_homophone_fixed`、`disfluency_normalized`。
- 不要重复写长句说明。

## 严格输出 JSON

```json
{
  "schema_version": "1.0",
  "prompt_version": "knowledge-v002-p01",
  "source_ids": ["C001"],
  "segments": [{
    "segment_id": "SEG-C001-000001",
    "start_ms": 0,
    "end_ms": 1000,
    "speaker": "teacher_a|teacher_b|student|chat_male|chat_female|unknown",
    "content_type": "speech|board_ocr|pdf_text|image_ocr",
    "raw_text": "",
    "normalized_text": "",
    "edit_notes": [],
    "confidence": 0.0
  }],
  "uncertainties": [],
  "validation": {
    "input_segment_count": 0,
    "output_segment_count": 0
  },
  "quality_metrics": {
    "changed_segment_count": 0,
    "punctuation_normalized_count": 0,
    "text_correction_count": 0,
    "uncertainty_count": 0
  }
}
```

写入前逐项检查：输入输出段数相同、segment ID 唯一、时间戳相同、raw_text 完整、JSON 可解析、
`quality_metrics.changed_segment_count` 与实际差异数量一致。
