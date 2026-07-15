"""Web-facing facade over ``AnalysisService`` (TASK-008) plus revision I/O."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from course_video_analyzer.exporters.json_exporter import export_analysis_json
from course_video_analyzer.exporters.srt_exporter import export_srt
from course_video_analyzer.exporters.txt_exporter import export_txt
from course_video_analyzer.jobs.workspace import JobWorkspace, atomic_write_text
from course_video_analyzer.models import (
    AnalysisResult,
    JobStage,
    JobState,
    MediaInfo,
    StageStatus,
)
from course_video_analyzer.pipeline import (
    PIPELINE_STAGES,
    REL_ANALYSIS,
    REL_BOARDS_INDEX,
    REL_SRT,
    REL_TXT,
    AnalysisService,
)
from course_video_analyzer.processing_profiles import DEFAULT_PROCESSING_PROFILE
from course_video_analyzer.web.revisions import (
    JobRevision,
    OcrLineCorrection,
    apply_revision_to_result,
    load_revision,
    merge_ocr_corrections,
    merge_speaker_mapping,
    save_revision,
)
from course_video_analyzer.web.runner import JobRunner
from course_video_analyzer.web.validation import VideoValidationError, validate_video_path

STAGE_HINTS: dict[str, str] = {
    JobStage.MEDIA.value: "检查 FFmpeg/FFprobe 是否在 PATH，并确认视频文件未损坏。",
    JobStage.TRANSCRIPT.value: "安装音频依赖：`uv sync --extra audio`，并确认 FunASR 模型可下载。",
    JobStage.DIARIZATION.value: "安装音频依赖：`uv sync --extra audio`，并确认 WeSpeaker 可导入。",
    JobStage.ALIGNMENT.value: "转录与说话人结果为空时也会完成；若失败请查看 artifacts/audio。",
    JobStage.BOARD_DETECT.value: "安装视觉依赖：`uv sync --extra vision`；或增大抽帧间隔。",
    JobStage.BOARD_TRACK.value: "检查预览帧是否生成；可切换课板模式或提供手动框选（后续版本）。",
    JobStage.BOARD_OCR.value: "安装视觉依赖：`uv sync --extra vision`，并确认 PaddleOCR 模型可用。",
    JobStage.MERGE.value: "确认 alignment 与 board segments JSON 可读。",
    JobStage.EXPORT.value: "确认磁盘可写且 artifacts 目录存在。",
}


@dataclass
class DependencyStatus:
    gradio: bool
    audio: bool
    vision: bool
    ffmpeg: bool
    messages: list[str] = field(default_factory=list)

    @property
    def ok_for_pipeline(self) -> bool:
        return self.ffmpeg and self.audio and self.vision


def probe_dependencies() -> DependencyStatus:
    import importlib
    import shutil

    messages: list[str] = []
    gradio_ok = True
    try:
        importlib.import_module("gradio")
    except ImportError:
        gradio_ok = False
        messages.append("未安装 Gradio。请执行：`uv sync --extra web`")

    audio_ok = True
    try:
        importlib.import_module("funasr")
        importlib.import_module("wespeaker")
    except ImportError:
        audio_ok = False
        messages.append("未安装音频依赖。请执行：`uv sync --extra audio`")

    vision_ok = True
    try:
        importlib.import_module("cv2")
        importlib.import_module("paddleocr")
    except ImportError:
        vision_ok = False
        messages.append("未安装视觉依赖。请执行：`uv sync --extra vision`")

    ffmpeg_ok = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
    if not ffmpeg_ok:
        messages.append("未找到 ffmpeg/ffprobe，请安装 FFmpeg 并加入 PATH。")

    return DependencyStatus(
        gradio=gradio_ok,
        audio=audio_ok,
        vision=vision_ok,
        ffmpeg=ffmpeg_ok,
        messages=messages,
    )


@dataclass
class JobSummary:
    job_id: str
    source_name: str
    status: str
    updated_at: str
    failed_stage: str | None = None


@dataclass
class DownloadBundle:
    analysis_json: Path | None
    transcript_txt: Path | None
    transcript_srt: Path | None
    boards_index: Path | None
    boards_zip: Path | None


class WebAnalysisFacade:
    """TASK-009 service boundary: create/list/poll/revise/download via AnalysisService."""

    def __init__(
        self,
        jobs_root: Path,
        *,
        analysis_service: AnalysisService | None = None,
        service_factory: Callable[[], AnalysisService] | None = None,
        runner: JobRunner | None = None,
        max_upload_bytes: int | None = None,
    ) -> None:
        self.jobs_root = Path(jobs_root)
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self._service = analysis_service
        self._service_factory = service_factory
        self.runner = runner or JobRunner()
        self.max_upload_bytes = max_upload_bytes

    def get_analysis_service(self) -> AnalysisService:
        if self._service is not None:
            return self._service
        if self._service_factory is not None:
            self._service = self._service_factory()
            return self._service
        from course_video_analyzer.pipeline import create_default_analysis_service

        try:
            self._service = create_default_analysis_service()
        except RuntimeError as exc:
            deps = probe_dependencies()
            hint = "；".join(deps.messages) if deps.messages else str(exc)
            raise RuntimeError(f"无法初始化处理管线：{hint}") from exc
        return self._service

    def inspect_media(self, video_path: str | Path) -> MediaInfo:
        path = self._validated(video_path)
        service = self.get_analysis_service()
        return service.deps.media_processor.inspect(path)

    def create_job(
        self,
        video_path: str | Path,
        *,
        device: str = "cpu",
        processing_profile: str = DEFAULT_PROCESSING_PROFILE,
        interval_ms: int = 5000,
        board_mode: str = "auto",
        speaker_count_hint: int | None = None,
        max_frames: int = 800,
        extra_config: dict[str, Any] | None = None,
        start: bool = True,
    ) -> JobState:
        path = self._validated(video_path)
        config: dict[str, Any] = {
            "device": device,
            "processing_profile": processing_profile,
            "interval_ms": int(interval_ms),
            "board_mode": board_mode,
            "max_frames": int(max_frames),
        }
        if speaker_count_hint is not None:
            config["speaker_count_hint"] = int(speaker_count_hint)
        if extra_config:
            config.update(extra_config)

        service = self.get_analysis_service()
        workspace = service.create_job(path, self.jobs_root, config=config)
        if start:
            self.start_job(workspace.job_id)
        return workspace.load_state()

    def start_job(self, job_id: str, *, resume: bool = True) -> None:
        workspace = self.open_workspace(job_id)

        def _run() -> None:
            service = self.get_analysis_service()
            service.run(workspace, resume=resume)

        self.runner.submit(job_id, _run)

    def open_workspace(self, job_id: str) -> JobWorkspace:
        ws = JobWorkspace(self.jobs_root, job_id=job_id)
        if not ws.job_json.exists():
            raise FileNotFoundError(f"任务不存在: {job_id}")
        return ws

    def list_jobs(self) -> list[JobSummary]:
        summaries: list[JobSummary] = []
        if not self.jobs_root.exists():
            return summaries
        for child in sorted(self.jobs_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            job_json = child / "job.json"
            if not job_json.is_file():
                continue
            try:
                state = JobState.model_validate_json(job_json.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            summaries.append(self._summarize(state))
        return summaries

    def get_state(self, job_id: str) -> JobState:
        return self.open_workspace(job_id).load_state()

    def format_progress(self, job_id: str) -> str:
        state = self.get_state(job_id)
        lines = [
            f"**任务** `{state.job_id}`",
            f"源文件：`{Path(state.source_path).name}`",
            f"更新：{state.updated_at}",
            "",
            "| 阶段 | 状态 | 说明 |",
            "|---|---|---|",
        ]
        failed: StageStatus | None = None
        failed_stage: str | None = None
        failed_error: str | None = None
        for stage in PIPELINE_STAGES:
            stage_state = state.stages.get(stage.value)
            if stage_state is None:
                status = StageStatus.PENDING.value
                note = ""
            else:
                status = stage_state.status.value
                note = stage_state.error or ""
                if stage_state.status is StageStatus.FAILED:
                    failed = stage_state.status
                    failed_stage = stage.value
                    failed_error = stage_state.error
            lines.append(f"| `{stage.value}` | {status} | {note} |")

        runtime_error = self.runner.get_error(job_id)
        if failed_stage and failed_error:
            hint = STAGE_HINTS.get(failed_stage, "查看 logs/ 与失败阶段 artifacts。")
            lines.extend(
                [
                    "",
                    f"**失败阶段**：`{failed_stage}`",
                    f"**错误**：{failed_error}",
                    f"**建议**：{hint}",
                ]
            )
        elif runtime_error and not failed:
            lines.extend(["", "**后台异常**：", f"```\n{runtime_error}\n```"])

        running = self.runner.is_running(job_id)
        lines.append("")
        lines.append(f"后台线程：{'运行中' if running else '空闲'}")
        return "\n".join(lines)

    def load_result_with_revisions(self, job_id: str) -> AnalysisResult | None:
        workspace = self.open_workspace(job_id)
        service = self.get_analysis_service()
        raw = service.load_result(workspace)
        if raw is None:
            return None
        revision = load_revision(workspace.job_dir)
        return apply_revision_to_result(raw, revision)

    def load_revision(self, job_id: str) -> JobRevision:
        return load_revision(self.open_workspace(job_id).job_dir)

    def save_speaker_mapping(self, job_id: str, mapping: dict[str, str]) -> JobRevision:
        workspace = self.open_workspace(job_id)
        revision = merge_speaker_mapping(load_revision(workspace.job_dir), mapping)
        save_revision(workspace.job_dir, revision)
        self._reexport_if_possible(job_id)
        return revision

    def save_ocr_corrections(
        self,
        job_id: str,
        corrections: list[OcrLineCorrection | dict[str, Any]],
    ) -> JobRevision:
        workspace = self.open_workspace(job_id)
        revision = merge_ocr_corrections(load_revision(workspace.job_dir), corrections)
        save_revision(workspace.job_dir, revision)
        self._reexport_if_possible(job_id)
        return revision

    def preview_payload(self, job_id: str) -> dict[str, Any]:
        result = self.load_result_with_revisions(job_id)
        state = self.get_state(job_id)
        revision = self.load_revision(job_id)
        if result is None:
            return {
                "job_id": job_id,
                "ready": False,
                "speech": [],
                "boards": [],
                "speakers": revision.speakers,
                "source_path": str(state.source_path),
            }

        speech_rows = [
            {
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "speaker_id": s.speaker_id,
                "speaker_name": s.speaker_name or s.speaker_id,
                "text": s.text,
            }
            for s in result.speech_segments
        ]
        board_rows = []
        for board in result.board_segments:
            board_rows.append(
                {
                    "version_id": board.version_id,
                    "start_ms": board.start_ms,
                    "end_ms": board.end_ms,
                    "image_path": str(board.image_path),
                    "lines": [
                        {
                            "index": index,
                            "text": line.text,
                            "corrected_text": line.corrected_text,
                            "confidence": line.confidence,
                        }
                        for index, line in enumerate(board.text_lines)
                    ],
                }
            )
        return {
            "job_id": job_id,
            "ready": True,
            "speech": speech_rows,
            "boards": board_rows,
            "speakers": result.speakers,
            "source_path": str(state.source_path),
            "media": result.media.model_dump(mode="json"),
        }

    def download_bundle(self, job_id: str) -> DownloadBundle:
        workspace = self.open_workspace(job_id)
        job_dir = workspace.job_dir
        analysis = job_dir / REL_ANALYSIS
        txt = job_dir / REL_TXT
        srt = job_dir / REL_SRT
        boards_index = job_dir / REL_BOARDS_INDEX
        zip_path = self.package_boards_zip(job_id)
        return DownloadBundle(
            analysis_json=analysis if analysis.exists() else None,
            transcript_txt=txt if txt.exists() else None,
            transcript_srt=srt if srt.exists() else None,
            boards_index=boards_index if boards_index.exists() else None,
            boards_zip=zip_path,
        )

    def package_boards_zip(self, job_id: str) -> Path | None:
        workspace = self.open_workspace(job_id)
        boards_dir = workspace.job_dir / "artifacts" / "boards"
        if not boards_dir.exists():
            return None
        zip_path = workspace.artifacts_dir / "boards_pack.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in boards_dir.rglob("*"):
                if path.is_file():
                    zf.write(path, arcname=str(path.relative_to(boards_dir)))
        return zip_path if zip_path.exists() else None

    def format_media_info(self, media: MediaInfo) -> str:
        duration_s = media.duration_ms / 1000.0
        return (
            f"**文件**：`{Path(media.source_path).name}`\n\n"
            f"- 时长：{duration_s:.1f}s（{media.duration_ms} ms）\n"
            f"- 分辨率：{media.width}×{media.height} @ {media.fps:.2f} fps\n"
            f"- 视频流：{'有' if media.has_video else '无'}（{media.video_codec or '-'}）\n"
            f"- 音频流：{'有' if media.has_audio else '无'} "
            f"({media.audio_sample_rate or '-'} Hz, {media.audio_channels or '-'} ch, "
            f"{media.audio_codec or '-'})"
        )

    def dependency_banner(self) -> str:
        deps = probe_dependencies()
        if not deps.messages:
            return "依赖检查：Gradio / 音频 / 视觉 / FFmpeg 可用。"
        bullets = "\n".join(f"- {m}" for m in deps.messages)
        return f"**依赖提示（不会因此直接崩溃，但完整分析可能失败）**\n\n{bullets}"

    def _validated(self, video_path: str | Path) -> Path:
        kwargs: dict[str, Any] = {}
        if self.max_upload_bytes is not None:
            kwargs["max_bytes"] = self.max_upload_bytes
        try:
            return validate_video_path(video_path, **kwargs)
        except VideoValidationError:
            raise

    def _summarize(self, state: JobState) -> JobSummary:
        failed_stage = None
        statuses = []
        for stage in PIPELINE_STAGES:
            stage_state = state.stages.get(stage.value)
            if stage_state is None:
                continue
            statuses.append(stage_state.status)
            if stage_state.status is StageStatus.FAILED:
                failed_stage = stage.value
        if any(s is StageStatus.RUNNING for s in statuses) or self.runner.is_running(state.job_id):
            status = "running"
        elif failed_stage:
            status = "failed"
        elif statuses and all(s is StageStatus.COMPLETED for s in statuses):
            status = "completed"
        else:
            status = "pending"
        return JobSummary(
            job_id=state.job_id,
            source_name=Path(state.source_path).name,
            status=status,
            updated_at=state.updated_at,
            failed_stage=failed_stage,
        )

    def _reexport_if_possible(self, job_id: str) -> None:
        """Rewrite human exports from revised view without touching raw JSON snapshot fields."""
        result = self.load_result_with_revisions(job_id)
        if result is None:
            return
        workspace = self.open_workspace(job_id)
        # Keep raw analysis.json as machine snapshot; write display overlay separately.
        overlay = workspace.job_dir / "artifacts" / "analysis.revised.json"
        export_analysis_json(result, overlay)
        export_txt(result, workspace.job_dir / REL_TXT)
        export_srt(result, workspace.job_dir / REL_SRT)
        meta = {
            "note": "TXT/SRT 已应用 revisions.json；原始 OCR text 仍保存在 analysis.json",
            "revision": load_revision(workspace.job_dir).model_dump(mode="json"),
        }
        atomic_write_text(
            workspace.job_dir / "artifacts" / "revision_export_meta.json",
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        )
