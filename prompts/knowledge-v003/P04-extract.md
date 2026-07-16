# P04 Extract v003 — 单案例证据化提取

输入只包含一个 P03 案例及其连续 segments。只提取该案例中能定位到 segment ID 的内容。
严格区分实际可观察内容、讲师观点、聊天原句和备选解释。

## 强制规则

1. 每个参与者、时间线事件、observation、instructor claim、outcome 和引用表达都必须带
   非空 `evidence_segment_ids`。
2. alternative explanation 必须带非空 `basis_evidence_segment_ids`，并明确是可能解释，不得写成事实。
3. 不得把“她一定在测试”、“潜台词是”等讲师判断写成 observation。
4. 不得根据常识补写原文没有的对话、心理、结果或人物身份。
5. 案例不完整时保留缺失，写入 `uncertainties`，不得为了形成完整故事而编造。
6. 表达原句只是课程证据与分析对象，此阶段不生成用户建议。

## 输出 JSON

```json
{
  "schema_version": "1.0",
  "prompt_version": "knowledge-v003-p04",
  "source_ids": ["C001"],
  "course_id": "C001",
  "case_id": "CASE-C001-001",
  "case_title": "",
  "summary": "",
  "participants": [{"role": "", "description": "", "evidence_segment_ids": []}],
  "timeline": [{"event_id": "EVT-001", "description": "", "epistemic_type": "observation|instructor_claim|quoted_statement|unknown", "evidence_segment_ids": []}],
  "observations": [{"id": "OBS-001", "text": "", "evidence_segment_ids": []}],
  "instructor_claims": [{"id": "CLM-001", "text": "", "evidence_segment_ids": []}],
  "alternative_explanations": [{"id": "ALT-001", "text": "", "basis_evidence_segment_ids": [], "confidence": 0.0}],
  "outcomes": [{"id": "OUT-001", "text": "", "status": "observed|claimed|uncertain", "evidence_segment_ids": []}],
  "quoted_expressions": [{"id": "QUO-001", "speaker_role": "", "text": "", "context": "", "evidence_segment_ids": []}],
  "evidence_spans": [{"evidence_id": "EVD-001", "segment_ids": [], "quote": ""}],
  "uncertainties": [{"field": "", "note": "", "evidence_segment_ids": []}],
  "confidence": 0.0
}
```

写入后重新解析 JSON，确认所有引用的 segment ID 均在输入案例范围内。
