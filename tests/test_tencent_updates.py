import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sau_cli
from uploader.tencent_uploader.main import TencentBaseUploader, TencentVideo, format_str_for_short_title
from utils.browser_runtime import BrowserSession


class TencentUpdatesTests(unittest.IsolatedAsyncioTestCase):
    async def test_cookie_check_uses_real_session_interface_and_cdp(self):
        from uploader.tencent_uploader import main as tencent
        session = MagicMock(spec=BrowserSession)
        page = MagicMock()
        page.frames = []
        page.goto = AsyncMock()
        page.wait_for_url = AsyncMock(side_effect=TimeoutError())
        page.locator.return_value.first.wait_for = AsyncMock()
        session.new_task_page = AsyncMock(return_value=page)
        session.close = AsyncMock()
        with patch.object(tencent, "async_playwright"), patch.object(
            tencent, "open_browser_session", new=AsyncMock(return_value=session)
        ) as opener, patch.object(tencent, "set_init_script", new=AsyncMock(return_value=session.context)):
            self.assertTrue(await tencent.cookie_auth("/tmp/test-account.json", cdp_url="http://127.0.0.1:9223"))
        self.assertEqual(opener.await_args.kwargs["cdp_url"], "http://127.0.0.1:9223")
        self.assertEqual(opener.await_args.kwargs["context_kwargs"]["storage_state"], "/tmp/test-account.json")
        session.close.assert_awaited_once()

    async def test_cli_preserves_cdp_and_explicit_metadata(self):
        request = sau_cli.TencentVideoUploadRequest(
            "smoke", Path("demo.mp4"), "测试标题", "", [], 0,
            cdp_url="http://127.0.0.1:9223", collection_name="测试合集", content_label="含AI生成内容",
        )
        with patch("sau_cli.tencent_setup", new=AsyncMock(return_value=True)) as setup, patch("sau_cli.TencentVideo") as cls:
            cls.return_value.tencent_upload_video = AsyncMock()
            await sau_cli.upload_tencent_video(request)
        self.assertEqual(setup.await_args.kwargs["cdp_url"], request.cdp_url)
        for key in ("cdp_url", "collection_name", "content_label"):
            self.assertEqual(cls.call_args.kwargs[key], getattr(request, key))

    async def test_content_label_is_not_invented(self):
        app = TencentVideo("测试标题", "demo.mp4", [], 0, "account.json")
        page = MagicMock()
        await app.apply_original_statement(page)
        page.get_by_text.assert_not_called()

    async def test_explicit_content_label_cannot_be_silently_skipped(self):
        app = TencentVideo("smoke", "demo.mp4", [], 0, "account.json", content_label="含AI生成内容")
        page = MagicMock()
        page.get_by_text.return_value.first.count = AsyncMock(return_value=0)
        with self.assertRaisesRegex(RuntimeError, "无法设置明确要求"):
            await app.apply_original_statement(page)

    async def test_schedule_checks_date_time_and_radio_state(self):
        cases = [("2026-10-17 12:00", "12:00", True, True),
                 ("2026-10-17 14:00", "14:00", True, False),
                 ("2026-10-17 12:00", "12:00", False, False)]
        for date_value, time_value, checked, succeeds in cases:
            with self.subTest(date=date_value, checked=checked):
                app = TencentBaseUploader(0, "account.json")
                page = MagicMock()
                label_root, label, radio, date_field, time_field, editor, day = [MagicMock() for _ in range(7)]
                label_root.filter.return_value.nth.return_value = label
                label.click = AsyncMock()
                label.locator.return_value = radio
                radio.count = AsyncMock(return_value=1)
                radio.is_checked = AsyncMock(return_value=checked)
                date_field.input_value = AsyncMock(return_value=date_value)
                time_field.input_value = AsyncMock(return_value=time_value)
                time_field.fill = AsyncMock()
                time_field.press = AsyncMock()
                editor.click = AsyncMock()
                page.locator.side_effect = lambda selector: {
                    "label": label_root, 'input[placeholder="请选择发表时间"]': date_field,
                    'input[placeholder="请选择时间"]': time_field,
                }.get(selector, editor)
                page.click = AsyncMock()
                page.inner_text = AsyncMock(return_value="10月")
                page.wait_for_timeout = AsyncMock()
                day.evaluate = AsyncMock(return_value="")
                day.inner_text = AsyncMock(return_value="17")
                day.click = AsyncMock()
                page.query_selector_all = AsyncMock(return_value=[day])
                if succeeds:
                    await app.set_schedule_time_tencent(page, datetime(2026, 10, 17, 12))
                else:
                    with self.assertRaisesRegex(RuntimeError, "未点击发表"):
                        await app.set_schedule_time_tencent(page, datetime(2026, 10, 17, 12))
                time_field.fill.assert_awaited_once_with("12:00")

    async def test_publish_click_is_never_retried_on_unknown_result(self):
        app = TencentVideo("unique-smoke", "demo.mp4", [], 0, "account.json")
        app.wait_for_realtime_verification = AsyncMock()
        app._dismiss_switch_account_dialog = AsyncMock()
        page = MagicMock()
        button = page.get_by_role.return_value.first
        button.wait_for = AsyncMock()
        button.click = AsyncMock()
        page.wait_for_url = AsyncMock(side_effect=TimeoutError("unknown"))
        with self.assertRaisesRegex(RuntimeError, "勿重复提交"):
            await app.submit_publish(page)
        button.click.assert_awaited_once()
        page.evaluate.assert_not_called()

    async def test_publish_requires_management_title_readback(self):
        app = TencentVideo("unique-smoke", "demo.mp4", [], 0, "account.json")
        app.wait_for_realtime_verification = AsyncMock()
        app._dismiss_switch_account_dialog = AsyncMock()
        page = MagicMock()
        page.get_by_role.return_value.first.wait_for = AsyncMock()
        page.get_by_role.return_value.first.click = AsyncMock()
        page.wait_for_url = AsyncMock()
        page.get_by_text.return_value.first.wait_for = AsyncMock()
        await app.submit_publish(page)
        page.get_by_text.assert_called_once_with("unique-smoke", exact=False)

    async def test_upload_retries_have_a_limit(self):
        app = TencentVideo("smoke", "demo.mp4", [], 0, "account.json")
        app.handle_upload_error = AsyncMock()
        page = MagicMock()
        page.screenshot = AsyncMock()
        publish = MagicMock()
        publish.first.count = AsyncMock(return_value=0)
        failed = MagicMock()
        failed.count = AsyncMock(return_value=1)
        page.locator.side_effect = lambda selector: publish if "发表" in selector else failed
        with patch("uploader.tencent_uploader.main.asyncio.sleep", new=AsyncMock()):
            with self.assertRaisesRegex(RuntimeError, "耗尽 1 次重试"):
                await app.wait_for_upload_complete(page, timeout_seconds=10, max_retries=1)
        app.handle_upload_error.assert_awaited_once()

    async def test_upload_timeout_stops_without_retry(self):
        app = TencentVideo("smoke", "demo.mp4", [], 0, "account.json")
        page = MagicMock()
        page.screenshot = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, "超过"):
            await app.wait_for_upload_complete(page, timeout_seconds=-1)

    async def test_real_name_verification_has_a_timeout(self):
        app = TencentBaseUploader(0, "account.json")
        page = MagicMock()
        dialog = page.locator.return_value.filter.return_value.first
        dialog.count = AsyncMock(return_value=1)
        dialog.is_visible = AsyncMock(return_value=True)
        dialog.screenshot = AsyncMock()
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(TimeoutError, "实名验证超时"):
                await app.wait_for_realtime_verification(page, Path(folder) / "qr.png", timeout_seconds=0)


class TencentParsingTests(unittest.TestCase):
    def test_short_title_matches_current_length_limits(self):
        for value in ("", "短", "这是非常长的视频号测试标题用于验证截断", "a,b!"):
            self.assertTrue(7 <= len(format_str_for_short_title(value)) <= 15)

    def test_check_supports_registered_browser(self):
        args = sau_cli.build_parser().parse_args(["tencent", "check", "--account", "smoke", "--browser", "9223"])
        self.assertEqual(args.browser, "9223")


if __name__ == "__main__":
    unittest.main()
