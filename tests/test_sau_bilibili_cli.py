import asyncio
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import sau_cli


class BilibiliCliTests(unittest.TestCase):
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
