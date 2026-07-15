"""Compare WeSpeaker vs CAM++ diarization quality and speed on labeled turns."""

from __future__ import annotations

from typing import Any

from benchmarks.metrics import Interval, diarization_error_rate


def compare_diarizers(
    reference_turns: list[dict[str, Any]],
    predictions: dict[str, list[dict[str, Any]]],
    *,
    timings_s: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    ``predictions`` maps engine name → list of {start_ms,end_ms,speaker_id}.

    Optional ``timings_s`` supplies externally measured runtimes so repeated
    offline scoring of the same predictions stays deterministic.
    """
    ref = [
        Interval(int(t["start_ms"]), int(t["end_ms"]), str(t["speaker_id"]))
        for t in reference_turns
    ]
    report: dict[str, Any] = {"engines": {}}
    for name, turns in predictions.items():
        hyp = [
            Interval(int(t["start_ms"]), int(t["end_ms"]), str(t["speaker_id"])) for t in turns
        ]
        der = diarization_error_rate(ref, hyp)
        report["engines"][name] = {
            **der,
            "elapsed_s": float((timings_s or {}).get(name, 0.0)),
            "turn_count": len(hyp),
        }
    # Rank by DER then elapsed.
    ranked = sorted(
        report["engines"].items(),
        key=lambda kv: (kv[1]["der"], kv[1]["elapsed_s"]),
    )
    report["ranking"] = [name for name, _ in ranked]
    if ranked:
        report["winner"] = ranked[0][0]
    return report
