# P05 Review v003 — 证据与安全审查

输入包含一个 P04 提取结果及该案例的原始证据段。逐条审查，不重写案例，不添加新结论。

## 审查范围

- P04 中每个 observation、instructor claim、alternative explanation、outcome 和 quoted expression
  必须且只能有一条 `evidence_reviews`。
- 状态使用 `supported|partially_supported|unsupported|contradicted`。
- 证据不足、说话人不确定、结果只由讲师口述时，不得标成完全支持的客观事实。

## 安全与边界

检查明确拒绝、撤回同意、不适、恐惧、报警/威胁、欺骗、施压、跟踪、隐私泄露、
酒精/意识不清、年龄不明等风险。明确拒绝或不适必须视为停止信号，不能解释成默认的“测试”。

输出严格 JSON：

```json
{
  "schema_version": "1.0",
  "prompt_version": "knowledge-v003-p05",
  "source_ids": ["C001"],
  "course_id": "C001",
  "case_id": "CASE-C001-001",
  "evidence_reviews": [{
    "target_type": "observation|instructor_claim|alternative_explanation|outcome|quoted_expression",
    "target_id": "",
    "status": "supported|partially_supported|unsupported|contradicted",
    "supported_by_segment_ids": [],
    "note": ""
  }],
  "safety_flags": [{"type": "", "severity": "low|medium|high|critical", "evidence_segment_ids": [], "note": ""}],
  "unsafe_recommendation_candidates": [{"text": "", "reason": "", "evidence_segment_ids": []}],
  "missing_context": [{"field": "", "note": "", "evidence_segment_ids": []}],
  "required_corrections": [{"target_type": "", "target_id": "", "action": "remove|downgrade|clarify", "note": ""}],
  "review_status": "pass|needs_revision|blocked",
  "confidence": 0.0
}
```

`review_status=pass` 只表示证据和安全标注可用，不表示课程中的行为均安全或值得推荐。
