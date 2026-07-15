"""Evaluate predictions against manifest annotations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from benchmarks.compare import compare_diarizers
from benchmarks.metrics import (
    Interval,
    board_detection_scores,
    board_page_rates,
    character_error_rate,
    diarization_error_rate,
    ocr_character_accuracy,
    word_error_rate,
)
from benchmarks.schema import BenchmarkManifest, BenchmarkSample, load_manifest


def evaluate_manifest(
    manifest: BenchmarkManifest,
    *,
    predictions: dict[str, dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Evaluate samples.

    ``predictions[sample_id]`` may contain:
      transcript_text, speaker_turns, board_boxes, board_page_ids, ocr_text,
      diarizer_predictions: {wespeaker: [...], campplus: [...]}

    Missing media when required for a non-dry live path is recorded under ``skipped``.
    """
    predictions = predictions or {}
    missing_media: list[str] = []
    skipped: list[dict[str, str]] = []
    components: dict[str, Any] = {
        "asr": [],
        "diarization": [],
        "board_detection": [],
        "board_pages": [],
        "ocr": [],
        "diarizer_compare": [],
        "e2e": [],
    }

    for sample in manifest.samples:
        media = manifest.resolve_media_path(sample)
        media_exists = media.exists()
        if not media_exists:
            missing_media.append(str(media))
            if dry_run:
                skipped.append(
                    {
                        "sample_id": sample.sample_id,
                        "reason": f"media missing: {media}",
                    }
                )
                continue
            # Soft skip: still allow annotation-only synthetic evaluation when
            # predictions are provided without local media.
            if sample.sample_id not in predictions:
                skipped.append(
                    {
                        "sample_id": sample.sample_id,
                        "reason": f"media missing and no predictions: {media}",
                    }
                )
                continue

        pred = predictions.get(sample.sample_id, {})
        sample_report = _evaluate_sample(sample, pred)
        for key, value in sample_report.items():
            if value is not None:
                components[key].append({"sample_id": sample.sample_id, **value})

    summary = _summarize(components)
    return {
        "manifest": manifest.name,
        "dry_run": dry_run,
        "missing_media": missing_media,
        "skipped": skipped,
        "components": components,
        "summary": summary,
    }


def evaluate_file(
    manifest_path: Path,
    *,
    predictions_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    predictions: dict[str, dict[str, Any]] = {}
    if predictions_path and Path(predictions_path).exists():
        import json

        predictions = json.loads(Path(predictions_path).read_text(encoding="utf-8"))
    return evaluate_manifest(manifest, predictions=predictions, dry_run=dry_run)


def _evaluate_sample(sample: BenchmarkSample, pred: dict[str, Any]) -> dict[str, Any | None]:
    ann = sample.annotations
    out: dict[str, Any | None] = {
        "asr": None,
        "diarization": None,
        "board_detection": None,
        "board_pages": None,
        "ocr": None,
        "diarizer_compare": None,
        "e2e": None,
    }

    if ann.transcript:
        ref_text = "".join(t.text for t in ann.transcript)
        hyp_text = str(pred.get("transcript_text") or "")
        if hyp_text or pred.get("transcript_text") == "":
            out["asr"] = {
                "cer": character_error_rate(ref_text, hyp_text),
                "wer": word_error_rate(ref_text, hyp_text),
            }

    if ann.speaker_turns:
        ref = [
            Interval(t.start_ms, t.end_ms, t.speaker_id) for t in ann.speaker_turns
        ]
        hyp_rows = pred.get("speaker_turns") or []
        if hyp_rows is not None and "speaker_turns" in pred:
            hyp = [
                Interval(int(t["start_ms"]), int(t["end_ms"]), str(t["speaker_id"]))
                for t in hyp_rows
            ]
            out["diarization"] = diarization_error_rate(ref, hyp)

        diar_preds = pred.get("diarizer_predictions")
        if isinstance(diar_preds, dict) and diar_preds:
            out["diarizer_compare"] = compare_diarizers(
                [t.model_dump() for t in ann.speaker_turns],
                diar_preds,
            )

    if ann.board_regions:
        refs = [(r.x, r.y, r.width, r.height) for r in ann.board_regions]
        hyps = [
            (int(b["x"]), int(b["y"]), int(b["width"]), int(b["height"]))
            for b in (pred.get("board_boxes") or [])
        ]
        if "board_boxes" in pred:
            out["board_detection"] = board_detection_scores(refs, hyps)

    if ann.board_pages:
        ref_ids = [p.version_id for p in ann.board_pages]
        hyp_ids = list(pred.get("board_page_ids") or [])
        if "board_page_ids" in pred:
            out["board_pages"] = board_page_rates(ref_ids, hyp_ids)
        # OCR from concatenated page texts when provided
        ref_ocr = "".join(p.text for p in ann.board_pages) or (ann.ocr_text or "")
        if ref_ocr and "ocr_text" in pred:
            hyp_ocr = str(pred.get("ocr_text") or "")
            out["ocr"] = {
                "char_accuracy": ocr_character_accuracy(ref_ocr, hyp_ocr),
                "cer": character_error_rate(ref_ocr, hyp_ocr),
            }
    elif ann.ocr_text is not None and "ocr_text" in pred:
        hyp_ocr = str(pred.get("ocr_text") or "")
        out["ocr"] = {
            "char_accuracy": ocr_character_accuracy(ann.ocr_text, hyp_ocr),
            "cer": character_error_rate(ann.ocr_text, hyp_ocr),
        }

    if sample.scenario.value == "end_to_end" or pred.get("e2e"):
        # Aggregate available component scores into a simple e2e dict.
        e2e: dict[str, Any] = {"scenario": sample.scenario.value}
        for key in ("asr", "diarization", "board_detection", "board_pages", "ocr"):
            if out[key] is not None:
                e2e[key] = out[key]
        if len(e2e) > 1:
            out["e2e"] = e2e

    return out


def _summarize(components: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    asr = components["asr"]
    if asr:
        summary["asr"] = {
            "mean_cer": sum(x["cer"] for x in asr) / len(asr),
            "mean_wer": sum(x["wer"] for x in asr) / len(asr),
            "n": len(asr),
        }
    diar = components["diarization"]
    if diar:
        summary["diarization"] = {
            "mean_der": sum(x["der"] for x in diar) / len(diar),
            "n": len(diar),
        }
    boards = components["board_detection"]
    if boards:
        summary["board_detection"] = {
            "mean_iou": sum(x["mean_iou"] for x in boards) / len(boards),
            "mean_top_k_hit_rate": sum(x["top_k_hit_rate"] for x in boards) / len(boards),
            "n": len(boards),
        }
    pages = components["board_pages"]
    if pages:
        summary["board_pages"] = {
            "mean_duplicate_rate": sum(x["duplicate_rate"] for x in pages) / len(pages),
            "mean_miss_rate": sum(x["miss_rate"] for x in pages) / len(pages),
            "n": len(pages),
        }
    ocr = components["ocr"]
    if ocr:
        summary["ocr"] = {
            "mean_char_accuracy": sum(x["char_accuracy"] for x in ocr) / len(ocr),
            "n": len(ocr),
        }
    compares = components["diarizer_compare"]
    if compares:
        summary["diarizer_compare"] = compares
    return summary
