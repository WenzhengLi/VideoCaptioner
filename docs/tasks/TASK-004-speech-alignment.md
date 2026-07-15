# TASK-004：转录与人物时间轴对齐

## 目标

把 FunASR 的 `TranscriptSegment[]` 和 WeSpeaker 的 `SpeakerTurn[]` 合成为可读的 `SpeechSegment[]`。

## 前置依赖

TASK-002 与 TASK-003 已完成，并提供标准化 JSON 样例。

## 允许修改

- `src/course_video_analyzer/audio/alignment.py`
- `src/course_video_analyzer/audio/speaker_mapping.py`
- `tests/test_audio/test_alignment.py`

不得修改两个模型适配器内部实现。

## 输入

- `TranscriptSegment[]`
- `SpeakerTurn[]`
- 可选人物名称映射
- 对齐阈值配置

## 输出

- `SpeechSegment[]`
- `artifacts/audio/alignment.json`
- 对齐诊断信息：重叠比例、推断方式、未匹配原因

## 必须完成

1. 以最大时间重叠作为默认人物分配；
2. 使用重叠时长/文字片段时长计算匹配比例；
3. 匹配比例不足时标记 `unknown`；
4. 文字跨越明确人物切换时，在有词级时间戳时拆分；
5. 无词级时间戳时不得伪造精确切分，保留低置信标记；
6. 短附和词的最近人物继承必须可配置，并记录 `inferred=true`；
7. 人物名称映射只改变展示名称，不改变原始 speaker id；
8. 算法必须是纯函数，可离线单元测试。

## 必须交付

- 对齐算法；
- 人物名称映射工具；
- 边界、无重叠、相同重叠、多人物切换测试；
- 对齐诊断 JSON 示例；
- 阈值默认值说明。

## 验收标准

- 所有输出区间合法并按时间排序；
- 原始文字不丢失；
- `unknown`、直接匹配和推断匹配可以区分；
- 输入为空时行为明确；
- 测试不依赖 FunASR 或 WeSpeaker 安装。

## 验收命令

```powershell
uv run pytest tests/test_audio/test_alignment.py -q
uv run ruff check src/course_video_analyzer/audio/alignment.py
uv run pyright
```

## 非目标

- 不运行语音模型；
- 不做语义断句或 LLM 修正；
- 不识别真实人物身份；
- 不修改媒体时间轴。

## 交接重点

说明默认匹配阈值、拆分条件、`inferred` 语义和 TASK-008 应读取的标准结果路径。
