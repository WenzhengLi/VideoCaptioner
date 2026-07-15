from pathlib import Path

import pytest
from pydantic import ValidationError

from course_video_analyzer.models import (
    AnalysisResult,
    BoardCandidate,
    BoardRegion,
    MediaInfo,
    SpeakerTurn,
    SpeechSegment,
    TranscriptSegment,
)


def test_speech_segment_requires_positive_duration() -> None:
    with pytest.raises(ValidationError):
        SpeechSegment(start_ms=1000, end_ms=1000, text="无效片段")


def test_media_info_accepts_audio_only() -> None:
    media = MediaInfo(
        source_path=Path("lesson.wav"),
        duration_ms=60_000,
        width=0,
        height=0,
        fps=0,
        has_video=False,
        has_audio=True,
        audio_sample_rate=16000,
        audio_channels=1,
    )
    assert media.duration_ms == 60_000
    assert media.has_video is False


def test_transcript_and_speaker_turn_are_independent() -> None:
    text = TranscriptSegment(start_ms=0, end_ms=1000, text="你好", raw_text="你好")
    turn = SpeakerTurn(start_ms=0, end_ms=1000, speaker_id="Speaker 0", source="wespeaker")
    assert "speaker" not in text.model_dump()
    assert "text" not in turn.model_dump()


def test_board_candidate_scores_roundtrip() -> None:
    candidate = BoardCandidate(
        region=BoardRegion(x=10, y=20, width=800, height=600),
        score=0.8,
        area_ratio=0.4,
        rectangularity=0.9,
        text_density=0.5,
        stability=0.7,
        occlusion_ratio=0.1,
    )
    restored = BoardCandidate.model_validate_json(candidate.model_dump_json())
    assert restored.region.width == 800
    assert restored.score == 0.8


def test_analysis_result_roundtrip() -> None:
    result = AnalysisResult(
        media=MediaInfo(
            source_path=Path("lesson.mp4"),
            duration_ms=1000,
            width=1280,
            height=720,
            fps=25,
        ),
        speech_segments=[
            SpeechSegment(start_ms=0, end_ms=500, text="开始", speaker_id="Speaker 0")
        ],
    )
    restored = AnalysisResult.model_validate_json(result.model_dump_json())
    assert restored.speech_segments[0].text == "开始"
