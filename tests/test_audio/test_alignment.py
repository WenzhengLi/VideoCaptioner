"""Offline unit tests for transcript ↔ speaker alignment (no ASR/diarization)."""

from __future__ import annotations

import json
from pathlib import Path

from course_video_analyzer.audio.alignment import (
    ALIGNMENT_ARTIFACT_NAME,
    AlignmentConfig,
    align_speech,
    align_speech_with_diagnostics,
    overlap_ms,
    write_alignment_artifact,
)
from course_video_analyzer.audio.speaker_mapping import (
    apply_speaker_names,
    resolve_speaker_name,
)
from course_video_analyzer.models import SpeakerTurn, TranscriptSegment


def _tx(
    start_ms: int,
    end_ms: int,
    text: str,
    *,
    words: list[dict] | None = None,
    confidence: float | None = 0.9,
) -> TranscriptSegment:
    return TranscriptSegment(
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        raw_text=text,
        confidence=confidence,
        words=words or [],
        source="funasr",
    )


def _turn(
    start_ms: int,
    end_ms: int,
    speaker_id: str,
    *,
    confidence: float | None = 0.95,
) -> SpeakerTurn:
    return SpeakerTurn(
        start_ms=start_ms,
        end_ms=end_ms,
        speaker_id=speaker_id,
        confidence=confidence,
        source="wespeaker",
    )


def test_overlap_ms_half_open_boundary() -> None:
    assert overlap_ms(0, 1000, 1000, 2000) == 0
    assert overlap_ms(0, 1000, 999, 2000) == 1
    assert overlap_ms(500, 1500, 0, 1000) == 500


def test_empty_inputs() -> None:
    assert align_speech([], []) == []
    assert align_speech([], [_turn(0, 1000, "Speaker 0")]) == []
    result = align_speech_with_diagnostics([_tx(0, 1000, "你好")], [])
    assert len(result.segments) == 1
    assert result.segments[0].speaker_id == "unknown"
    assert result.segments[0].text == "你好"
    assert result.diagnostics[0]["unmatched_reason"] == "no_overlap"


def test_max_overlap_assigns_speaker() -> None:
    transcripts = [_tx(0, 1000, "我们开始")]
    turns = [
        _turn(0, 800, "Speaker 0"),
        _turn(800, 2000, "Speaker 1"),
    ]
    segments = align_speech(transcripts, turns)
    assert len(segments) == 1
    assert segments[0].speaker_id == "Speaker 0"
    assert segments[0].match_ratio == 0.8
    assert segments[0].inferred is False
    assert segments[0].start_ms == 0
    assert segments[0].end_ms == 1000


def test_below_threshold_becomes_unknown() -> None:
    transcripts = [_tx(0, 1000, "长句内容")]
    turns = [_turn(0, 400, "Speaker 0")]  # ratio 0.4 < 0.5
    segments = align_speech(transcripts, turns)
    assert segments[0].speaker_id == "unknown"
    assert segments[0].match_ratio == 0.4
    assert segments[0].inferred is False


def test_equal_overlap_is_unknown() -> None:
    transcripts = [_tx(0, 1000, "两人各半")]
    turns = [
        _turn(0, 500, "Speaker 0"),
        _turn(500, 1000, "Speaker 1"),
    ]
    result = align_speech_with_diagnostics(
        transcripts,
        turns,
        config=AlignmentConfig(enable_particle_inherit=False),
    )
    assert result.segments[0].speaker_id == "unknown"
    assert result.diagnostics[0]["unmatched_reason"] == "equal_overlap"
    assert result.diagnostics[0]["match_ratio"] == 0.5


def test_no_word_split_keeps_single_low_confidence_span() -> None:
    """Clear multi-speaker span without word timestamps must not invent a cut."""
    transcripts = [_tx(0, 2000, "跨越两人但没有词级时间戳", confidence=0.9)]
    turns = [
        _turn(0, 1000, "Speaker 0"),
        _turn(1000, 2000, "Speaker 1"),
    ]
    # Equal overlap → unknown; still a single interval.
    segments = align_speech(transcripts, turns)
    assert len(segments) == 1
    assert segments[0].start_ms == 0
    assert segments[0].end_ms == 2000
    assert segments[0].text == "跨越两人但没有词级时间戳"


def test_word_level_split_on_speaker_switch() -> None:
    words = [
        {"start_ms": 0, "end_ms": 400, "text": "你好"},
        {"start_ms": 400, "end_ms": 800, "text": "世界"},
        {"start_ms": 800, "end_ms": 1200, "text": "下一"},
        {"start_ms": 1200, "end_ms": 1600, "text": "位"},
    ]
    transcripts = [_tx(0, 1600, "你好世界下一位", words=words)]
    turns = [
        _turn(0, 800, "Speaker 0"),
        _turn(800, 1600, "Speaker 1"),
    ]
    segments = align_speech(transcripts, turns)
    assert len(segments) == 2
    assert segments[0].speaker_id == "Speaker 0"
    assert segments[0].text == "你好世界"
    assert segments[0].start_ms == 0
    assert segments[0].end_ms == 800
    assert segments[1].speaker_id == "Speaker 1"
    assert segments[1].text == "下一位"
    assert segments[1].start_ms == 800
    assert segments[1].end_ms == 1600
    joined = "".join(s.text for s in segments)
    assert joined == "你好世界下一位"


def test_short_particle_inherits_nearest_speaker() -> None:
    transcripts = [
        _tx(0, 1000, "我们继续讲"),
        _tx(1050, 1300, "好的"),  # short particle, slight gap after Speaker 0
    ]
    turns = [
        _turn(0, 1000, "Speaker 0"),
        _turn(2000, 3000, "Speaker 1"),
    ]
    # "好的" has no overlap; without inherit → unknown.
    no_inherit = align_speech(
        transcripts,
        turns,
        config=AlignmentConfig(
            enable_particle_inherit=False,
            enable_context_inherit=False,
        ),
    )
    assert no_inherit[1].speaker_id == "unknown"
    assert no_inherit[1].inferred is False

    with_inherit = align_speech(
        transcripts,
        turns,
        config=AlignmentConfig(enable_particle_inherit=True),
    )
    assert with_inherit[1].speaker_id == "Speaker 0"
    assert with_inherit[1].inferred is True
    assert with_inherit[1].text == "好的"


def test_particle_inherit_respects_duration_and_char_limits() -> None:
    long_text = _tx(1050, 2500, "这不是短附和词因为它很长")
    turns = [_turn(0, 1000, "Speaker 0")]
    segments = align_speech([long_text], turns)
    assert segments[0].speaker_id == "unknown"
    assert segments[0].inferred is False


def test_unknown_run_inherits_same_surrounding_speaker() -> None:
    transcripts = [
        _tx(0, 500, "前句"),
        _tx(600, 1400, "VAD空洞中的句子"),
        _tx(1500, 2000, "后句"),
    ]
    turns = [
        _turn(0, 500, "Speaker 0"),
        _turn(1500, 2000, "Speaker 0"),
    ]
    result = align_speech_with_diagnostics(
        transcripts,
        turns,
        config=AlignmentConfig(enable_particle_inherit=False),
    )
    assert result.segments[1].speaker_id == "Speaker 0"
    assert result.segments[1].inferred is True
    assert result.diagnostics[1]["match_method"] == "context_inherit"


def test_unknown_run_not_inherited_across_speaker_switch() -> None:
    transcripts = [
        _tx(0, 500, "甲"),
        _tx(600, 1400, "无法判断"),
        _tx(1500, 2000, "乙"),
    ]
    turns = [
        _turn(0, 500, "Speaker 0"),
        _turn(1500, 2000, "Speaker 1"),
    ]
    result = align_speech_with_diagnostics(
        transcripts,
        turns,
        config=AlignmentConfig(enable_particle_inherit=False),
    )
    assert result.segments[1].speaker_id == "unknown"
    assert result.segments[1].inferred is False


def test_speaker_name_mapping_does_not_change_id() -> None:
    transcripts = [_tx(0, 1000, "你好")]
    turns = [_turn(0, 1000, "Speaker 0")]
    segments = align_speech(
        transcripts,
        turns,
        speaker_names={"Speaker 0": "导师", "Speaker 1": "助教"},
    )
    assert segments[0].speaker_id == "Speaker 0"
    assert segments[0].speaker_name == "导师"

    remapped = apply_speaker_names(segments, {"Speaker 0": "主讲"})
    assert remapped[0].speaker_id == "Speaker 0"
    assert remapped[0].speaker_name == "主讲"
    assert resolve_speaker_name("unknown", {"Speaker 0": "导师"}) is None
    assert resolve_speaker_name("Speaker 9", {"Speaker 0": "导师"}) is None


def test_segments_sorted_and_intervals_valid() -> None:
    transcripts = [
        _tx(2000, 3000, "第二句"),
        _tx(0, 1000, "第一句"),
    ]
    turns = [
        _turn(2000, 3000, "Speaker 1"),
        _turn(0, 1000, "Speaker 0"),
    ]
    segments = align_speech(transcripts, turns)
    assert [s.text for s in segments] == ["第一句", "第二句"]
    for seg in segments:
        assert seg.end_ms > seg.start_ms


def test_custom_min_match_ratio() -> None:
    transcripts = [_tx(0, 1000, "阈值调整")]
    turns = [_turn(0, 400, "Speaker 0")]
    strict = align_speech(
        transcripts, turns, config=AlignmentConfig(min_match_ratio=0.5)
    )
    loose = align_speech(
        transcripts, turns, config=AlignmentConfig(min_match_ratio=0.3)
    )
    assert strict[0].speaker_id == "unknown"
    assert loose[0].speaker_id == "Speaker 0"


def test_alignment_json_diagnostics(tmp_path: Path) -> None:
    transcripts = [_tx(0, 1000, "写入诊断")]
    turns = [_turn(0, 900, "Speaker 0")]
    result = align_speech_with_diagnostics(transcripts, turns)
    path = write_alignment_artifact(tmp_path, result, config=AlignmentConfig())
    assert path.name == ALIGNMENT_ARTIFACT_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["config"]["min_match_ratio"] == 0.5
    assert payload["speech_segments"][0]["speaker_id"] == "Speaker 0"
    diag = payload["diagnostics"][0]
    assert diag["match_method"] == "max_overlap"
    assert diag["match_ratio"] == 0.9
    assert diag["inferred"] is False
    assert isinstance(diag["overlaps"], list)
    assert diag["overlaps"][0]["speaker_id"] == "Speaker 0"

    # Convenience API with artifact_dir
    out_dir = tmp_path / "artifacts" / "audio"
    align_speech(transcripts, turns, artifact_dir=out_dir)
    assert (out_dir / ALIGNMENT_ARTIFACT_NAME).is_file()


def test_original_text_not_lost_on_direct_match() -> None:
    text = "原始文字必须保留，标点也要在。"
    segments = align_speech([_tx(10, 510, text)], [_turn(0, 1000, "Speaker 0")])
    assert segments[0].text == text
