import json
from pathlib import Path

from course_video_analyzer.knowledge.cleaning_qa import validate_p01_output


def test_validate_p01_output_checks_raw_completeness(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.txt"
    transcript.write_text(
        "[00:00:00.000 -> 00:00:01.000] 导师\n你好。\n\n"
        "[00:00:01.000 -> 00:00:02.000] 课板[board-v001]\n标题\n",
        encoding="utf-8",
    )
    output = tmp_path / "p01.json"
    output.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "prompt_version": "knowledge-v001-p01",
                "source_ids": ["C001"],
                "segments": [
                    {
                        "segment_id": "SEG-C001-000001",
                        "start_ms": 0,
                        "end_ms": 1000,
                        "speaker": "teacher_a",
                        "content_type": "speech",
                        "raw_text": "你好。",
                        "normalized_text": "你好。",
                    },
                    {
                        "segment_id": "SEG-C001-000002",
                        "start_ms": 1000,
                        "end_ms": 2000,
                        "speaker": "unknown",
                        "content_type": "board_ocr",
                        "raw_text": "标题",
                        "normalized_text": "标题",
                    },
                ],
                "uncertainties": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = validate_p01_output("C001", transcript, output)

    assert report["status"] == "pass"
    assert report["metrics"]["input_segment_count"] == 2
    assert report["metrics"]["raw_mismatch_count"] == 0
