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

## TASK-013 ~ TASK-018

- 状态：待执行（交 CC Switch；见 `docs/cursor-handoff/CCSWITCH-NEXT-AFENG-DIFY-PRODUCTIONIZATION.md`）
- 当前基线：阿峰前 20 课 40 案例已完成，36 published / 2 manual_review / 2 rejected / 0 failed；
- 当前离线包：`data/dify/afeng-release-v002.5/`（36 文档）；
- 当前 Dify（2026-07-17 独立验收后）：
  - 平台 1.15.0 / 管理员 / Dataset「阿峰课程方法库-研究版」(`economy`) / API Key：**已完成**
  - `afeng-release-v002.5` **已导入**，indexing 36/36 `completed`，keyword retrieve 有命中
  - 历史冒烟条目已从 document-map 清除；远端无 SMOKE
  - embedding / `high_quality` / Chatflow 可回答应用：**未完成**（外部密钥阻塞）
- 注意：TASK-013 须在已导入的 v002.5 之上做 canonical ID 迁移（v002.6），不能假设“尚未入库”
- 执行顺序：TASK-013 → TASK-014 → TASK-015 → TASK-016 → TASK-017 → TASK-018；
- TASK-015 优先走本地 embedding（候选 `BAAI/bge-m3`，必须以 Dify 1.15.0 实际兼容性验证为准）；
- TASK-016 使用新的正式 high_quality Dataset 和独立 map；已有 economy Dataset 只保留作工作/历史库；
- TASK-018 负责最终只读审计、备份/恢复 dry-run 和无上下文运维交接；
- 任务入口：[TASK-013-afeng-stable-identity.md](TASK-013-afeng-stable-identity.md)。

### TASK-013

- 状态：已完成
- 修改文件：
  - `src/course_video_analyzer/knowledge/afeng.py`（`canonical_knowledge_id` + 三个 ID 归一化器）
  - `src/course_video_analyzer/knowledge/afeng_pipeline.py`（manifest 永远取 canonical；draft/audit/publication 归一化写入）
  - `src/course_video_analyzer/knowledge/afeng_dify.py`（bundle 以 canonical 为权威身份 + model/run_token/input_hash/source_summary 血缘 + Markdown frontmatter 归一）
  - `src/course_video_analyzer/knowledge/dify_sync.py`（course+case 在场时用 canonical 作 map 幂等键）
  - `scripts/verify_afeng_release_bundle.py`（新增 bundle 完整性校验工具）
  - `tests/test_knowledge/test_afeng.py`、`tests/test_knowledge/test_afeng_dify.py`、`tests/test_knowledge/test_dify_sync.py`
  - `docs/tasks/TASK-013-afeng-stable-identity.md`、`docs/tasks/STATUS.md`
- 关键决策：
  - canonical ID `AFENG-{course_id}-{case_id}` 由程序控制，模型自写 ID 一律归一，不再作远端幂等主键；
  - historical 40 案例产物只读，不修改；迁移在 v002.6 bundle 层完成身份归一；
  - terminal 案例重跑 early-return，归一化写入只对新运行生效；
  - dify_sync 在 frontmatter 含 course+case 时用 canonical 作 map 键，使已入库 v002.5 可按 canonical 做 update/skip。
- 验证结果：`pytest -q` 263 passed、1 skipped；`ruff` 通过；`pyright` 0 errors。
- 下一任务 TASK-014 满足 Definition of Ready。

### TASK-014

- 状态：已完成
- 修改文件：
  - `data/dify/afeng-release-v002.6/`（36 文档 bundle + manifest + verify-report + case-review-report）
  - `docs/evaluation/afeng-v0026-case-review.md`
  - `docs/tasks/TASK-014-afeng-v0026-review.md`、`docs/tasks/STATUS.md`
- 关键决策：
  - v002.6 使用 7 个模型运行汇总文件构建，不调用模型；
  - 仅纳入 36 个 published 文档，4 个排除（manual_review/rejected）；
  - 所有文档使用 canonical ID `AFENG-{course_id}-{case_id}`；
  - Lineage 字段（model/run_token/input_hash/source_summary）100% 覆盖；
  - v002.5 历史包未被覆盖。
- 验证结果：
  - Bundle 校验：canonical 唯一 36/36、lineage 缺失 0、hash 不匹配 0、frontmatter 不匹配 0
  - Dry-run：create=36, update=0, skip=0, duplicate=0
  - 9 个重点案例审查完成，human_confirmation_required 仅用于排除案例
  - `pytest -q` 263 passed、1 skipped；`ruff` 通过
- 下一任务 TASK-015 满足 Definition of Ready。

### TASK-015

- 状态：代码完成（embedding Provider 需 Web UI 配置）
- 修改文件：
  - `src/course_video_analyzer/knowledge/dify_sync.py`（`sync_markdown_dir` 新增 `indexing_technique` 参数 + 模式校验 + dataset_id 不一致 fail-fast 防护）
  - `src/course_video_analyzer/knowledge/cli.py`（`dify-sync-markdown` 新增 `--indexing-technique`）
  - `tests/test_knowledge/test_dify_sync.py`（新增 5 个测试：显式参数、模式校验、回退逻辑、dataset_id 不一致 fail-fast、新 map 允许同步）
  - `scripts/probe_local_embedding.py`（embedding 探测工具）
  - `scripts/create_formal_dataset.py`（正式 Dataset 创建脚本）
  - `docs/evaluation/afeng-embedding-investigation.md`
  - `docs/tasks/STATUS.md`
- 关键决策：
  - 本地 embedding 已验证可用：Ollama v0.32.1 + bge-m3 (1024 维, GGUF F16)
  - `sync_markdown_dir` 新增 dataset_id 不一致校验：map 已绑定不同 dataset_id 时 fail-fast，防止跨 Dataset 错绑
  - 正式库必须使用独立 map（如 `data/dify/document-map-v1.json`），禁止复用旧 economy 工作库 map
  - 代码层面已移除硬编码、添加显式参数和模式校验
- 验证结果：`pytest -q` 268 passed、1 skipped；`ruff` 通过；`pyright` 0 errors。
- 阻塞：需用户通过 Dify Web UI 配置 Ollama embedding provider（一步操作）。
- Gate 1 状态：Ollama + bge-m3 宿主机验证 OK，Dify 侧需 Web UI 配置
- 详见 `docs/evaluation/afeng-embedding-investigation.md` 第六节精确 UI 步骤

### TASK-016

- 状态：代码完成（依赖正式 high_quality Dataset 可用）
- 已完成：
  - `data/dify/afeng-retrieval-test-v001.json`（20 问检索测试集，覆盖课程/案例/方法/条件/限制/话术/时间戳/evidence）
  - `scripts/run_afeng_retrieval_test.py`（检索验收脚本，生成 JSON + Markdown 报告）
  - `scripts/validate_afeng_citations.py`（引用校验器）
- 待完成：正式 Dataset 创建后执行真实同步和检索验收
- 阻塞：依赖 TASK-015 的 embedding Provider 配置

### TASK-017

- 状态：代码完成（依赖 Dify LLM Provider）
- 已完成：
  - `scripts/validate_afeng_citations.py`（引用校验器）
  - 20 问应用测试集（含在检索测试集中）
- 待完成：Workflow/Chatflow DSL、Prompt、应用验收
- 阻塞：需 Dify LLM Provider 配置

### TASK-018

- 状态：代码完成（离线审计已通过）
- 已完成：
  - `scripts/audit_afeng_production.py`（一键只读审计）
  - 离线审计结果：Bundle PASS（36 docs, 4 exclusions, canonical 36 unique, lineage 100%, hash 100%）、Aggregate PASS（40 cases, 36 published, 2 manual_review, 2 rejected, 0 failures）
  - Dify Dataset + Workflow 审计：待 TASK-016/017 完成后执行
- 验证结果：`pytest -q` 268 passed、1 skipped；`ruff` 通过；`pyright` 0 errors。
