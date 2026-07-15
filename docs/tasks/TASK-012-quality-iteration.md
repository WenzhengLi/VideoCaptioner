# TASK-012：真实视频质量第二轮优化

## 目标

在不使用 LLM 的前提下，进一步减少课板重复与说话人误切换，并建立可重复的真实视频局部回归集。

## 问题背景

- 当前聊天课板共有 366 个视觉版本；3334 条 OCR 行中精确唯一行仅 578 条，原始重复率约 82.66%；
- TXT 已做精确行级增量输出，但相似错字、时间栏和 UI 固定元素仍可能重复；
- 当前人物聚类得到两位主要人物和少量 `unknown`，需要抽样确认短附和词与交叉讲话的标签质量。

## 必须完成

1. 从真实视频抽取不少于 6 个、每段 60～120 秒的局部样本，覆盖开头问答、聊天滚动、课板换位、结尾互动；
2. 为每个样本保存人工最小标注：讲话人区间、参考文字、课板新增文字；不得提交原视频；
3. 实现 OCR 行模糊去重：统一空白、标点、时间栏，允许小范围 OCR 错字，但不得吞掉真正的新聊天内容；
4. 把固定 UI 文本与动态聊天正文分开统计；
5. 评估 `unknown` 和 300ms～1500ms 短句的说话人归属；
6. 比较 WeSpeaker 默认参数与 CAM++ 备用路径，记录 DER 等价指标、耗时和人物数量稳定性；
7. 生成优化前后报告，至少包含文字覆盖率、OCR 新增行精确率/召回率、重复率、人物切换错误数；
8. 保持第一版无 LLM，所有规则必须可测试和可解释。

## 允许修改

- `src/course_video_analyzer/vision/`
- `src/course_video_analyzer/audio/`
- `src/course_video_analyzer/exporters/`
- `benchmarks/`
- `tests/test_vision/`、`tests/test_audio/`、`tests/test_exporters/`、`tests/test_benchmarks/`
- `docs/evaluation.md`

## 交付内容

- OCR 模糊增量去重实现及单元测试；
- 人物短句归属优化及单元测试；
- WeSpeaker/CAM++ 对比报告；
- 不含私有媒体的局部样本 manifest；
- `docs/evaluation-real-video.md` 优化前后报告。

## 验收标准

- 真实视频 TXT 的课板块相对原始 366 个视觉版本至少下降 30%；
- 新出现的聊天正文召回率不低于 95%；
- 31 个 `unknown` 片段均有原因分类，能够安全推断的片段被修复；
- 全量 Ruff、Pyright、非集成测试通过；
- PaddleOCR 与 WeSpeaker 集成烟雾测试通过。
