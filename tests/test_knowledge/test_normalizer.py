import json
from pathlib import Path

from course_video_analyzer.knowledge.normalizer import normalize_transcript_p01


def test_normalizer_preserves_raw_and_applies_reusable_rules(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.txt"
    transcript.write_text(
        "[00:00:00.000 -> 00:00:01.000] 导师\n然后然后你好吗?\n\n"
        "[00:00:01.000 -> 00:00:02.000] 课板[board-v001]\nA.B\n",
        encoding="utf-8",
    )
    output = tmp_path / "p01.json"

    normalize_transcript_p01("C001", transcript, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert len(payload["segments"]) == 2
    assert payload["segments"][0]["raw_text"] == "然后然后你好吗?"
    assert payload["segments"][0]["normalized_text"] == "然后你好吗？"
    assert payload["segments"][1]["normalized_text"] == "A.B"
    assert payload["quality_metrics"]["changed_segment_count"] == 1


def test_normalizer_refuses_overwrite(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.txt"
    transcript.write_text(
        "[00:00:00.000 -> 00:00:01.000] 导师\n你好,\n",
        encoding="utf-8",
    )
    output = tmp_path / "p01.json"
    output.write_text("{}", encoding="utf-8")

    try:
        normalize_transcript_p01("C001", transcript, output)
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing output must not be overwritten")
