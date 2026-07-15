# TASK-005：课板候选区域检测

## 目标

在单张或连续采样帧中，自动找出课件、共享屏幕、黑板或白板的候选区域，并对候选区域评分。

## 前置依赖

TASK-001 已冻结 `BoardCandidate`、`BoardRegion` 和 `BoardDetector`。

## 允许修改

- `src/course_video_analyzer/vision/detection.py`
- `src/course_video_analyzer/vision/candidates.py`
- `src/course_video_analyzer/vision/scoring.py`
- `tests/test_vision/test_detection.py`
- `tests/fixtures/images/` 中的合成或可公开小图

## 输入

- 视频采样帧；
- 上一帧可选课板区域；
- 电子课件/实体课板/自动模式；
- 候选数量和评分阈值。

## 输出

- 排序后的 `BoardCandidate[]`；
- 每项包含区域、面积比、矩形度、文字密度、稳定性、遮挡比例和总分；
- 可选调试叠加图。

## 必须完成

1. 使用轮廓、边缘或线段生成大矩形候选；
2. 支持左侧、右侧和全屏，不使用固定位置规则；
3. OCR 在本任务只用于文字框检测或通过协议注入，不负责识别正文；
4. 评分函数独立且可配置；
5. 没有可靠候选时返回空列表或低置信候选；
6. 调试模式输出候选框和各项分数；
7. 单元测试使用合成布局覆盖左、右、全屏和无课板场景。

## 必须交付

- 候选生成器；
- 候选评分器；
- 自动模式检测入口；
- 合成测试图和单元测试；
- 调试图生成方法；
- 默认阈值说明。

## 验收标准

- 左、右、全屏合成样本的正确区域进入 Top 3；
- 人物小窗不会因面积小而默认胜出；
- 无课板画面不应强制返回高置信区域；
- 代码不依赖 Gradio；
- OCR 正文识别不出现在该模块。

## 验收命令

```powershell
uv run pytest tests/test_vision/test_detection.py -q
uv run ruff check src/course_video_analyzer/vision/detection.py
uv run pyright
```

## 非目标

- 不跨帧追踪；
- 不判断是否换页；
- 不输出 OCR 正文；
- 不训练 YOLO 模型。

## 交接重点

说明候选分数构成、Top 3 选择策略、调试图格式和 TASK-006 可依赖的字段。
