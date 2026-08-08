import asyncio
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import sau_cli
from uploader.douyin_uploader.main import DouYinVideo


class DouyinCliTests(unittest.TestCase):
    def _temp_video(self, temp_dir: str, name: str = "demo.mp4") -> Path:
        video = Path(temp_dir) / name
        video.write_bytes(b"video")
        return video

    def test_build_parser_defaults_declaration_to_no_declaration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = self._temp_video(temp_dir)
            args = sau_cli.build_parser().parse_args(
                [
                    "douyin", "upload-video",
                    "--account", "peach", "--file", str(video),
                    "--title", "hello",
                ]
            )
        self.assertEqual(args.declaration, "无需添加自主声明")
        self.assertIsNone(args.collection)

    def test_build_parser_accepts_explicit_declaration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = self._temp_video(temp_dir)
            args = sau_cli.build_parser().parse_args(
                [
                    "douyin", "upload-video",
                    "--account", "peach", "--file", str(video),
                    "--title", "hello", "--declaration", "内容为个人观点或见解",
                ]
            )
        self.assertEqual(args.declaration, "内容为个人观点或见解")

    def test_build_parser_rejects_unknown_declaration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = self._temp_video(temp_dir)
            with self.assertRaises(SystemExit):
                sau_cli.build_parser().parse_args(
                    [
                        "douyin", "upload-video",
                        "--account", "peach", "--file", str(video),
                        "--title", "hello", "--declaration", "不存在的声明",
                    ]
                )

    def test_build_parser_accepts_collection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = self._temp_video(temp_dir)
            args = sau_cli.build_parser().parse_args(
                [
                    "douyin", "upload-video",
                    "--account", "peach", "--file", str(video),
                    "--title", "hello", "--collection", "英语新闻（训练版）",
                ]
            )
        self.assertEqual(args.collection, "英语新闻（训练版）")

    def test_upload_video_passes_declaration_and_collection_to_uploader(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            account_file = Path(temp_dir) / "account.json"
            account_file.write_text("{}", encoding="utf-8")
            video = self._temp_video(temp_dir)
            request = sau_cli.DouyinVideoUploadRequest(
                account_name="peach",
                video_file=video,
                title="hello",
                description="",
                tags=[],
                publish_date=0,
                declaration="内容由AI生成",
                collection="英语新闻（训练版）",
            )
            with patch("sau_cli.resolve_account_file", return_value=account_file), patch(
                "sau_cli.douyin_setup", new=AsyncMock(return_value=True)
            ), patch(
                "sau_cli.DouYinVideo", autospec=True
            ) as mock_cls:
                mock_cls.return_value.douyin_upload_video = AsyncMock()
                asyncio.run(sau_cli.upload_video(request))

            _, kwargs = mock_cls.call_args
            self.assertEqual(kwargs["declaration"], "内容由AI生成")
            self.assertEqual(kwargs["collection"], "英语新闻（训练版）")

    def test_upload_video_passes_default_declaration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            account_file = Path(temp_dir) / "account.json"
            account_file.write_text("{}", encoding="utf-8")
            video = self._temp_video(temp_dir)
            request = sau_cli.DouyinVideoUploadRequest(
                account_name="peach",
                video_file=video,
                title="hello",
                description="",
                tags=[],
                publish_date=0,
            )
            with patch("sau_cli.resolve_account_file", return_value=account_file), patch(
                "sau_cli.douyin_setup", new=AsyncMock(return_value=True)
            ), patch(
                "sau_cli.DouYinVideo", autospec=True
            ) as mock_cls:
                mock_cls.return_value.douyin_upload_video = AsyncMock()
                asyncio.run(sau_cli.upload_video(request))

            _, kwargs = mock_cls.call_args
            self.assertEqual(kwargs["declaration"], "无需添加自主声明")
            self.assertIsNone(kwargs["collection"])


class DouyinUploaderDefaultTests(unittest.TestCase):
    def test_douyin_video_default_declaration_is_no_declaration(self):
        app = DouYinVideo(
            title="hello",
            file_path="demo.mp4",
            tags=[],
            publish_date=0,
            account_file="account.json",
        )
        self.assertEqual(app.declaration, "无需添加自主声明")
        self.assertIsNone(app.collection)

    def test_douyin_video_explicit_declaration_and_collection(self):
        app = DouYinVideo(
            title="hello",
            file_path="demo.mp4",
            tags=[],
            publish_date=0,
            account_file="account.json",
            declaration="内容为个人观点或见解",
            collection="英语新闻（训练版）",
        )
        self.assertEqual(app.declaration, "内容为个人观点或见解")
        self.assertEqual(app.collection, "英语新闻（训练版）")


class DouyinScheduleTests(unittest.TestCase):
    def _make_app(self):
        return DouYinVideo(
            title="hello",
            file_path="demo.mp4",
            tags=[],
            publish_date=0,
            account_file="account.json",
        )

    def _make_wheel_page(self, eval_side):
        from unittest.mock import MagicMock

        page = MagicMock()
        page.eval_on_selector = AsyncMock(side_effect=eval_side)
        page.mouse = SimpleNamespace(wheel=AsyncMock(), move=AsyncMock())
        wheel_locator = MagicMock()
        wheel_locator.wait_for = AsyncMock()
        wheel_locator.bounding_box = AsyncMock(return_value={"x": 100, "y": 200, "width": 140, "height": 267})
        # page.locator(sel) returns a locator whose .first resolves to the same async-capable mock
        page.locator = MagicMock(return_value=SimpleNamespace(first=wheel_locator))
        return page

    def test_spin_wheel_to_rolls_forward(self):
        app = self._make_app()
        state = {"hour": 6}

        def eval_side(selector, js):
            if "list-hour" in selector:
                cur = state["hour"]
                state["hour"] += 1
                return f"{cur:02d}时"
            return "00分"

        page = self._make_wheel_page(eval_side)

        async def run():
            await app._spin_wheel_to(page, "hour", 8)

        asyncio.run(run())
        # read 06 → wheel(1) → read 07 → wheel(2) → read 08 done
        self.assertEqual(page.mouse.wheel.call_count, 2)
        self.assertTrue(page.mouse.move.called)

    def test_spin_wheel_to_rolls_backward(self):
        app = self._make_app()
        state = {"hour": 15}

        def eval_side(selector, js):
            if "list-hour" in selector:
                cur = state["hour"]
                state["hour"] -= 1
                return f"{cur:02d}时"
            return "30分"

        page = self._make_wheel_page(eval_side)

        async def run():
            await app._spin_wheel_to(page, "hour", 6)

        asyncio.run(run())
        # started at 15, target 6 → backward rolls (wheel negative)
        self.assertGreater(page.mouse.wheel.call_count, 0)
        args = page.mouse.wheel.call_args_list
        self.assertLess(args[0].args[1], 0)

    def _make_locator(self, **attrs):
        """A fake locator supporting both `.click()` (direct) and `.first.<op>()`."""
        from unittest.mock import MagicMock

        loc = MagicMock()
        for name, mock in attrs.items():
            setattr(loc, name, mock)
        # real Locator.click is async; expose it on both the locator and .first
        loc.click = AsyncMock()
        loc.first = loc
        return loc

    def test_set_schedule_time_readback_mismatch_raises(self):
        from unittest.mock import MagicMock

        app = self._make_app()
        page = MagicMock()

        radio_locator = self._make_locator()
        date_input_locator = self._make_locator()
        date_input_locator.input_value = AsyncMock(return_value="2026-08-13 06:03")
        day_cell = self._make_locator()
        time_switch = self._make_locator()
        page.keyboard = SimpleNamespace(press=AsyncMock())
        app._spin_wheel_to = AsyncMock()

        def locator_side(sel):
            if "日期和时间" in sel:
                return date_input_locator
            if "semi-datepicker:visible span" in sel:
                return day_cell
            if "semi-datepicker-switch-text" in sel:
                return time_switch
            return radio_locator

        page.locator = MagicMock(side_effect=locator_side)

        async def run():
            await app.set_schedule_time_douyin(page, datetime(2026, 8, 13, 6, 0))

        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(run())
        self.assertIn("回读核验失败", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
