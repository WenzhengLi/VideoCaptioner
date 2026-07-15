"""Package-level smoke for Gradio entrypoint."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_course_video_web_entrypoint_imports() -> None:
    pytest.importorskip("gradio")
    from course_video_analyzer.web import build_app, main

    assert callable(main)
    app = build_app(jobs_root=Path("jobs"))
    assert app is not None
