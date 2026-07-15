"""Unit tests for page dedup (pHash/SSIM) and representative keyframe scoring."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from course_video_analyzer.models import BoardRegion
from course_video_analyzer.vision.dedup import BoardPageDeduper, DedupConfig
from course_video_analyzer.vision.keyframes import KeyframeScorer, KeyframeScoringConfig
from course_video_analyzer.vision.tracking import BoardTracker, FrameSample

FRAME_W, FRAME_H = 960, 540


def _page_crop(*, seed: int, scale: float = 1.0, person: bool = False) -> np.ndarray:
    """Synthetic board crop with strongly distinct page families."""
    w = int(400 * scale)
    h = int(300 * scale)
    image = np.full((h, w, 3), 240, dtype=np.uint8)
    family = seed % 4
    color = (20, 20, 20)
    if family == 0:
        for i, yy in enumerate(range(30, h - 20, 16)):
            cv2.line(image, (20, yy), (20 + int(w * 0.7), yy), color, 2)
    elif family == 1:
        for xx in range(30, w - 20, 18):
            cv2.line(image, (xx, 40), (xx, h - 30), color, 2)
        cv2.rectangle(image, (40, 50), (w // 2, h // 2), color, 3)
    elif family == 2:
        for i in range(8):
            y0 = 40 + i * (h // 10)
            cv2.line(image, (30, y0), (w - 40, y0 + 25), color, 2)
            cv2.circle(image, (80 + i * 35, y0 + 15), 10, color, 2)
    else:
        for r in range(3):
            for c in range(4):
                if (r + c + seed) % 3 == 0:
                    continue
                x0, y0 = 30 + c * (w // 5), 40 + r * (h // 4)
                cv2.rectangle(image, (x0, y0), (x0 + 50, y0 + 40), color, -1)

    cv2.putText(
        image,
        f"PAGE{seed}",
        (24, 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        color,
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        f"ID{seed * 13}",
        (w // 4, h // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.4,
        color,
        3,
        cv2.LINE_AA,
    )

    if person:
        pw, ph = w // 2, int(h * 0.55)
        x, y = w - pw - 8, h - ph - 8
        cv2.rectangle(image, (x, y), (x + pw, y + ph), (40, 40, 40), thickness=-1)
        cv2.ellipse(
            image,
            (x + pw // 2, y + ph // 2),
            (max(1, pw // 2), max(1, ph // 2)),
            0,
            0,
            360,
            (90, 140, 200),
            thickness=-1,
        )
    return image


def _board_frame(*, page_seed: int, person_xy: tuple[int, int] | None = None) -> tuple[np.ndarray, BoardRegion]:
    """Minimal left-board frame used by tracker-integrated dedup tests."""
    image = np.full((FRAME_H, FRAME_W, 3), 48, dtype=np.uint8)
    board = BoardRegion(x=20, y=30, width=560, height=480)
    cv2.rectangle(
        image,
        (board.x, board.y),
        (board.x + board.width, board.y + board.height),
        (245, 245, 245),
        thickness=-1,
    )
    cv2.rectangle(
        image,
        (board.x, board.y),
        (board.x + board.width, board.y + board.height),
        (150, 150, 150),
        thickness=3,
    )
    crop = _page_crop(seed=page_seed)
    resized = cv2.resize(crop, (board.width - 20, board.height - 20))
    image[board.y + 10 : board.y + 10 + resized.shape[0], board.x + 10 : board.x + 10 + resized.shape[1]] = (
        resized
    )
    if person_xy is None:
        person_xy = (640, 320)
    pw, ph = 280, 180
    cv2.rectangle(
        image,
        person_xy,
        (person_xy[0] + pw, person_xy[1] + ph),
        (35, 35, 35),
        thickness=-1,
    )
    cv2.ellipse(
        image,
        (person_xy[0] + pw // 2, person_xy[1] + ph // 2),
        (pw // 3, ph // 3),
        0,
        0,
        360,
        (90, 140, 200),
        thickness=-1,
    )
    return image, board


def _samples(images: list[np.ndarray], *, interval_ms: int = 1000) -> list[FrameSample]:
    return [
        FrameSample(frame_index=i, timestamp_ms=i * interval_ms, image_bgr=img)
        for i, img in enumerate(images)
    ]


def test_same_page_under_scale() -> None:
    deduper = BoardPageDeduper()
    a = _page_crop(seed=3, scale=1.0)
    b = cv2.resize(a, (int(a.shape[1] * 0.92), int(a.shape[0] * 0.92)))
    result = deduper.compare(a, b)
    assert result.decision == "same_page"
    assert result.same_by_phash or result.same_by_ssim


def test_person_occlusion_does_not_force_new_page() -> None:
    """Skin-toned person overlay should keep same_page when layout is unchanged."""
    deduper = BoardPageDeduper()
    clean = _page_crop(seed=11, person=False)
    occluded = _page_crop(seed=11, person=True)
    scorer = KeyframeScorer()
    occ_clean = scorer.score_crop(clean).occlusion_ratio
    occ_person = scorer.score_crop(occluded).occlusion_ratio
    result = deduper.compare(
        clean,
        occluded,
        previous_occlusion=occ_clean,
        current_occlusion=occ_person,
    )
    assert result.decision == "same_page"
    assert result.reason in {
        "phash_similar",
        "ssim_similar",
        "phash_and_ssim_similar",
        "person_occlusion_guard",
    }


def test_true_page_change_produces_new_page() -> None:
    deduper = BoardPageDeduper()
    a = _page_crop(seed=1)  # family 1
    b = _page_crop(seed=2)  # family 2
    result = deduper.compare(a, b)
    assert result.decision == "new_page"
    assert result.reason == "phash_and_ssim_divergent"
    assert not result.same_by_phash
    assert not result.same_by_ssim


def test_is_same_page_helper() -> None:
    deduper = BoardPageDeduper(DedupConfig())
    assert deduper.is_same_page(_page_crop(seed=4), _page_crop(seed=4))
    assert not deduper.is_same_page(_page_crop(seed=4), _page_crop(seed=1))


def test_keyframe_prefers_sharp_low_occlusion() -> None:
    scorer = KeyframeScorer(KeyframeScoringConfig())
    sharp = _page_crop(seed=2, person=False)
    blurry = cv2.GaussianBlur(sharp, (31, 31), 0)
    occluded = _page_crop(seed=2, person=True)
    best_i, best = scorer.pick_best([blurry, occluded, sharp])
    assert best_i == 2
    assert best.total >= scorer.score_crop(blurry).total
    assert best.total >= scorer.score_crop(occluded).total
    assert best.occlusion_ratio <= scorer.score_crop(occluded).occlusion_ratio


def test_tracker_dedups_same_page_with_person_motion(tmp_path: Path) -> None:
    """Slight person PIP motion on one page → single version."""
    imgs: list[np.ndarray] = []
    gt: BoardRegion | None = None
    for person_x in (640, 690, 650, 700, 660):
        img, board = _board_frame(page_seed=8, person_xy=(person_x, 320))
        imgs.append(img)
        if gt is None:
            gt = board
    result = BoardTracker().track(
        _samples(imgs),
        output_dir=tmp_path / "dedup_person",
        initial_region=gt,
    )
    assert len(result.segments) == 1
    seg = result.segments[0]
    assert seg.end_ms > seg.start_ms
    assert seg.image_path.exists()
    assert seg.page_change_reason is None


def test_tracker_new_page_creates_version(tmp_path: Path) -> None:
    page_a = [_board_frame(page_seed=1)[0] for _ in range(2)]
    page_b = [_board_frame(page_seed=2)[0] for _ in range(2)]
    frames = _samples(page_a + page_b)
    result = BoardTracker().track(frames, output_dir=tmp_path / "dedup_pages")
    assert len(result.segments) >= 2
    assert result.segments[0].version_id != result.segments[1].version_id
    assert result.segments[1].page_change_reason is not None
    for seg in result.segments:
        assert seg.image_path.suffix.lower() == ".png"
        assert seg.image_path.exists()
        # TASK-007 consumes PNG representative crops via BoardSegment.image_path.
        crop = cv2.imread(str(seg.image_path), cv2.IMREAD_COLOR)
        assert crop is not None and crop.ndim == 3


def test_empty_pick_best() -> None:
    idx, score = KeyframeScorer().pick_best([])
    assert idx == -1
    assert score.total == 0.0


def test_phash_ssim_config_exposed() -> None:
    cfg = DedupConfig()
    assert cfg.phash_same_max > 0
    assert 0.0 < cfg.ssim_same_min < 1.0
    assert cfg.phash_ssim_max >= cfg.phash_same_max
