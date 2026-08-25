import asyncio
import json
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, call, patch

import sau_cli
from utils.account_identity import AccountIdentity
from utils.browser_selector import BrowserTarget, resolve_browser_target, resolve_browser_targets


class BrowserSelectorPoolTests(unittest.TestCase):
    def test_pool_preserves_order_and_deduplicates_port(self):
        targets = [
            BrowserTarget("one", 9225, "http://127.0.0.1:9225"),
            BrowserTarget("two", 9226, "http://127.0.0.1:9226"),
            BrowserTarget("one", 9225, "http://127.0.0.1:9225"),
        ]
        with patch("utils.browser_selector.resolve_browser_target", side_effect=targets):
            result = resolve_browser_targets(["9225", "9226", "one"])
        self.assertEqual(result, targets[:2])

    def test_pool_rejects_conflicting_same_port_anchor(self):
        targets = [
            BrowserTarget("one", 9225, "http://127.0.0.1:9225"),
            BrowserTarget("other", 9225, "http://127.0.0.1:9925"),
        ]
        with patch("utils.browser_selector.resolve_browser_target", side_effect=targets):
            with self.assertRaisesRegex(RuntimeError, "conflicting"):
                resolve_browser_targets(["9225", "other"])


class BrowserCliParserTests(unittest.TestCase):
    def test_runtime_browser_flag_accepts_name_or_port(self):
        parser = sau_cli.build_parser()
        args = parser.parse_args(["youtube", "check", "--account", "creator", "--browser", "9225"])
        self.assertEqual(args.browser, "9225")

    def test_browser_pool_and_target_account_flags_are_available(self):
        parser = sau_cli.build_parser()
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            video_path.write_bytes(b"video")
            args = parser.parse_args([
                "bilibili", "upload-video", "--account", "creator", "--file", str(video_path),
                "--title", "标题", "--desc", "简介", "--tid", "1", "--browsers", "9225,9226",
                "--target-account", "526557505", "--task-id", "task-1",
            ])
        self.assertEqual(args.browsers, "9225,9226")
        self.assertEqual(args.target_account, "526557505")
        self.assertEqual(args.task_id, "task-1")

    def test_accounts_scan_parser_accepts_platforms(self):
        args = sau_cli.build_parser().parse_args([
            "accounts", "scan", "--browsers", "9225,9226", "--platforms", "douyin,youtube,bilibili"
        ])
        self.assertEqual(args.platform, "accounts")
        self.assertEqual(args.action, "scan")

    def test_explicit_browser_pool_and_cdp_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            sau_cli.build_parser().parse_args([
                "youtube", "check", "--account", "creator", "--browser", "9225", "--cdp-url", "http://127.0.0.1:9225"
            ])

    def test_bilibili_runtime_flags_are_available_for_login_check_and_upload(self):
        parser = sau_cli.build_parser()
        for action in ("login", "check"):
            args = parser.parse_args(["bilibili", action, "--account", "creator", "--browser", "9225"])
            self.assertEqual(args.browser, "9225")
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            video_path.write_bytes(b"video")
            args = parser.parse_args([
                "bilibili", "upload-video", "--account", "creator", "--file", str(video_path),
                "--title", "标题", "--desc", "简介", "--tid", "1", "--browser", "9225",
            ])
        self.assertEqual(args.browser, "9225")

    def test_build_parser_accepts_xiaohongshu_login(self):
        parser = sau_cli.build_parser()
        args = parser.parse_args(["xiaohongshu", "login", "--account", "creator"])
        self.assertEqual(args.platform, "xiaohongshu")
        self.assertEqual(args.action, "login")

    def test_douyin_upload_video_accepts_desc(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            video_path.write_bytes(b"video")

            parser = sau_cli.build_parser()
            args = parser.parse_args(
                [
                    "douyin",
                    "upload-video",
                    "--account",
                    "creator",
                    "--file",
                    str(video_path),
                    "--title",
                    "标题",
                    "--desc",
                    "视频简介",
                ]
            )

        self.assertEqual(args.desc, "视频简介")

    def test_douyin_upload_video_accepts_dual_thumbnail_aspects(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            landscape_path = Path(tmp_dir) / "landscape.png"
            portrait_path = Path(tmp_dir) / "portrait.png"
            video_path.write_bytes(b"video")
            landscape_path.write_bytes(b"image")
            portrait_path.write_bytes(b"image")

            parser = sau_cli.build_parser()
            args = parser.parse_args(
                [
                    "douyin",
                    "upload-video",
                    "--account",
                    "creator",
                    "--file",
                    str(video_path),
                    "--title",
                    "标题",
                    "--thumbnail-landscape",
                    str(landscape_path),
                    "--thumbnail-portrait",
                    str(portrait_path),
                ]
            )

        self.assertEqual(args.thumbnail_landscape, landscape_path)
        self.assertEqual(args.thumbnail_portrait, portrait_path)

    def test_tencent_upload_video_accepts_dual_thumbnail_aspects(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            landscape_path = Path(tmp_dir) / "landscape.png"
            portrait_path = Path(tmp_dir) / "portrait.png"
            video_path.write_bytes(b"video")
            landscape_path.write_bytes(b"image")
            portrait_path.write_bytes(b"image")

            parser = sau_cli.build_parser()
            args = parser.parse_args(
                [
                    "tencent",
                    "upload-video",
                    "--account",
                    "creator",
                    "--file",
                    str(video_path),
                    "--title",
                    "标题",
                    "--thumbnail-landscape",
                    str(landscape_path),
                    "--thumbnail-portrait",
                    str(portrait_path),
                ]
            )

        self.assertEqual(args.thumbnail_landscape, landscape_path)
        self.assertEqual(args.thumbnail_portrait, portrait_path)

    def test_kuaishou_upload_note_accepts_title_and_note(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "1.png"
            image_path.write_bytes(b"image")

            parser = sau_cli.build_parser()
            args = parser.parse_args(
                [
                    "kuaishou",
                    "upload-note",
                    "--account",
                    "creator",
                    "--images",
                    str(image_path),
                    "--title",
                    "图文标题",
                    "--note",
                    "图文正文",
                ]
            )

        self.assertEqual(args.title, "图文标题")
        self.assertEqual(args.note, "图文正文")

    def test_xiaohongshu_upload_video_defaults_to_headless(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            video_path.write_bytes(b"video")

            parser = sau_cli.build_parser()
            args = parser.parse_args(
                [
                    "xiaohongshu",
                    "upload-video",
                    "--account",
                    "creator",
                    "--file",
                    str(video_path),
                    "--title",
                    "视频标题",
                ]
            )

        self.assertTrue(args.headless)
        self.assertIsNone(args.cdp_url)

    def test_douyin_upload_video_accepts_agent_chrome_cdp_url(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            video_path.write_bytes(b"video")

            parser = sau_cli.build_parser()
            args = parser.parse_args(
                [
                    "douyin",
                    "upload-video",
                    "--account",
                    "creator",
                    "--file",
                    str(video_path),
                    "--title",
                    "视频标题",
                    "--cdp-url",
                    "http://127.0.0.1:9223",
                ]
            )

        self.assertEqual(args.cdp_url, "http://127.0.0.1:9223")

    def test_xiaohongshu_upload_note_accepts_headed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "1.png"
            image_path.write_bytes(b"image")

            parser = sau_cli.build_parser()
            args = parser.parse_args(
                [
                    "xiaohongshu",
                    "upload-note",
                    "--account",
                    "creator",
                    "--images",
                    str(image_path),
                    "--title",
                    "图文标题",
                    "--note",
                    "图文正文",
                    "--headed",
                ]
            )

        self.assertFalse(args.headless)


class BrowserCliDispatchTests(unittest.TestCase):
    def test_scan_continues_after_logged_out_and_error_items(self):
        targets = [BrowserTarget("one", 9225, "http://127.0.0.1:9225")]
        logged_in = AccountIdentity("youtube", True, "UC123", "Creator")
        logged_out = AccountIdentity("douyin", False, None, None)
        async def read_identity(platform, _target):
            if platform == "youtube":
                return logged_in
            if platform == "douyin":
                return logged_out
            raise RuntimeError("parser failed")

        args = Namespace(platform="accounts", action="scan", browsers="9225", platforms="douyin,youtube,bilibili")
        with patch("sau_cli.resolve_browser_targets", return_value=targets), patch(
            "sau_cli._read_platform_identity", new=read_identity
        ):
            with patch("builtins.print") as output:
                self.assertEqual(asyncio.run(sau_cli.dispatch(args)), 0)
        payload = json.loads(output.call_args.args[0])
        self.assertEqual([item["status"] for item in payload["items"]], ["interaction_required", "logged_in", "error"])

    def test_pool_router_requires_one_exact_target_match(self):
        targets = [
            BrowserTarget("one", 9225, "http://127.0.0.1:9225"),
            BrowserTarget("two", 9226, "http://127.0.0.1:9226"),
        ]
        identities = {
            9225: AccountIdentity("youtube", True, "UC1", "One"),
            9226: AccountIdentity("youtube", True, "UC2", "Two"),
        }
        async def read_identity(_platform, target):
            return identities[target.port]

        args = Namespace(platform="youtube", browsers="9225,9226", target_account="UC2", browser=None, cdp_url=None)
        with patch("sau_cli.resolve_browser_targets", return_value=targets), patch(
            "sau_cli._read_platform_identity", new=read_identity
        ):
            result = asyncio.run(sau_cli._resolve_upload_target(args))
        self.assertEqual(result.port, 9226)

    def test_pool_router_rejects_multiple_targets_without_selector(self):
        args = Namespace(platform="youtube", browsers="9225,9226", target_account=None, browser=None, cdp_url=None)
        with patch("sau_cli.resolve_browser_targets", return_value=[
            BrowserTarget("one", 9225, "http://127.0.0.1:9225"),
            BrowserTarget("two", 9226, "http://127.0.0.1:9226"),
        ]):
            with self.assertRaisesRegex(ValueError, "target-account"):
                asyncio.run(sau_cli._resolve_upload_target(args))
    def test_cdp_checks_do_not_require_cookie_files(self):
        with patch("sau_cli.resolve_account_file", return_value=Path("/missing/account.json")), patch(
            "sau_cli.douyin_cookie_auth", new=AsyncMock(return_value=True)
        ) as douyin_auth, patch("sau_cli.youtube_cookie_auth", new=AsyncMock(return_value=True)) as youtube_auth:
            self.assertTrue(asyncio.run(sau_cli.check_douyin_account("creator", "http://127.0.0.1:9225")))
            self.assertTrue(asyncio.run(sau_cli.check_youtube_account("creator", "http://127.0.0.1:9225")))
        douyin_auth.assert_awaited_once()
        youtube_auth.assert_awaited_once()

    def test_dispatch_resolves_browser_and_passes_cdp_url(self):
        args = Namespace(platform="youtube", action="check", account="creator", browser="9225", cdp_url=None)
        target = BrowserTarget("managed", 9225, "http://127.0.0.1:9225")
        with patch("sau_cli.resolve_browser_target", return_value=target) as resolve, patch(
            "sau_cli.check_youtube_account", new=AsyncMock(return_value=True)
        ) as check:
            self.assertEqual(asyncio.run(sau_cli.dispatch(args)), 0)
        resolve.assert_called_once_with("9225", None)
        check.assert_awaited_once_with("creator", cdp_url="http://127.0.0.1:9225")

    def test_dispatch_xiaohongshu_check_prints_valid(self):
        args = Namespace(platform="xiaohongshu", action="check", account="creator")
        with patch("sau_cli.check_xiaohongshu_account", new=AsyncMock(return_value=True)):
            code = asyncio.run(sau_cli.dispatch(args))
        self.assertEqual(code, 0)

    def test_dispatch_douyin_upload_note_uses_new_request_fields(self):
        args = Namespace(
            platform="douyin",
            action="upload-note",
            account="creator",
            images=[Path("1.png")],
            title="图文标题",
            note="图文正文",
            notef="",
            tags="测试,图文",
            schedule=0,
            bgm="",
            debug=False,
            headless=True,
        )
        with patch("sau_cli.upload_note", new=AsyncMock()) as mock_upload:
            asyncio.run(sau_cli.dispatch(args))

        request = mock_upload.await_args.args[0]
        self.assertEqual(request.title, "图文标题")
        self.assertEqual(request.note, "图文正文")

    def test_dispatch_douyin_upload_video_uses_dual_thumbnail_request_fields(self):
        args = Namespace(
            platform="douyin",
            action="upload-video",
            account="creator",
            file=Path("demo.mp4"),
            title="视频标题",
            desc="视频简介",
            tags="测试,视频",
            schedule=0,
            thumbnail=None,
            thumbnail_landscape=Path("landscape.png"),
            thumbnail_portrait=Path("portrait.png"),
            product_link="",
            product_title="",
            debug=False,
            headless=True,
            declaration="无需添加自主声明",
            collection=None,
        )
        with patch("sau_cli.upload_video", new=AsyncMock()) as mock_upload:
            asyncio.run(sau_cli.dispatch(args))

        request = mock_upload.await_args.args[0]
        self.assertEqual(request.thumbnail_landscape_file, Path("landscape.png"))
        self.assertEqual(request.thumbnail_portrait_file, Path("portrait.png"))

    def test_dispatch_tencent_upload_video_uses_dual_thumbnail_request_fields(self):
        args = Namespace(
            platform="tencent",
            action="upload-video",
            account="creator",
            file=Path("demo.mp4"),
            title="视频标题",
            desc="视频简介",
            tags="测试,视频",
            schedule=0,
            thumbnail=None,
            thumbnail_landscape=Path("landscape.png"),
            thumbnail_portrait=Path("portrait.png"),
            short_title=None,
            category=None,
            draft=False,
            debug=False,
            headless=True,
        )
        with patch("sau_cli.upload_tencent_video", new=AsyncMock()) as mock_upload:
            asyncio.run(sau_cli.dispatch(args))

        request = mock_upload.await_args.args[0]
        self.assertEqual(request.thumbnail_landscape_file, Path("landscape.png"))
        self.assertEqual(request.thumbnail_portrait_file, Path("portrait.png"))

    def test_dispatch_xiaohongshu_upload_video_uses_headed_request(self):
        args = Namespace(
            platform="xiaohongshu",
            action="upload-video",
            account="creator",
            file=Path("demo.mp4"),
            title="视频标题",
            desc="视频简介",
            tags="测试,视频",
            schedule=0,
            thumbnail=None,
            debug=False,
            headless=False,
            cdp_url="http://127.0.0.1:9223",
        )
        with patch("sau_cli.resolve_browser_target", return_value=BrowserTarget("managed", 9223, "http://127.0.0.1:9223")), patch("sau_cli.upload_xiaohongshu_video", new=AsyncMock()) as mock_upload:
            asyncio.run(sau_cli.dispatch(args))

        request = mock_upload.await_args.args[0]
        self.assertEqual(request.title, "视频标题")
        self.assertEqual(request.description, "视频简介")
        self.assertFalse(request.headless)
        self.assertEqual(request.cdp_url, "http://127.0.0.1:9223")

    def test_dispatch_xiaohongshu_upload_note_uses_headless_request(self):
        args = Namespace(
            platform="xiaohongshu",
            action="upload-note",
            account="creator",
            images=[Path("1.png"), Path("2.png")],
            title="图文标题",
            note="图文正文",
            tags="测试,图文",
            schedule=0,
            debug=False,
            headless=True,
        )
        with patch("sau_cli.upload_xiaohongshu_note", new=AsyncMock()) as mock_upload:
            asyncio.run(sau_cli.dispatch(args))

        request = mock_upload.await_args.args[0]
        self.assertEqual(request.title, "图文标题")
        self.assertEqual(request.note, "图文正文")
        self.assertTrue(request.headless)
        self.assertEqual(len(request.image_files), 2)


class YouTubeAgentChromeCliTests(unittest.TestCase):
    def test_youtube_upload_accepts_no_submit_and_cdp_url(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            video_path.write_bytes(b"video")
            args = sau_cli.build_parser().parse_args(
                [
                    "youtube", "upload-video", "--account", "watermelon",
                    "--file", str(video_path), "--title", "smoke",
                    "--no-submit", "--cdp-url", "http://127.0.0.1:9223",
                ]
            )

        self.assertFalse(args.submit)
        self.assertEqual(args.cdp_url, "http://127.0.0.1:9223")


class BrowserSelectorTests(unittest.TestCase):
    def test_resolve_name_uses_fleet_resolve(self):
        audit = {"registered": [{"name": "managed", "port": 9225, "status": "running", "health": "ok", "problems": []}]}
        result = {"name": "managed", "port": 9225, "cdp_url": "http://127.0.0.1:9225", "status": "running", "health": "ok"}
        with patch("utils.browser_selector._fleet_json", side_effect=[audit, result]) as run:
            self.assertEqual(resolve_browser_target("managed"), BrowserTarget("managed", 9225, "http://127.0.0.1:9225"))
        self.assertEqual(run.call_count, 2)

    def test_resolve_port_audits_then_rechecks_name(self):
        audit = {"registered": [{"name": "managed", "port": 9225, "status": "running", "health": "ok", "problems": []}]}
        resolved = {"name": "managed", "port": 9225, "cdp_url": "http://127.0.0.1:9225", "status": "running", "health": "ok"}
        responses = [Namespace(returncode=0, stdout=json.dumps(audit), stderr=""), Namespace(returncode=0, stdout=json.dumps(resolved), stderr="")]
        with patch("utils.browser_selector.subprocess.run", side_effect=responses):
            self.assertEqual(resolve_browser_target("9225"), BrowserTarget("managed", 9225, "http://127.0.0.1:9225"))

    def test_resolve_rejects_unhealthy_or_conflicting_target(self):
        audit = {"registered": [{"name": "managed", "port": 9225, "status": "running", "health": "bad", "problems": ["mismatch"]}]}
        with patch("utils.browser_selector.subprocess.run", return_value=Namespace(returncode=0, stdout=json.dumps(audit), stderr="")):
            with self.assertRaises(RuntimeError):
                resolve_browser_target("9225")

    def test_legacy_cdp_url_accepts_localhost_and_rejects_remote(self):
        with patch("utils.browser_selector.subprocess.run", side_effect=OSError("mocked")):
            with self.assertRaises(RuntimeError):
                resolve_browser_target(None, "http://127.0.0.1:9333")
        with self.assertRaises(ValueError):
            resolve_browser_target(None, "https://example.com:9333")

    def test_legacy_cdp_url_rejects_registered_unhealthy_target(self):
        audit = {"registered": [{"name": "managed", "port": 9225, "status": "running", "health": "bad", "problems": ["profile mismatch"]}]}
        with patch("utils.browser_selector.subprocess.run", return_value=Namespace(returncode=0, stdout=json.dumps(audit), stderr="")):
            with self.assertRaises(RuntimeError):
                resolve_browser_target(None, "http://127.0.0.1:9225")

    def test_offline_name_starts_then_resolves_registered_browser(self):
        audit = {"registered": [{"name": "managed", "port": 9225, "status": "stopped", "health": "ok", "problems": []}]}
        resolved = {"name": "managed", "port": 9225, "cdp_url": "http://127.0.0.1:9225", "status": "running", "health": "ok"}
        with patch("utils.browser_selector._fleet_json", side_effect=[audit, {"status": "running"}, resolved]) as fleet:
            self.assertEqual(resolve_browser_target("managed"), BrowserTarget("managed", 9225, "http://127.0.0.1:9225"))
        self.assertEqual([call.args for call in fleet.call_args_list], [
            ("audit",), ("start", "--name", "managed"), ("resolve", "--name", "managed")
        ])

    def test_offline_port_starts_then_resolves_registered_browser(self):
        audit = {"registered": [{"name": "managed", "port": 9225, "status": "stopped", "health": "ok", "problems": []}]}
        resolved = {"name": "managed", "port": 9225, "cdp_url": "http://127.0.0.1:9225", "status": "running", "health": "ok"}
        with patch("utils.browser_selector._fleet_json", side_effect=[audit, {"status": "running"}, resolved]) as fleet:
            self.assertEqual(resolve_browser_target("9225"), BrowserTarget("managed", 9225, "http://127.0.0.1:9225"))
        self.assertEqual(fleet.call_args_list[1].args, ("start", "--name", "managed"))

    def test_registered_cdp_url_starts_without_accepting_unmanaged_port(self):
        audit = {"registered": [{"name": "managed", "port": 9225, "status": "stopped", "health": "ok", "problems": []}]}
        resolved = {"name": "managed", "port": 9225, "cdp_url": "http://127.0.0.1:9225", "status": "running", "health": "ok"}
        with patch("utils.browser_selector._fleet_json", side_effect=[audit, {"status": "running"}, resolved]):
            self.assertEqual(resolve_browser_target(None, "http://127.0.0.1:9225"), BrowserTarget("managed", 9225, "http://127.0.0.1:9225"))
        with patch("utils.browser_selector._fleet_json", return_value={"registered": []}):
            with self.assertRaises(RuntimeError):
                resolve_browser_target(None, "http://127.0.0.1:9333")

    def test_running_browser_does_not_call_start(self):
        audit = {"registered": [{"name": "managed", "port": 9225, "status": "running", "health": "ok", "problems": []}]}
        resolved = {"name": "managed", "port": 9225, "cdp_url": "http://127.0.0.1:9225", "status": "running", "health": "ok"}
        with patch("utils.browser_selector._fleet_json", side_effect=[audit, resolved]) as fleet:
            resolve_browser_target("managed")
        self.assertEqual([call.args for call in fleet.call_args_list], [("audit",), ("resolve", "--name", "managed")])

    def test_conflict_and_duplicate_registration_fail_closed_without_create(self):
        conflict = {"registered": [{"name": "managed", "port": 9225, "status": "stopped", "health": "conflict", "problems": ["port_conflict"]}]}
        with patch("utils.browser_selector._fleet_json", return_value=conflict) as fleet:
            with self.assertRaises(RuntimeError):
                resolve_browser_target("9225")
        self.assertEqual(fleet.call_args_list[0].args, ("audit",))

        duplicate = {"registered": [
            {"name": "one", "port": 9225, "status": "stopped", "health": "ok", "problems": []},
            {"name": "two", "port": 9225, "status": "stopped", "health": "ok", "problems": []},
        ]}
        with patch("utils.browser_selector._fleet_json", return_value=duplicate) as fleet:
            with self.assertRaises(RuntimeError):
                resolve_browser_target("9225")
        self.assertEqual(fleet.call_args_list[0].args, ("audit",))

    def test_start_failure_does_not_create_or_resolve(self):
        audit = {"registered": [{"name": "managed", "port": 9225, "status": "stopped", "health": "ok", "problems": []}]}
        with patch("utils.browser_selector._fleet_json", side_effect=[audit, RuntimeError("start failed")]) as fleet:
            with self.assertRaises(RuntimeError):
                resolve_browser_target("managed")
        self.assertEqual([call.args for call in fleet.call_args_list], [("audit",), ("start", "--name", "managed")])

    def test_multiple_browser_targets_keep_input_order(self):
        resolved = {
            "one": {"name": "one", "port": 9225},
            "two": {"name": "two", "port": 9226},
        }
        def fleet(*args):
            if args == ("audit",):
                return {"registered": [
                    {"name": "one", "port": 9225, "status": "running", "health": "ok", "problems": []},
                    {"name": "two", "port": 9226, "status": "running", "health": "ok", "problems": []},
                ]}
            item = resolved[args[-1]]
            return {**item, "cdp_url": f"http://127.0.0.1:{item['port']}", "status": "running", "health": "ok"}
        with patch("utils.browser_selector._fleet_json", side_effect=fleet):
            result = resolve_browser_targets(["9226", "9225"])
        self.assertEqual([target.port for target in result], [9226, 9225])

    def test_youtube_check_accepts_agent_chrome_cdp_url(self):
        args = sau_cli.build_parser().parse_args(
            ["youtube", "check", "--account", "watermelon", "--cdp-url", "http://127.0.0.1:9223"]
        )
        self.assertEqual(args.cdp_url, "http://127.0.0.1:9223")

    def test_dispatch_youtube_upload_passes_no_submit_to_request(self):
        args = Namespace(
            platform="youtube", action="upload-video", account="watermelon",
            file=Path("demo.mp4"), title="smoke", desc="", tags="",
            thumbnail=None, playlist=None, visibility="private", debug=False,
            headless=False, cdp_url="http://127.0.0.1:9223", submit=False,
        )
        with patch("sau_cli.resolve_browser_target", return_value=BrowserTarget("managed", 9223, "http://127.0.0.1:9223")), patch("sau_cli.upload_youtube_video", new=AsyncMock()) as mock_upload:
            asyncio.run(sau_cli.dispatch(args))

        request = mock_upload.await_args.args[0]
        self.assertFalse(request.submit)
        self.assertEqual(request.cdp_url, "http://127.0.0.1:9223")
    def test_upload_youtube_video_passes_no_submit_to_uploader(self):
        request = sau_cli.YouTubeVideoUploadRequest(
            account_name="watermelon", video_file=Path("demo.mp4"), title="smoke",
            description="", tags=[], cdp_url="http://127.0.0.1:9223", submit=False,
        )
        with patch("sau_cli.youtube_setup", new=AsyncMock(return_value=True)), patch("sau_cli.YouTubeVideo") as mock_app:
            mock_app.return_value.main = AsyncMock()
            asyncio.run(sau_cli.upload_youtube_video(request))

        self.assertFalse(mock_app.call_args.kwargs["submit"])


class YouTubeScheduleCliTests(unittest.TestCase):
    def test_youtube_upload_accepts_schedule_and_explicit_timezone(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            video_path.write_bytes(b"video")
            args = sau_cli.build_parser().parse_args(
                [
                    "youtube", "upload-video", "--account", "watermelon",
                    "--file", str(video_path), "--title", "scheduled smoke",
                    "--schedule", "2099-08-02 06:00", "--timezone", "Asia/Shanghai",
                ]
            )

        self.assertEqual(args.schedule, datetime(2099, 8, 2, 6, 0))
        self.assertEqual(args.timezone, "Asia/Shanghai")

    def test_youtube_schedule_and_no_submit_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            video_path.write_bytes(b"video")
            with self.assertRaises(SystemExit):
                sau_cli.build_parser().parse_args(
                    [
                        "youtube", "upload-video", "--account", "watermelon",
                        "--file", str(video_path), "--title", "scheduled smoke",
                        "--schedule", "2099-08-02 06:00", "--no-submit",
                    ]
                )

    def test_dispatch_youtube_schedule_passes_request_fields(self):
        args = Namespace(
            platform="youtube", action="upload-video", account="watermelon",
            file=Path("demo.mp4"), title="scheduled smoke", desc="", tags="",
            thumbnail=None, playlist=None, visibility="public", debug=False,
            headless=False, cdp_url="http://127.0.0.1:9223", submit=True,
            schedule=datetime(2099, 8, 2, 6, 0), timezone="Asia/Shanghai",
        )
        with patch("sau_cli.resolve_browser_target", return_value=BrowserTarget("managed", 9223, "http://127.0.0.1:9223")), patch("sau_cli.upload_youtube_video", new=AsyncMock(return_value={"visibility": "scheduled"})) as mock_upload:
            asyncio.run(sau_cli.dispatch(args))

        request = mock_upload.await_args.args[0]
        self.assertEqual(request.schedule, datetime(2099, 8, 2, 6, 0))
        self.assertEqual(request.timezone, "Asia/Shanghai")

    def test_dispatch_youtube_recoverable_result_prints_json_and_returns_failure(self):
        args = Namespace(
            platform="youtube", action="upload-video", account="watermelon",
            file=Path("demo.mp4"), title="scheduled smoke", desc="", tags="",
            thumbnail=None, playlist=None, visibility="public", debug=False,
            headless=False, cdp_url=None, browser=None, browsers=None, submit=True,
            schedule=datetime(2099, 8, 2, 6, 0), timezone="Asia/Shanghai",
            target_account=None,
        )
        result = {
            "status": "interaction_required", "platform": "youtube",
            "reason": "final_schedule_button_missing", "recoverable": True,
            "submitted": False, "videoId": "QMiJvZPJJv0",
            "publishUrl": "https://www.youtube.com/watch?v=QMiJvZPJJv0",
        }
        with patch("sau_cli.upload_youtube_video", new=AsyncMock(return_value=result)), patch(
            "builtins.print"
        ) as output:
            self.assertEqual(asyncio.run(sau_cli.dispatch(args)), 1)
        self.assertEqual(json.loads(output.call_args.args[0]), result)


if __name__ == "__main__":
    unittest.main()
