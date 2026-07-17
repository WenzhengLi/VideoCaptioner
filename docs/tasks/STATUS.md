# 任务状态跟踪

## TASK-000

- 状态：完成
- 修改文件：
  - `.python-version`
  - `pyproject.toml`
  - `uv.lock`
  - `scripts/verify_runtime.py`
  - `docs/environment.md`
- 关键决策：
  - Python `>=3.11,<3.12`
  - WeSpeaker Git commit `dfa741957e5c11f477623b6e583d67d0af25ee88`
  - 默认 Torch/Torchaudio 使用 `pytorch-cpu` 索引（`2.6.0+cpu`）
  - 额外声明 `onnxruntime`（WeSpeaker diar 导入依赖）
- 验证结果：
  - `uv sync --all-extras --group dev` 成功
  - `uv run python scripts/verify_runtime.py`：required/tools/optional 全部 OK（CPU）
  - `ruff` / `pyright` / `pytest -m "not integration"` 通过
- 已知限制：
  - CUDA 未在本机验证（`cuda_available=False`）
  - 导入 WeSpeaker 时 s3prl 提示 ESPnet 未安装，不影响基础 diarization 导入
  - 本机 FFmpeg 需将 WinGet 安装目录加入 PATH

## TASK-001 ~ TASK-008

- 状态：完成（既有实现，本次未重做）
- 说明：共享模型、FunASR、WeSpeaker、对齐、课板检测/追踪/OCR、时间轴与导出均已在仓库中并通过非集成测试。

## TASK-009

- 状态：完成
- 修改文件：
  - `src/course_video_analyzer/web/`（包：`app.py` / `service.py` / `revisions.py` / `runner.py` / `validation.py`）
  - 删除冲突的 `src/course_video_analyzer/web.py`，入口改为包导出
  - `tests/test_web/`
  - `docs/web.md`
- 关键决策：
  - Web 仅通过 `WebAnalysisFacade` 调用 `AnalysisService`
  - 长任务用后台线程；进度来自 `job.json`
  - 修订写入 `jobs/<id>/revisions.json`，不覆盖原始 OCR `text`
  - 默认 `127.0.0.1`，`build_app()` 不自动开浏览器
- 验证结果：
  - `uv run pytest tests/test_web -q` 通过
  - `uv run python -c "from course_video_analyzer.web import build_app; build_app()"` 通过
  - `ruff` / `pyright` 通过
- 已知限制：
  - 生产管线仍依赖本机 FFmpeg 与 audio/vision extras
  - Gradio 文件下载组件展示的是导出路径；未做公网鉴权

## TASK-010

- 状态：完成
- 修改文件：
  - `benchmarks/`（`schema` / `metrics` / `evaluate` / `report` / `compare` / `resources` / `run`）
  - `tests/fixtures/manifests/example.json`
  - `tests/fixtures/manifests/example_predictions.json`
  - `tests/test_benchmarks/`
  - `docs/evaluation.md`
  - `docs/evaluation-example-report.md`
  - `pyproject.toml`（打包 `benchmarks`、pyright 包含路径与 venv）
  - `.gitignore`（`/benchmarks/output/`）
- 关键决策：
  - Manifest 只存路径与标注；缺媒体时 dry-run / skip，不下载
  - DER 采用无复现的贪心说话人映射近似
  - WeSpeaker vs CAM++ 对比读取 predictions 侧车字段
- 验证结果：
  - `uv run pytest tests/test_benchmarks -q` 通过
  - `uv run python -m benchmarks.run --manifest tests/fixtures/manifests/example.json --dry-run` 成功列出缺失媒体并退出 0
- 已知限制：
  - 真实课堂/换位/遮挡样本未入库，需本机 `data/benchmark_media/`
  - 端到端真实模型/GPU 集成评估未在本机执行

## 全量回归（本次）

```text
uv run ruff check .
uv run pyright
uv run pytest -q -m "not integration"
```

- ruff：通过（并顺手清理 2 处既有 unused 告警）
- pyright：0 errors
- pytest：147 passed, 4 deselected（integration）

后续验证更新：WeSpeaker、PaddleOCR 与真实 FFmpeg 媒体已通过；FunASR 已通过完整真实视频转录。CUDA 仍未验证。

## TASK-011

- 状态：完成
- 真实视频任务：`jobs/real/<job-id>/`（私有样本不提交仓库）
- 输出：`output/01.txt`
- 结果：归一化序列相似度 `0.9064`，基准字符覆盖率 `0.9257`
- 兼容修复：PaddlePaddle 3.2.2、scikit-learn <1.8、WinGet FFmpeg 自动发现
- 完整记录：[TASK-011-real-video-validation.md](TASK-011-real-video-validation.md)

## TASK-012

- 状态：进行中（已完成 OCR 精确/模糊增量去重、安全上下文人物继承、全片 WeSpeaker/CAM++ 对比）
- 目标：OCR 模糊增量去重、短句人物归属、WeSpeaker/CAM++ 真实局部对比
- 当前结果：TXT 课板块 366 → 175；未知人物片段 31 → 16；CAM++ 全片对比已落盘
- 任务文件：[TASK-012-quality-iteration.md](TASK-012-quality-iteration.md)

## TASK-013 ~ TASK-017

- 状态：待执行
- 当前基线：阿峰前 20 课 40 案例已完成，36 published / 2 manual_review / 2 rejected / 0 failed；
- 当前离线包：`data/dify/afeng-release-v002.5/`，尚未正式导入；
- 当前 Dify：平台、管理员、economy Dataset 和冒烟文档已完成，embedding/正式索引/Workflow 未完成；
- 执行顺序：TASK-013 → TASK-014 → TASK-015 → TASK-016 → TASK-017；
- 任务入口：[TASK-013-afeng-stable-identity.md](TASK-013-afeng-stable-identity.md)。
