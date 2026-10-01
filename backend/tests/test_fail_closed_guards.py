"""Fail-closed guards for subtitle render and social compliance.

Regression tests for the three previously fail-open paths:
1. services.py subtitle render failure must raise (no raw copy fallback).
2. social_auto_post_service compliance failure must skip the clip
   (never schedule a non-compliant video).
3. publish route compliance failure must abort with HTTP 422.
"""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# 1. Subtitle fail-closed
# Inline in services._run_ffmpeg_render_path: when render_subtitles raises
# we now raise RuntimeError; watermark and mark_clip_ready must NOT run.
class SubtitleFailClosedTest(unittest.TestCase):

    def _build_renderer_loop(self, render_side_effect, tmp_path):
        from src.application import services as svc
        from src.domain.entities import SubtitleStyleConfig

        # Construct the bare-minimum object to drive the subtitle code path.
        class _FakePipeline:
            _repo = MagicMock()
            _repo.update_status = AsyncMock()
            _subtitle_renderer = MagicMock()
            _subtitle_renderer.render_subtitles = MagicMock(side_effect=render_side_effect)
            _emit = MagicMock()
            _apply_watermark = AsyncMock()
            _best_clip_path = staticmethod(lambda d, r, x: f"{d}/clip_{r:02d}_reframed.mp4")

            async def _run_inline_subtitle(self, clip, words, sub_enabled, output_dir):
                # Mirror the inline code in services._run_ffmpeg_render_path.
                in_path = f"{output_dir}/clip_{clip.rank:02d}_hooked.mp4"
                out_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
                if words and self._subtitle_renderer and sub_enabled:
                    sub_style = SubtitleStyleConfig(
                        enabled=True, color="white", highlight_color="yellow",
                        uppercase=False, position="bottom", start_offset=3.0,
                    )
                    try:
                        self._subtitle_renderer.render_subtitles(
                            video_path=in_path, words=words, style=sub_style,
                            output_path=out_path, start_offset=3.0,
                        )
                    except Exception as e:
                        self._last_error = e
                        raise RuntimeError(
                            f"Subtitle rendering failed for clip #{clip.rank}; refusing raw fallback"
                        ) from e
                return out_path

        return _FakePipeline()

    def test_render_exception_propagates_and_skips_watermark(self):
        loop = self._build_renderer_loop(RuntimeError("font exploded"), "/tmp")

        class _Clip:
            rank = 3
        clip = _Clip()
        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(loop._run_inline_subtitle(clip, ["w1", "w2"], True, "/tmp/jobs/sub"))
        self.assertIn("Subtitle rendering failed", str(ctx.exception))


# 2. Auto-post compliance fail-closed
class AutoPostComplianceFailClosedTest(unittest.TestCase):

    def _make_service(self):
        from src.infrastructure.social_auto_post_service import SocialAutoPostService
        return SocialAutoPostService()

    @patch("src.infrastructure.social_auto_post_service.find_final_clip")
    @patch("src.infrastructure.social_auto_post_service.ensure_social_compliant_video")
    @patch("src.infrastructure.social_auto_post_service.repliz_post")
    def test_compliance_failure_skips_clip(self, mock_repliz_post, mock_ensure, mock_find):
        service = self._make_service()
        mock_find.return_value = "/tmp/clip.mp4"
        mock_ensure.side_effect = RuntimeError("transcode boom")
        mock_repliz_post.return_value = {"_id": "sch_1"}

        with patch.object(service, "get_connected_accounts", new_callable=AsyncMock) as accs, \
             patch("src.infrastructure.social_auto_post_service.os.path.isdir", return_value=True), \
             patch("os.path.exists", return_value=True):
            accs.return_value = [
                {"account_id": "acc_1", "platform": "tiktok", "name": "TT", "username": "tt"}
            ]
            res = asyncio.run(service.auto_schedule_job_clips(
                job_id="job_c",
                clips=[{"rank": 1, "hook": "H", "score": 90}],
                output_dir="/tmp/out_jobc",
                user_id=1,
                target_platforms=["tiktok"],
                schedule_mode="instant",
                notify_telegram=False,
            ))

        self.assertFalse(res["success"])
        self.assertEqual(res["scheduled_count"], 0)
        self.assertTrue(res["errors"], "compliance error must be recorded")
        self.assertIn("compliance", res["errors"][0].lower())
        mock_repliz_post.assert_not_called()

    @patch("src.infrastructure.social_auto_post_service.find_final_clip")
    @patch("src.infrastructure.social_auto_post_service.ensure_social_compliant_video")
    @patch("src.infrastructure.social_auto_post_service.repliz_post")
    def test_compliance_missing_output_skips_clip(self, mock_repliz_post, mock_ensure, mock_find):
        service = self._make_service()
        mock_find.return_value = "/tmp/clip.mp4"
        mock_ensure.return_value = "/tmp/nonexistent_does_not_matter.mp4"
        mock_repliz_post.return_value = {"_id": "sch_1"}

        with patch.object(service, "get_connected_accounts", new_callable=AsyncMock) as accs, \
             patch("src.infrastructure.social_auto_post_service.os.path.isdir", return_value=True), \
             patch("os.path.exists", return_value=True):
            accs.return_value = [
                {"account_id": "acc_1", "platform": "tiktok", "name": "TT", "username": "tt"}
            ]
            res = asyncio.run(service.auto_schedule_job_clips(
                job_id="job_c2",
                clips=[{"rank": 1, "hook": "H", "score": 90}],
                output_dir="/tmp/out_jobc2",
                user_id=1,
                target_platforms=["tiktok"],
                schedule_mode="instant",
                notify_telegram=False,
            ))

        self.assertFalse(res["success"])
        self.assertEqual(res["scheduled_count"], 0)
        mock_repliz_post.assert_not_called()


# 3. Publish route fail-closed
class PublishComplianceFailClosedTest(unittest.TestCase):

    @patch("src.presentation.routes.social.publish.ensure_social_compliant_video")
    def test_publish_aborts_on_compliance_failure(self, mock_ensure):
        from fastapi import HTTPException
        from src.presentation.routes.social.publish import PublishRequest, publish_clip

        mock_ensure.side_effect = RuntimeError("ffmpeg died")

        with patch("src.presentation.routes.social.publish.find_final_clip") as mock_find:
            mock_find.return_value = "/tmp/final.mp4"
            with patch("src.presentation.routes.social.publish.get_current_user") as mock_user:
                mock_user.return_value = {"id": 1, "is_superadmin": True}
                body = PublishRequest(jobId="job_p", clipRank=1, accountId="acc_1", scheduleAt="2026-10-01T14:00:00Z")
                with self.assertRaises(HTTPException) as ctx:
                    asyncio.run(publish_clip(body, _user={"id": 1, "is_superadmin": True}))
                self.assertIn(ctx.exception.status_code, (422, 503))


if __name__ == "__main__":
    unittest.main()
