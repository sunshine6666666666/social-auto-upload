import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from uploader.bilibili_uploader.runtime import (
    _bilibili_identity_from_observation,
    _exchange_bilibili_web_cookies,
    build_biliup_runtime_path,
    ensure_biliup_binary,
    extract_bilibili_dom_identity,
    export_bilibili_cdp_account,
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


class BilibiliCdpExportTests(unittest.TestCase):
    @staticmethod
    def _login_info(mid, cookies):
        return {
            "cookie_info": {"cookies": cookies, "domains": [".bilibili.com"]},
            "token_info": {
                "access_token": "fake-access",
                "expires_in": 3600,
                "mid": mid,
                "refresh_token": "fake-refresh",
            },
            "platform": "BiliTV",
            "sso": [],
        }

    def _page(self, nav):
        class Page:
            url = "https://member.bilibili.com/platform/home"

            async def goto(self, *args, **kwargs):
                return None

            async def evaluate(self, *_args):
                return nav

        return Page()

    def _context(self, page, cookies):
        class Context:
            async def new_page(self):
                return page

            async def cookies(self, *_args):
                return cookies

        return Context()

    def test_export_writes_biliup_json_and_identity(self):
        from types import SimpleNamespace

        nav = {"code": 0, "data": {"isLogin": True, "mid": 518800384, "uname": "creator"}}
        cookies = [
            {"name": "SESSDATA", "value": "fake-sess", "domain": ".bilibili.com", "path": "/", "expires": 0, "httpOnly": True, "secure": True, "sameSite": "Lax"},
            {"name": "bili_jct", "value": "fake-csrf", "domain": ".bilibili.com", "path": "/", "expires": 0, "httpOnly": True, "secure": True, "sameSite": "Lax"},
        ]
        page = self._page(nav)
        context = self._context(page, cookies)
        session = SimpleNamespace(context=context, close=AsyncMock())
        with tempfile.TemporaryDirectory() as td, patch(
            "uploader.bilibili_uploader.runtime.async_playwright"
        ) as playwright, patch(
            "uploader.bilibili_uploader.runtime.open_browser_session", new=AsyncMock(return_value=session)
        ), patch(
            "uploader.bilibili_uploader.runtime._exchange_bilibili_web_cookies",
            return_value=self._login_info(518800384, cookies),
        ):
            playwright.return_value.__aenter__ = AsyncMock(return_value=object())
            playwright.return_value.__aexit__ = AsyncMock(return_value=None)
            target = SimpleNamespace(name="managed", port=9225)
            path = Path(td) / "account.json"
            identity = asyncio.run(export_bilibili_cdp_account("http://127.0.0.1:9225", path, target))
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(identity.stable_id, "518800384")
        self.assertEqual(payload["token_info"]["mid"], 518800384)
        self.assertEqual(payload["platform"], "BiliTV")
        self.assertEqual({item["name"] for item in payload["cookie_info"]["cookies"]}, {"SESSDATA", "bili_jct"})
        self.assertNotIn("fake-sess", str(identity.to_dict()))

    def test_web_cookie_exchange_returns_bilitv_credentials_for_same_mid(self):
        cookies = [
            {"name": "SESSDATA", "value": "fake-sess"},
            {"name": "bili_jct", "value": "fake-csrf"},
        ]
        responses = []
        for payload in (
            {"code": 0, "data": {"auth_code": "auth-code"}},
            {"code": 0, "data": {}},
            {"code": 0, "data": self._login_info(526557505, cookies)},
        ):
            response = Mock()
            response.json.return_value = payload
            responses.append(response)
        session = Mock()
        session.post.side_effect = responses
        with patch("uploader.bilibili_uploader.runtime.requests.Session", return_value=session):
            result = _exchange_bilibili_web_cookies(cookies, 526557505)
        self.assertEqual(result["platform"], "BiliTV")
        self.assertEqual(result["token_info"]["mid"], 526557505)
        self.assertEqual(session.post.call_count, 3)

    def test_web_cookie_exchange_ignores_same_named_non_bilibili_cookies(self):
        cookies = [
            {"name": "SESSDATA", "value": "wrong", "domain": ".example.com"},
            {"name": "SESSDATA", "value": "right", "domain": ".bilibili.com"},
            {"name": "bili_jct", "value": "csrf", "domain": ".bilibili.com"},
        ]
        response = Mock()
        response.json.return_value = {"code": -1}
        session = Mock()
        session.post.return_value = response
        with patch("uploader.bilibili_uploader.runtime.requests.Session", return_value=session):
            with self.assertRaises(RuntimeError):
                _exchange_bilibili_web_cookies(cookies, 1)
        self.assertNotIn("wrong", str(session.post.call_args_list))

    def test_export_failure_does_not_overwrite_existing_file(self):
        from types import SimpleNamespace

        page = self._page({"code": 0, "data": {"isLogin": False, "mid": 0, "uname": ""}})
        context = self._context(page, [])
        session = SimpleNamespace(context=context, close=AsyncMock())
        with tempfile.TemporaryDirectory() as td, patch(
            "uploader.bilibili_uploader.runtime.async_playwright"
        ) as playwright, patch(
            "uploader.bilibili_uploader.runtime.open_browser_session", new=AsyncMock(return_value=session)
        ):
            playwright.return_value.__aenter__ = AsyncMock(return_value=object())
            playwright.return_value.__aexit__ = AsyncMock(return_value=None)
            path = Path(td) / "account.json"
            path.write_text('{"old": true}', encoding="utf-8")
            with self.assertRaises(RuntimeError):
                asyncio.run(export_bilibili_cdp_account("http://127.0.0.1:9225", path, SimpleNamespace(name="managed", port=9225)))
            self.assertEqual(path.read_text(encoding="utf-8"), '{"old": true}')

    def test_visible_cached_dom_cannot_override_logged_out_nav(self):
        from types import SimpleNamespace

        class Locator:
            async def inner_text(self):
                return "Stella英语听力磨耳朵 正式会员"

            async def evaluate_all(self, _script):
                return ["https://space.bilibili.com/526557505"]

        page = self._page({"code": -101, "data": {"isLogin": False, "mid": 0}})
        page.locator = lambda _selector: Locator()
        session = SimpleNamespace(context=self._context(page, []), close=AsyncMock())
        with tempfile.TemporaryDirectory() as td, patch(
            "uploader.bilibili_uploader.runtime.async_playwright"
        ) as playwright, patch(
            "uploader.bilibili_uploader.runtime.open_browser_session", new=AsyncMock(return_value=session)
        ):
            playwright.return_value.__aenter__ = AsyncMock(return_value=object())
            playwright.return_value.__aexit__ = AsyncMock(return_value=None)
            path = Path(td) / "account.json"
            with self.assertRaisesRegex(RuntimeError, "freshly authenticated"):
                asyncio.run(export_bilibili_cdp_account("http://127.0.0.1:9225", path))
            self.assertFalse(path.exists())

    def test_observed_logged_out_nav_is_interaction_required_even_with_cached_dom(self):
        identity = _bilibili_identity_from_observation(
            "个人中心\nCached creator\n正式会员",
            ["https://space.bilibili.com/526557505"],
            {"code": -101, "data": {"isLogin": False, "mid": 0, "uname": ""}},
        )
        self.assertFalse(identity.logged_in)
        self.assertIsNone(identity.stable_id)

    def test_account_home_dom_extracts_visible_name_and_space_uid(self):
        uid, name = extract_bilibili_dom_identity(
            "个人中心\n首页\n大会员\nStella英语听力磨耳朵 正式会员",
            ["https://space.bilibili.com/526557505"],
        )
        self.assertEqual(uid, "526557505")
        self.assertEqual(name, "Stella英语听力磨耳朵")

    def test_account_home_dom_ignores_unrelated_deep_space_link(self):
        uid, _ = extract_bilibili_dom_identity(
            "Stella英语听力磨耳朵 正式会员",
            [
                "https://space.bilibili.com/526557505/",
                "https://space.bilibili.com/6823116#/album",
            ],
        )
        self.assertEqual(uid, "526557505")

    def test_account_home_dom_uses_unique_majority_profile_uid(self):
        uid, _ = extract_bilibili_dom_identity(
            "Stella英语听力磨耳朵 正式会员",
            [
                "https://space.bilibili.com/526557505",
                "https://space.bilibili.com/526557505/",
                "https://space.bilibili.com/9",
            ],
        )
        self.assertEqual(uid, "526557505")

    def test_account_home_dom_conflicting_space_uids_block(self):
        with self.assertRaisesRegex(RuntimeError, "conflicting"):
            extract_bilibili_dom_identity(
                "个人中心\nStella英语听力磨耳朵",
                ["https://space.bilibili.com/526557505", "https://space.bilibili.com/9"],
            )

    def test_export_blocks_when_dom_and_api_uids_conflict(self):
        class Locator:
            async def inner_text(self):
                return "个人中心\nStella英语听力磨耳朵"

            async def evaluate_all(self, _script):
                return ["https://space.bilibili.com/526557505"]

        class Page:
            url = "https://account.bilibili.com/account/home"

            async def goto(self, *_args, **_kwargs):
                return None

            def locator(self, selector):
                return Locator()

            async def evaluate(self, *_args):
                return {"code": 0, "data": {"isLogin": True, "mid": 9, "uname": "other"}}

        cookies = [
            {"name": "SESSDATA", "value": "secret-one"},
            {"name": "bili_jct", "value": "secret-two"},
        ]
        page = Page()
        context = self._context(page, cookies)
        session = __import__("types").SimpleNamespace(context=context, close=AsyncMock())
        with tempfile.TemporaryDirectory() as td, patch(
            "uploader.bilibili_uploader.runtime.async_playwright"
        ) as playwright, patch(
            "uploader.bilibili_uploader.runtime.open_browser_session", new=AsyncMock(return_value=session)
        ):
            playwright.return_value.__aenter__ = AsyncMock(return_value=object())
            playwright.return_value.__aexit__ = AsyncMock(return_value=None)
            path = Path(td) / "account.json"
            with self.assertRaisesRegex(RuntimeError, "conflict"):
                asyncio.run(export_bilibili_cdp_account("http://127.0.0.1:9225", path))
            self.assertFalse(path.exists())
