import asyncio
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import sau_cli
from utils.account_identity import AccountIdentity


class BilibiliCliTests(unittest.TestCase):
    def test_bilibili_account_files_use_fixed_external_directory_and_account_key(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            sau_cli.os.environ,
            {"SAU_BILIBILI_ACCOUNT_DIR": temp_dir},
        ):
            first = sau_cli.resolve_account_file("bilibili", "shuimitao-english")
            second = sau_cli.resolve_account_file("bilibili", "stella-english")

        self.assertEqual(first, Path(temp_dir) / "shuimitao-english.json")
        self.assertEqual(second, Path(temp_dir) / "stella-english.json")
        self.assertNotEqual(first, second)

    def test_build_parser_accepts_bilibili_login(self):
        parser = sau_cli.build_parser()
        args = parser.parse_args(["bilibili", "login", "--account", "creator"])
        self.assertEqual(args.platform, "bilibili")
        self.assertEqual(args.action, "login")

    def test_build_parser_requires_tid_for_upload_video(self):
        parser = sau_cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "bilibili",
                    "upload-video",
                    "--account",
                    "creator",
                    "--file",
                    "demo.mp4",
                    "--title",
                    "hello",
                    "--desc",
                    "hello",
                ]
            )

    def test_dispatch_bilibili_check_prints_valid(self):
        args = Namespace(platform="bilibili", action="check", account="creator")
        with patch("sau_cli.check_bilibili_account", new=AsyncMock(return_value=True)):
            code = asyncio.run(sau_cli.dispatch(args))
        self.assertEqual(code, 0)

    def test_check_bilibili_with_cdp_renews_without_reexporting(self):
        identity = AccountIdentity(
            platform="bilibili", logged_in=True, stable_id="518800384",
            display_name="水蜜桃英语", profile_url=None,
            browser_name="SAU-自媒体运营-2号-9226", cdp_port=9226, extra={},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            account_file = Path(temp_dir) / "shuimitao-english.json"
            account_file.write_text('{"token_info":{"mid":518800384}}', encoding="utf-8")
            with patch("sau_cli.resolve_account_file", return_value=account_file), patch(
                "sau_cli.get_bilibili_cdp_identity", new=AsyncMock(return_value=identity)
            ) as get_identity, patch(
                "sau_cli.export_bilibili_cdp_account", new=AsyncMock()
            ) as export_account, patch(
                "sau_cli.run_biliup_command",
                return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
            ):
                valid = asyncio.run(sau_cli.check_bilibili_account(
                    "shuimitao-english", "http://127.0.0.1:9226"
                ))

        self.assertTrue(valid)
        get_identity.assert_awaited_once()
        export_account.assert_not_awaited()

    def test_dispatch_bilibili_upload_with_cdp_only_reads_identity(self):
        identity = AccountIdentity(
            platform="bilibili", logged_in=True, stable_id="518800384",
            display_name="水蜜桃英语", profile_url=None,
            browser_name="SAU-自媒体运营-2号-9226", cdp_port=9226, extra={},
        )
        target = SimpleNamespace(
            name="SAU-自媒体运营-2号-9226", port=9226,
            cdp_url="http://127.0.0.1:9226",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            video = Path(temp_dir) / "demo.mp4"
            video.write_bytes(b"video")
            args = sau_cli.build_parser().parse_args([
                "bilibili", "upload-video", "--account", "shuimitao-english",
                "--file", str(video), "--title", "hello", "--desc", "hello",
                "--tid", "36", "--cdp-url", target.cdp_url,
                "--target-account", "518800384",
            ])
            with patch(
                "sau_cli._resolve_upload_target", new=AsyncMock(return_value=target)
            ), patch(
                "sau_cli.get_bilibili_cdp_identity", new=AsyncMock(return_value=identity)
            ) as get_identity, patch(
                "sau_cli.export_bilibili_cdp_account", new=AsyncMock(return_value=identity)
            ) as export_account, patch(
                "sau_cli.upload_bilibili_video",
                new=AsyncMock(return_value={"status": "success"}),
            ):
                code = asyncio.run(sau_cli.dispatch(args))

        self.assertEqual(code, 0)
        get_identity.assert_awaited()
        export_account.assert_not_awaited()

    def test_login_bilibili_account_returns_friendly_message_without_terminal(self):
        with patch("sau_cli.has_interactive_terminal", return_value=False):
            result = asyncio.run(sau_cli.login_bilibili_account("creator"))
        self.assertFalse(result["success"])
        self.assertIn("local interactive terminal", result["message"].lower())
        self.assertIn("qrcode.png", result["message"].lower())

    def test_build_parser_accepts_bilibili_thumbnail_for_upload_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = Path(temp_dir) / "demo.mp4"
            cover = Path(temp_dir) / "cover.png"
            video.write_bytes(b"video")
            cover.write_bytes(b"cover")
            args = sau_cli.build_parser().parse_args(
                [
                    "bilibili", "upload-video", "--account", "creator",
                    "--file", str(video), "--title", "hello", "--desc", "hello",
                    "--tid", "249", "--thumbnail", str(cover),
                ]
            )
        self.assertEqual(args.thumbnail, cover)

    def test_build_parser_accepts_bilibili_charging_pay_for_upload_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = Path(temp_dir) / "demo.mp4"
            video.write_bytes(b"video")
            args = sau_cli.build_parser().parse_args(
                [
                    "bilibili", "upload-video", "--account", "creator",
                    "--file", str(video), "--title", "hello", "--desc", "hello",
                    "--tid", "36", "--charging-pay",
                ]
            )
        self.assertTrue(args.charging_pay)

    def test_upload_bilibili_video_passes_charging_pay_to_biliup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            account_file = Path(temp_dir) / "account.json"
            account_file.write_text("{}", encoding="utf-8")
            request = sau_cli.BilibiliVideoUploadRequest(
                account_name="creator",
                video_file=Path("demo.mp4"),
                title="hello",
                description="hello",
                tid=36,
                tags=[],
                publish_date=0,
                charging_pay=True,
            )
            with patch("sau_cli.resolve_account_file", return_value=account_file), patch(
                "sau_cli.run_biliup_command",
                return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
            ) as run_biliup:
                asyncio.run(sau_cli.upload_bilibili_video(request))

        self.assertIn("--charging-pay", run_biliup.call_args.args[0])
        self.assertEqual(
            run_biliup.call_args.args[0][run_biliup.call_args.args[0].index("--charging-pay") + 1],
            "1",
        )

    def test_upload_bilibili_video_passes_thumbnail_to_biliup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            account_file = Path(temp_dir) / "account.json"
            account_file.write_text("{}", encoding="utf-8")
            request = sau_cli.BilibiliVideoUploadRequest(
                account_name="creator",
                video_file=Path("demo.mp4"),
                title="hello",
                description="hello",
                tid=249,
                tags=["test"],
                publish_date=0,
                thumbnail_file=Path("cover.png"),
            )
            with patch("sau_cli.resolve_account_file", return_value=account_file), patch(
                "sau_cli.run_biliup_command",
                return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
            ) as run_biliup:
                asyncio.run(sau_cli.upload_bilibili_video(request))

        self.assertEqual(
            run_biliup.call_args.args[0],
            [
                "-u", str(account_file), "upload", "demo.mp4",
                "--title", "hello", "--desc", "hello", "--tid", "249",
                "--tag", "test", "--cover", "cover.png",
            ],
        )

    def test_upload_bilibili_video_renews_before_upload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            account_file = Path(temp_dir) / "account.json"
            account_file.write_text("{}", encoding="utf-8")
            request = sau_cli.BilibiliVideoUploadRequest(
                account_name="creator", video_file=Path("demo.mp4"),
                title="hello", description="hello", tid=36,
                tags=[], publish_date=0,
            )
            success = SimpleNamespace(returncode=0, stdout="", stderr="")
            with patch("sau_cli.resolve_account_file", return_value=account_file), patch(
                "sau_cli.run_biliup_command", side_effect=[success, success]
            ) as run_biliup:
                asyncio.run(sau_cli.upload_bilibili_video(request))

        self.assertEqual(run_biliup.call_args_list[0].args[0], ["-u", str(account_file), "renew"])
        self.assertEqual(run_biliup.call_args_list[1].args[0][2], "upload")

    def test_upload_bilibili_video_stops_before_upload_when_renew_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            account_file = Path(temp_dir) / "account.json"
            account_file.write_text("{}", encoding="utf-8")
            request = sau_cli.BilibiliVideoUploadRequest(
                account_name="creator", video_file=Path("demo.mp4"),
                title="hello", description="hello", tid=36,
                tags=[], publish_date=0,
            )
            failure = SimpleNamespace(returncode=1, stdout="", stderr="expired")
            with patch("sau_cli.resolve_account_file", return_value=account_file), patch(
                "sau_cli.run_biliup_command", return_value=failure
            ) as run_biliup:
                with self.assertRaisesRegex(RuntimeError, "BILIBILI_AUTH_REQUIRED"):
                    asyncio.run(sau_cli.upload_bilibili_video(request))

        self.assertEqual(run_biliup.call_count, 1)
        self.assertEqual(run_biliup.call_args.args[0], ["-u", str(account_file), "renew"])

    def test_build_parser_accepts_bilibili_collection_for_upload_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = Path(temp_dir) / "demo.mp4"
            video.write_bytes(b"video")
            args = sau_cli.build_parser().parse_args(
                [
                    "bilibili", "upload-video", "--account", "creator",
                    "--file", str(video), "--title", "hello", "--desc", "hello",
                    "--tid", "36", "--collection", "英语新闻博客",
                ]
            )
        self.assertEqual(args.collection, "英语新闻博客")

    def test_upload_bilibili_video_passes_season_id_via_extra_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            account_file = Path(temp_dir) / "account.json"
            account_file.write_text("{}", encoding="utf-8")
            request = sau_cli.BilibiliVideoUploadRequest(
                account_name="creator",
                video_file=Path("demo.mp4"),
                title="hello",
                description="hello",
                tid=36,
                tags=[],
                publish_date=0,
                collection="英语新闻博客",
            )
            with patch("sau_cli.resolve_account_file", return_value=account_file), patch(
                "sau_cli.resolve_bilibili_season_id", return_value=8762246
            ), patch(
                "sau_cli.resolve_bilibili_section_id", return_value=9765963
            ), patch(
                "sau_cli.find_bilibili_archive_aid", return_value=117046750808432
            ), patch(
                "sau_cli.fetch_bilibili_archive_cid", return_value=40644183101
            ), patch(
                "sau_cli.add_archive_to_season"
            ) as mock_add, patch(
                "sau_cli.run_biliup_command",
                return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
            ) as run_biliup:
                asyncio.run(sau_cli.upload_bilibili_video(request))

        self.assertIn("--extra-fields", run_biliup.call_args.args[0])
        idx = run_biliup.call_args.args[0].index("--extra-fields")
        self.assertEqual(run_biliup.call_args.args[0][idx + 1], '{"season_id": 8762246}')
        mock_add.assert_called_once_with(account_file, 117046750808432, 40644183101, "hello", 9765963)

    def test_upload_bilibili_video_without_collection_skips_extra_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            account_file = Path(temp_dir) / "account.json"
            account_file.write_text("{}", encoding="utf-8")
            request = sau_cli.BilibiliVideoUploadRequest(
                account_name="creator",
                video_file=Path("demo.mp4"),
                title="hello",
                description="hello",
                tid=36,
                tags=[],
                publish_date=0,
            )
            with patch("sau_cli.resolve_account_file", return_value=account_file), patch(
                "sau_cli.run_biliup_command",
                return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
            ) as run_biliup:
                asyncio.run(sau_cli.upload_bilibili_video(request))

        self.assertNotIn("--extra-fields", run_biliup.call_args.args[0])

    def test_naive_schedule_is_converted_from_shanghai_before_biliup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            account_file = Path(temp_dir) / "account.json"
            account_file.write_text("{}", encoding="utf-8")
            request = sau_cli.BilibiliVideoUploadRequest(
                account_name="creator",
                video_file=Path("demo.mp4"),
                title="hello",
                description="hello",
                tid=249,
                tags=[],
                publish_date=datetime(2026, 8, 29, 20, 0),
            )
            with patch("sau_cli.resolve_account_file", return_value=account_file), patch(
                "sau_cli.run_biliup_command",
                return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
            ) as run_biliup:
                asyncio.run(sau_cli.upload_bilibili_video(request))
        args = run_biliup.call_args.args[0]
        expected = int(datetime(2026, 8, 29, 20, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp())
        self.assertEqual(args[args.index("--dtime") + 1], str(expected))
