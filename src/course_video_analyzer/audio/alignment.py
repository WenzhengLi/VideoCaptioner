"""Align FunASR transcripts with speaker turns into ``SpeechSegment`` intervals.

Pure functions: no model I/O. Optional ``alignment.json`` diagnostics for recovery.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from course_video_analyzer.audio.speaker_mapping import apply_speaker_names
from course_video_analyzer.models import SpeakerTurn, SpeechSegment, TranscriptSegment

ALIGNMENT_ARTIFACT_NAME = "alignment.json"
UNKNOWN_SPEAKER = "unknown"

MatchMethod = Literal[
    "max_overlap",
    "word_split",
    "particle_inherit",
    "context_inherit",
    "unknown",
]

# Strip punctuation / whitespace when measuring short-particle text length.
_NON_CONTENT_RE = re.compile(r"[\s\W_]+", re.UNICODE)


@dataclass(frozen=True)
class AlignmentConfig:
    """Thresholds controlling overlap matching, word splits, and particle inherit."""

    #: Overlap duration / transcript duration; below → ``unknown`` (unless inherit).
    min_match_ratio: float = 0.5
    #: Split a transcript at speaker switches when word-level timestamps exist.
    enable_word_split: bool = True
    #: Secondary speaker must cover at least this fraction of the transcript to count
    #: as a clear switch (avoids splitting on tiny overlaps / VAD jitter).
    split_min_secondary_ratio: float = 0.15
    #: Allow short affirmatives ("嗯", "好的") to inherit the nearest speaker.
    enable_particle_inherit: bool = True
    particle_max_duration_ms: int = 800
    particle_max_chars: int = 4
    #: Fill a no-overlap run when the same known speaker appears immediately
    #: before and after it. This repairs short VAD holes without guessing across
    #: an actual speaker switch.
    enable_context_inherit: bool = True
    context_inherit_max_gap_ms: int = 1000
    context_inherit_max_run_ms: int = 8000
    #: When text spans multiple speakers but has no word timestamps, keep the best
    #: speaker if above threshold and scale confidence by this factor.
    multi_speaker_confidence_scale: float = 0.5


@dataclass(frozen=True)
class AlignmentResult:
    """Aligned segments plus parallel diagnostics for ``alignment.json``."""

    segments: list[SpeechSegment]
    diagnostics: list[dict[str, Any]]


def overlap_ms(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    """Half-open interval overlap length in milliseconds."""
    return max(0, min(end_a, end_b) - max(start_a, start_b))


def align_speech(
    transcripts: list[TranscriptSegment],
    turns: list[SpeakerTurn],
    *,
    config: AlignmentConfig | None = None,
    speaker_names: dict[str, str] | None = None,
    artifact_dir: Path | None = None,
) -> list[SpeechSegment]:
    """Assign speakers to transcript intervals; optionally write diagnostics JSON.

    Returns segments sorted by ``(start_ms, end_ms)``. Empty transcripts → ``[]``.
    """
    result = align_speech_with_diagnostics(
        transcripts,
        turns,
        config=config,
        speaker_names=speaker_names,
    )
    if artifact_dir is not None:
        write_alignment_artifact(
            artifact_dir,
            result,
            config=config or AlignmentConfig(),
        )
    return result.segments


def align_speech_with_diagnostics(
    transcripts: list[TranscriptSegment],
    turns: list[SpeakerTurn],
    *,
    config: AlignmentConfig | None = None,
    speaker_names: dict[str, str] | None = None,
) -> AlignmentResult:
    """Pure alignment returning both ``SpeechSegment`` list and diagnostic rows."""
    cfg = config or AlignmentConfig()
    if not transcripts:
        return AlignmentResult(segments=[], diagnostics=[])

    sorted_turns = sorted(turns, key=lambda t: (t.start_ms, t.end_ms, t.speaker_id))
    segments: list[SpeechSegment] = []
    diagnostics: list[dict[str, Any]] = []

    for transcript in transcripts:
        pieces = _align_one_transcript(transcript, sorted_turns, cfg)
        for speech, diag in pieces:
            segments.append(speech)
            diagnostics.append(diag)

    segments.sort(key=lambda s: (s.start_ms, s.end_ms, s.speaker_id, s.text))
    diagnostics.sort(key=lambda d: (d["start_ms"], d["end_ms"], d["speaker_id"], d["text"]))

    if cfg.enable_context_inherit:
        segments, diagnostics = _inherit_unknown_segment_runs(segments, diagnostics, cfg)

    if speaker_names:
        segments = apply_speaker_names(segments, speaker_names)

    return AlignmentResult(segments=segments, diagnostics=diagnostics)


def _inherit_unknown_segment_runs(
    segments: list[SpeechSegment],
    diagnostics: list[dict[str, Any]],
    config: AlignmentConfig,
) -> tuple[list[SpeechSegment], list[dict[str, Any]]]:
    """Fill unknown runs only when surrounding context is unambiguous."""
    updated = list(segments)
    updated_diags = [dict(row) for row in diagnostics]
    i = 0
    while i < len(updated):
        if updated[i].speaker_id != UNKNOWN_SPEAKER:
            i += 1
            continue
        j = i
        while j < len(updated) and updated[j].speaker_id == UNKNOWN_SPEAKER:
            j += 1
        run_start = updated[i].start_ms
        run_end = updated[j - 1].end_ms
        if run_end - run_start > config.context_inherit_max_run_ms:
            i = j
            continue

        left = updated[i - 1] if i > 0 else None
        right = updated[j] if j < len(updated) else None
        chosen: str | None = None
        if (
            left is not None
            and right is not None
            and left.speaker_id == right.speaker_id
            and left.speaker_id != UNKNOWN_SPEAKER
            and run_start - left.end_ms <= config.context_inherit_max_gap_ms
            and right.start_ms - run_end <= config.context_inherit_max_gap_ms
        ):
            chosen = left.speaker_id
        elif (
            right is None
            and left is not None
            and left.speaker_id != UNKNOWN_SPEAKER
            and run_start - left.end_ms <= min(250, config.context_inherit_max_gap_ms)
        ):
            chosen = left.speaker_id
        elif (
            left is None
            and right is not None
            and right.speaker_id != UNKNOWN_SPEAKER
            and right.start_ms - run_end <= min(250, config.context_inherit_max_gap_ms)
        ):
            chosen = right.speaker_id

        if chosen is not None:
            for k in range(i, j):
                updated[k] = updated[k].model_copy(
                    update={"speaker_id": chosen, "inferred": True}
                )
                updated_diags[k]["speaker_id"] = chosen
                updated_diags[k]["inferred"] = True
                updated_diags[k]["match_method"] = "context_inherit"
                updated_diags[k]["unmatched_reason"] = None
        i = j
    return updated, updated_diags


def write_alignment_artifact(
    artifact_dir: Path,
    result: AlignmentResult,
    *,
    config: AlignmentConfig,
) -> Path:
    """Write ``alignment.json`` under ``artifact_dir`` (usually ``artifacts/audio``)."""
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / ALIGNMENT_ARTIFACT_NAME
    payload = {
        "config": asdict(config),
        "speech_segments": [seg.model_dump(mode="json") for seg in result.segments],
        "diagnostics": result.diagnostics,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _align_one_transcript(
    transcript: TranscriptSegment,
    turns: list[SpeakerTurn],
    config: AlignmentConfig,
) -> list[tuple[SpeechSegment, dict[str, Any]]]:
    overlaps = _overlap_summary(transcript.start_ms, transcript.end_ms, turns)
    clear_switch = _has_clear_speaker_switch(overlaps, config.split_min_secondary_ratio)
    words = _usable_words(transcript)

    if config.enable_word_split and clear_switch and words:
        return _align_by_words(transcript, turns, words, config)

    speech, diag = _assign_whole_segment(
        transcript,
        turns,
        overlaps,
        config,
        multi_speaker=clear_switch,
    )
    return [(speech, diag)]


def _assign_whole_segment(
    transcript: TranscriptSegment,
    turns: list[SpeakerTurn],
    overlaps: list[dict[str, Any]],
    config: AlignmentConfig,
    *,
    multi_speaker: bool,
) -> tuple[SpeechSegment, dict[str, Any]]:
    duration = transcript.duration_ms
    best_id, best_ratio, reason = _pick_best_speaker(overlaps, config.min_match_ratio)

    inferred = False
    method: MatchMethod = "max_overlap"
    speaker_id = best_id
    match_ratio = best_ratio
    unmatched_reason = reason

    if speaker_id == UNKNOWN_SPEAKER and _try_particle_inherit(transcript, config):
        nearest = _nearest_speaker(transcript.start_ms, transcript.end_ms, turns)
        if nearest is not None:
            speaker_id = nearest
            inferred = True
            method = "particle_inherit"
            unmatched_reason = None
            # Keep observed overlap ratio (may be 0) for diagnostics transparency.
            if match_ratio is None:
                match_ratio = 0.0

    if speaker_id == UNKNOWN_SPEAKER:
        method = "unknown"
        if unmatched_reason is None:
            unmatched_reason = "no_overlap" if not overlaps else "below_threshold"

    confidence = _resolve_confidence(
        transcript.confidence,
        match_ratio=match_ratio,
        multi_speaker=multi_speaker and method == "max_overlap",
        scale=config.multi_speaker_confidence_scale,
        inferred=inferred,
        unknown=speaker_id == UNKNOWN_SPEAKER,
    )

    speech = SpeechSegment(
        start_ms=transcript.start_ms,
        end_ms=transcript.end_ms,
        text=transcript.text,
        speaker_id=speaker_id,
        speaker_name=None,
        confidence=confidence,
        match_ratio=match_ratio,
        inferred=inferred,
        source="aligned",
    )
    diag = _diagnostic_row(
        start_ms=speech.start_ms,
        end_ms=speech.end_ms,
        text=speech.text,
        speaker_id=speaker_id,
        match_ratio=match_ratio,
        inferred=inferred,
        match_method=method,
        unmatched_reason=unmatched_reason,
        overlaps=overlaps,
        transcript_duration_ms=duration,
    )
    return speech, diag


def _align_by_words(
    transcript: TranscriptSegment,
    turns: list[SpeakerTurn],
    words: list[dict[str, Any]],
    config: AlignmentConfig,
) -> list[tuple[SpeechSegment, dict[str, Any]]]:
    labeled: list[tuple[dict[str, Any], str, float, list[dict[str, Any]]]] = []
    for word in words:
        w_start = int(word["start_ms"])
        w_end = int(word["end_ms"])
        overlaps = _overlap_summary(w_start, w_end, turns)
        speaker_id, ratio, _reason = _pick_best_speaker(overlaps, config.min_match_ratio)
        labeled.append((word, speaker_id, ratio if ratio is not None else 0.0, overlaps))

    # Inherit nearest speaker for short unknown word groups when enabled.
    if config.enable_particle_inherit:
        labeled = _inherit_unknown_word_runs(labeled, turns, config)

    groups = _group_consecutive(labeled)
    pieces: list[tuple[SpeechSegment, dict[str, Any]]] = []
    for group in groups:
        start_ms = int(group[0][0]["start_ms"])
        end_ms = int(group[-1][0]["end_ms"])
        if end_ms <= start_ms:
            continue
        text = _join_word_texts([g[0] for g in group])
        if not text:
            continue
        speaker_id = group[0][1]
        group_overlaps = _overlap_summary(start_ms, end_ms, turns)
        duration = end_ms - start_ms
        overlap_for_speaker = next(
            (o["overlap_ms"] for o in group_overlaps if o["speaker_id"] == speaker_id),
            0,
        )
        match_ratio = overlap_for_speaker / duration if duration > 0 else 0.0
        # Mark inferred if any word in the group was inherited from neighbors.
        inferred = any(bool(g[0].get("_inferred")) for g in group)
        if speaker_id == UNKNOWN_SPEAKER:
            method: MatchMethod = "unknown"
            unmatched_reason: str | None = "below_threshold"
            if not group_overlaps:
                unmatched_reason = "no_overlap"
        elif inferred:
            method = "particle_inherit"
            unmatched_reason = None
        else:
            method = "word_split"
            unmatched_reason = None

        confidence = _resolve_confidence(
            transcript.confidence,
            match_ratio=match_ratio,
            multi_speaker=False,
            scale=config.multi_speaker_confidence_scale,
            inferred=inferred,
            unknown=speaker_id == UNKNOWN_SPEAKER,
        )
        speech = SpeechSegment(
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
            speaker_id=speaker_id,
            speaker_name=None,
            confidence=confidence,
            match_ratio=match_ratio,
            inferred=inferred,
            source="aligned",
        )
        diag = _diagnostic_row(
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
            speaker_id=speaker_id,
            match_ratio=match_ratio,
            inferred=inferred,
            match_method=method,
            unmatched_reason=unmatched_reason,
            overlaps=group_overlaps,
            transcript_duration_ms=duration,
            parent_text=transcript.text,
        )
        pieces.append((speech, diag))

    # Safety: word split produced nothing → fall back to whole-segment assignment.
    if not pieces:
        overlaps = _overlap_summary(transcript.start_ms, transcript.end_ms, turns)
        return [
            _assign_whole_segment(
                transcript,
                turns,
                overlaps,
                config,
                multi_speaker=_has_clear_speaker_switch(
                    overlaps, config.split_min_secondary_ratio
                ),
            )
        ]
    return pieces


def _inherit_unknown_word_runs(
    labeled: list[tuple[dict[str, Any], str, float, list[dict[str, Any]]]],
    turns: list[SpeakerTurn],
    config: AlignmentConfig,
) -> list[tuple[dict[str, Any], str, float, list[dict[str, Any]]]]:
    """Fill short unknown runs from neighboring assigned speakers."""
    if not labeled:
        return labeled

    result = list(labeled)
    n = len(result)
    i = 0
    while i < n:
        if result[i][1] != UNKNOWN_SPEAKER:
            i += 1
            continue
        j = i
        while j < n and result[j][1] == UNKNOWN_SPEAKER:
            j += 1
        run = result[i:j]
        run_start = int(run[0][0]["start_ms"])
        run_end = int(run[-1][0]["end_ms"])
        run_text = _join_word_texts([w[0] for w in run])
        duration = run_end - run_start
        if (
            duration <= config.particle_max_duration_ms
            and _content_char_count(run_text) <= config.particle_max_chars
        ):
            left = result[i - 1][1] if i > 0 else None
            right = result[j][1] if j < n else None
            chosen = None
            if left and left != UNKNOWN_SPEAKER:
                chosen = left
            elif right and right != UNKNOWN_SPEAKER:
                chosen = right
            else:
                chosen = _nearest_speaker(run_start, run_end, turns)
            if chosen is not None:
                for k in range(i, j):
                    word = dict(result[k][0])
                    word["_inferred"] = True
                    result[k] = (word, chosen, result[k][2], result[k][3])
        i = j
    return result


def _group_consecutive(
    labeled: list[tuple[dict[str, Any], str, float, list[dict[str, Any]]]],
) -> list[list[tuple[dict[str, Any], str, float, list[dict[str, Any]]]]]:
    if not labeled:
        return []
    groups: list[list[tuple[dict[str, Any], str, float, list[dict[str, Any]]]]] = []
    current = [labeled[0]]
    for item in labeled[1:]:
        if item[1] == current[-1][1]:
            current.append(item)
        else:
            groups.append(current)
            current = [item]
    groups.append(current)
    return groups


def _overlap_summary(
    start_ms: int,
    end_ms: int,
    turns: list[SpeakerTurn],
) -> list[dict[str, Any]]:
    duration = max(1, end_ms - start_ms)
    by_speaker: dict[str, int] = {}
    for turn in turns:
        ov = overlap_ms(start_ms, end_ms, turn.start_ms, turn.end_ms)
        if ov <= 0:
            continue
        by_speaker[turn.speaker_id] = by_speaker.get(turn.speaker_id, 0) + ov
    rows = [
        {
            "speaker_id": speaker_id,
            "overlap_ms": ov,
            "ratio": ov / duration,
        }
        for speaker_id, ov in by_speaker.items()
    ]
    rows.sort(key=lambda r: (-r["overlap_ms"], r["speaker_id"]))
    return rows


def _pick_best_speaker(
    overlaps: list[dict[str, Any]],
    min_match_ratio: float,
) -> tuple[str, float | None, str | None]:
    """Return ``(speaker_id, match_ratio, unmatched_reason)``."""
    if not overlaps:
        return UNKNOWN_SPEAKER, 0.0, "no_overlap"

    best = overlaps[0]
    best_ov = int(best["overlap_ms"])
    tied = [o for o in overlaps if int(o["overlap_ms"]) == best_ov]
    if len(tied) > 1:
        return UNKNOWN_SPEAKER, float(best["ratio"]), "equal_overlap"

    ratio = float(best["ratio"])
    if ratio < min_match_ratio:
        return UNKNOWN_SPEAKER, ratio, "below_threshold"
    return str(best["speaker_id"]), ratio, None


def _has_clear_speaker_switch(
    overlaps: list[dict[str, Any]],
    min_secondary_ratio: float,
) -> bool:
    significant = [o for o in overlaps if float(o["ratio"]) >= min_secondary_ratio]
    return len(significant) >= 2


def _usable_words(transcript: TranscriptSegment) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for raw in transcript.words:
        if not isinstance(raw, dict):
            continue
        try:
            start_ms = int(raw["start_ms"])
            end_ms = int(raw["end_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        text = raw.get("text")
        if not isinstance(text, str) or not text:
            continue
        if end_ms <= start_ms or start_ms < 0:
            continue
        # Clamp word to parent interval when slightly outside.
        start_ms = max(start_ms, transcript.start_ms)
        end_ms = min(end_ms, transcript.end_ms)
        if end_ms <= start_ms:
            continue
        words.append({"start_ms": start_ms, "end_ms": end_ms, "text": text})
    words.sort(key=lambda w: (w["start_ms"], w["end_ms"]))
    return words


def _try_particle_inherit(transcript: TranscriptSegment, config: AlignmentConfig) -> bool:
    if not config.enable_particle_inherit:
        return False
    if transcript.duration_ms > config.particle_max_duration_ms:
        return False
    return _content_char_count(transcript.text) <= config.particle_max_chars


def _content_char_count(text: str) -> int:
    cleaned = _NON_CONTENT_RE.sub("", text)
    return len(cleaned)


def _nearest_speaker(
    start_ms: int,
    end_ms: int,
    turns: list[SpeakerTurn],
) -> str | None:
    """Pick speaker of the temporally nearest turn (prefer earlier turn on ties)."""
    if not turns:
        return None
    best: tuple[int, int, str] | None = None  # (distance, start_ms, speaker_id)
    for turn in turns:
        ov = overlap_ms(start_ms, end_ms, turn.start_ms, turn.end_ms)
        if ov > 0:
            distance = 0
        elif turn.end_ms <= start_ms:
            distance = start_ms - turn.end_ms
        else:
            distance = turn.start_ms - end_ms
        candidate = (distance, turn.start_ms, turn.speaker_id)
        if best is None or candidate < best:
            best = candidate
    return best[2] if best is not None else None


def _join_word_texts(words: list[dict[str, Any]]) -> str:
    texts = [str(w.get("text", "")) for w in words if w.get("text")]
    if not texts:
        return ""
    # Space-separated tokens when ASR used spaces; otherwise concatenate.
    if any(" " in t for t in texts) or all(len(t) > 1 for t in texts):
        return "".join(texts) if all(_looks_cjk_token(t) for t in texts) else " ".join(texts)
    return "".join(texts)


def _looks_cjk_token(token: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in token)


def _resolve_confidence(
    base: float | None,
    *,
    match_ratio: float | None,
    multi_speaker: bool,
    scale: float,
    inferred: bool,
    unknown: bool,
) -> float | None:
    if unknown:
        return None if base is None else min(base, 0.3)
    value = base
    if value is None and match_ratio is not None:
        value = match_ratio
    if value is None:
        return None
    if multi_speaker:
        value = value * scale
    if inferred:
        value = value * 0.8
    return max(0.0, min(1.0, value))


def _diagnostic_row(
    *,
    start_ms: int,
    end_ms: int,
    text: str,
    speaker_id: str,
    match_ratio: float | None,
    inferred: bool,
    match_method: MatchMethod,
    unmatched_reason: str | None,
    overlaps: list[dict[str, Any]],
    transcript_duration_ms: int,
    parent_text: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "text": text,
        "speaker_id": speaker_id,
        "match_ratio": match_ratio,
        "inferred": inferred,
        "match_method": match_method,
        "unmatched_reason": unmatched_reason,
        "overlaps": overlaps,
        "transcript_duration_ms": transcript_duration_ms,
    }
    if parent_text is not None:
        row["parent_text"] = parent_text
    return row
