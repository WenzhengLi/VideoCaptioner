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


def test_classifier_uses_dominant_diarization_cluster_as_reviewable_instructor(tmp_path: Path) -> None:
    p01 = tmp_path / "p01.json"
    segments = []
    for index, speaker in enumerate(["speaker_0", "speaker_0", "speaker_1"], start=1):
        segments.append(
            {
                "segment_id": f"SEG-C002-{index:06d}",
                "start_ms": index * 1000,
                "end_ms": (index + 1) * 1000,
                "speaker": speaker,
                "content_type": "speech",
                "raw_text": "示例",
                "normalized_text": "示例",
                "edit_notes": [],
                "confidence": 0.8,
            }
        )
    p01.write_text(json.dumps({"segments": segments}, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "p02.json"

    classify_p02_baseline("C002", p01, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["segments"][0]["source_role"] == "instructor_explanation"
    assert payload["segments"][2]["source_role"] == "student_question"
    assert payload["classification_metrics"]["speaker_cluster_role_baseline"] == {
        "speaker_0": "instructor_explanation",
        "speaker_1": "student_question",
    }
