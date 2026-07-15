"""Gradio Blocks UI for course video analysis."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from course_video_analyzer.web.service import WebAnalysisFacade
from course_video_analyzer.web.validation import VideoValidationError

DEFAULT_JOBS_ROOT = Path("jobs")


def build_app(
    *,
    facade: WebAnalysisFacade | None = None,
    jobs_root: Path | None = None,
) -> Any:
    """Build the Gradio application without launching a browser."""
    try:
        gr = importlib.import_module("gradio")
    except ImportError as exc:
        raise RuntimeError("请先安装 Web 依赖：uv sync --extra web") from exc

    web = facade or WebAnalysisFacade(Path(jobs_root or DEFAULT_JOBS_ROOT))

    with gr.Blocks(title="课程视频分析") as app:
        gr.Markdown("# 课程视频分析")
        gr.Markdown(
            "上传课程视频，识别「谁在何时说了什么」以及同步课板内容。"
            " 默认仅监听 `127.0.0.1`。"
        )
        dep_md = gr.Markdown(web.dependency_banner())

        with gr.Row():
            with gr.Column(scale=1):
                video = gr.Video(label="课程视频", sources=["upload"])
                local_path = gr.Textbox(
                    label="或填写本地视频绝对路径",
                    placeholder=r"D:\videos\lesson.mp4",
                )
                device = gr.Dropdown(
                    choices=["cpu", "cuda"],
                    value="cpu",
                    label="计算设备",
                )
                processing_profile = gr.Dropdown(
                    choices=["complete-v1", "adaptive-complete", "adaptive-balanced"],
                    value="complete-v1",
                    label="处理模式（默认 01 完整度）",
                )
                interval_ms = gr.Number(
                    value=5000,
                    precision=0,
                    label="完整度优先抽帧间隔 (ms)",
                )
                board_mode = gr.Dropdown(
                    choices=["auto", "left", "right", "fullscreen"],
                    value="auto",
                    label="课板模式",
                )
                speaker_hint = gr.Number(
                    value=None,
                    precision=0,
                    label="说话人数提示（可空）",
                )
                inspect_btn = gr.Button("读取媒体信息")
                create_btn = gr.Button("创建并开始分析", variant="primary")
                media_md = gr.Markdown("媒体信息将显示在这里。")
                create_md = gr.Markdown()

            with gr.Column(scale=1):
                job_dropdown = gr.Dropdown(label="任务列表（运行中 / 历史）", choices=[])
                refresh_btn = gr.Button("刷新任务与进度")
                progress_md = gr.Markdown("选择任务后查看阶段进度。")
                preview_video = gr.Video(label="源视频预览", interactive=False)
                speech_md = gr.Markdown("讲话列表")
                boards_md = gr.Markdown("课板代表帧 / OCR")

        with gr.Accordion("人物映射与 OCR 修订", open=False):
            speaker_json = gr.Textbox(
                label='人物映射 JSON，例如 {"spk_0":"导师","spk_1":"助教"}',
                lines=3,
            )
            ocr_json = gr.Textbox(
                label=(
                    "OCR 修订 JSON 数组，例如 "
                    '[{"version_id":"v1","line_index":0,"corrected_text":"公式"}]'
                    "；只写入 corrected_text，不覆盖原始 text"
                ),
                lines=4,
            )
            save_rev_btn = gr.Button("保存修订")
            rev_md = gr.Markdown()

        with gr.Accordion("下载导出", open=False):
            dl_json = gr.File(label="analysis.json")
            dl_txt = gr.File(label="transcript.txt")
            dl_srt = gr.File(label="transcript.srt")
            dl_zip = gr.File(label="课板图片包 (zip)")
            refresh_dl_btn = gr.Button("刷新下载文件")

        def _resolve_video(upload: Any, typed: str | None) -> str:
            if typed and str(typed).strip():
                return str(typed).strip()
            if upload is None:
                raise VideoValidationError("请先上传视频或填写本地路径。")
            if isinstance(upload, dict):
                path = upload.get("path") or upload.get("name") or upload.get("video")
                if path:
                    return str(path)
            return str(upload)

        def on_inspect(upload: Any, typed: str | None) -> str:
            try:
                path = _resolve_video(upload, typed)
                media = web.inspect_media(path)
                return web.format_media_info(media)
            except Exception as exc:  # noqa: BLE001 - surface in UI
                return f"**无法读取媒体**：{exc}"

        def on_create(
            upload: Any,
            typed: str | None,
            device_v: str,
            profile_v: str,
            interval_v: float | int | None,
            board_v: str,
            speaker_v: float | int | None,
        ) -> tuple[str, Any]:
            try:
                path = _resolve_video(upload, typed)
                speaker_hint_i = None if speaker_v in (None, "") else int(speaker_v)
                state = web.create_job(
                    path,
                    device=str(device_v or "cpu"),
                    processing_profile=str(profile_v or "complete-v1"),
                    interval_ms=int(interval_v or 5000),
                    board_mode=str(board_v or "auto"),
                    speaker_count_hint=speaker_hint_i,
                    start=True,
                )
                choices = _job_choices(web)
                label = f"{state.job_id} | running | {Path(state.source_path).name}"
                msg = (
                    f"已创建任务 `{state.job_id}` 并在后台启动。"
                    " 请在右侧刷新进度；页面重载后仍可从任务目录恢复。"
                )
                return msg, gr.update(choices=choices, value=label)
            except Exception as exc:  # noqa: BLE001
                return f"**创建失败**：{exc}", gr.update()

        def on_refresh(selected: str | None) -> tuple[Any, str, Any, str, str, str, str]:
            choices = _job_choices(web)
            job_id = _parse_job_id(selected)
            if not job_id:
                return (
                    gr.update(choices=choices),
                    "请选择任务。",
                    None,
                    "",
                    "",
                    "",
                    "",
                )
            try:
                progress = web.format_progress(job_id)
                preview = web.preview_payload(job_id)
                speech = _format_speech(preview)
                boards = _format_boards(preview)
                source = preview.get("source_path") or None
                speakers = json.dumps(preview.get("speakers") or {}, ensure_ascii=False, indent=2)
                ocr = _format_ocr_editor(preview)
                label = _job_label(web, job_id) or selected
                return (
                    gr.update(choices=choices, value=label),
                    progress,
                    source,
                    speech,
                    boards,
                    speakers,
                    ocr,
                )
            except Exception as exc:  # noqa: BLE001
                return (
                    gr.update(choices=choices, value=selected),
                    f"**刷新失败**：{exc}",
                    None,
                    "",
                    "",
                    "",
                    "",
                )

        def on_save_revision(selected: str | None, speakers_raw: str, ocr_raw: str) -> str:
            job_id = _parse_job_id(selected)
            if not job_id:
                return "请先选择任务。"
            try:
                mapping = json.loads(speakers_raw or "{}")
                if not isinstance(mapping, dict):
                    raise ValueError("人物映射必须是 JSON 对象")
                corrections = json.loads(ocr_raw or "[]")
                if not isinstance(corrections, list):
                    raise ValueError("OCR 修订必须是 JSON 数组")
                web.save_speaker_mapping(job_id, {str(k): str(v) for k, v in mapping.items()})
                web.save_ocr_corrections(job_id, corrections)
                return (
                    f"已写入 `revisions.json`（任务 `{job_id}`）。"
                    " 原始 OCR `text` 未覆盖；TXT/SRT 已按修订重新导出。"
                )
            except Exception as exc:  # noqa: BLE001
                return f"**保存失败**：{exc}"

        def on_downloads(selected: str | None):
            empty = (None, None, None, None)
            job_id = _parse_job_id(selected)
            if not job_id:
                return empty
            try:
                bundle = web.download_bundle(job_id)
                return (
                    str(bundle.analysis_json) if bundle.analysis_json else None,
                    str(bundle.transcript_txt) if bundle.transcript_txt else None,
                    str(bundle.transcript_srt) if bundle.transcript_srt else None,
                    str(bundle.boards_zip) if bundle.boards_zip else None,
                )
            except Exception:  # noqa: BLE001
                return empty

        inspect_btn.click(on_inspect, inputs=[video, local_path], outputs=[media_md])
        create_btn.click(
            on_create,
            inputs=[
                video,
                local_path,
                device,
                processing_profile,
                interval_ms,
                board_mode,
                speaker_hint,
            ],
            outputs=[create_md, job_dropdown],
        )
        refresh_btn.click(
            on_refresh,
            inputs=[job_dropdown],
            outputs=[
                job_dropdown,
                progress_md,
                preview_video,
                speech_md,
                boards_md,
                speaker_json,
                ocr_json,
            ],
        )
        save_rev_btn.click(
            on_save_revision,
            inputs=[job_dropdown, speaker_json, ocr_json],
            outputs=[rev_md],
        )
        refresh_dl_btn.click(
            on_downloads,
            inputs=[job_dropdown],
            outputs=[dl_json, dl_txt, dl_srt, dl_zip],
        )

        app.load(lambda: web.dependency_banner(), outputs=[dep_md])
        app.load(lambda: gr.update(choices=_job_choices(web)), outputs=[job_dropdown])

    return app


def main(
    *,
    jobs_root: Path | None = None,
    server_name: str = "127.0.0.1",
    server_port: int = 7860,
    share: bool = False,
    inbrowser: bool = False,
) -> None:
    app = build_app(jobs_root=jobs_root)
    app.launch(
        server_name=server_name,
        server_port=server_port,
        share=share,
        inbrowser=inbrowser,
    )


def _job_choices(web: WebAnalysisFacade) -> list[str]:
    return [f"{item.job_id} | {item.status} | {item.source_name}" for item in web.list_jobs()]


def _parse_job_id(selected: str | None) -> str | None:
    if not selected:
        return None
    text = str(selected).strip()
    if not text:
        return None
    return text.split("|", 1)[0].strip()


def _job_label(web: WebAnalysisFacade, job_id: str) -> str | None:
    for item in web.list_jobs():
        if item.job_id == job_id:
            return f"{item.job_id} | {item.status} | {item.source_name}"
    return None


def _format_speech(preview: dict[str, Any]) -> str:
    rows = preview.get("speech") or []
    if not rows:
        return "_暂无讲话片段（任务未完成或无音轨）。_"
    lines = ["| 开始(ms) | 结束(ms) | 说话人 | 文本 |", "|---:|---:|---|---|"]
    for row in rows:
        lines.append(
            f"| {row['start_ms']} | {row['end_ms']} | "
            f"{row.get('speaker_name') or row.get('speaker_id')} | {row['text']} |"
        )
    return "\n".join(lines)


def _format_boards(preview: dict[str, Any]) -> str:
    rows = preview.get("boards") or []
    if not rows:
        return "_暂无课板片段。_"
    parts: list[str] = []
    for board in rows:
        parts.append(
            f"### `{board.get('version_id')}`  "
            f"{board.get('start_ms')}–{board.get('end_ms')} ms\n"
            f"图片：`{board.get('image_path')}`"
        )
        for line in board.get("lines") or []:
            corrected = line.get("corrected_text")
            extra = f" → **修订** `{corrected}`" if corrected else ""
            parts.append(
                f"- [{line.get('index')}] `{line.get('text')}`"
                f" (conf={line.get('confidence')}){extra}"
            )
    return "\n".join(parts)


def _format_ocr_editor(preview: dict[str, Any]) -> str:
    corrections: list[dict[str, Any]] = []
    for board in preview.get("boards") or []:
        version = board.get("version_id") or ""
        for line in board.get("lines") or []:
            if line.get("corrected_text"):
                corrections.append(
                    {
                        "version_id": version,
                        "line_index": line.get("index", 0),
                        "corrected_text": line.get("corrected_text"),
                    }
                )
    return json.dumps(corrections, ensure_ascii=False, indent=2)
