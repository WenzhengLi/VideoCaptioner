import json
from pathlib import Path

from course_video_analyzer.knowledge.runs import archive_successful_job, compare_transcripts


def _successful_job(root: Path, transcript: str) -> Path:
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True)
    (root / "job.json").write_text(
        json.dumps({"job_id": "job-1", "stages": {"export": {"status": "completed"}}}),
        encoding="utf-8",
    )
    (root / "media.json").write_text("{}", encoding="utf-8")
    (artifacts / "transcript.txt").write_text(transcript, encoding="utf-8")
    return root


def test_compare_transcripts_reports_exact_match(tmp_path: Path) -> None:
    content = "[00:00:00.000 -> 00:00:01.000] 导师\n你好\n"
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text(content, encoding="utf-8")
    second.write_text(content, encoding="utf-8")

    report = compare_transcripts(first, second)

    assert report["exact_match"] is True
    assert report["candidate"]["timestamp_count"] == 1
    assert report["delta"]["non_whitespace_chars"] == 0


def test_archive_successful_job_refuses_overwrite(tmp_path: Path) -> None:
    job = _successful_job(tmp_path / "job", "hello")
    data = tmp_path / "data"
    target = archive_successful_job("C001", job, data, run_id="RUN-001")

    assert (target / "transcript.txt").read_text(encoding="utf-8") == "hello"
    assert (target / "run.json").is_file()

    try:
        archive_successful_job("C001", job, data, run_id="RUN-001")
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing run must not be overwritten")
