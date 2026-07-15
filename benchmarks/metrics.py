"""Deterministic evaluation metrics for ASR, diarization, boards, and OCR."""

from __future__ import annotations

import re
from dataclasses import dataclass


_PUNCT_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def normalize_text(text: str, *, remove_space: bool = True) -> str:
    text = text.strip().lower()
    if remove_space:
        text = _PUNCT_RE.sub("", text)
    else:
        text = re.sub(r"\s+", " ", text)
    return text


def character_error_rate(reference: str, hypothesis: str) -> float:
    """CER = edit_distance(chars) / len(reference_chars). Empty ref → 0 if hyp empty else 1."""
    ref = list(normalize_text(reference))
    hyp = list(normalize_text(hypothesis))
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


def word_error_rate(reference: str, hypothesis: str) -> float:
    """WER over whitespace-tokenized words (Chinese may fall back to chars if no spaces)."""
    ref_tokens = _tokenize_words(reference)
    hyp_tokens = _tokenize_words(hypothesis)
    if not ref_tokens:
        return 0.0 if not hyp_tokens else 1.0
    return _levenshtein(ref_tokens, hyp_tokens) / len(ref_tokens)


def _tokenize_words(text: str) -> list[str]:
    cleaned = normalize_text(text, remove_space=False)
    if " " in cleaned:
        return [t for t in cleaned.split(" ") if t]
    # CJK without spaces: treat each char as a token for a stable WER proxy.
    return list(normalize_text(text, remove_space=True))


def _levenshtein(a: list[str], b: list[str]) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur.append(min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


@dataclass(frozen=True)
class Interval:
    start_ms: int
    end_ms: int
    label: str = ""

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)


def overlap_ms(a: Interval, b: Interval) -> int:
    return max(0, min(a.end_ms, b.end_ms) - max(a.start_ms, b.start_ms))


def diarization_error_rate(
    reference: list[Interval],
    hypothesis: list[Interval],
) -> dict[str, float]:
    """
    Collar-free DER approximation:

    DER = (false_alarm + missed + speaker_error) / total_reference_speech

    Speakers are matched greedily by maximum overlap (Hungarian-free for small N).
    """
    ref_total = sum(i.duration_ms for i in reference)
    if ref_total <= 0:
        return {
            "der": 0.0 if not hypothesis else 1.0,
            "false_alarm": float(sum(i.duration_ms for i in hypothesis)),
            "missed": 0.0,
            "speaker_error": 0.0,
            "ref_speech_ms": 0.0,
        }

    ref_ids = sorted({i.label for i in reference})
    hyp_ids = sorted({i.label for i in hypothesis})
    mapping = _greedy_speaker_map(reference, hypothesis, ref_ids, hyp_ids)

    # Build per-ms vote by expanding interval unions via sweep is heavy;
    # use pairwise labeled overlap accounting instead.
    missed = 0.0
    speaker_error = 0.0
    for ref in reference:
        covered = 0
        correct = 0
        for hyp in hypothesis:
            ov = overlap_ms(ref, hyp)
            if ov <= 0:
                continue
            covered += ov
            mapped = mapping.get(hyp.label)
            if mapped == ref.label:
                correct += ov
        missed += max(0, ref.duration_ms - covered)
        speaker_error += max(0, covered - correct)

    # False alarm: hyp speech not overlapping any reference speech.
    false_alarm = 0.0
    for hyp in hypothesis:
        covered = sum(overlap_ms(hyp, ref) for ref in reference)
        false_alarm += max(0, hyp.duration_ms - covered)

    der = (false_alarm + missed + speaker_error) / ref_total
    return {
        "der": der,
        "false_alarm": false_alarm,
        "missed": missed,
        "speaker_error": speaker_error,
        "ref_speech_ms": float(ref_total),
    }


def _greedy_speaker_map(
    reference: list[Interval],
    hypothesis: list[Interval],
    ref_ids: list[str],
    hyp_ids: list[str],
) -> dict[str, str]:
    scores: list[tuple[float, str, str]] = []
    for hid in hyp_ids:
        for rid in ref_ids:
            score = 0.0
            for h in hypothesis:
                if h.label != hid:
                    continue
                for r in reference:
                    if r.label != rid:
                        continue
                    score += overlap_ms(h, r)
            scores.append((score, hid, rid))
    scores.sort(reverse=True)
    mapped_h: set[str] = set()
    mapped_r: set[str] = set()
    mapping: dict[str, str] = {}
    for score, hid, rid in scores:
        if score <= 0 or hid in mapped_h or rid in mapped_r:
            continue
        mapping[hid] = rid
        mapped_h.add(hid)
        mapped_r.add(rid)
    return mapping


def box_iou(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
) -> float:
    """IoU for (x, y, w, h) boxes."""
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    inter_w = max(0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0, min(ay2, by2) - max(ay1, by1))
    inter = inter_w * inter_h
    if inter <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def board_detection_scores(
    references: list[tuple[int, int, int, int]],
    hypotheses: list[tuple[int, int, int, int]],
    *,
    iou_threshold: float = 0.5,
    top_k: int = 1,
) -> dict[str, float]:
    """Mean best IoU and Top-K hit rate (ref matched if any of top-k hyp exceeds threshold)."""
    if not references:
        return {"mean_iou": 1.0 if not hypotheses else 0.0, "top_k_hit_rate": 1.0}

    mean_iou = 0.0
    hits = 0
    for ref in references:
        scored = sorted(
            ((box_iou(ref, hyp), idx) for idx, hyp in enumerate(hypotheses)),
            reverse=True,
        )
        best = scored[0][0] if scored else 0.0
        mean_iou += best
        top = scored[: max(1, top_k)]
        if any(score >= iou_threshold for score, _ in top):
            hits += 1
    n = len(references)
    return {"mean_iou": mean_iou / n, "top_k_hit_rate": hits / n}


def board_page_rates(
    reference_ids: list[str],
    hypothesis_ids: list[str],
) -> dict[str, float]:
    """Duplicate rate among hyp pages; miss rate vs reference page ids."""
    ref_set = set(reference_ids)
    hyp_set = list(hypothesis_ids)
    unique_hyp = set(hyp_set)
    dup = 0.0
    if hyp_set:
        dup = (len(hyp_set) - len(unique_hyp)) / len(hyp_set)
    missed = 0.0
    if ref_set:
        missed = len(ref_set - unique_hyp) / len(ref_set)
    return {"duplicate_rate": dup, "miss_rate": missed}


def ocr_character_accuracy(reference: str, hypothesis: str) -> float:
    """1 - CER, clamped to [0, 1]."""
    return max(0.0, min(1.0, 1.0 - character_error_rate(reference, hypothesis)))
