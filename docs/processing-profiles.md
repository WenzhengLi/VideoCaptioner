# 处理 Profile

处理 Profile 把“完整度还是速度优先”的产品选择集中到一个配置入口，避免 Web、脚本和
流水线分别维护不同默认值。解析逻辑位于
`src/course_video_analyzer/processing_profiles.py`。

## 默认：`complete-v1`

当前默认恢复到 `output/01.txt` 对应的视觉行为：

- 固定每 5 秒抽取一张基准帧；
- 最多 800 张，65 分 48 秒样本实际为 790 张；
- 每张帧都参与课板检测和跟踪；
- OCR 后保留完整 JSON/图片产物，TXT 再做增量行去重；
- 优先保留短暂出现、只出现一次的课板内容。

该 Profile 对应配置：

```json
{
  "processing_profile": "complete-v1",
  "sampling_mode": "fixed",
  "interval_ms": 5000,
  "max_frames": 800,
  "ocr_dedup_enabled": true
}
```

## 可选 Profile

| Profile | 抽帧方式 | 目标 |
| --- | --- | --- |
| `complete-v1` | 固定 5 秒 | 默认；内容完整度优先 |
| `adaptive-complete` | 自适应区间拆分 | 减少 OCR，保守识别变化 |
| `adaptive-balanced` | 自适应区间拆分 | 更快，但可能遗漏短暂内容 |

调用者可以传 `processing_profile`，再用单独配置键覆盖其中某个默认值。旧的
`adaptive_sampling=true/false`、`adaptive_ocr_*` 配置仍兼容；新代码优先使用
`sampling_mode`、`ocr_dedup_enabled` 和 `ocr_*` 通用名称。

## 架构边界

- Profile 只负责选择并解析配置，不读取视频，也不调用 OCR。
- 固定抽帧和自适应抽帧继续通过同一流水线阶段输出统一的 frame manifest。
- OCR 去重属于固定和自适应路径共享的下游能力，不再由名称带 `adaptive_` 的开关决定。
- SQLite、JPEG 磁盘缓存、内容区域裁剪、8% 留边、裁剪框抗抖动和内存 LRU 均保留在
  自适应实现中，可继续单独迭代，不影响默认 01 完整度路径。
