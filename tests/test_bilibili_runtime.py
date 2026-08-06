import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from uploader.bilibili_uploader.runtime import (
    build_biliup_runtime_path,
    ensure_biliup_binary,
    resolve_bilibili_season_id,
    run_biliup_command,
)


class BiliupRuntimeTests(unittest.TestCase):
    def test_build_biliup_runtime_path_returns_platform_path(self):
        path = build_biliup_runtime_path("Windows")
        self.assertTrue(str(path).endswith("biliup.exe"))

    @patch("uploader.bilibili_uploader.runtime.fetch_latest_release")
    def test_ensure_biliup_binary_downloads_when_missing(self, mock_release):
        mock_release.return_value = {
            "tag_name": "v1.0.0",
            "asset_url": "https://example.invalid/biliup.exe",
            "asset_name": "biliup.exe",
        }
        with patch("uploader.bilibili_uploader.runtime.read_local_biliup_version", return_value=None):
            with patch("pathlib.Path.exists", return_value=False):
                with patch("uploader.bilibili_uploader.runtime.download_biliup_asset") as mock_download:
                    with patch("uploader.bilibili_uploader.runtime.write_local_biliup_version") as mock_write_version:
                        ensure_biliup_binary(force_check=True)
        mock_download.assert_called_once()
        mock_write_version.assert_called_once_with("v1.0.0")


class BilibiliSeasonResolutionTests(unittest.TestCase):
    def _write_account(self, path: Path) -> Path:
        account = {
            "cookie_info": {
                "cookies": [
                    {"name": "SESSDATA", "value": "abc", "expires": 0, "http_only": True, "secure": True, "same_site": "none"},
                    {"name": "bili_jct", "value": "xyz", "expires": 0, "http_only": True, "secure": True, "same_site": "none"},
                ],
                "domains": [".bilibili.com"],
            },
            "sso": [],
            "token_info": {"mid": 518800384},
            "platform": "bilibili",
        }
        path.write_text(__import__("json").dumps(account), encoding="utf-8")
        return path

    def _api_payload(self, seasons):
        return {"code": 0, "message": "OK", "data": {"seasons": seasons, "total": len(seasons)}}

    def test_resolve_season_id_by_exact_name(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            account = self._write_account(Path(td) / "account.json")
            payload = self._api_payload(
                [
                    {"season": {"id": 5626003, "title": "英语新闻【训练版】"}, "seasonStat": {}},
                    {"season": {"id": 8762246, "title": "英语新闻博客"}, "seasonStat": {}},
                ]
            )
            with patch("uploader.bilibili_uploader.runtime.requests.get") as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = payload
                result = resolve_bilibili_season_id(account, "英语新闻博客")
        self.assertEqual(result, 8762246)

    def test_resolve_season_id_raises_when_name_missing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            account = self._write_account(Path(td) / "account.json")
            payload = self._api_payload(
                [{"season": {"id": 8762246, "title": "英语新闻博客"}, "seasonStat": {}}]
            )
            with patch("uploader.bilibili_uploader.runtime.requests.get") as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = payload
                with self.assertRaises(RuntimeError) as ctx:
                    resolve_bilibili_season_id(account, "不存在的合集")
        self.assertIn("not found", str(ctx.exception))
        self.assertIn("英语新闻博客", str(ctx.exception))

    def test_resolve_season_id_raises_on_api_failure(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            account = self._write_account(Path(td) / "account.json")
            with patch("uploader.bilibili_uploader.runtime.requests.get") as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = {"code": -101, "message": "账号未登录"}
                with self.assertRaises(RuntimeError) as ctx:
                    resolve_bilibili_season_id(account, "英语新闻博客")
        self.assertIn("-101", str(ctx.exception))

    def test_resolve_season_id_raises_when_account_missing(self):
        with self.assertRaises(RuntimeError):
            resolve_bilibili_season_id(Path("/nonexistent/account.json"), "英语新闻博客")

    @patch("uploader.bilibili_uploader.runtime.fetch_latest_release")
    def test_ensure_biliup_binary_reuses_local_when_up_to_date(self, mock_release):
        mock_release.return_value = {
            "tag_name": "v1.0.0",
            "asset_url": "https://example.invalid/biliup.exe",
            "asset_name": "biliup.exe",
        }
        with patch("uploader.bilibili_uploader.runtime.read_local_biliup_version", return_value="v1.0.0"):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("uploader.bilibili_uploader.runtime.download_biliup_asset") as mock_download:
                    with patch("uploader.bilibili_uploader.runtime.write_local_biliup_version") as mock_write_version:
                        ensure_biliup_binary(force_check=True)
        mock_download.assert_not_called()
        mock_write_version.assert_not_called()

    @patch("uploader.bilibili_uploader.runtime.subprocess.run")
    @patch("uploader.bilibili_uploader.runtime.ensure_biliup_binary")
    def test_run_biliup_command_returns_completed_process(self, mock_ensure_binary, mock_run):
        mock_ensure_binary.return_value = build_biliup_runtime_path("Windows")
        mock_run.return_value = Mock(returncode=0, stdout="ok", stderr="")
        result = run_biliup_command(["login"])
        self.assertEqual(result.returncode, 0)

    @patch("uploader.bilibili_uploader.runtime.subprocess.run")
    @patch("uploader.bilibili_uploader.runtime.ensure_biliup_binary")
    def test_run_biliup_command_login_uses_interactive_stdio(self, mock_ensure_binary, mock_run):
        mock_ensure_binary.return_value = Path("C:/mock/biliup.exe")
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        run_biliup_command(["login"], interactive=True)
        _, kwargs = mock_run.call_args
        self.assertNotIn("capture_output", kwargs)
