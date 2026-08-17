import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sau_cli import (
    YouTubeVideoUploadRequest,
    assert_video_duration_within_limit,
    probe_video_duration_seconds,
    upload_youtube_video,
)


def _subprocess_result(stdout: str, returncode: int = 0):
    return SimpleNamespace(stdout=stdout, returncode=returncode)


class ProbeVideoDurationTests(unittest.TestCase):
    def test_probe_parses_ffprobe_seconds_output(self):
        with patch("sau_cli.subprocess.run", return_value=_subprocess_result("1000.470000\n")):
            duration = probe_video_duration_seconds(Path("/tmp/fake.mp4"))
            self.assertIsInstance(duration, float)
            self.assertEqual(round(duration, 2), 1000.47)

    def test_probe_returns_none_when_ffprobe_missing(self):
        with patch("sau_cli.subprocess.run", side_effect=FileNotFoundError("ffprobe")):
            self.assertIsNone(probe_video_duration_seconds(Path("/tmp/fake.mp4")))

    def test_probe_returns_none_on_nonzero_exit(self):
        with patch("sau_cli.subprocess.run", return_value=_subprocess_result("", returncode=1)):
            self.assertIsNone(probe_video_duration_seconds(Path("/tmp/fake.mp4")))

    def test_probe_returns_none_on_unparseable_output(self):
        with patch("sau_cli.subprocess.run", return_value=_subprocess_result("N/A\n")):
            self.assertIsNone(probe_video_duration_seconds(Path("/tmp/fake.mp4")))


class DurationLimitTests(unittest.TestCase):
    def test_over_limit_raises_before_upload(self):
        with patch(
            "sau_cli.probe_video_duration_seconds", return_value=1000.47
        ), self.assertRaisesRegex(ValueError, "超过账号上传上限"):
            assert_video_duration_within_limit(Path("/tmp/long.mp4"), 900)

    def test_within_limit_passes(self):
        with patch("sau_cli.probe_video_duration_seconds", return_value=120.5):
            self.assertEqual(
                assert_video_duration_within_limit(Path("/tmp/short.mp4"), 900), 120.5
            )

    def test_unprobeable_file_passes_with_warning(self):
        with patch("sau_cli.probe_video_duration_seconds", return_value=None):
            self.assertIsNone(
                assert_video_duration_within_limit(Path("/tmp/unknown.mp4"), 900)
            )


class YoutubeCliDurationGuardTests(unittest.TestCase):
    def _request(self, temp_dir: str) -> YouTubeVideoUploadRequest:
        video = Path(temp_dir) / "long.mp4"
        video.write_bytes(b"video")
        return YouTubeVideoUploadRequest(
            account_name="shuimitao-english",
            video_file=video,
            title="hello",
            description="",
            tags=[],
            visibility="public",
            submit=True,
        )

    def test_upload_youtube_video_aborts_before_account_setup_when_over_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            request = self._request(temp_dir)
            with patch(
                "sau_cli.probe_video_duration_seconds", return_value=1000.47
            ), patch("sau_cli.resolve_account_file") as mock_account, patch(
                "sau_cli.youtube_setup", new=AsyncMock()
            ) as mock_setup:
                with self.assertRaisesRegex(ValueError, "超过账号上传上限"):
                    asyncio.run(upload_youtube_video(request))
            mock_account.assert_not_called()
            mock_setup.assert_not_awaited()

    def test_upload_youtube_video_aborts_before_account_setup_when_default_cap_exceeded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            request = self._request(temp_dir)
            with patch(
                "sau_cli.assert_video_duration_within_limit", side_effect=ValueError("时长超限")
            ), patch("sau_cli.resolve_account_file") as mock_account, patch(
                "sau_cli.youtube_setup", new=AsyncMock()
            ) as mock_setup:
                with self.assertRaisesRegex(ValueError, "时长超限"):
                    asyncio.run(upload_youtube_video(request))
            mock_account.assert_not_called()
            mock_setup.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()