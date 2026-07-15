"""Protocols for board detection and OCR."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from course_video_analyzer.models import BoardCandidate, BoardRegion, OcrLine


class BoardDetector(Protocol):
    def detect(
        self,
        frame_path: Path,
        *,
        previous_region: BoardRegion | None = None,
    ) -> list[BoardCandidate]: ...


class BoardOcr(Protocol):
    def recognize(self, image_path: Path, artifact_dir: Path) -> list[OcrLine]: ...
