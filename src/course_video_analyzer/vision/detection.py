"""Automatic board / slide region detection entrypoint."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from course_video_analyzer.models import BoardCandidate, BoardRegion
from course_video_analyzer.vision.candidates import (
    BoardMode,
    CandidateGenerator,
    CandidateGeneratorConfig,
)
from course_video_analyzer.vision.scoring import (
    BoardScorer,
    ScoringThresholds,
    ScoringWeights,
    TextDensityEstimator,
)

DebugOverlayStyle = Literal["boxes", "boxes_scores"]


@dataclass
class BoardDetectorConfig:
    """Runtime options for ``OpenCvBoardDetector``."""

    mode: BoardMode = "auto"
    top_k: int = 3
    min_score: float = 0.35
    keep_low_confidence: bool = False
    debug_dir: Path | None = None
    frame_index: int | None = None
    timestamp_ms: int | None = None
    candidate_config: CandidateGeneratorConfig | None = None
    weights: ScoringWeights | None = None
    text_density_estimator: TextDensityEstimator | None = None


class OpenCvBoardDetector:
    """OpenCV-backed ``BoardDetector`` for left / right / fullscreen layouts.

    Does not call OCR for text recognition. Text density defaults to edge density,
    and callers may inject a ``TextDensityEstimator`` that only returns densities.
    """

    def __init__(self, config: BoardDetectorConfig | None = None) -> None:
        self.config = config or BoardDetectorConfig()
        self.generator = CandidateGenerator(self.config.candidate_config)
        thresholds = ScoringThresholds(
            min_score=self.config.min_score,
            keep_low_confidence=self.config.keep_low_confidence,
        )
        self.scorer = BoardScorer(
            weights=self.config.weights or ScoringWeights(),
            thresholds=thresholds,
            text_density_estimator=self.config.text_density_estimator,
        )

    def detect(
        self,
        frame_path: Path,
        *,
        previous_region: BoardRegion | None = None,
    ) -> list[BoardCandidate]:
        image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"failed to read frame image: {frame_path}")

        proposals = self.generator.generate(image, mode=self.config.mode)
        candidates = self.scorer.score_all(
            image,
            proposals,
            previous_region=previous_region,
            frame_index=self.config.frame_index,
            timestamp_ms=self.config.timestamp_ms,
            top_k=self.config.top_k,
        )

        if self.config.debug_dir is not None:
            self.config.debug_dir.mkdir(parents=True, exist_ok=True)
            overlay_path = self.config.debug_dir / f"{frame_path.stem}_board_debug.png"
            self.render_debug_overlay(image, candidates, overlay_path)

        return candidates

    def render_debug_overlay(
        self,
        image_bgr: np.ndarray,
        candidates: list[BoardCandidate],
        output_path: Path,
        *,
        style: DebugOverlayStyle = "boxes_scores",
    ) -> Path:
        """Draw ranked candidate boxes and optional score text; write PNG."""
        canvas = image_bgr.copy()
        colors = [
            (40, 180, 40),
            (40, 160, 220),
            (220, 140, 40),
            (180, 80, 200),
        ]
        for idx, cand in enumerate(candidates):
            color = colors[idx % len(colors)]
            x1, y1, x2, y2 = cand.region.as_xyxy()
            thickness = 3 if idx == 0 else 2
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)
            if style == "boxes_scores":
                label = (
                    f"#{idx + 1} s={cand.score:.2f} "
                    f"a={cand.area_ratio:.2f} t={cand.text_density:.2f} "
                    f"o={cand.occlusion_ratio:.2f}"
                )
                ty = max(18, y1 - 8)
                cv2.putText(
                    canvas,
                    label,
                    (x1, ty),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    color,
                    1,
                    cv2.LINE_AA,
                )
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output_path), canvas):
            raise OSError(f"failed to write debug overlay: {output_path}")
        return output_path


# Convenience alias matching the Protocol name used in docs/handoffs.
BoardDetector = OpenCvBoardDetector
