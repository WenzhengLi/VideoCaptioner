# P06 Tidy v002 — 原子知识条目

仅使用 P04 提取与 P05 审查结果，生成可检索、可追溯的原子条目。一个条目只表达一个案例、
原则、风险、反例或表达方式，不生成针对当前用户的最终建议。

规则：

1. 仅使用 P05 中 `supported` 或 `partially_supported` 的内容；部分支持必须保留限定。
2. 讲师观点必须保留在 `instructor_claims`，不能改写成已证实普遍事实。
3. 每个条目必须带非空 `evidence_spans`，值为原始 segment ID。
4. 如 P05 `review_status=blocked`，只可生成 `risk`/`counterexample` 条目，`response_options` 必须为空。
5. 对明确拒绝、不适、隐私、威胁或施压的内容，优先生成风险/边界条目，不得转换为推进技巧。
6. `response_options` 只保存经审查、尊重边界的表达类型或示例；证据不足时留空。

输出严格 JSON：

```json
{
  "schema_version": "1.0",
  "prompt_version": "knowledge-v002-p06",
  "source_ids": ["C001"],
  "course_id": "C001",
  "case_id": "CASE-C001-001",
  "entries": [{
    "id": "KNOW-C001-CASE001-001",
    "title": "",
    "type": "case|principle|risk|counterexample|expression",
    "source_ids": ["C001"],
    "case_id": "CASE-C001-001",
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
  }]
}
```
