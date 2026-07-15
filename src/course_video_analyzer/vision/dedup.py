"""Page-change detection and board-version deduplication via pHash / SSIM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import cv2
import imagehash
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

PageDecision = Literal["same_page", "new_page"]


@dataclass(frozen=True)
class DedupConfig:
    """Central thresholds for same-page / page-change decisions.

    Same-page when:
    - pHash is close, **or**
    - SSIM is high **and** pHash is not wildly divergent, **or**
    - person-occlusion guard fires (occlusion jumped, structure still plausible).

    Requiring a pHash ceiling alongside SSIM prevents almost-identical layouts with
    different slide text from collapsing into one version.
    """

    phash_size: int = 16
    # Hamming distance on hash bits; at or below → similar by pHash alone.
    phash_same_max: int = 18
    # SSIM in [0, 1]; above → candidate for same_page (needs phash_ssim_max too).
    ssim_same_min: float = 0.78
    # Max pHash distance still allowed when leaning on SSIM.
    phash_ssim_max: int = 40
    # Resize crops before compare for scale robustness.
    compare_size: tuple[int, int] = (256, 256)
    # If skin occlusion rises a lot while SSIM stays above floor → same_page.
    person_occlusion_delta: float = 0.04
    person_ssim_floor: float = 0.50
    # Looser pHash ceiling when person_guard is also considering occlusion.
    person_phash_slack: int = 80


@dataclass(frozen=True)
class PageCompareResult:
    """Detailed comparison between two board crops."""

    decision: PageDecision
    reason: str
    phash_distance: int
    ssim: float
    same_by_phash: bool
    same_by_ssim: bool
    debug: dict[str, Any] = field(default_factory=dict)


class BoardPageDeduper:
    """Decide whether two board crops show the same slide/page."""

    def __init__(self, config: DedupConfig | None = None) -> None:
        self.config = config or DedupConfig()

    def compute_phash(self, image_bgr: np.ndarray) -> imagehash.ImageHash:
        """Perceptual hash on an edge-emphasized gray crop (layout-stable)."""
        prepared = self._prepare(image_bgr)
        # Edge emphasis reduces sensitivity to soft lighting changes.
        edges = cv2.Canny(prepared, 40, 120)
        blended = cv2.addWeighted(prepared, 0.65, edges, 0.35, 0)
        pil = Image.fromarray(blended)
        return imagehash.phash(pil, hash_size=self.config.phash_size)

    def phash_distance(self, a: imagehash.ImageHash, b: imagehash.ImageHash) -> int:
        return int(a - b)

    def compute_ssim(self, a_bgr: np.ndarray, b_bgr: np.ndarray) -> float:
        a = self._prepare(a_bgr)
        b = self._prepare(b_bgr)
        raw = structural_similarity(a, b, data_range=255)
        if isinstance(raw, tuple):
            raw = raw[0]
        return float(raw)

    def compare(
        self,
        previous_bgr: np.ndarray,
        current_bgr: np.ndarray,
        *,
        previous_occlusion: float | None = None,
        current_occlusion: float | None = None,
    ) -> PageCompareResult:
        """Compare two crops and return same_page / new_page with diagnostics."""
        cfg = self.config
        hash_prev = self.compute_phash(previous_bgr)
        hash_curr = self.compute_phash(current_bgr)
        distance = self.phash_distance(hash_prev, hash_curr)
        ssim = self.compute_ssim(previous_bgr, current_bgr)

        same_by_phash = distance <= cfg.phash_same_max
        same_by_ssim = ssim >= cfg.ssim_same_min and distance <= cfg.phash_ssim_max

        # Person motion: occlusion jumps while layout still plausible by SSIM / loose pHash.
        person_guard = False
        if (
            previous_occlusion is not None
            and current_occlusion is not None
            and abs(current_occlusion - previous_occlusion) >= cfg.person_occlusion_delta
            and ssim >= cfg.person_ssim_floor
            and distance <= cfg.person_phash_slack
        ):
            person_guard = True

        if same_by_phash or same_by_ssim or person_guard:
            if person_guard and not (same_by_phash or same_by_ssim):
                reason = "person_occlusion_guard"
            elif same_by_phash and same_by_ssim:
                reason = "phash_and_ssim_similar"
            elif same_by_phash:
                reason = "phash_similar"
            else:
                reason = "ssim_similar"
            decision: PageDecision = "same_page"
        else:
            decision = "new_page"
            reason = "phash_and_ssim_divergent"

        return PageCompareResult(
            decision=decision,
            reason=reason,
            phash_distance=distance,
            ssim=ssim,
            same_by_phash=same_by_phash,
            same_by_ssim=same_by_ssim,
            debug={
                "phash_same_max": cfg.phash_same_max,
                "phash_ssim_max": cfg.phash_ssim_max,
                "ssim_same_min": cfg.ssim_same_min,
                "person_guard": person_guard,
                "previous_occlusion": previous_occlusion,
                "current_occlusion": current_occlusion,
            },
        )

    def is_same_page(
        self,
        previous_bgr: np.ndarray,
        current_bgr: np.ndarray,
        *,
        previous_occlusion: float | None = None,
        current_occlusion: float | None = None,
    ) -> bool:
        return (
            self.compare(
                previous_bgr,
                current_bgr,
                previous_occlusion=previous_occlusion,
                current_occlusion=current_occlusion,
            ).decision
            == "same_page"
        )

    def _prepare(self, image_bgr: np.ndarray) -> np.ndarray:
        if image_bgr.size == 0:
            return np.zeros(self.config.compare_size, dtype=np.uint8)
        gray = image_bgr if image_bgr.ndim == 2 else cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, self.config.compare_size, interpolation=cv2.INTER_AREA)
