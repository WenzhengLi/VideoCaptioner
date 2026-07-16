# P02 Compact Review v003

输入是程序从完整 P02 baseline 生成的紧凑复核包。只输出复核决策，不复制全量 segments，
不改写文本。后续程序会把这些决策确定性应用到全量数据。

1. 通读每个 `speaker_cluster_profiles` 的均匀抽样，判断为
   `instructor_explanation`、`student_question` 或 `unknown`。
2. 从 `actual_chat_candidates` 中选出明确是案例实际聊天原句/复述的 segment ID。
   讲师一般说明中偶然出现“他说”，但没有引用内容时不要强标。
3. 从 `marketing_candidates` 中选出明确的课程营销、联系方式或招生内容。
4. 只把确实无法判断且会影响后续知识属性的段放入 `uncertain_segment_ids`。
5. 所有 ID 必须来自输入的对应候选列表；禁止编造 ID。

输出严格 JSON：

```json
{
  "schema_version": "1.0",
  "prompt_version": "knowledge-v003-p02-review",
  "course_id": "C001",
  "speaker_cluster_roles": {
    "speaker_0": "instructor_explanation|student_question|unknown"
  },
  "actual_chat_segment_ids": [],
  "marketing_segment_ids": [],
  "uncertain_segment_ids": [],
  "review_notes": [],
  "confidence": 0.0
}
```

写入后重新解析 JSON，确认每个 speaker cluster 都有且只有一个角色，所有 ID 都未越界。
