import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.clip_outputs import (
    discover_ready_clip_ranks,
    initialize_clip_readiness,
    mark_clip_ready,
)


def _write_video(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"completed-video")


class ProgressiveClipAvailabilityTests(unittest.TestCase):
    def test_ready_markers_do_not_expose_in_progress_files(self):
        with TemporaryDirectory() as temporary_dir:
            tmp_path = Path(temporary_dir)
            initialize_clip_readiness(temporary_dir)
            _write_video(tmp_path / "clip_01_final.mp4")

            self.assertEqual(discover_ready_clip_ranks(temporary_dir), [])

            mark_clip_ready(temporary_dir, 1)
            self.assertEqual(discover_ready_clip_ranks(temporary_dir), [1])

    def test_each_clip_unlocks_independently(self):
        with TemporaryDirectory() as temporary_dir:
            tmp_path = Path(temporary_dir)
            initialize_clip_readiness(temporary_dir)
            _write_video(tmp_path / "clip_01_final.mp4")
            _write_video(tmp_path / "clip_02_final.mp4")

            mark_clip_ready(temporary_dir, 2)
            self.assertEqual(discover_ready_clip_ranks(temporary_dir), [2])

            mark_clip_ready(temporary_dir, 1)
            self.assertEqual(discover_ready_clip_ranks(temporary_dir), [1, 2])

    def test_legacy_outputs_remain_discoverable_without_markers(self):
        with TemporaryDirectory() as temporary_dir:
            tmp_path = Path(temporary_dir)
            _write_video(tmp_path / "clip_03_final.mp4")
            _write_video(tmp_path / "final" / "clip_04.mp4")

            self.assertEqual(discover_ready_clip_ranks(temporary_dir), [3, 4])


if __name__ == "__main__":
    unittest.main()
