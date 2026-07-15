# TASK-010：评估集与回归基准

## 目标

建立可重复运行的评估工具，量化 ASR、说话人分离、时间轴对齐、课板检测、去重和 OCR 的质量与性能。

## 前置依赖

TASK-004、TASK-006、TASK-007 完成；完整端到端评估等待 TASK-008。

## 允许修改

- `benchmarks/`
- `tests/fixtures/manifests/`
- `tests/test_benchmarks/`
- `docs/evaluation.md`

不得提交真实课程视频、模型权重或版权不明数据。

## 评估清单

- 单人、双人、多人音频；
- 短附和词；
- 同时讲话；
- 背景音乐和远场回声；
- 课板固定在左侧；
- 课板固定在右侧；
- 左右换位；
- 分屏与全屏切换；
- 人物遮挡；
- 电子课件、黑板和白板。

## 必须完成

1. 定义只保存路径和标注、不提交媒体本体的 manifest 格式；
2. 实现 ASR 字错率 CER/WER；
3. 实现说话人 DER 或明确采用的等价指标；
4. 实现课板区域 IoU、Top-K 命中率；
5. 实现课板重复率和漏页率；
6. 实现 OCR 字符准确率；
7. 记录每分钟视频处理耗时、峰值内存和可用时峰值显存；
8. 比较 WeSpeaker 与 CAM++；
9. 生成机器可读 JSON 和人类可读 Markdown 报告；
10. 基准命令在缺少本地数据时明确跳过，而不是失败或下载数据。

## 必须交付

- 评估 manifest schema；
- 指标实现与单元测试；
- benchmark CLI；
- 报告生成器；
- `docs/evaluation.md`；
- 一份不含敏感内容的示例报告。

## 验收标准

- 指标使用小型合成数据得到已知答案；
- 缺少媒体时能列出待提供文件；
- 相同结果重复评估数值一致；
- 报告能够分别展示各组件和端到端指标；
- 能明确比较 WeSpeaker 与 CAM++ 的质量和速度。

## 验收命令

```powershell
uv run pytest tests/test_benchmarks -q
uv run python -m benchmarks.run --manifest tests/fixtures/manifests/example.json --dry-run
uv run ruff check benchmarks tests/test_benchmarks
uv run pyright
```

## 非目标

- 不把用户私有视频加入 Git；
- 不为了提高分数修改生产算法；
- 不使用 LLM 主观打分；
- 不建立公网排行榜。

## 交接重点

说明数据准备方法、指标定义、跳过规则、硬件信息记录方式，以及当前仍缺少哪些真实场景样本。
