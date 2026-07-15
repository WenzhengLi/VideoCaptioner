# TASK-011：真实视频端到端验证与兼容修复

## 状态

已完成（2026-07-15）。

## 目标

使用用户指定的 65 分 48 秒课程视频完成真实模型端到端处理，生成 `output/01.txt`，并与既有字幕进行定量比较。

## 输入与输出

- 输入：本地私有长视频样本（不提交仓库）
- 输出：`output/01.txt`
- 基准：同一视频的另一套自动字幕结果（不提交仓库）
- 任务目录：`jobs/real/<job-id>/`

## 已完成修复

1. 固定 `paddlepaddle==3.2.2`，修复 3.3.1 在 Windows oneDNN 下的 OCR 推理异常；
2. 固定 `scikit-learn>=1.4,<1.8`，修复 WeSpeaker/UMAP 调用已删除的 `force_all_finite`；
3. 长视频默认最多抽取 800 帧，并自动调整间隔以覆盖整段视频；
4. TXT 中同一课板版本只输出一次；
5. 滚动聊天课板只输出新出现的 OCR 行，完整 OCR 仍保留在 JSON 与图片产物；
6. 写入人物映射：`Speaker 0 → 导师`、`Speaker 1 → 学员`、`unknown → 未知`；
7. Windows 下自动发现 WinGet 安装的 FFmpeg/FFprobe。
8. 同一人物包围的 VAD 空洞使用上下文继承，未知片段从 31 降至 16；剩余 14 条位于人物切换边界，2 条因间隔或连续段过长而保留未知。
9. OCR 精确与高阈值模糊增量去重使 TXT 课板块从 366 降至 175。

## 真实结果

- 转录片段：3076；
- 说话人区间：1278；
- 对齐讲话片段：3284；
- 课板版本：366；
- OCR 行：3334，其中低置信度 77；
- 两位主要说话人片段：导师 2040、学员 1228；未知 16；
- 与基准归一化字符序列相似度：`0.9064`；
- 基准字符覆盖率：`0.9257`；
- 生成文字匹配精度：`0.8879`。

## 验收

```powershell
uv run ruff check .
uv run pyright
uv run pytest -q -m "not integration"
uv run pytest tests/integration/test_paddleocr_integration.py -q
uv run pytest tests/integration/test_wespeaker_integration.py -q
```

必须确认 `output/01.txt` 存在、人物名称可读、课板不再在每句讲话后整块重复。
