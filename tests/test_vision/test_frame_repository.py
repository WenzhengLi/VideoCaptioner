from pathlib import Path

import numpy as np

from course_video_analyzer.vision.frame_repository import DiskFrameRepository


def test_disk_repository_persists_frames_ocr_and_limits_memory(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    with DiskFrameRepository(root, memory_cache_size=2) as repository:
        for index in range(5):
            image = np.full((40, 60, 3), index * 20, dtype=np.uint8)
            repository.store_frame(index * 1000, index, image, sharpness=float(index))
        repository.store_ocr(
            2000,
            has_text=True,
            score=0.9,
            text="board text",
            text_lines=[{"text": "board text", "confidence": 0.9}],
            content_region=(5, 6, 50, 35),
        )
        assert repository.memory_image_count <= 2
        assert repository.frame_count() == 5
        assert repository.ocr_count() == 1

    with DiskFrameRepository(root, memory_cache_size=1) as reopened:
        frame = reopened.get_frame(2000)
        assert frame is not None
        assert reopened.load_image(frame).shape == (40, 60, 3)
        ocr = reopened.load_ocr_by_frame_index(2)
        assert ocr is not None
        assert ocr["text"] == "board text"
        assert ocr["content_region"] == (5, 6, 50, 35)
        assert reopened.memory_image_count == 1
