import json
from pathlib import Path

from course_video_analyzer.knowledge.answering import validate_answer_output


def test_answer_qa_requires_valid_citations_and_three_styles(tmp_path: Path) -> None:
    context = tmp_path / "context.json"
    context.write_text(
        json.dumps({"query": "怎么回复", "retrieved_entries": [{"id": "KNOW-1"}]}),
        encoding="utf-8",
    )
    output = tmp_path / "answer.json"
    plan = {
        "applicability": [],
        "risks": [],
        "stop_conditions": [],
        "reply_options": [
            {"style": "自然稳妥", "text": "a"},
            {"style": "轻松幽默", "text": "b"},
            {"style": "直接真诚", "text": "c"},
        ],
    }
    output.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "query": "怎么回复",
                "objective_facts": [],
                "interpretations": [{}, {}],
                "plans": [plan, plan],
                "knowledge_citations": [{"entry_id": "KNOW-1"}],
                "knowledge_limitations": [],
                "safety_and_boundaries": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = validate_answer_output(context, output)

    assert report["status"] == "pass"
