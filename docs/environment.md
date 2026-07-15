# 运行环境说明

## Python 版本

本项目固定使用 **Python 3.11**（`requires-python = ">=3.11,<3.12"`）。

WeSpeaker 及相关 PyTorch / HDBSCAN 依赖在 Windows + Python 3.12 上兼容性较差，因此不允许使用 3.12。

```powershell
uv python install 3.11
uv sync --all-extras --group dev
```

当前冻结版本：

| 组件 | 版本 / 标识 |
|---|---|
| Python | 3.11（见 `.python-version`） |
| WeSpeaker | Git commit `dfa741957e5c11f477623b6e583d67d0af25ee88` |
| Torch / Torchaudio | `>=2.2,<2.7`（默认 CPU wheel） |
| FunASR | `>=1.2` |
| PaddleOCR | `>=3.0` |
| Gradio | `>=5.0` |
| OpenCV | `opencv-python>=4.10` |

## 依赖分组

| 组 | 用途 |
|---|---|
| 默认 | `pydantic` 与领域模型 |
| `web` | Gradio 本地界面 |
| `audio` | FunASR、WeSpeaker、Torch、聚类依赖 |
| `vision` | OpenCV、PaddleOCR、图像增强 |
| `dev` | pytest / ruff / pyright |

安装全部开发依赖：

```powershell
uv sync --all-extras --group dev
```

仅核心与测试：

```powershell
uv sync --group dev
```

## CPU 安装（默认）

`pyproject.toml` 已将 `torch` / `torchaudio` 指向 PyTorch CPU 索引：

```toml
[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true
```

因此默认 `uv sync --extra audio` 会安装 CPU 版 Torch，适合无独立显卡的开发机。

验证：

```powershell
uv run python scripts/verify_runtime.py
```

该脚本只做导入与工具检查，**不会下载识别模型**。

## CUDA 安装

若需要 GPU：

1. 确认本机已安装兼容的 NVIDIA 驱动与 CUDA Runtime（建议 CUDA 12.1 / 12.4 工具链）。
2. 临时覆盖 uv 源，安装对应 CUDA wheel，例如 CUDA 12.4：

```powershell
uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
```

3. 再安装项目其余依赖：

```powershell
uv sync --all-extras --group dev --no-install-package torch --no-install-package torchaudio
```

4. 用检查脚本确认：

```powershell
uv run python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
```

PaddleOCR / PaddlePaddle 的 GPU 轮子需按官方文档单独选择，避免与 CPU wheel 混装。第一版默认按 CPU 验收。

## 系统工具

必须安装并可在 PATH 中调用：

- `ffmpeg`
- `ffprobe`

Windows 可用 [gyan.dev builds](https://www.gyan.dev/ffmpeg/builds/) 或 `winget install Gyan.FFmpeg`。

若 `winget` 安装后新开终端仍找不到命令，将如下目录加入用户 PATH（版本号随安装变化）：

```text
%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-*-full_build\bin
```

## 模型缓存与首次运行

建议统一缓存根目录：

```text
%USERPROFILE%\.cache\course-video-analyzer\
├─ funasr\
├─ wespeaker\
└─ paddleocr\
```

也可沿用各框架默认缓存：

- FunASR / ModelScope：`%USERPROFILE%\.cache\modelscope\`
- WeSpeaker：首次 `load_model("chinese")` 时下载
- PaddleOCR：首次初始化时下载检测/识别模型

预计首次下载体积（约值，随版本变化）：

| 模型 | 大约体积 |
|---|---|
| FunASR 中文 Paraformer + 标点 | 200–500 MB |
| WeSpeaker chinese / CAM++ | 100–300 MB |
| PaddleOCR 中文检测+识别 | 20–100 MB |

首次运行注意：

1. 需要能访问 HuggingFace / ModelScope / GitHub Release（或提前手动放置模型）。
2. 单元测试使用 fake/mock，**不得**在 CI 中联网下载模型。
3. 真实模型测试使用 `pytest -m integration`。
4. 不要把模型权重、真实课程视频或 `jobs/` 输出提交到 Git。

## 验证矩阵

| 检查项 | CPU | CUDA |
|---|---|---|
| `uv sync --all-extras --group dev` | 必验 | 必验 |
| `scripts/verify_runtime.py` 导入 | 必验 | 必验 |
| FunASR 集成测试 | 可选 | 可选 |
| WeSpeaker 集成测试 | 可选 | 可选 |
| PaddleOCR 集成测试 | 可选 | 可选 |

若某项因网络、GPU 或驱动无法执行，应在任务交接中记为“未验证”，不得谎报通过。
