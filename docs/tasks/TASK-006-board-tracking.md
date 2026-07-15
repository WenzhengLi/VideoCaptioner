# TASK-006：课板追踪、换位与去重

## 目标

在视频时间轴上持续追踪课板区域，处理课板从左到右、分屏到全屏等布局变化，并生成去重后的课板版本。

## 前置依赖

TASK-005 已提供排序后的 `BoardCandidate[]`。

## 允许修改

- `src/course_video_analyzer/vision/tracking.py`
- `src/course_video_analyzer/vision/matching.py`
- `src/course_video_analyzer/vision/dedup.py`
- `src/course_video_analyzer/vision/keyframes.py`
- `tests/test_vision/test_tracking.py`
- `tests/test_vision/test_dedup.py`

## 输入

- 按时间排序的采样帧；
- 每个重检测点的候选区域；
- 跟踪、特征匹配和去重阈值。

## 输出

- 带时间范围的稳定课板区域序列；
- 课板版本与代表帧；
- 追踪状态：tracked、redetected、lost；
- 去重距离和换页原因。

## 必须完成

1. 正常帧使用 ORB/特征匹配或适当跟踪器保持区域；
2. 特征不足、布局突变或区域消失时触发全帧重检测；
3. 重检测可在另一侧找到与上一课板相似的内容；
4. 使用 pHash/SSIM 判断相同页和换页；
5. 人物移动不能轻易触发课件换页；
6. 同一课板版本中选择清晰度高、遮挡少的代表帧；
7. 所有阈值集中配置；
8. 输出追踪诊断，禁止静默丢帧。

## 必须交付

- 区域追踪器；
- 特征匹配与重定位；
- 换页与去重器；
- 代表帧评分器；
- 左右换位、全屏切换、人物移动和丢失恢复测试。

## 验收标准

- 左右换位合成序列能在规定重检测窗口内恢复；
- 同一页轻微缩放、人物遮挡不会产生大量重复版本；
- 真正换页能够生成新版本；
- 跟踪失败明确标记 lost；
- 不调用 OCR 正文识别。

## 验收命令

```powershell
uv run pytest tests/test_vision/test_tracking.py tests/test_vision/test_dedup.py -q
uv run ruff check src/course_video_analyzer/vision/tracking.py src/course_video_analyzer/vision/dedup.py
uv run pyright
```

## 非目标

- 不实现首次候选检测；
- 不识别文字；
- 不处理声音；
- 不把所有视频帧永久保存。

## 交接重点

说明重检测触发条件、相似度阈值、代表帧选择公式和 TASK-007 接收的图片格式。
