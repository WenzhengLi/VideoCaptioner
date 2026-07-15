# 视频自适应区间拆帧与 OCR 优化

> 后续的内容区域稳定化、SQLite 磁盘缓存和版本 02/03 对比见
> `docs/region-disk-iteration.md`。本文件保留第一轮 OCR 调度基准。

## 1. 原有逻辑的问题

原实现位于 `media/frames.py` 和 `pipeline.py`：按固定 `interval_ms` 使用 FFmpeg
抽取整段视频，再把全部图片交给 `BoardTracker`，最后对跟踪器产生的每个视觉版本调用一次
PaddleOCR。

主要问题：

- 不主动判断无文字片头、片尾，固定间隔可能保留无效画面。
- 间隔过大时会漏掉中间短暂出现的课板；间隔过小时又会产生大量重复检测和 OCR。
- 固定时间戳由文件名推算，无法表达递归找到的真实代表帧时间。
- 没有独立的 OCR 调度器和帧级 OCR 缓存，无法保证同一帧只识别一次。
- 真实 65 分钟视频旧结果为 790 张固定抽样帧、366 次完整 OCR；视觉抽帧和跟踪耗时
  67 秒，完整 OCR 耗时 1459 秒。

## 2. 可选自适应方法流程

自适应方法目前不是默认路径。默认 `complete-v1` 已恢复为 01 的固定 5 秒覆盖；需要减少
OCR 调用时，可显式选择 `adaptive-complete` 或 `adaptive-balanced` Profile。

公开入口是 `sample_video_adaptively(...)`，核心调度器是 `AdaptiveVideoSampler`。

1. 以较大的 `initial_stride_ms` 从开头到结尾建立粗采样点，并始终包含首帧和尾帧。
2. 先复用自动课板区域检测定位左侧、右侧或全屏课板，再对粗采样基准帧的课板区域执行
   一次完整 OCR。OCR 结果同时按时间点和原视频帧序号缓存，同一实际帧后续无论作为递归
   端点、代表帧还是恢复任务再次请求，都不重复调用 OCR。
3. 对相邻采样点分类：
   - 无文字到有文字、有文字到无文字：递归二分定位边界。
   - 两端都有文字但图片明显不同：递归二分定位页面切换。
   - 两端都有文字且相似：作为稳定内容，不继续拆分。
   - 两端都无文字且相似：跳过；若跨度过大或图片差异明显，检查中间点，防止漏掉
     中间短暂出现的文字。
4. 只有状态变化、图片差异明显且 OCR 文本也发生变化，或者两端无字但区间过大时，才对
   中间帧执行 OCR。稳定区间不对中间帧 OCR。
5. 找到稳定区间后，在区间内部额外抽取多张候选帧。这些帧只计算清晰度、稳定度和图片
   差异，不调用 OCR。
6. 如果选中的代表帧已经在 OCR 缓存中，直接复用；否则只补做这一次 OCR。
7. 代表帧进入现有 `BoardTracker`。跟踪器记录所选原视频帧序号，`BOARD_OCR` 阶段直接
   复用源帧 OCR 缓存，不再重复识别课板图片。
8. OCR 后再使用 OCR 文本和图片相似度合并相邻重复结果。`frames/manifest.json` 保存真实
   代表帧时间、区间、OCR 缓存和统计。

## 3. 封装与配置

`AdaptiveSamplingConfig` 的主要参数：

| 参数 | 默认值 | 含义 |
| --- | ---: | --- |
| `initial_stride_ms` | 60000 | 初始粗抽帧跨度 |
| `min_interval_ms` | 1000 | 递归允许继续拆分的最小时间间距 |
| `max_recursion_depth` | 8 | 最大递归深度 |
| `max_no_text_span_ms` | 8000 | 两端无字时必须检查中间帧的最大跨度 |
| `text_presence_threshold` | 0.42 | 轻量文字存在分数阈值 |
| `text_min_components` | 3 | 最小文字形态组件数 |
| `text_similarity_threshold` | 0.55 | 有字画面的重大变化相似度阈值 |
| `no_text_similarity_threshold` | 0.94 | 无字画面相似度阈值 |
| `image_difference_threshold` | 0.45 | 图片明显变化阈值 |
| `ocr_text_similarity_threshold` | 0.88 | OCR 文本发生变化的阈值 |
| `ocr_presence_min_confidence` | 0.20 | 判断有效文字时的最低 OCR 置信度 |
| `ocr_presence_min_lines` | 2 | 至少多少行文字才认为画面包含有效课板内容 |
| `representative_sample_count` | 5 | 每个稳定区间额外抽取但不 OCR 的候选帧数 |
| `content_region_padding_ratio` | 0.08 | 内容区域四周预留比例 |
| `memory_frame_cache_size` | 8 | 内存中最多保留的解码图片数 |
| `disk_cache_enabled` | true | 使用 SQLite 和图片目录持久化缓存 |
| `max_detected_frames` | 2000 | 安全上限，避免异常视频无限细分 |
| `jpeg_quality` | 92 | 代表帧 JPEG 质量 |

建议通过 Profile 启用，再使用 `adaptive_` 参数覆盖具体算法配置，例如：

```json
{
  "processing_profile": "adaptive-complete",
  "adaptive_initial_stride_ms": 60000,
  "adaptive_min_interval_ms": 1000,
  "adaptive_max_recursion_depth": 8,
  "adaptive_text_presence_threshold": 0.42,
  "adaptive_image_difference_threshold": 0.45,
  "adaptive_max_no_text_span_ms": 8000,
  "adaptive_max_detected_frames": 2000,
  "adaptive_ocr_text_similarity_threshold": 0.88,
  "adaptive_ocr_presence_min_confidence": 0.20,
  "adaptive_ocr_presence_min_lines": 2,
  "adaptive_representative_sample_count": 5,
  "adaptive_content_region_padding_ratio": 0.08,
  "adaptive_memory_frame_cache_size": 8
}
```

默认 `complete-v1` 使用固定抽帧路径。旧的 `adaptive_sampling=true/false` 参数继续兼容；
Web 界面默认显示 5000 ms 的完整度优先抽帧间隔。已有 `preview-*.jpg` 的旧任务也继续按旧
manifest 兼容恢复。

随机帧源、帧缓存、图片比较、OCR Provider、OCR 缓存、代表帧选择和 OCR 后去重均通过
独立类型或协议解耦。没有配置 OCR Provider 时才使用形态学文字检测作为测试或降级路径；
正式流水线使用现有 PaddleOCR。

## 4. 修改文件

- `src/course_video_analyzer/vision/adaptive_sampling.py`：独立自适应采样模块。
- `src/course_video_analyzer/vision/ocr_dedup.py`：OCR 文本和图片联合去重。
- `src/course_video_analyzer/processing_profiles.py`：集中管理默认完整度与可选自适应模式。
- `src/course_video_analyzer/pipeline.py`：接入固定/自适应路径、真实时间戳和统计。
- `src/course_video_analyzer/web/app.py`：Web 默认恢复 5000 ms 完整度间隔。
- `src/course_video_analyzer/web/service.py`：服务默认恢复 5000 ms 完整度间隔。
- `tests/test_vision/test_adaptive_sampling.py`：递归边界、短暂文字、稳定页面、页面切换、
  停止条件、代表帧和真实 OpenCV 视频测试。
- `tests/test_vision/test_ocr_dedup.py`：OCR 后去重测试。
- `tests/test_pipeline.py`：自适应 manifest 和真实代表帧时间传递测试。
- `scripts/benchmark_adaptive_sampling.py`：可重复运行真实视频采样、跟踪和可选 OCR 基准。

## 5. 验证结果

### 合成视频

真实 OpenCV 视频包含：0～2 秒无字片头、2～5 秒页面 A、5～8 秒页面 B、8～10 秒
无字片尾。测试配置最小间距为 250 ms，结果：

- 自动识别两段有效文字区间。
- 片头结束边界与 2 秒的误差不超过 250 ms。
- 片尾开始边界与 8 秒的误差不超过 250 ms。
- 页面 A/B 各保留一张代表帧。

另外的纯调度测试覆盖了“首尾都无字但中间短暂有字”，确认即使两个粗采样端点相似，
只要区间跨度超过上限也会继续检查中间帧。

### 60 秒真实样本

- 抽取 7 张帧用于基准和代表帧选择。
- 图片比较 2 次。
- OCR 调度请求 5 次，其中缓存命中 3 次，真实 OCR 只有首尾两张基准帧的 2 次。
- 最终保留 1 个稳定区间和 1 张代表图。
- 稳定区间内部额外抽取的图片没有触发 OCR。

### 前 10 分钟真实片段

- 旧固定路径在同一时段执行 45 次 OCR。
- 新调度抽取 55 张帧、图片比较 75 次。
- OCR 请求 144 次，其中 108 次命中缓存，真实 OCR 36 次，减少 20%。
- 最终形成 4 个稳定区间。
- 实际耗时约 161.9 秒。

### 65 分钟真实视频

视频总帧数约 98,700。最终使用自动课板区域 OCR，并要求至少两行、置信度至少 0.20
才认为存在有效课板文字。这样不会把开头固定的微信水印或人物衣服文字当成有效内容。

| 指标 | 旧固定抽帧 | 新自适应拆帧 | 变化 |
| --- | ---: | ---: | ---: |
| 视频输入总帧 | 98,700 | 98,700 | - |
| 实际抽取帧 | 790 | 296 | -62.5%（不是主要优化目标） |
| 图片比较次数 | 未统计 | 531 | - |
| OCR 调度请求 | 366 | 982 | 允许重复请求 |
| OCR 缓存命中 | 0 | 744 | 同一实际帧不重复 OCR |
| 真实完整 OCR 次数 | 366 | 238 | -35.0% |
| 有效稳定区间/最终图片 | 366 | 12 | -96.7% |
| 无效片头 | 未主动识别 | `0～57187 ms` | 自动定位 |
| 无效片尾 | 未主动识别 | `3942765～3948019 ms` | 自动定位 |
| 旧视觉流程实耗 | 1526.0 s | - | - |
| 新流程估算冷启动实耗 | - | 987.2 s | -35.3% |

全片实测复用了前 10 分钟的 30 个真实 OCR 缓存，剩余 208 次新推理实耗 852.7 秒。
冷启动时间使用前 10 分钟同一适配器的真实单次耗时补回，估算约 987.2 秒。

完整数据位于：

- `benchmarks/results/ocr-scheduled-real-full-cropped/benchmark.json`
- `benchmarks/results/ocr-scheduled-real-full-cropped/comparison.json`
- `benchmarks/results/ocr-scheduled-real-full-cropped/combined_ocr_lines.json`

内容覆盖审查只统计置信度至少 0.5、归一化长度至少 6 的 OCR 行。相对旧结果：

- 所有只出现过一次的高置信行，模糊覆盖率 69.3%；其中包含瞬时滚动内容和 OCR 偶发值。
- 旧结果中至少出现 2 次的行，覆盖率 82.1%。
- 至少出现 3 次的内容，覆盖率 88.3%。
- 至少出现 5 次的稳定内容，覆盖率 91.4%。
- 至少出现 10 次的长期稳定内容，覆盖率 100%。

12 个稳定区间最终组合了 422 行缓存 OCR 文本。中间帧已经付出的 OCR 结果不会丢弃，
会在所属稳定区间内按文本相似度去重并组合到最终结果中。

## 6. 统计输出

`frames/manifest.json` 的 `stats` 包含：

- `video_total_frames`
- `actual_detected_frames`
- `image_comparison_count`
- `ocr_request_count`
- `ocr_cache_hit_count`
- `full_ocr_count`（自适应调度阶段真实 OCR 推理次数）
- `downstream_full_ocr_count`
- `downstream_ocr_cache_hit_count`
- `actual_full_ocr_count`
- `intro_filtered_range_ms`
- `outro_filtered_range_ms`
- `valid_interval_count`
- `final_image_count`
- `final_image_count_after_ocr_dedup`
- `max_recursion_depth_reached`
- 完整配置快照

每个 `intervals` 条目还包含开始/结束时间、代表帧时间、原视频帧序号、代表图片、参与
选择的检测时间点、文字分数和稳定度分数。

完整 OCR 后还会生成 `artifacts/boards/adaptive_results.json`，把最终课板图片、时间区间、
对应的原视频代表帧序号/时间点和 OCR 行放在同一条结果中，便于后续算法和 Web 页面直接
消费。
