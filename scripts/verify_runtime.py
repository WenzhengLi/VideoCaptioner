"""Verify Python 3.11 runtime and optional dependency imports without downloading models."""

from __future__ import annotations

import argparse
import importlib
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _run(cmd: list[str]) -> tuple[int, str]:
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, output.strip()


def check_python() -> CheckResult:
    version = sys.version_info
    ok = version.major == 3 and version.minor == 11
    detail = f"{sys.version.split()[0]} ({sys.executable})"
    if not ok:
        detail += "；需要 Python 3.11"
    return CheckResult("python", ok, detail)


def check_tool(name: str) -> CheckResult:
    path = shutil.which(name)
    if not path:
        return CheckResult(name, False, "未在 PATH 中找到")
    # ffmpeg/ffprobe use -version; most other tools use --version
    flag = "-version" if name.startswith("ff") else "--version"
    code, output = _run([name, flag])
    version_line = output.splitlines()[0] if output else ""
    return CheckResult(name, code == 0, f"{path}; {version_line}")


def check_import(module: str, attr: str | None = None) -> CheckResult:
    try:
        mod = importlib.import_module(module)
        if attr:
            getattr(mod, attr)
        version = getattr(mod, "__version__", "unknown")
        return CheckResult(module, True, f"version={version}")
    except Exception as exc:  # noqa: BLE001 - surface exact import failure
        return CheckResult(module, False, f"{type(exc).__name__}: {exc}")


def check_torch_device() -> CheckResult:
    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        return CheckResult("torch.device", False, f"{type(exc).__name__}: {exc}")
    cuda = torch.cuda.is_available()
    detail = f"cuda_available={cuda}"
    if cuda:
        detail += f"; device0={torch.cuda.get_device_name(0)}"
    else:
        detail += "; using CPU"
    return CheckResult("torch.device", True, detail)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Course Video Analyzer runtime")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON summary",
    )
    parser.add_argument(
        "--strict-optional",
        action="store_true",
        help="Fail when optional extras (audio/vision/web) cannot be imported",
    )
    args = parser.parse_args()

    required = [
        check_python(),
        check_import("pydantic"),
    ]
    tools = [
        check_tool("ffmpeg"),
        check_tool("ffprobe"),
    ]
    optional = [
        check_import("torch"),
        check_import("torchaudio"),
        check_import("funasr"),
        check_import("wespeaker"),
        check_import("cv2"),
        check_import("paddleocr"),
        check_import("gradio"),
        check_torch_device(),
    ]

    results = required + tools + optional
    required_ok = all(item.ok for item in required)
    tools_ok = all(item.ok for item in tools)
    optional_ok = all(item.ok for item in optional)

    summary = {
        "required_ok": required_ok,
        "tools_ok": tools_ok,
        "optional_ok": optional_ok,
        "checks": [asdict(item) for item in results],
        "notes": [
            "本脚本只验证导入与工具可用性，不会下载 FunASR/WeSpeaker/PaddleOCR 模型。",
            "CPU wheel 默认来自 pytorch-cpu 索引；CUDA 安装见 docs/environment.md。",
            f"模型建议缓存目录: {Path.home() / '.cache' / 'course-video-analyzer'}",
        ],
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("Course Video Analyzer 运行环境检查")
        print("=" * 48)
        for item in results:
            mark = "OK" if item.ok else "FAIL"
            print(f"[{mark}] {item.name}: {item.detail}")
        print("=" * 48)
        print(f"required_ok={required_ok} tools_ok={tools_ok} optional_ok={optional_ok}")
        for note in summary["notes"]:
            print(f"- {note}")

    if not required_ok:
        return 1
    if not tools_ok:
        print("警告: FFmpeg/FFprobe 缺失，媒体探测与抽帧将不可用。", file=sys.stderr)
        return 1
    if args.strict_optional and not optional_ok:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
