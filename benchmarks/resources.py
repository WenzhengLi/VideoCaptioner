"""Hardware / runtime resource sampling for benchmark reports."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResourceSample:
    elapsed_s: float
    peak_rss_mb: float | None
    peak_gpu_mb: float | None
    video_duration_ms: int | None = None

    @property
    def minutes_per_video_minute(self) -> float | None:
        if not self.video_duration_ms or self.video_duration_ms <= 0:
            return None
        return self.elapsed_s / (self.video_duration_ms / 60000.0)


@dataclass
class ResourceTracker:
    """Best-effort peak RSS / GPU memory tracker (works without psutil)."""

    video_duration_ms: int | None = None
    _t0: float = field(default_factory=time.perf_counter)
    _peak_rss_mb: float | None = None
    _peak_gpu_mb: float | None = None

    def poll(self) -> None:
        rss = _current_rss_mb()
        if rss is not None:
            self._peak_rss_mb = rss if self._peak_rss_mb is None else max(self._peak_rss_mb, rss)
        gpu = _current_gpu_mb()
        if gpu is not None:
            self._peak_gpu_mb = gpu if self._peak_gpu_mb is None else max(self._peak_gpu_mb, gpu)

    def finish(self) -> ResourceSample:
        self.poll()
        return ResourceSample(
            elapsed_s=time.perf_counter() - self._t0,
            peak_rss_mb=self._peak_rss_mb,
            peak_gpu_mb=self._peak_gpu_mb,
            video_duration_ms=self.video_duration_ms,
        )


def hardware_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "platform": os.name,
        "cpu_count": os.cpu_count(),
        "cuda_available": False,
        "cuda_device_name": None,
    }
    try:
        import torch

        info["cuda_available"] = bool(torch.cuda.is_available())
        if info["cuda_available"]:
            info["cuda_device_name"] = torch.cuda.get_device_name(0)
    except ImportError:
        pass
    return info


def _current_rss_mb() -> float | None:
    try:
        import psutil  # type: ignore[import-not-found]

        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except Exception:
        pass

    if os.name == "nt":
        return _windows_rss_mb()

    try:
        import resource as resource_mod

        getrusage = getattr(resource_mod, "getrusage", None)
        rusage_self = getattr(resource_mod, "RUSAGE_SELF", None)
        if getrusage is None or rusage_self is None:
            return None
        usage = getrusage(rusage_self).ru_maxrss
        # Linux: KB; macOS: bytes
        return usage / (1024 * 1024) if usage > 10_000_000 else usage / 1024.0
    except Exception:
        return None


def _windows_rss_mb() -> float | None:
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        # ``ctypes.windll`` only exists on Windows.  Resolve it dynamically so
        # Linux CI/type checking can import this module without platform-only
        # attribute errors.
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return None
        handle = windll.kernel32.GetCurrentProcess()
        ok = windll.psapi.GetProcessMemoryInfo(
            handle,
            ctypes.byref(counters),
            counters.cb,
        )
        if not ok:
            return None
        return float(counters.WorkingSetSize) / (1024 * 1024)
    except Exception:
        return None


def _current_gpu_mb() -> float | None:
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        return torch.cuda.max_memory_allocated() / (1024 * 1024)
    except Exception:
        return None
