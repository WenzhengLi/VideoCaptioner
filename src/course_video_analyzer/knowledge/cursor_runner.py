"""Run one versioned cleaning stage in a fresh full-access Cursor Agent process."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

STAGE_PROMPTS = {
    "P01": "P01-normalize.md",
    "P02": "P02-classify.md",
    "P03": "P03-segment-cases.md",
    "P04": "P04-extract.md",
    "P05": "P05-review.md",
    "P06": "P06-tidy.md",
}


@dataclass(frozen=True)
class CursorStageConfig:
    cursor_agent: Path = Path(
        r"C:\Users\Administrator\AppData\Local\cursor-agent\cursor-agent.cmd"
    )
    model: str = "auto"
    prompt_root: Path = Path("prompts/knowledge-v001")
    timeout_seconds: int = 3600


def run_cursor_stage(
    course_id: str,
    stage: str,
    input_path: Path,
    output_path: Path,
    workspace: Path,
    *,
    config: CursorStageConfig | None = None,
) -> Path:
    """Execute one stage without resuming any previous Cursor conversation."""
    cfg = config or CursorStageConfig()
    stage = stage.upper()
    if stage not in STAGE_PROMPTS:
        raise ValueError(f"未知 Cursor 阶段: {stage}")
    workspace = Path(workspace).resolve()
    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()
    prompt_path = (workspace / cfg.prompt_root / STAGE_PROMPTS[stage]).resolve()
    cursor_agent = Path(cfg.cursor_agent).resolve()
    if not cursor_agent.is_file():
        raise FileNotFoundError(f"Cursor Agent 不存在: {cursor_agent}")
    if not prompt_path.is_file():
        raise FileNotFoundError(f"阶段 Prompt 不存在: {prompt_path}")
    if not input_path.is_file():
        raise FileNotFoundError(f"阶段输入不存在: {input_path}")
    if output_path.exists():
        raise FileExistsError(f"阶段输出已存在，拒绝覆盖: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = output_path.with_suffix(output_path.suffix + ".cursor.log")

    instruction = f"""使用 Flow 工作方式完成一次独立、无上下文继承的课程清洗任务。

课程 ID：{course_id}
阶段：{stage}
规则文件：{prompt_path}
输入文件：{input_path}
唯一允许写入的结果文件：{output_path}

严格要求：
1. 先完整读取规则文件，再按规则处理输入文件。
2. 不得修改输入文件、规则文件、项目源代码或其他课程数据。
3. 输出必须是严格可解析的 UTF-8 JSON，不要使用 Markdown 代码围栏。
4. 保留证据定位、原始文本和不确定项；不得为了缩短结果而删除有效内容。
5. 写入后必须重新读取并解析 JSON，自检失败则修正。
6. 完成后只在最终响应中输出 CURSOR_STAGE_COMPLETED。
"""
    command = [
        str(cursor_agent),
        "-p",
        "--force",
        "--sandbox",
        "disabled",
        "--approve-mcps",
        "--trust",
        "--workspace",
        str(workspace),
        "--model",
        cfg.model,
        "--output-format",
        "text",
        instruction,
    ]
    process = subprocess.Popen(
        command,
        cwd=workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = process.communicate(timeout=cfg.timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        stdout, stderr = process.communicate()
        log_path.write_text((stdout or "") + ("\n" + stderr if stderr else ""), encoding="utf-8")
        raise TimeoutError(
            f"Cursor 阶段超时: course={course_id}, stage={stage}, log={log_path}"
        ) from exc
    log_path.write_text(
        (stdout or "") + ("\n" + stderr if stderr else ""),
        encoding="utf-8",
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"Cursor 阶段失败: course={course_id}, stage={stage}, "
            f"exit={process.returncode}, log={log_path}"
        )
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Cursor 未生成有效输出: {output_path}; log={log_path}")
    try:
        json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cursor 输出不是有效 JSON: {output_path}") from exc
    return output_path
