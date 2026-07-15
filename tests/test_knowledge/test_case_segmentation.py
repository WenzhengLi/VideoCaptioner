import json
from pathlib import Path

from course_video_analyzer.knowledge.case_segmentation import build_p03_timeline_input


def test_build_p03_timeline_keeps_order_and_boundary_fields(tmp_path: Path) -> None:
    p02 = tmp_path / "p02.json"
    p02.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "segment_id": "SEG-C001-000001",
                        "start_ms": 0,
                        "end_ms": 1000,
                        "speaker": "speaker_0",
                        "content_type": "speech",
                        "source_role": "instructor_explanation",
                        "epistemic_type": "instructor_claim",
                        "relevance": "core",
                        "normalized_text": "开始讲案例",
                        "raw_text": "开始讲案例",
                        "edit_notes": [],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "timeline.json"

    build_p03_timeline_input("C001", p02, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["input_segment_count"] == 1
    assert payload["segments"][0]["text"] == "开始讲案例"
    assert "raw_text" not in payload["segments"][0]
