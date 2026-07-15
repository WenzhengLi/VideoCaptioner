"""Course video analysis domain package."""

from .models import (
    AnalysisResult,
    BoardCandidate,
    BoardSegment,
    MediaInfo,
    SpeakerTurn,
    SpeechSegment,
    TimelineEntry,
    TranscriptSegment,
)

__all__ = [
    "AnalysisResult",
    "BoardCandidate",
    "BoardSegment",
    "MediaInfo",
    "SpeakerTurn",
    "SpeechSegment",
    "TimelineEntry",
    "TranscriptSegment",
]
