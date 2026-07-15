"""Map anonymous speaker ids to display names without mutating ids."""

from __future__ import annotations

from collections.abc import Mapping

from course_video_analyzer.models import SpeechSegment

UNKNOWN_SPEAKER = "unknown"


def resolve_speaker_name(
    speaker_id: str,
    name_map: Mapping[str, str] | None,
) -> str | None:
    """Return display name for ``speaker_id``, or ``None`` for unknown/unmapped."""
    if not name_map or speaker_id == UNKNOWN_SPEAKER:
        return None
    name = name_map.get(speaker_id)
    if name is None:
        return None
    stripped = name.strip()
    return stripped or None


def apply_speaker_names(
    segments: list[SpeechSegment],
    name_map: Mapping[str, str],
) -> list[SpeechSegment]:
    """Return new segments with ``speaker_name`` filled; ``speaker_id`` unchanged."""
    if not name_map:
        return list(segments)
    return [
        segment.model_copy(
            update={"speaker_name": resolve_speaker_name(segment.speaker_id, name_map)}
        )
        for segment in segments
    ]
