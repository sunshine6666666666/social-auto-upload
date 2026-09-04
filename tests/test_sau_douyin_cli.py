import asyncio
from contextlib import contextmanager
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import sau_cli
from uploader.douyin_uploader.main import (
    DouYinVideo,
    _wait_for_douyin_login,
    assert_douyin_publish_identity,
    extract_douyin_identity,
    extract_douyin_identity_from_context,
    has_douyin_sms_challenge,
)


class DouyinCliTests(unittest.TestCase):
    def _temp_video(self, temp_dir: str, name: str = "demo.mp4") -> Path:
        video = Path(temp_dir) / name
        video.write_bytes(b"video")
        return video

    def test_login_dispatch_does_not_require_upload_schedule(self):
        args = sau_cli.build_parser().parse_args(
            ["douyin", "login", "--account", "peach", "--browser", "9226"]
        )
        target = SimpleNamespace(cdp_url="http://127.0.0.1:9226")
        with patch(
            "sau_cli._resolve_upload_target", new=AsyncMock(return_value=target)
        ), patch(
            "sau_cli.login_douyin_account",
            new=AsyncMock(return_value={"success": True, "account_file": "/tmp/account.json"}),
        ) as login, patch("builtins.print"):
            self.assertEqual(asyncio.run(sau_cli.dispatch(args)), 0)
        login.assert_awaited_once_with("peach", headless=args.headless, cdp_url=target.cdp_url)

    def test_login_wait_handles_navigation_without_unbound_state(self):
        class Page:
            def __init__(self):
                self._reads = 0

            @property
            def url(self):
                self._reads += 1
                return "https://creator.douyin.com/" if self._reads == 1 else "https://creator.douyin.com/check"

            def locator(self, _selector):
                return SimpleNamespace(count=AsyncMock(return_value=0))

        with patch(
            "uploader.douyin_uploader.main._is_douyin_login_completed",
            new=AsyncMock(return_value=False),
        ):
            result = asyncio.run(
                _wait_for_douyin_login(Page(), "account.json", {}, poll_interval=0, max_checks=1)
            )
        self.assertEqual(result["status"], "timeout")

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
    def test_cdp_validation_does_not_require_cookie_file(self):
        app = DouYinVideo("hello", "demo.mp4", [], 0, "missing.json", cdp_url="http://127.0.0.1:9225")
        asyncio.run(app.validate_base_args())

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

    def test_explicit_declaration_failure_blocks(self):
        app = DouYinVideo("hello", "demo.mp4", [], 0, "account.json", declaration="无需添加自主声明")
        app.set_self_declaration = AsyncMock(return_value=False)
        with self.assertRaisesRegex(RuntimeError, "blocked"):
            asyncio.run(app.apply_self_declaration(object()))


class DouyinSafetyFlowTests(unittest.TestCase):
    def test_sms_challenge_is_detected_without_reading_code(self):
        locator = SimpleNamespace(count=AsyncMock(return_value=1), is_visible=AsyncMock(return_value=True))
        page = SimpleNamespace(locator=lambda _selector: SimpleNamespace(first=locator))
        self.assertTrue(asyncio.run(has_douyin_sms_challenge(page)))


class DouyinIdentityTests(unittest.TestCase):
    class Page:
        url = "https://creator.douyin.com/creator-micro/home"

        async def content(self):
            return '{"uid":"douyin-123","nickname":"Creator"}'

        async def title(self):
            return "Creator"

    def test_identity_uses_uid_not_nickname(self):
        identity = asyncio.run(extract_douyin_identity(self.Page(), browser_name="managed", cdp_port=9225))
        self.assertEqual(identity.stable_id, "douyin-123")
        self.assertEqual(identity.browser_name, "managed")
        self.assertEqual(identity.cdp_port, 9225)

    def test_identity_change_blocks_before_publish(self):
        expected = asyncio.run(extract_douyin_identity(self.Page()))

        class ChangedPage(self.Page):
            async def content(self):
                return '{"uid":"douyin-999"}'

        with self.assertRaisesRegex(RuntimeError, "blocked"):
            asyncio.run(assert_douyin_publish_identity(ChangedPage(), expected))

    def test_context_identity_uses_home_page_and_closes_it(self):
        page = self.Page()
        page.goto = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.close = AsyncMock()
        context = SimpleNamespace(new_page=AsyncMock(return_value=page))

        identity = asyncio.run(extract_douyin_identity_from_context(context))

        self.assertEqual(identity.stable_id, "douyin-123")
        page.goto.assert_awaited_once_with(
            "https://creator.douyin.com/creator-micro/home",
            wait_until="domcontentloaded",
            timeout=90000,
        )
        page.close.assert_awaited_once()

    def test_context_identity_uses_session_background_page_when_available(self):
        page = self.Page()
        page.goto = AsyncMock()
        page.wait_for_timeout = AsyncMock()
        page.close = AsyncMock()
        context = SimpleNamespace(new_page=AsyncMock())
        session = SimpleNamespace(new_task_page=AsyncMock(return_value=page))

        identity = asyncio.run(extract_douyin_identity_from_context(context, session=session))

        self.assertEqual(identity.stable_id, "douyin-123")
        session.new_task_page.assert_awaited_once_with()
        context.new_page.assert_not_awaited()

    def test_identity_reads_visible_handle_and_adjacent_account_name(self):
        class VisiblePage:
            url = "https://creator.douyin.com/creator-micro/home"

            async def content(self):
                return '<title>抖音创作者中心</title>'

            async def title(self):
                return "抖音创作者中心"

            def locator(self, selector):
                return SimpleNamespace(inner_text=AsyncMock(return_value="水蜜桃英语\n抖音号：202851389"))

        page = VisiblePage()
        identity = asyncio.run(extract_douyin_identity(page))
        self.assertTrue(identity.logged_in)
        self.assertEqual(identity.stable_id, "202851389")
        self.assertEqual(identity.display_name, "水蜜桃英语")

    def test_identity_accepts_half_width_colon_and_does_not_use_generic_title(self):
        class VisiblePage(self.Page):
            async def content(self):
                return '<title>抖音创作者中心</title>'

            def locator(self, _selector):
                return SimpleNamespace(inner_text=AsyncMock(return_value="水蜜桃英语\n抖音号 : 202851389"))

            async def title(self):
                return "抖音创作者中心"

        identity = asyncio.run(extract_douyin_identity(VisiblePage()))
        self.assertEqual(identity.stable_id, "202851389")
        self.assertEqual(identity.display_name, "水蜜桃英语")

    def test_identity_without_visible_or_structured_id_is_logged_out(self):
        class LoggedOutPage(self.Page):
            async def content(self):
                return "<html>手机号登录</html>"

            def locator(self, _selector):
                return SimpleNamespace(inner_text=AsyncMock(return_value="手机号登录"))

        identity = asyncio.run(extract_douyin_identity(LoggedOutPage()))
        self.assertFalse(identity.logged_in)
        self.assertIsNone(identity.stable_id)

    def test_identity_conflicting_visible_and_page_data_ids_blocks(self):
        class ConflictingPage(self.Page):
            async def content(self):
                return '{"uid":"100"}'

            def locator(self, _selector):
                return SimpleNamespace(inner_text=AsyncMock(return_value="水蜜桃英语\n抖音号：200"))

        with self.assertRaisesRegex(RuntimeError, "conflicting"):
            asyncio.run(extract_douyin_identity(ConflictingPage()))


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
        wheel_locator.hover = AsyncMock()
        wheel_locator.bounding_box = AsyncMock(return_value={"x": 100, "y": 200, "width": 140, "height": 267})
        # page.locator(sel) returns a locator whose .first resolves to the same async-capable mock
        page.locator = MagicMock(return_value=SimpleNamespace(first=wheel_locator))
        return page

    def test_spin_wheel_to_rolls_forward(self):
        app = self._make_app()
        state = {"hour": 6}

        def eval_side(selector, js):
            if "list-hour" in selector:
                return f"{state['hour']:02d}时"
            return "00分"

        page = self._make_wheel_page(eval_side)
        page.mouse.wheel.side_effect = lambda _x, y: state.update(
            hour=state["hour"] + (1 if y > 0 else -1)
        )

        async def run():
            await app._spin_wheel_to(page, "hour", 8)

        asyncio.run(run())
        # read 06 → wheel(1) → read 07 → wheel(2) → read 08 done
        self.assertEqual(page.mouse.wheel.call_count, 2)
        page.locator.return_value.first.hover.assert_awaited_once_with(timeout=6000)

    def test_spin_wheel_to_rolls_backward(self):
        app = self._make_app()
        state = {"hour": 15}

        def eval_side(selector, js):
            if "list-hour" in selector:
                return f"{state['hour']:02d}时"
            return "30分"

        page = self._make_wheel_page(eval_side)
        page.mouse.wheel.side_effect = lambda _x, y: state.update(
            hour=state["hour"] + (1 if y > 0 else -1)
        )

        async def run():
            await app._spin_wheel_to(page, "hour", 6)

        asyncio.run(run())
        # started at 15, target 6 → backward rolls (wheel negative)
        self.assertGreater(page.mouse.wheel.call_count, 0)
        args = page.mouse.wheel.call_args_list
        self.assertLess(args[0].args[1], 0)

    def test_spin_wheel_to_reverses_after_overshoot(self):
        app = self._make_app()
        state = {"hour": 12}

        def eval_side(selector, js):
            if "list-hour" in selector:
                return f"{state['hour']:02d}时"
            return "00分"

        async def wheel_side(_x, y):
            if y > 0 and state["hour"] == 12:
                state["hour"] = 14
            else:
                state["hour"] += 1 if y > 0 else -1

        page = self._make_wheel_page(eval_side)
        page.mouse.wheel.side_effect = wheel_side

        asyncio.run(app._spin_wheel_to(page, "hour", 13))

        self.assertEqual(
            [call.args[1] for call in page.mouse.wheel.call_args_list[:2]],
            [36, -36],
        )

    def test_spin_wheel_to_waits_for_target_to_settle(self):
        app = self._make_app()
        page = self._make_wheel_page(
            ["12时", "13时", "15时", "14时", "13时", "13时"]
        )

        asyncio.run(app._spin_wheel_to(page, "hour", 13))

        self.assertEqual(
            [call.args[1] for call in page.mouse.wheel.call_args_list],
            [36, -36, -36],
        )

    def test_spin_wheel_to_waits_for_wheel_animation(self):
        app = self._make_app()
        state = {"hour": 19}
        clock = [0.0]
        ready_at = [0.0]

        def eval_side(selector, js):
            if "list-hour" in selector:
                return f"{state['hour']:02d}时"
            return "00分"

        async def wheel_side(_x, y):
            if clock[0] < ready_at[0]:
                state["hour"] += 1
            else:
                state["hour"] -= 1
            ready_at[0] = clock[0] + 1.0

        async def sleep_side(delay):
            clock[0] += delay

        page = self._make_wheel_page(eval_side)
        page.mouse.wheel.side_effect = wheel_side

        with patch(
            "uploader.douyin_uploader.main.asyncio.sleep",
            new=AsyncMock(side_effect=sleep_side),
        ):
            asyncio.run(app._spin_wheel_to(page, "hour", 13))

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

    def _make_schedule_page(self, readbacks, calendar_month="2026年 8月"):
        from unittest.mock import MagicMock

        page = MagicMock()
        radio_locator = self._make_locator()
        date_input_locator = self._make_locator()
        date_input_locator.input_value = AsyncMock(side_effect=readbacks)
        day_cell = self._make_locator()
        time_switch = self._make_locator()
        month_label = self._make_locator()
        month_label.inner_text = AsyncMock(return_value=calendar_month)
        previous_month = self._make_locator()
        next_month = self._make_locator()
        navigation_buttons = MagicMock()
        navigation_buttons.nth = MagicMock(
            side_effect=lambda index: previous_month if index == 0 else next_month
        )
        page.keyboard = SimpleNamespace(press=AsyncMock())
        page.next_month_button = next_month

        def locator_side(selector):
            if "日期和时间" in selector:
                return date_input_locator
            if "semi-datepicker-navigation-month" in selector:
                return month_label
            if "semi-datepicker-navigation button" in selector:
                return navigation_buttons
            if "semi-datepicker:visible span" in selector:
                return day_cell
            if "semi-datepicker-switch-text" in selector:
                return time_switch
            return radio_locator

        page.locator = MagicMock(side_effect=locator_side)
        return page

    def test_set_schedule_time_navigates_to_target_month(self):
        app = self._make_app()
        app._spin_wheel_to = AsyncMock()
        page = self._make_schedule_page(
            ["2026-09-06 13:00"], calendar_month="2026年 8月"
        )

        asyncio.run(
            app.set_schedule_time_douyin(page, datetime(2026, 9, 6, 13, 0))
        )

        page.next_month_button.click.assert_awaited_once_with(timeout=6000)

    def test_set_schedule_time_retries_after_readback_mismatch(self):
        app = self._make_app()
        app._spin_wheel_to = AsyncMock()
        page = self._make_schedule_page(
            ["2026-08-13 15:00", "2026-08-13 13:00"]
        )

        asyncio.run(
            app.set_schedule_time_douyin(page, datetime(2026, 8, 13, 13, 0))
        )

        self.assertEqual(app._spin_wheel_to.await_count, 4)

    def test_set_schedule_time_readback_mismatch_raises(self):
        app = self._make_app()
        app._spin_wheel_to = AsyncMock()
        page = self._make_schedule_page(
            ["2026-08-13 16:00", "2026-08-13 14:00", "2026-08-13 15:00"]
        )

        with self.assertRaises(RuntimeError) as context:
            asyncio.run(
                app.set_schedule_time_douyin(page, datetime(2026, 8, 13, 13, 0))
            )

        message = str(context.exception)
        self.assertIn("回读核验失败", message)
        self.assertIn("尝试 3 次", message)
        self.assertIn("期望 2026-08-13 13:00", message)
        self.assertIn("最后实际 2026-08-13 15:00", message)
        self.assertEqual(app._spin_wheel_to.await_count, 6)


class DouyinLargeFileInputTests(unittest.TestCase):
    @contextmanager
    def _app_and_page(self, cdp_url=None):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as video:
            app = DouYinVideo("hello", video.name, [], 0, "account.json", cdp_url=cdp_url)
            from unittest.mock import MagicMock
            page = MagicMock()
            locator = MagicMock()
            locator.set_input_files = AsyncMock()
            page.locator.return_value = locator
            yield app, page, video.name, locator

    def test_large_cdp_first_upload_uses_local_file_helper(self):
        with self._app_and_page("http://127.0.0.1:9225") as values:
            app, page, path, locator = values
            with patch("uploader.douyin_uploader.main.requires_local_cdp_file_input", return_value=True), patch(
                "uploader.douyin_uploader.main.set_local_file_input_via_cdp", new=AsyncMock()
            ) as helper:
                asyncio.run(app.set_video_file_input(page, "div[class^='container'] input"))
            helper.assert_awaited_once_with(page, "div[class^='container'] input", path)
            locator.set_input_files.assert_not_awaited()

    def test_large_cdp_retry_uses_local_file_helper(self):
        with self._app_and_page("http://127.0.0.1:9225") as values:
            app, page, path, locator = values
            with patch("uploader.douyin_uploader.main.requires_local_cdp_file_input", return_value=True), patch(
                "uploader.douyin_uploader.main.set_local_file_input_via_cdp", new=AsyncMock()
            ) as helper:
                asyncio.run(app.handle_upload_error(page))
            helper.assert_awaited_once_with(page, 'div.progress-div [class^="upload-btn-input"]', path)
            locator.set_input_files.assert_not_awaited()

    def test_small_file_uses_locator_input(self):
        with self._app_and_page("http://127.0.0.1:9225") as values:
            app, page, path, locator = values
            with patch("uploader.douyin_uploader.main.requires_local_cdp_file_input", return_value=False), patch(
                "uploader.douyin_uploader.main.set_local_file_input_via_cdp", new=AsyncMock()
            ) as helper:
                asyncio.run(app.set_video_file_input(page, "input[type='file']"))
            locator.set_input_files.assert_awaited_once_with(path)
            helper.assert_not_awaited()

    def test_non_cdp_large_file_uses_locator_input(self):
        with self._app_and_page() as values:
            app, page, path, locator = values
            with patch("uploader.douyin_uploader.main.requires_local_cdp_file_input", return_value=False), patch(
                "uploader.douyin_uploader.main.set_local_file_input_via_cdp", new=AsyncMock()
            ) as helper:
                asyncio.run(app.set_video_file_input(page, "input[type='file']"))
            locator.set_input_files.assert_awaited_once_with(path)
            helper.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
