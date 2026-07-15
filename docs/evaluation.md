# 评估与回归基准（TASK-010）

## 目标

用可重复的离线指标量化 ASR、说话人分离、课板检测/去重与 OCR，并比较 WeSpeaker 与 CAM++。

## Manifest 格式

文件只保存路径与标注，不提交媒体本体。示例：

- `tests/fixtures/manifests/example.json`
- `tests/fixtures/manifests/example_predictions.json`

关键字段：

| 字段 | 说明 |
|---|---|
| `media_root` | 本机媒体根目录 |
| `samples[].media_path` | 相对 `media_root` 或绝对路径 |
| `samples[].annotations` | transcript / speaker_turns / board_regions / board_pages / ocr_text |
| `samples[].scenario` | 场景枚举（单人、双人、换位、遮挡等） |
| `diarizers` | 计划对比的引擎列表 |

## 指标定义

| 指标 | 定义 |
|---|---|
| CER / WER | 编辑距离 / 参考长度 |
| DER | `(FA + Miss + SpeakerError) / RefSpeech`，说话人映射为贪心最大重叠 |
| Board IoU / Top-K | 参考框与预测框 IoU；Top-K 命中率 |
| 课板重复率 / 漏页率 | 预测 `version_id` 重复占比；参考页未命中占比 |
| OCR 字符准确率 | `1 - CER` |
| 耗时与内存 | `ResourceTracker` 记录 elapsed、峰值 RSS；可用时记录峰值 GPU |

## 命令

```powershell
# 缺少本地媒体时跳过，不失败、不下载
uv run python -m benchmarks.run --manifest tests/fixtures/manifests/example.json --dry-run

# 使用合成预测跑通指标并写报告
uv run python -m benchmarks.run `
  --manifest tests/fixtures/manifests/example.json `
  --predictions tests/fixtures/manifests/example_predictions.json `
  --output-dir benchmarks/output

uv run course-video-benchmark --manifest tests/fixtures/manifests/example.json --list-missing
```

报告输出：

- `benchmarks/output/benchmark_report.json`
- `benchmarks/output/benchmark_report.md`

示例报告（无敏感内容）见 `docs/evaluation-example-report.md`。

## 数据准备

1. 在本机创建 `data/benchmark_media/`（已在 `.gitignore`）；
2. 按 manifest 放置 wav/mp4；
3. 填写或导出标注 JSON；
4. 生成系统预测 JSON（或接 TASK-008 导出结果后自行转换）；
5. 运行评估。

## 跳过规则

- 媒体不存在 → 记入 `missing_media` / `skipped`；
- `--dry-run` / `--list-missing` 退出码为 0；
- 不自动下载任何数据集或模型。

## 当前仍缺的真实场景样本

- 真实多人课堂 / 同时讲话 / 背景音乐与远场回声；
- 课板左右换位、分屏与全屏切换、人物遮挡；
- 电子课件 / 黑板 / 白板对照集。

请仅在本地私有目录准备上述样本，不要提交到 Git。
