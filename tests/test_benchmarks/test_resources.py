from __future__ import annotations

from benchmarks import resources


def test_windows_rss_probe_is_safe_on_non_windows(monkeypatch) -> None:
    monkeypatch.setattr(resources.os, "name", "posix")

    assert resources._windows_rss_mb() is None
