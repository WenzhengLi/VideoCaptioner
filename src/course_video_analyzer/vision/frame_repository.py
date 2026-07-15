"""Disk-first frame/OCR repository backed by SQLite metadata and JPEG files."""

from __future__ import annotations

import json
import sqlite3
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class StoredFrame:
    timestamp_ms: int
    frame_index: int
    image_path: Path
    sharpness: float


class DiskFrameRepository:
    """Keep durable state on disk while limiting decoded images held in RAM."""

    def __init__(
        self,
        root: Path,
        *,
        memory_cache_size: int = 8,
        jpeg_quality: int = 92,
    ) -> None:
        self.root = Path(root)
        self.images_dir = self.root / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "frames.sqlite3"
        self.memory_cache_size = max(1, int(memory_cache_size))
        self.jpeg_quality = int(jpeg_quality)
        self._images: OrderedDict[int, np.ndarray] = OrderedDict()
        self._connection = sqlite3.connect(self.db_path)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self._connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            CREATE TABLE IF NOT EXISTS frames (
                timestamp_ms INTEGER PRIMARY KEY,
                frame_index INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                sharpness REAL NOT NULL,
                has_text INTEGER,
                text_score REAL,
                ocr_text TEXT,
                ocr_lines_json TEXT,
                content_region_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_frames_frame_index
                ON frames(frame_index);
            """
        )
        self._connection.commit()

    def get_frame(self, timestamp_ms: int) -> StoredFrame | None:
        row = self._connection.execute(
            "SELECT timestamp_ms, frame_index, image_path, sharpness "
            "FROM frames WHERE timestamp_ms = ?",
            (int(timestamp_ms),),
        ).fetchone()
        if row is None:
            return None
        path = self.root / str(row["image_path"])
        if not path.is_file():
            return None
        return StoredFrame(
            timestamp_ms=int(row["timestamp_ms"]),
            frame_index=int(row["frame_index"]),
            image_path=path,
            sharpness=float(row["sharpness"]),
        )

    def get_frame_by_index(self, frame_index: int) -> StoredFrame | None:
        row = self._connection.execute(
            "SELECT timestamp_ms, frame_index, image_path, sharpness "
            "FROM frames WHERE frame_index = ? ORDER BY timestamp_ms LIMIT 1",
            (int(frame_index),),
        ).fetchone()
        if row is None:
            return None
        path = self.root / str(row["image_path"])
        if not path.is_file():
            return None
        return StoredFrame(
            timestamp_ms=int(row["timestamp_ms"]),
            frame_index=int(row["frame_index"]),
            image_path=path,
            sharpness=float(row["sharpness"]),
        )

    def store_frame(
        self,
        timestamp_ms: int,
        frame_index: int,
        image_bgr: np.ndarray,
        *,
        sharpness: float,
    ) -> StoredFrame:
        existing = self.get_frame(timestamp_ms)
        if existing is not None:
            self._remember(existing.timestamp_ms, image_bgr)
            return existing
        name = f"frame-{int(frame_index):08d}-{int(timestamp_ms):010d}.jpg"
        image_path = self.images_dir / name
        if not cv2.imwrite(
            str(image_path),
            image_bgr,
            [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality],
        ):
            raise OSError(f"无法写入磁盘帧缓存: {image_path}")
        relative = image_path.relative_to(self.root).as_posix()
        self._connection.execute(
            "INSERT OR REPLACE INTO frames "
            "(timestamp_ms, frame_index, image_path, sharpness) VALUES (?, ?, ?, ?)",
            (int(timestamp_ms), int(frame_index), relative, float(sharpness)),
        )
        self._connection.commit()
        self._remember(int(timestamp_ms), image_bgr)
        return StoredFrame(int(timestamp_ms), int(frame_index), image_path, float(sharpness))

    def load_image(self, frame: StoredFrame) -> np.ndarray:
        cached = self._images.get(frame.timestamp_ms)
        if cached is not None:
            self._images.move_to_end(frame.timestamp_ms)
            return cached
        image = cv2.imread(str(frame.image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"无法读取磁盘帧缓存: {frame.image_path}")
        self._remember(frame.timestamp_ms, image)
        return image

    def store_ocr(
        self,
        timestamp_ms: int,
        *,
        has_text: bool,
        score: float,
        text: str,
        text_lines: list[dict[str, Any]],
        content_region: tuple[int, int, int, int] | None,
    ) -> None:
        self._connection.execute(
            "UPDATE frames SET has_text = ?, text_score = ?, ocr_text = ?, "
            "ocr_lines_json = ?, content_region_json = ? WHERE timestamp_ms = ?",
            (
                int(bool(has_text)),
                float(score),
                text,
                json.dumps(text_lines, ensure_ascii=False),
                json.dumps(content_region) if content_region is not None else None,
                int(timestamp_ms),
            ),
        )
        self._connection.commit()

    def load_ocr(self, timestamp_ms: int) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT has_text, text_score, ocr_text, ocr_lines_json, content_region_json "
            "FROM frames WHERE timestamp_ms = ? AND has_text IS NOT NULL",
            (int(timestamp_ms),),
        ).fetchone()
        if row is None:
            return None
        region_raw = json.loads(row["content_region_json"]) if row["content_region_json"] else None
        return {
            "has_text": bool(row["has_text"]),
            "score": float(row["text_score"] or 0.0),
            "text": str(row["ocr_text"] or ""),
            "text_lines": json.loads(row["ocr_lines_json"] or "[]"),
            "content_region": tuple(int(value) for value in region_raw) if region_raw else None,
        }

    def load_ocr_by_frame_index(self, frame_index: int) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT timestamp_ms FROM frames WHERE frame_index = ? AND has_text IS NOT NULL "
            "ORDER BY timestamp_ms LIMIT 1",
            (int(frame_index),),
        ).fetchone()
        if row is None:
            return None
        return self.load_ocr(int(row["timestamp_ms"]))

    def frame_count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) AS count FROM frames").fetchone()
        return int(row["count"] if row is not None else 0)

    def ocr_count(self) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS count FROM frames WHERE has_text IS NOT NULL"
        ).fetchone()
        return int(row["count"] if row is not None else 0)

    @property
    def memory_image_count(self) -> int:
        return len(self._images)

    def close(self) -> None:
        self._images.clear()
        self._connection.close()

    def _remember(self, timestamp_ms: int, image_bgr: np.ndarray) -> None:
        self._images[int(timestamp_ms)] = image_bgr
        self._images.move_to_end(int(timestamp_ms))
        while len(self._images) > self.memory_cache_size:
            self._images.popitem(last=False)

    def __enter__(self) -> DiskFrameRepository:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
