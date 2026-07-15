# TASK-003：WeSpeaker 说话人分离适配器

## 目标

实现 `SpeakerDiarizer` 的 WeSpeaker 版本，只回答“什么时候是哪个声音在说话”。

## 前置依赖

TASK-001 已冻结 `SpeakerTurn` 与 `SpeakerDiarizer`；TASK-000 已固定 WeSpeaker commit。

## 允许修改

- `src/course_video_analyzer/audio/wespeaker_adapter.py`
- `src/course_video_analyzer/audio/wespeaker_parser.py`
- `src/course_video_analyzer/audio/campplus_adapter.py`
- `tests/test_audio/test_wespeaker_adapter.py`
- `tests/integration/test_wespeaker_integration.py`

CAM++ 只实现最小备用接口，不得扩展为第二套完整主流程。

## 输入

- 16kHz 单声道 WAV；
- 模型 `chinese` 或明确模型路径；
- `cpu` 或 `cuda:N` 设备配置。

## 输出

- `list[SpeakerTurn]`；
- `artifacts/audio/wespeaker_raw.json`；
- `artifacts/audio/speaker_turns.json`。

## 必须完成

1. 延迟导入 WeSpeaker；
2. 使用 `wespeaker.load_model("chinese")` 或配置模型；
3. 调用 `model.diarize()` 并解析 `(utt, start, end, label)`；
4. 秒转整数毫秒，人物统一为 `Speaker 0/1/...`；
5. 输出排序稳定，相同 label 在单任务内保持一致；
6. 处理无语音、短语音、非法返回和设备不可用；
7. 保存原始输出；
8. 单元测试使用 fake model；
9. 提供最小 CAM++ 备用适配器和相同协议，但默认配置仍为 WeSpeaker。

## 必须交付

- WeSpeaker 主适配器；
- CAM++ 备用适配器；
- 解析与错误处理测试；
- 一项双人音频集成测试；
- CPU/CUDA 行为说明。

## 验收标准

- 输出不包含转录文字；
- 无语音返回空列表而不是崩溃；
- 人物区间合法、排序且不出现负数；
- 双人样例至少产生两个 speaker label；
- 未执行的 CUDA 验证必须明确记录。

## 验收命令

```powershell
uv run pytest tests/test_audio/test_wespeaker_adapter.py -q
uv run pytest tests/integration/test_wespeaker_integration.py -q -m integration
uv run ruff check src/course_video_analyzer/audio/wespeaker_adapter.py
uv run pyright
```

## 非目标

- 不识别真实姓名；
- 不做跨视频声纹注册；
- 不合并 FunASR 文字；
- 不承诺多人重叠讲话的完美处理。

## 交接重点

说明固定的 WeSpeaker commit、中文模型来源、输出 label 稳定策略和已知容易分错的音频类型。
