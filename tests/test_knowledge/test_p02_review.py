import json
from pathlib import Path

from course_video_analyzer.knowledge.p02_review import (
    apply_p02_review,
    build_p02_review_pack,
)


def test_compact_p02_review_applies_cluster_and_quote_decisions(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    segments = []
    for index, (speaker, text) in enumerate(
        [("speaker_0", "今天讲案例"), ("speaker_1", "老师我有问题"), ("speaker_0", "他说可以")],
        start=1,
    ):
        segments.append(
            {
                "segment_id": f"SEG-C002-{index:06d}",
                "speaker": speaker,
                "content_type": "speech",
                "normalized_text": text,
                "source_role": "unknown",
                "epistemic_type": "unknown",
                "relevance": "uncertain",
                "classification_reasons": ["baseline"],
                "classification_confidence": 0.5,
            }
        )
    baseline.write_text(json.dumps({"segments": segments}, ensure_ascii=False), encoding="utf-8")
    pack = tmp_path / "pack.json"
    build_p02_review_pack("C002", baseline, pack)
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps(
            {
                "course_id": "C002",
                "speaker_cluster_roles": {
                    "speaker_0": "instructor_explanation",
                    "speaker_1": "student_question",
                },
                "actual_chat_segment_ids": ["SEG-C002-000003"],
                "marketing_segment_ids": [],
                "uncertain_segment_ids": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output.json"

    apply_p02_review("C002", baseline, pack, review, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["segments"][0]["source_role"] == "instructor_explanation"
    assert payload["segments"][1]["source_role"] == "student_question"
    assert payload["segments"][2]["source_role"] == "actual_chat"
    assert payload["review_metrics"]["review_mode"] == "compact_decisions_applied_deterministically"
