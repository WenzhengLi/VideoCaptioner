# TASK-002：FunASR 转录适配器

## 目标

实现 `SpeechRecognizer` 的 FunASR 版本，只回答“什么时候说了什么”，不处理人物身份。

## 前置依赖

TASK-001 已冻结 `TranscriptSegment` 与 `SpeechRecognizer`。

## 允许修改

- `src/course_video_analyzer/audio/funasr_adapter.py`
- `src/course_video_analyzer/audio/funasr_parser.py`
- `tests/test_audio/test_funasr_adapter.py`
- `tests/integration/test_funasr_integration.py`

不得修改公共模型和 WeSpeaker 文件。

## 输入

- 16kHz 单声道 WAV；
- 模型名、设备、批大小和缓存目录配置。

## 输出

- 按时间排序的 `list[TranscriptSegment]`；
- `artifacts/audio/funasr_raw.json` 原始结果；
- `artifacts/audio/transcript.json` 标准化结果。

## 必须完成

1. 延迟导入 FunASR，未安装时给出可操作错误；
2. 模型实例可复用，不得每段音频重复加载；
3. 解析句级时间戳、文本和可用置信度；
4. 标准化空白和标点，但保留原始文本字段；
5. 过滤空片段并校验区间；
6. 长音频策略通过配置控制，不把切片逻辑写死；
7. 原始返回结构变化时抛出明确解析错误；
8. 单元测试使用 fake model，不下载模型。

## 必须交付

- FunASR 适配器与解析器；
- 原始结果和标准结果序列化；
- 正常、空结果、非法时间戳、模型异常测试；
- 一项带 `integration` 标记的真实模型测试；
- 配置项和已验证模型名说明。

## 验收标准

- 输出不含 speaker 字段推断；
- 区间使用毫秒且按开始时间排序；
- 单元测试离线执行；
- 相同输入和配置可复用缓存；
- 真实中文样例能够输出非空文字和有效时间戳。

## 验收命令

```powershell
uv run pytest tests/test_audio/test_funasr_adapter.py -q
uv run pytest tests/integration/test_funasr_integration.py -q -m integration
uv run ruff check src/course_video_analyzer/audio/funasr_adapter.py
uv run pyright
```

## 非目标

- 不做说话人分离；
- 不把短句合并为人物对话；
- 不调用 LLM 修正文本；
- 不修改媒体提取逻辑。

## 交接重点

提供一份标准化 JSON 示例，说明时间戳精度、模型缓存路径和集成测试使用的模型。
