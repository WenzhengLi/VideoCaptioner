# TASK-007：课板 OCR 与图像增强

## 目标

对 TASK-006 选出的代表帧进行图像增强和 PaddleOCR 识别，保留原始结果并支持后续人工修订。

## 前置依赖

TASK-005 已冻结区域模型；TASK-006 提供代表帧格式。实现可以与 TASK-006 并行，但集成验收需等待 TASK-006。

## 允许修改

- `src/course_video_analyzer/vision/enhance.py`
- `src/course_video_analyzer/vision/ocr.py`
- `src/course_video_analyzer/vision/ocr_parser.py`
- `tests/test_vision/test_enhance.py`
- `tests/test_vision/test_ocr.py`
- `tests/integration/test_paddleocr_integration.py`

## 输入

- 已裁剪或带四角坐标的课板代表帧；
- 电子课件/黑板/白板模式；
- OCR 语言、设备和阈值配置。

## 输出

- `OcrLine[]`，包含文字、置信度、文字框和 `corrected_text`；
- 原始 PaddleOCR JSON；
- 增强前后图片路径；
- 汇总后的课板正文。

## 必须完成

1. 实体课板支持透视矫正；
2. 提供 CLAHE、灰度、二值化、降噪等可配置预处理；
3. 电子课件默认避免破坏彩色文字；
4. 延迟导入 PaddleOCR；
5. 解析文字框、文本和置信度；
6. 按阅读顺序排序并合并同一行；
7. 低置信结果必须保留并标记；
8. 人工修订写入 `corrected_text`，不得覆盖原始 `text`；
9. 单元测试使用 fake OCR engine。

## 必须交付

- 图像增强模块；
- PaddleOCR 适配器与解析器；
- 阅读顺序和行合并算法；
- 单元测试和一项真实 OCR 集成测试；
- 不同课板模式的默认配置说明。

## 验收标准

- 电子课件小样可以识别主要中文文字；
- 透视输入能生成矩形校正图；
- 空结果和低置信结果行为明确；
- 原文和修订字段同时可序列化；
- 单元测试不下载模型。

## 验收命令

```powershell
uv run pytest tests/test_vision/test_enhance.py tests/test_vision/test_ocr.py -q
uv run pytest tests/integration/test_paddleocr_integration.py -q -m integration
uv run ruff check src/course_video_analyzer/vision/enhance.py src/course_video_analyzer/vision/ocr.py
uv run pyright
```

## 非目标

- 不用 LLM 修正文案；
- 不保证潦草手写公式高精度；
- 不负责课板区域追踪；
- 不生成 PDF。

## 交接重点

说明 PaddleOCR 版本、模型语言、输入尺寸、默认增强参数和 TASK-008 应使用原文还是修订文的规则。
