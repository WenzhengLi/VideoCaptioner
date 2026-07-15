"""Background job runner so Gradio event handlers stay responsive."""

from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _TrackedJob:
    thread: threading.Thread
    error: str | None = None
    finished: bool = False


@dataclass
class JobRunner:
    """Track long-running pipeline threads without blocking the UI thread."""

    _lock: threading.Lock = field(default_factory=threading.Lock)
    _jobs: dict[str, _TrackedJob] = field(default_factory=dict)

    def submit(self, job_id: str, fn: Callable[[], Any]) -> None:
        with self._lock:
            existing = self._jobs.get(job_id)
            if existing is not None and not existing.finished:
                raise RuntimeError(f"任务已在运行中: {job_id}")

            tracked = _TrackedJob(thread=threading.Thread(target=lambda: None, daemon=True))

            def _wrapped() -> None:
                try:
                    fn()
                except Exception as exc:  # noqa: BLE001 - errors are shown in the UI
                    tracked.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=8)}"
                finally:
                    tracked.finished = True

            tracked.thread = threading.Thread(target=_wrapped, daemon=True, name=f"job-{job_id}")
            self._jobs[job_id] = tracked
            tracked.thread.start()

    def is_running(self, job_id: str) -> bool:
        with self._lock:
            tracked = self._jobs.get(job_id)
            return tracked is not None and not tracked.finished

    def get_error(self, job_id: str) -> str | None:
        with self._lock:
            tracked = self._jobs.get(job_id)
            return None if tracked is None else tracked.error

    def running_job_ids(self) -> list[str]:
        with self._lock:
            return [jid for jid, tracked in self._jobs.items() if not tracked.finished]
