"""Unit tests for offline benchmark metrics and CLI dry-run."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.evaluate import evaluate_file, evaluate_manifest
from benchmarks.metrics import (
    Interval,
    board_detection_scores,
    board_page_rates,
    character_error_rate,
    diarization_error_rate,
    ocr_character_accuracy,
    word_error_rate,
)
from benchmarks.report import write_reports
from benchmarks.schema import load_manifest


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "manifests"


def test_cer_wer_known_values() -> None:
    assert character_error_rate("abcd", "abcd") == 0.0
    assert character_error_rate("abcd", "abxd") == 0.25
    assert word_error_rate("hello world", "hello world") == 0.0
    assert word_error_rate("hello world", "hello there") == 0.5


def test_der_perfect_and_mismatch() -> None:
    ref = [
        Interval(0, 1000, "A"),
        Interval(1000, 2000, "B"),
    ]
    perfect = [
        Interval(0, 1000, "spk0"),
        Interval(1000, 2000, "spk1"),
    ]
    assert diarization_error_rate(ref, perfect)["der"] == 0.0

    bad = [Interval(0, 2000, "spk0")]
    der = diarization_error_rate(ref, bad)["der"]
    assert der > 0.0


def test_board_iou_and_pages() -> None:
    scores = board_detection_scores(
        [(10, 20, 100, 80)],
        [(10, 20, 100, 80)],
    )
    assert scores["mean_iou"] == 1.0
    assert scores["top_k_hit_rate"] == 1.0
    pages = board_page_rates(["p1", "p2"], ["p1", "p2", "p2"])
    assert pages["duplicate_rate"] == 1 / 3
    assert pages["miss_rate"] == 0.0


def test_ocr_accuracy() -> None:
    assert ocr_character_accuracy("公式一", "公式一") == 1.0
    assert ocr_character_accuracy("公式一", "公式二") < 1.0


def test_metrics_deterministic() -> None:
    a = character_error_rate("课程视频", "课程视屏")
    b = character_error_rate("课程视频", "课程视屏")
    assert a == b


def test_example_manifest_with_predictions(tmp_path: Path) -> None:
    manifest = load_manifest(FIXTURES / "example.json")
    predictions = json.loads((FIXTURES / "example_predictions.json").read_text(encoding="utf-8"))
    result = evaluate_manifest(manifest, predictions=predictions, dry_run=False)
    assert "synth_asr_01" not in [s["sample_id"] for s in result["skipped"] if "no predictions" in s.get("reason", "")]
    assert result["summary"]["asr"]["mean_cer"] == 0.0
    assert result["summary"]["diarization"]["mean_der"] == 0.0
    assert result["summary"]["board_detection"]["mean_iou"] > 0.9
    assert result["summary"]["ocr"]["mean_char_accuracy"] == 1.0
    assert result["summary"]["diarizer_compare"]

    paths = write_reports(result, tmp_path / "out")
    assert paths["json"].exists()
    assert paths["markdown"].exists()
    md = paths["markdown"].read_text(encoding="utf-8")
    assert "Summary" in md

    # Repeatability
    again = evaluate_manifest(manifest, predictions=predictions, dry_run=False)
    assert again["summary"] == result["summary"]


def test_dry_run_lists_missing_without_failing() -> None:
    result = evaluate_file(FIXTURES / "example.json", dry_run=True)
    assert result["dry_run"] is True
    assert result["missing_media"]
    assert result["skipped"]
