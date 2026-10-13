import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure import gpu_encoder


class GpuEncoderDetectionTests(unittest.TestCase):
    def test_nvenc_listed_but_unusable_falls_back_to_cpu(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["ffmpeg", "-encoders"]:
                return type("Result", (), {"returncode": 0, "stdout": " V....D h264_nvenc NVIDIA NVENC H.264 encoder", "stderr": ""})()
            return type("Result", (), {"returncode": 171, "stdout": "", "stderr": "CUDA_ERROR_COMPAT_NOT_SUPPORTED_ON_DEVICE"})()

        with patch.object(gpu_encoder.subprocess, "run", side_effect=fake_run):
            self.assertFalse(gpu_encoder._detect_nvenc())

    @patch("src.infrastructure.renderer.asyncio.create_subprocess_exec")
    def test_ffmpeg_renderer_cleans_up_file_on_failure(self, mock_exec):
        import asyncio
        from src.domain.entities import Clip
        from src.infrastructure.renderer import FFmpegRenderer
        import tempfile

        renderer = FFmpegRenderer()
        clip = Clip(rank=1, start=10.0, end=20.0, score=90, hook="Test", reason="Viral")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "clip_01.mp4")
            # Create a 0-byte dummy file as if ffmpeg touched it before dying
            with open(out_file, "w") as f:
                f.write("")

            mock_proc = unittest.mock.AsyncMock()
            mock_proc.communicate.return_value = (b"", b"banner header\n" * 50 + b"\nreal fatal error: cuInit failed")
            mock_proc.returncode = 171
            mock_exec.return_value = mock_proc

            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(renderer.trim_clip("/fake/in.mp4", clip, out_file))

            # The 0-byte file should have been cleaned up
            self.assertFalse(os.path.exists(out_file))
            # The exception should contain the real fatal error from the tail
            self.assertIn("real fatal error", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

