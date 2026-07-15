import json
from pathlib import Path

from course_video_analyzer.knowledge.classifier import classify_p02_baseline


def test_classifier_preserves_p01_and_uses_conservative_roles(tmp_path: Path) -> None:
    p01 = tmp_path / "p01.json"
    p01.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "segment_id": "SEG-C001-000001",
                        "start_ms": 0,
                        "end_ms": 1000,
                        "speaker": "teacher_a",
                        "content_type": "speech",
                        "raw_text": "她就是在测试你。",
                        "normalized_text": "她就是在测试你。",
                        "edit_notes": [],
                        "confidence": 0.9,
                    },
                    {
                        "segment_id": "SEG-C001-000002",
                        "start_ms": 1000,
                        "end_ms": 2000,
                        "speaker": "unknown",
                        "content_type": "board_ocr",
                        "raw_text": "聊天截图",
                        "normalized_text": "聊天截图",
                        "edit_notes": [],
                        "confidence": 0.8,
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "p02.json"

    classify_p02_baseline("C001", p01, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["segments"][0]["epistemic_type"] == "instructor_claim"
    assert payload["segments"][1]["source_role"] == "board"
    assert payload["segments"][0]["raw_text"] == "她就是在测试你。"
