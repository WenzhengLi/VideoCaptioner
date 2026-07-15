# P06 Tidy — 原子知识条目

仅使用通过 P05 审查的内容生成适合知识库检索的原子条目。一个条目只表达一个案例、原则、
风险或冲突观点。输出 JSON 数组，不直接生成最终用户建议。

每条记录使用以下字段：

```json
{
  "schema_version": "1.0",
  "prompt_version": "knowledge-v001-p06",
  "id": "KNOW-C001-CASE001-001",
  "title": "",
  "type": "case|principle|risk|counterexample|expression",
  "source_ids": ["C001"],
  "evidence_spans": [],
  "relationship_stage": [],
  "scenario": [],
  "observations": [],
  "instructor_claims": [],
  "alternative_explanations": [],
  "principles": [],
  "applicability": [],
  "contraindications": [],
  "risks": [],
  "safety_flags": [],
  "response_options": [],
  "confidence": 0.0
}
```

`response_options` 只保存经过审查、尊重边界的表达类型与示例。证据不足时留空，不得为了满足
“多方案”而编造内容。
