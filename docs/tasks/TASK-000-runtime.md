# TASK-000：Python 3.11 与依赖基线

## 目标

建立一套在 Windows 上可重复安装的 Python 3.11 环境，验证 FunASR、WeSpeaker、OpenCV、PaddleOCR 和 Gradio 可以共存。该任务是技术验证和依赖冻结任务，不实现业务流水线。

## 前置依赖

无。

## 允许修改

- `.python-version`
- `pyproject.toml`
- `uv.lock`
- `.gitignore`
- `scripts/verify_runtime.py`
- `docs/environment.md`
- 与运行环境验证直接相关的测试

不得修改领域模型、处理流水线或 Web 功能。

## 必须完成

1. 将项目 Python 版本固定为 `>=3.11,<3.12`；
2. 使用 uv 创建 Python 3.11 环境；
3. 将依赖拆为 `web`、`audio`、`vision` 和 `dev` 组；
4. WeSpeaker 使用明确的 Git commit 或 tag，不能跟随浮动的 `master`；
5. 明确 CPU 安装方式，并记录 CUDA 安装方式；
6. 编写运行环境检查脚本，检查 Python、FFmpeg、FFprobe、依赖导入和设备信息；
7. 验证 FunASR、WeSpeaker、OpenCV、PaddleOCR、Gradio 能在同一环境导入；
8. 记录模型缓存目录、预计下载体积和首次运行注意事项。

## 必须交付

- `.python-version`
- 更新后的 `pyproject.toml` 与 `uv.lock`
- `scripts/verify_runtime.py`
- `docs/environment.md`
- 依赖选择与版本记录

## 验收标准

- `uv sync --all-extras --group dev` 成功；
- `uv run python scripts/verify_runtime.py` 返回成功；
- 基础导入验证不触发模型下载；
- 文档分别给出 CPU 与 CUDA 安装说明；
- Windows 新环境能够根据文档复现。

## 验收命令

```powershell
uv python find 3.11
uv sync --all-extras --group dev
uv run python scripts/verify_runtime.py
uv run ruff check .
uv run pyright
uv run pytest -q -m "not integration"
```

## 非目标

- 不处理真实视频；
- 不下载完整识别模型作为提交内容；
- 不实现 FunASR 或 WeSpeaker 适配器；
- 不根据当前机器自动锁死 CUDA 版本。

## 交接重点

说明最终 Python、Torch、Torchaudio、WeSpeaker commit，以及哪些验证只在 CPU 或只在 CUDA 上执行过。
