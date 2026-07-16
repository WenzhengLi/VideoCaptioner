# P03 Segment v003 — 课程章节与案例边界

输入为程序从通过 P02 QA 的 JSON 生成的紧凑时间线；它逐段保留 segment ID、时间、
说话人、分类与规范化文本，只去除边界判断不需要的冗余字段。本阶段只划分连续案例边界，不总结技巧、不改写原文、
不判断讲师观点是否正确，也不生成建议。

## 完整性约束

1. 输入中每个 `segment_id` 必须且只能出现在一个案例的起止闭区间内，或出现在
   `unassigned_segment_ids`。禁止遗漏、重复和交叉。
2. 案例区间必须按原始 segment 顺序排列，且不能重叠。
3. 寒暄、直播调试、广告和无法归入具体案例的过渡内容放入
   `unassigned_segment_ids`，不得为了降低未分配数而强行并入案例。
4. 边界不确定时优先保留较宽的完整区间，并标记 `partial` 或 `uncertain`，
   不得为了简短而切掉案例背景、对话或结果。
5. 同一案例中的讲师串讲、课板 OCR 穿插、学员补充问答，只要仍在讨论同一人物/聊天记录/
   结果线，必须留在该案例闭区间内，不得因“讲解段落”而被丢进 `unassigned_segment_ids`。
6. 完成覆盖校验后计算 `unassigned_segment_count / input_segment_count`。若该比值
   **大于 0.20**，必须重新扫描未分配区：把仍能定位到相邻案例的讲解/OCR/复盘并回案例，
   或在 `uncertainties` 列出无法归案的具体原因（广告、开场、整段跑题等）。不得只留下
   空白高未分配结果。

## 边界判断

- 新案例开始的强证据：明确的“下一个案例”、新学员自我介绍、新时间/地点/人物，
  或课板切换到新聊天记录。
- 案例结束的强证据：结果、复盘收尾、问答结束、明确切换主题或新案例。
- 同一案例中的讲师讲解、学员补充、实际聊天引用和课板 OCR 可以保留在同一连续区间。
- 只有类似人名、“他说”、“然后”等弱信号时，不要立即断开。
- 不要因为中间夹杂通用恋爱理论讲解就切断案例；若讲解显式回指当前聊天/课板，继续归入当前案例。

## 输出 JSON

```json
{
  "schema_version": "1.0",
  "prompt_version": "knowledge-v003-p03",
  "source_ids": ["C001"],
  "course_id": "C001",
  "cases": [{
    "case_id": "CASE-C001-001",
    "title": "中性、可定位的案例标题",
    "start_segment_id": "SEG-C001-000100",
    "end_segment_id": "SEG-C001-000300",
    "participant_roles": ["teacher_a", "student", "unknown"],
    "boundary_evidence": {
      "start_reason": "",
      "end_reason": "",
      "evidence_segment_ids": []
    },
    "completeness": "complete|partial|uncertain",
    "confidence": 0.0
  }],
  "unassigned_segment_ids": [],
  "uncertainties": [{
    "case_id": "CASE-C001-001",
    "note": ""
  }],
  "segmentation_metrics": {
    "input_segment_count": 0,
    "case_count": 0,
    "assigned_segment_count": 0,
    "unassigned_segment_count": 0
  }
}
```

写入后必须重新解析 JSON，按输入顺序展开每个案例闭区间，确认与
`unassigned_segment_ids` 的并集恰好覆盖全部输入 segment，且不存在任何交集。
