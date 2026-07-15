# P02 Classify — 内容来源与类型标注

输入为 P01 JSON。不得改写文本，只给每个 segment 添加分类。

分类维度：

- `source_role`: instructor_explanation、actual_chat、student_question、board、pdf、marketing、unknown
- `epistemic_type`: observation、instructor_claim、quoted_statement、model_inference、unknown
- `relevance`: core、supporting、boilerplate、uncertain

输出保留 P01 全部字段，并加入上述字段、`classification_reasons`、`confidence`、
`uncertainties`。广告、联系方式和课程营销标记为 `boilerplate`，但此阶段仍不得删除。
