"""Protocols for speech recognition and speaker diarization."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from course_video_analyzer.models import SpeakerTurn, TranscriptSegment


class SpeechRecognizer(Protocol):
    def transcribe(self, wav_path: Path, artifact_dir: Path) -> list[TranscriptSegment]: ...


class SpeakerDiarizer(Protocol):
    def diarize(self, wav_path: Path, artifact_dir: Path) -> list[SpeakerTurn]: ...
