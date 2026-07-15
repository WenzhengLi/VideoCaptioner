"""Unit tests for board tracking, relocate, and lost recovery."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from course_video_analyzer.models import BoardCandidate, BoardRegion
from course_video_analyzer.vision.candidates import region_iou
from course_video_analyzer.vision.tracking import BoardTracker, FrameSample, TrackingConfig

FRAME_W, FRAME_H = 960, 540


def _draw_text_pattern(
    image: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    *,
    seed: int = 0,
    line_gap: int = 18,
    color: tuple[int, int, int] = (30, 30, 30),
) -> None:
    """Stable text-like pattern; ``seed`` changes page identity strongly."""
    rng = np.random.default_rng(seed)
    x2, y2 = x + w, y + h
    family = seed % 4
    if family == 0:
        # Horizontal lecture outline.
        for i, yy in enumerate(range(y + 24, y2 - 16, line_gap)):
            length = int(w * (0.55 + 0.25 * float(rng.random())))
            x0 = x + 16 + int(8 * (i % 3))
            cv2.line(image, (x0, yy), (x0 + length, yy), color, 2)
    elif family == 1:
        # Dense vertical bars + boxed title.
        for i, xx in enumerate(range(x + 24, x2 - 16, line_gap)):
            length = int(h * (0.45 + 0.35 * float(rng.random())))
            y0 = y + 40 + int(6 * (i % 3))
            cv2.line(image, (xx, y0), (xx, y0 + length), color, 2)
        cv2.rectangle(image, (x + 40, y + 60), (x + w // 2, y + h // 2), color, 3)
    elif family == 2:
        # Diagonal chevrons / formula blocks.
        for i in range(8):
            y0 = y + 40 + i * (h // 10)
            cv2.line(image, (x + 30, y0), (x + w - 40, y0 + 30 + (seed % 5)), color, 2)
            cv2.circle(image, (x + 80 + i * 40, y0 + 20), 12 + (seed % 7), color, 2)
    else:
        # Grid of filled tiles (different slide layout).
        cols, rows = 4, 3
        tw, th = w // (cols + 1), h // (rows + 1)
        for r in range(rows):
            for c in range(cols):
                if (r + c + seed) % 3 == 0:
                    continue
                x0 = x + 30 + c * tw
                y0 = y + 40 + r * th
                cv2.rectangle(image, (x0, y0), (x0 + tw - 12, y0 + th - 12), color, -1 if (seed + r) % 2 else 2)

    # Distinct corner glyph per seed for ORB / pHash.
    cv2.putText(
        image,
        f"P{seed}",
        (x + 30, y + 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        color,
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        f"S{seed * 17 % 97}",
        (x + w // 3, y + h // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.6,
        color,
        3,
        cv2.LINE_AA,
    )


def _draw_person(image: np.ndarray, x: int, y: int, w: int, h: int) -> None:
    cv2.rectangle(image, (x, y), (x + w, y + h), (35, 35, 35), thickness=-1)
    cv2.ellipse(
        image,
        (x + w // 2, y + h // 2),
        (w // 3, h // 3),
        0,
        0,
        360,
        (90, 140, 200),
        thickness=-1,
    )


def make_board_frame(
    *,
    side: str,
    page_seed: int = 1,
    person_xy: tuple[int, int] | None = None,
    fullscreen: bool = False,
) -> tuple[np.ndarray, BoardRegion]:
    image = np.full((FRAME_H, FRAME_W, 3), 48, dtype=np.uint8)
    if fullscreen:
        board = BoardRegion(x=10, y=10, width=FRAME_W - 20, height=FRAME_H - 20)
    elif side == "left":
        board = BoardRegion(x=20, y=30, width=560, height=480)
    else:
        board = BoardRegion(x=360, y=30, width=560, height=480)

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
    _draw_text_pattern(
        image,
        board.x,
        board.y,
        board.width,
        board.height,
        seed=page_seed,
        line_gap=16 if fullscreen else 18,
    )

    if person_xy is None:
        if fullscreen:
            person_xy = (FRAME_W - 170, FRAME_H - 130)
        elif side == "left":
            person_xy = (640, 320)
        else:
            person_xy = (40, 320)
    pw, ph = (150, 110) if fullscreen else (280, 180)
    _draw_person(image, person_xy[0], person_xy[1], pw, ph)
    return image, board


def make_empty_frame() -> np.ndarray:
    ys = np.linspace(40, 100, FRAME_H, dtype=np.float32)
    xs = np.linspace(50, 120, FRAME_W, dtype=np.float32)
    base = ys[:, None] + xs[None, :]
    gray = np.clip(base, 0, 255).astype(np.uint8)
    gray = cv2.GaussianBlur(gray, (51, 51), 0)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def _samples_from_images(
    images: list[np.ndarray],
    *,
    interval_ms: int = 1000,
) -> list[FrameSample]:
    return [
        FrameSample(frame_index=i, timestamp_ms=i * interval_ms, image_bgr=img)
        for i, img in enumerate(images)
    ]


def test_left_to_right_relocate_within_window(tmp_path: Path) -> None:
    """Same page jumping left→right must redetect within a few frames."""
    left, left_gt = make_board_frame(side="left", page_seed=7)
    right, right_gt = make_board_frame(side="right", page_seed=7)
    frames = _samples_from_images([left, left, right, right])
    tracker = BoardTracker(TrackingConfig())
    result = tracker.track(frames, output_dir=tmp_path / "out", initial_region=left_gt)

    assert len(result.observations) == len(frames)
    # After the switch, a non-lost observation must overlap the right board.
    post = result.observations[2:]
    recovered = [o for o in post if o.status != "lost" and o.region is not None]
    assert recovered, "expected relocate after left→right switch"
    assert any(region_iou(o.region, right_gt) >= 0.35 for o in recovered if o.region)
    assert any(o.status == "redetected" for o in post)
    assert "lost_frames" in result.diagnostics


def test_fullscreen_layout_switch(tmp_path: Path) -> None:
    left, left_gt = make_board_frame(side="left", page_seed=3)
    full, full_gt = make_board_frame(side="left", page_seed=3, fullscreen=True)
    frames = _samples_from_images([left, left, full, full])
    tracker = BoardTracker()
    result = tracker.track(frames, output_dir=tmp_path / "out", initial_region=left_gt)

    assert len(result.observations) == 4
    post = result.observations[2:]
    recovered = [o for o in post if o.region is not None and o.status != "lost"]
    assert recovered
    assert any(region_iou(o.region, full_gt) >= 0.45 for o in recovered if o.region)
    assert any(o.status == "redetected" for o in result.observations)


def test_relocate_prefers_credible_fullscreen_expansion(monkeypatch) -> None:
    image = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)
    previous = BoardRegion(x=20, y=30, width=560, height=480)
    previous_crop = np.zeros((480, 560, 3), dtype=np.uint8)
    partial = BoardCandidate(
        region=BoardRegion(x=20, y=30, width=560, height=480),
        score=0.80,
        area_ratio=560 * 480 / (FRAME_W * FRAME_H),
    )
    fullscreen = BoardCandidate(
        region=BoardRegion(x=0, y=0, width=FRAME_W, height=FRAME_H),
        score=0.68,
        area_ratio=1.0,
    )
    tracker = BoardTracker()

    def fake_similarity(_previous: np.ndarray, current: np.ndarray) -> float:
        return 0.18 if current.shape[1] == FRAME_W else 0.30

    monkeypatch.setattr(tracker.matcher, "content_similarity", fake_similarity)
    selected = tracker._pick_relocate_candidate(
        image,
        [partial, fullscreen],
        previous_crop,
        previous,
    )

    assert selected is not None
    assert selected[0] == fullscreen


def test_person_motion_keeps_tracking(tmp_path: Path) -> None:
    """Person PIP moving should not mark the board lost."""
    imgs: list[np.ndarray] = []
    gt: BoardRegion | None = None
    for i, person_x in enumerate((640, 700, 620, 680)):
        img, board = make_board_frame(side="left", page_seed=11, person_xy=(person_x, 320))
        imgs.append(img)
        if i == 0:
            gt = board
    assert gt is not None
    result = BoardTracker().track(
        _samples_from_images(imgs),
        output_dir=tmp_path / "out",
        initial_region=gt,
    )
    assert all(o.status != "lost" for o in result.observations)
    assert sum(1 for o in result.observations if o.region is not None) == len(imgs)


def test_lost_and_recovery(tmp_path: Path) -> None:
    left, gt = make_board_frame(side="left", page_seed=5)
    empty = make_empty_frame()
    frames = _samples_from_images([left, left, empty, empty, left, left])
    result = BoardTracker().track(frames, output_dir=tmp_path / "out", initial_region=gt)

    assert len(result.observations) == 6
    lost = [o for o in result.observations if o.status == "lost"]
    assert lost, "empty frames must be marked lost (no silent drop)"
    assert result.diagnostics["status_counts"]["lost"] >= 1

    recovered = result.observations[4:]
    assert any(o.status == "redetected" and o.region is not None for o in recovered)
    assert any(
        o.region is not None and region_iou(o.region, gt) >= 0.35 for o in recovered
    )


def test_every_frame_emits_observation(tmp_path: Path) -> None:
    imgs = [make_board_frame(side="left", page_seed=1)[0] for _ in range(5)]
    frames = _samples_from_images(imgs)
    result = BoardTracker().track(frames, output_dir=tmp_path / "obs")
    assert len(result.observations) == 5
    assert all(o.reason for o in result.observations)
    assert set(result.diagnostics["status_counts"]) >= {"tracked", "redetected", "lost"}


def test_segments_have_time_range_and_representative(tmp_path: Path) -> None:
    page_a = [make_board_frame(side="left", page_seed=21)[0] for _ in range(3)]
    page_b = [make_board_frame(side="left", page_seed=99)[0] for _ in range(2)]
    frames = _samples_from_images(page_a + page_b)
    result = BoardTracker().track(frames, output_dir=tmp_path / "seg")
    assert result.segments, "expected at least one board version"
    for seg in result.segments:
        assert seg.end_ms > seg.start_ms
        assert seg.version_id
        assert seg.image_path.exists()
        assert seg.track_status in {"tracked", "redetected", "lost"}
