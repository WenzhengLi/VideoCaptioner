"""Local Tidy-compatible SQLite index for atomic P06 entries."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_entries (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    source_path TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    id UNINDEXED,
    title,
    body,
    tokenize='unicode61'
);
"""


def _entry_body(entry: dict[str, Any]) -> str:
    values: list[str] = [str(entry.get("title", "")), str(entry.get("type", ""))]
    for field in (
        "relationship_stage",
        "scenario",
        "observations",
        "instructor_claims",
        "alternative_explanations",
        "principles",
        "applicability",
        "contraindications",
        "risks",
        "safety_flags",
        "response_options",
    ):
        values.extend(str(value) for value in entry.get(field, []))
    return "\n".join(value for value in values if value)


def index_tidy_entries(data_root: Path, database_path: Path) -> dict[str, int]:
    data_root = Path(data_root).resolve()
    database_path = Path(database_path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    sources = sorted(
        path
        for path in data_root.glob("courses/*/05_tidy/P06-knowledge-v002/*.json")
        if not path.name.endswith(".cursor-task.json") and ".invalid-" not in path.name
    )
    indexed = 0
    with sqlite3.connect(database_path) as connection:
        connection.executescript(SCHEMA)
        connection.execute("DELETE FROM knowledge_entries")
        connection.execute("DELETE FROM knowledge_fts")
        for path in sources:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for entry in payload.get("entries", []):
                body = _entry_body(entry)
                connection.execute(
                    """INSERT INTO knowledge_entries
                    (id, course_id, case_id, type, title, body, evidence_json, confidence, source_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entry["id"],
                        payload["course_id"],
                        payload["case_id"],
                        entry["type"],
                        entry["title"],
                        body,
                        json.dumps(entry.get("evidence_spans", []), ensure_ascii=False),
                        float(entry["confidence"]),
                        str(path),
                    ),
                )
                connection.execute(
                    "INSERT INTO knowledge_fts (id, title, body) VALUES (?, ?, ?)",
                    (entry["id"], entry["title"], body),
                )
                indexed += 1
        connection.commit()
    return {"source_file_count": len(sources), "entry_count": indexed}


def search_tidy_entries(database_path: Path, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        return []
    with sqlite3.connect(Path(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """SELECT e.*, bm25(knowledge_fts) AS rank
                FROM knowledge_fts
                JOIN knowledge_entries e ON e.id = knowledge_fts.id
                WHERE knowledge_fts MATCH ?
                ORDER BY rank, e.confidence DESC
                LIMIT ?""",
                (query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if not rows:
            all_rows = connection.execute(
                "SELECT *, 0.0 AS rank FROM knowledge_entries"
            ).fetchall()
            chunks = re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+", query)
            ignored = {"如何", "应该", "分别", "方式", "时候", "怎么", "什么", "进行"}
            tokens: set[str] = set()
            for chunk in chunks:
                if re.fullmatch(r"[\u4e00-\u9fff]+", chunk):
                    for size in (2, 3, 4):
                        tokens.update(
                            chunk[index : index + size]
                            for index in range(max(0, len(chunk) - size + 1))
                        )
                elif len(chunk) >= 2:
                    tokens.add(chunk.lower())
            tokens -= ignored
            document_frequency = {
                token: sum(
                    token in (str(row["title"]) + "\n" + str(row["body"]))
                    for row in all_rows
                )
                for token in tokens
            }
            scored: list[tuple[float, sqlite3.Row]] = []
            total = max(1, len(all_rows))
            for row in all_rows:
                title = str(row["title"])
                body = str(row["body"])
                score = 0.0
                for token in tokens:
                    if token not in title and token not in body:
                        continue
                    idf = math.log((total + 1) / (document_frequency[token] + 1)) + 1
                    score += len(token) * idf * (2.5 if token in title else 1.0)
                if score > 0:
                    scored.append((score + float(row["confidence"]), row))
            scored.sort(key=lambda item: item[0], reverse=True)
            rows = [row for _, row in scored[:limit]]
    return [
        {
            "id": row["id"],
            "course_id": row["course_id"],
            "case_id": row["case_id"],
            "type": row["type"],
            "title": row["title"],
            "body": row["body"],
            "evidence_spans": json.loads(row["evidence_json"]),
            "confidence": row["confidence"],
            "rank": row["rank"],
        }
        for row in rows
    ]


def build_answer_context(database_path: Path, query: str, *, limit: int = 8) -> dict[str, Any]:
    return {
        "query": query,
        "retrieved_entries": search_tidy_entries(database_path, query, limit=limit),
        "answer_contract": {
            "objective_facts": True,
            "multiple_interpretations": 3,
            "multiple_plans": 3,
            "reply_styles_per_plan": ["自然稳妥", "轻松幽默", "直接真诚"],
            "cite_entry_ids_and_evidence": True,
            "include_applicability_risks_and_stop_conditions": True,
            "respect_explicit_refusal_and_discomfort": True,
            "state_when_evidence_is_insufficient": True,
        },
    }
