# P05 Review — 证据与安全审查

输入为 P04 JSON 和其引用的原始证据。逐条判断结论是否被证据支持，不重写案例。

输出：

- `evidence_reviews[]`: supported、partially_supported、unsupported、contradicted
- `safety_flags[]`: 拒绝、报警、威胁、欺骗、施压、隐私、年龄不明等
- `unsafe_recommendation_candidates[]`
- `missing_context[]`
- `required_corrections[]`
- `review_status`: pass、needs_revision、blocked

明确拒绝和撤回同意应被视为停止信号。不能把防备、拒绝或报警解释成默认的“测试”“欲拒还迎”。
