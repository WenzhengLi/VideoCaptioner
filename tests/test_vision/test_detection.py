"""Unit tests for board candidate detection on synthetic layouts."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from course_video_analyzer.models import BoardRegion
from course_video_analyzer.vision.candidates import CandidateGenerator, region_iou
from course_video_analyzer.vision.detection import BoardDetectorConfig, OpenCvBoardDetector
from course_video_analyzer.vision.scoring import BoardScorer, ScoringWeights, edge_density

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "images"
FRAME_W, FRAME_H = 960, 540


def _ensure_fixtures_dir() -> Path:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    return FIXTURES


def _draw_text_like_lines(
    image: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    *,
    color: tuple[int, int, int] = (30, 30, 30),
    line_gap: int = 18,
) -> None:
    """Dense horizontal strokes as a stand-in for slide / board text."""
    y2 = y + h
    for yy in range(y + 24, y2 - 16, line_gap):
        length = int(w * 0.72)
        cv2.line(image, (x + 20, yy), (x + 20 + length, yy), color, 2)
        if yy % (line_gap * 2) == 0:
            cv2.line(image, (x + 40, yy + 8), (x + 40 + length // 2, yy + 8), color, 1)


def _draw_person_pip(image: np.ndarray, x: int, y: int, w: int, h: int) -> BoardRegion:
    """Small skin-toned window that must not outrank a real board."""
    cv2.rectangle(image, (x, y), (x + w, y + h), (40, 40, 40), thickness=-1)
    # YCrCb skin-ish BGR tones.
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
    return BoardRegion(x=x, y=y, width=w, height=h)


def make_left_board_frame() -> tuple[np.ndarray, BoardRegion]:
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
        (160, 160, 160),
        thickness=3,
    )
    _draw_text_like_lines(image, board.x, board.y, board.width, board.height)
    _draw_person_pip(image, 640, 320, 280, 180)
    return image, board


def make_right_board_frame() -> tuple[np.ndarray, BoardRegion]:
    image = np.full((FRAME_H, FRAME_W, 3), 48, dtype=np.uint8)
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
        (160, 160, 160),
        thickness=3,
    )
    _draw_text_like_lines(image, board.x, board.y, board.width, board.height)
    _draw_person_pip(image, 40, 320, 280, 180)
    return image, board


def make_fullscreen_board_frame() -> tuple[np.ndarray, BoardRegion]:
    image = np.full((FRAME_H, FRAME_W, 3), 32, dtype=np.uint8)
    board = BoardRegion(x=10, y=10, width=FRAME_W - 20, height=FRAME_H - 20)
    cv2.rectangle(
        image,
        (board.x, board.y),
        (board.x + board.width, board.y + board.height),
        (250, 250, 250),
        thickness=-1,
    )
    _draw_text_like_lines(
        image,
        board.x,
        board.y,
        board.width,
        board.height,
        line_gap=16,
    )
    # Tiny corner PIP — must stay out of Top-1.
    _draw_person_pip(image, FRAME_W - 170, FRAME_H - 130, 150, 110)
    return image, board


def make_no_board_frame() -> np.ndarray:
    """Soft gradients without large sharp rectangles or text-like edges."""
    ys = np.linspace(40, 100, FRAME_H, dtype=np.float32)
    xs = np.linspace(50, 120, FRAME_W, dtype=np.float32)
    base = ys[:, None] + xs[None, :]
    gray = np.clip(base, 0, 255).astype(np.uint8)
    gray = cv2.GaussianBlur(gray, (51, 51), 0)
    image = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    # Soft blob, not a sharp board edge.
    overlay = image.copy()
    cv2.circle(overlay, (FRAME_W // 2, FRAME_H // 2), 90, (70, 90, 110), thickness=-1)
    image = cv2.addWeighted(overlay, 0.35, image, 0.65, 0)
    return image


def _save_fixture(name: str, image: np.ndarray) -> Path:
    path = _ensure_fixtures_dir() / name
    assert cv2.imwrite(str(path), image)
    return path


def _top3_hits(candidates: list, gt: BoardRegion, *, min_iou: float = 0.45) -> bool:
    return any(region_iou(c.region, gt) >= min_iou for c in candidates[:3])


@pytest.fixture(scope="module")
def fixture_paths() -> dict[str, Path]:
    left_img, _ = make_left_board_frame()
    right_img, _ = make_right_board_frame()
    full_img, _ = make_fullscreen_board_frame()
    none_img = make_no_board_frame()
    return {
        "left": _save_fixture("board_left.png", left_img),
        "right": _save_fixture("board_right.png", right_img),
        "fullscreen": _save_fixture("board_fullscreen.png", full_img),
        "none": _save_fixture("board_none.png", none_img),
    }


def test_left_board_in_top3(fixture_paths: dict[str, Path]) -> None:
    _, gt = make_left_board_frame()
    detector = OpenCvBoardDetector(BoardDetectorConfig(mode="auto", top_k=3))
    candidates = detector.detect(fixture_paths["left"])
    assert candidates, "expected at least one board candidate"
    assert _top3_hits(candidates, gt)
    assert candidates[0].score >= 0.35


def test_right_board_in_top3(fixture_paths: dict[str, Path]) -> None:
    _, gt = make_right_board_frame()
    detector = OpenCvBoardDetector(BoardDetectorConfig(mode="auto", top_k=3))
    candidates = detector.detect(fixture_paths["right"])
    assert candidates
    assert _top3_hits(candidates, gt)


def test_fullscreen_board_in_top3(fixture_paths: dict[str, Path]) -> None:
    _, gt = make_fullscreen_board_frame()
    detector = OpenCvBoardDetector(BoardDetectorConfig(mode="auto", top_k=3))
    candidates = detector.detect(fixture_paths["fullscreen"])
    assert candidates
    assert _top3_hits(candidates, gt, min_iou=0.5)


def test_no_board_returns_empty_or_low_confidence(fixture_paths: dict[str, Path]) -> None:
    detector = OpenCvBoardDetector(
        BoardDetectorConfig(mode="auto", top_k=3, min_score=0.35, keep_low_confidence=False)
    )
    candidates = detector.detect(fixture_paths["none"])
    assert candidates == []


def test_person_pip_does_not_win_by_default(fixture_paths: dict[str, Path]) -> None:
    image, board_gt = make_left_board_frame()
    pip = BoardRegion(x=640, y=320, width=280, height=180)
    path = _save_fixture("board_left_pip_check.png", image)
    detector = OpenCvBoardDetector(BoardDetectorConfig(mode="auto", top_k=3))
    candidates = detector.detect(path)
    assert candidates
    top = candidates[0]
    assert region_iou(top.region, board_gt) > region_iou(top.region, pip)
    assert top.area_ratio >= 0.18


def test_previous_region_boosts_stability(fixture_paths: dict[str, Path]) -> None:
    _, gt = make_left_board_frame()
    detector = OpenCvBoardDetector(BoardDetectorConfig(mode="auto", top_k=3))
    without = detector.detect(fixture_paths["left"])
    with_prev = detector.detect(fixture_paths["left"], previous_region=gt)
    assert without and with_prev
    matched_without = max(without, key=lambda c: region_iou(c.region, gt))
    matched_with = max(with_prev, key=lambda c: region_iou(c.region, gt))
    assert matched_with.stability >= matched_without.stability


def test_debug_overlay_written(tmp_path: Path, fixture_paths: dict[str, Path]) -> None:
    detector = OpenCvBoardDetector(
        BoardDetectorConfig(mode="auto", top_k=3, debug_dir=tmp_path / "debug")
    )
    candidates = detector.detect(fixture_paths["left"])
    assert candidates
    overlays = list((tmp_path / "debug").glob("*_board_debug.png"))
    assert len(overlays) == 1
    loaded = cv2.imread(str(overlays[0]))
    assert loaded is not None


def test_edge_density_proxy_higher_on_board_than_blank() -> None:
    image, board = make_left_board_frame()
    blank = BoardRegion(x=700, y=40, width=200, height=200)
    # Ensure blank ROI is dark empty background.
    image[blank.y : blank.y + blank.height, blank.x : blank.x + blank.width] = 48
    board_d = edge_density(image, board)
    blank_d = edge_density(image, blank)
    assert board_d > blank_d


def test_scorer_weights_are_configurable() -> None:
    image, board = make_left_board_frame()
    gen = CandidateGenerator()
    proposals = gen.generate(image, mode="auto")
    assert proposals
    scorer_area = BoardScorer(weights=ScoringWeights(area=0.7, rectangularity=0.1, text_density=0.1, stability=0.05, occlusion=0.05))
    scorer_text = BoardScorer(weights=ScoringWeights(area=0.05, rectangularity=0.05, text_density=0.7, stability=0.1, occlusion=0.1))
    a = scorer_area.score_all(image, proposals, top_k=3)
    b = scorer_text.score_all(image, proposals, top_k=3)
    assert a and b
    # Both should still retrieve a large board-like region under either emphasis.
    assert any(c.area_ratio >= 0.2 for c in a)
    assert any(c.area_ratio >= 0.2 for c in b)
    assert board.area > 0


def test_optional_text_density_injection(fixture_paths: dict[str, Path]) -> None:
    class FixedDensity:
        def estimate(self, image_bgr: np.ndarray, region: BoardRegion) -> float:
            _ = image_bgr
            return 0.91 if region.width > 400 else 0.05

    detector = OpenCvBoardDetector(
        BoardDetectorConfig(mode="auto", top_k=3, text_density_estimator=FixedDensity())
    )
    candidates = detector.detect(fixture_paths["left"])
    assert candidates
    assert candidates[0].text_density in {0.91, 0.05}
    assert max(c.text_density for c in candidates) == 0.91
