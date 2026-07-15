# P03 Segment — 案例边界

输入为 P02 JSON。只识别课程章节与独立案例边界，不提炼技巧。

输出 JSON 包含：

- `course_id`
- `cases[]`: `case_id`、标题、起止 segment ID、参与角色、边界依据、完整性状态
- `unassigned_segment_ids[]`
- `uncertainties[]`

案例 ID 使用 `CASE-C001-001`。边界必须引用 segment ID。一个案例跨越讲师讲解与聊天记录时
可以归入同一案例；证据不足时标记 `partial`，不得强行合并。
