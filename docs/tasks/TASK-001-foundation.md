# TASK-001：共享模型、媒体输入与任务工作区

## 目标

冻结后续 Agent 共用的数据契约，并实现媒体探测、音频提取、预览抽帧和可恢复任务目录。

## 前置依赖

TASK-000 已完成，Python 3.11 环境和依赖可安装。

## 允许修改

- `src/course_video_analyzer/models.py`
- `src/course_video_analyzer/pipeline.py`
- `src/course_video_analyzer/media/`
- `src/course_video_analyzer/jobs/`
- `src/course_video_analyzer/audio/base.py`
- `src/course_video_analyzer/vision/base.py`
- `tests/test_models.py`
- `tests/test_media/`
- `tests/test_jobs/`

## 输入

- 本地视频或音频路径；
- 工作区根目录；
- 抽帧间隔配置。

## 输出

```text
jobs/<job-id>/
├─ job.json
├─ media.json
├─ audio/audio.wav
├─ frames/preview-*.jpg
├─ artifacts/
└─ logs/
```

## 必须完成

1. 将现有 `SpeechSegment` 拆为 `TranscriptSegment`、`SpeakerTurn` 和对齐后的 `SpeechSegment`；
2. 补充 `BoardCandidate`、任务状态、处理阶段和来源追踪字段；
3. 统一毫秒区间 `[start_ms, end_ms)`；
4. 定义 `SpeechRecognizer`、`SpeakerDiarizer`、`BoardDetector`、`BoardOcr` 协议；
5. 用 ffprobe 读取时长、帧率、分辨率、音视频流；
6. 用 FFmpeg 提取 16kHz 单声道 PCM WAV；
7. 实现按间隔抽帧；
8. 建立任务状态文件并使用原子写入；
9. 已完成阶段可跳过，失败阶段保留错误信息；
10. subprocess 错误必须包含退出码和清理后的 stderr。

## 必须交付

- 冻结后的公共 Pydantic 模型；
- 媒体探测与转换实现；
- `JobWorkspace` 或等价任务工作区实现；
- 音频、视觉适配器协议；
- 单元测试与一项 FFmpeg 集成测试；
- 字段说明或 JSON 示例。

## 验收标准

- 视频输入生成规定目录和元数据文件；
- 重复执行不会重复提取已完成产物；
- 不存在输入、无 FFmpeg、损坏媒体均返回明确错误；
- 下游 TASK-002、003、005 无需修改公共模型即可开工；
- 所有 JSON 可以由 Pydantic 重新加载。

## 验收命令

```powershell
uv run pytest tests/test_models.py tests/test_media tests/test_jobs -q
uv run pytest tests/test_media -q -m integration
uv run ruff check src/course_video_analyzer/media src/course_video_analyzer/jobs
uv run pyright
```

## 非目标

- 不调用 ASR、说话人模型或 OCR；
- 不实现时间轴对齐；
- 不实现 Web 上传；
- 不修改 TASK-000 已冻结的依赖。

## 交接重点

列出所有冻结模型、协议方法签名、任务目录格式和下游可依赖的异常类型。
