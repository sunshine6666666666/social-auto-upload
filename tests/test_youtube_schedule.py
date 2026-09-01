import asyncio
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from uploader.youtube_uploader.main import (
    SCHEDULE_BUTTON_SELECTOR,
    _configure_scheduled_publication,
    _click_if_present,
    _click_required_final_button,
    _youtube_context_kwargs,
    assert_youtube_publish_identity,
    advance_to_visibility,
    extract_youtube_identity,
    extract_youtube_draft_reference,
    find_processing_failure,
    parse_scheduled_publish_readback,
    readback_scheduled_publication,
    wait_for_schedule_control,
    youtube_setup,
)
from utils.browser_runtime import requires_local_cdp_file_input, set_local_file_input_via_cdp


class YouTubeScheduleReadbackTests(unittest.TestCase):
    def test_cdp_reuses_browser_profile_without_cookie_file(self):
        self.assertEqual(_youtube_context_kwargs("missing.json", "http://127.0.0.1:9225"), {})
        with patch("uploader.youtube_uploader.main.cookie_auth", new=AsyncMock(return_value=True)) as auth, patch(
            "pathlib.Path.exists", return_value=False
        ):
            self.assertTrue(asyncio.run(youtube_setup("missing.json", cdp_url="http://127.0.0.1:9225")))
        auth.assert_awaited_once_with("missing.json", cdp_url="http://127.0.0.1:9225")

    class IdentityPage:
        url = "https://studio.youtube.com/channel/UC1234567890123456789012/videos"

        async def content(self):
            return '<script>{"channelId":"UC1234567890123456789012"}</script>'

        async def title(self):
            return "Creator - YouTube Studio"

    def test_identity_extracts_channel_id_from_studio(self):
        identity = asyncio.run(extract_youtube_identity(self.IdentityPage(), browser_name="managed", cdp_port=9225))
        self.assertEqual(identity.stable_id, "UC1234567890123456789012")
        self.assertTrue(identity.logged_in)
        self.assertEqual(identity.browser_name, "managed")

    def test_identity_extracts_visible_channel_name(self):
        class Locator:
            first = None

            def __init__(self):
                self.first = self

            async def inner_text(self):
                return "我的频道\n水蜜桃英语"

        class NamedPage(self.IdentityPage):
            def locator(self, _selector):
                return Locator()

        identity = asyncio.run(extract_youtube_identity(NamedPage()))
        self.assertEqual(identity.display_name, "水蜜桃英语")

    def test_identity_falls_back_to_studio_html_channel_id(self):
        class HtmlOnlyPage(self.IdentityPage):
            url = "https://studio.youtube.com/"

        identity = asyncio.run(extract_youtube_identity(HtmlOnlyPage()))
        self.assertEqual(identity.stable_id, "UC1234567890123456789012")

    def test_identity_change_blocks_before_submit(self):
        expected = asyncio.run(extract_youtube_identity(self.IdentityPage()))

        class ChangedPage(self.IdentityPage):
            url = "https://studio.youtube.com/channel/UC9999999999999999999999/videos"

        with self.assertRaisesRegex(RuntimeError, "blocked"):
            asyncio.run(assert_youtube_publish_identity(ChangedPage(), expected))

    def test_readback_returns_machine_readable_scheduled_result(self):
        html = '''
        <script>
        {"entity_id":"UC04E0U6ZAZoD5y3lcVNUNHQ"}
        {"entity_id":"QMiJvZPJJv0", "scheduledPublishingDetails":
          {"scheduledPublishings":[{"scheduledTimeSeconds":"1785621600",
          "action":"SCHEDULED_PUBLISHING_ACTION_SET_PUBLIC",
          "status":"SCHEDULED_PUBLISHING_STATUS_SCHEDULED"}]}}
        </script>
        '''

        result = parse_scheduled_publish_readback(
            html, expected_schedule=datetime(2026, 8, 2, 6, 0), timezone="Asia/Shanghai"
        )

        self.assertEqual(result["videoId"], "QMiJvZPJJv0")
        self.assertEqual(result["publishUrl"], "https://www.youtube.com/watch?v=QMiJvZPJJv0")
        self.assertEqual(result["visibility"], "scheduled")
        self.assertEqual(result["scheduledTimeSeconds"], 1785621600)
        self.assertEqual(result["scheduledAt"], "2026-08-02T06:00:00+08:00")
        self.assertEqual(result["timezone"], "Asia/Shanghai")

    def test_draft_reference_parser_accepts_four_video_sources(self):
        cases = (
            '<ytcp-uploads-dialog video-id="QMiJvZPJJv0">',
            '{"videoId":"QMiJvZPJJv0"}',
            "https://youtu.be/QMiJvZPJJv0",
            "https://www.youtube.com/watch?v=QMiJvZPJJv0",
        )
        for html in cases:
            with self.subTest(html=html):
                self.assertEqual(
                    extract_youtube_draft_reference(html),
                    {
                        "videoId": "QMiJvZPJJv0",
                        "publishUrl": "https://www.youtube.com/watch?v=QMiJvZPJJv0",
                    },
                )

    def test_draft_reference_parser_does_not_return_channel_id(self):
        self.assertEqual(
            extract_youtube_draft_reference('{"channelId":"UC04E0U6ZAZoD5y3lcVNUNHQ"}'), {}
        )

    def test_readback_rejects_missing_schedule_evidence(self):
        with self.assertRaisesRegex(RuntimeError, "scheduledTimeSeconds"):
            parse_scheduled_publish_readback(
                '{"entity_id":"QMiJvZPJJv0"}',
                expected_schedule=datetime(2026, 8, 2, 6, 0),
                timezone="Asia/Shanghai",
            )

    def test_readback_rejects_mismatched_scheduled_time(self):
        html = '''
        {"entity_id":"QMiJvZPJJv0", "scheduledPublishingDetails":
          {"scheduledPublishings":[{"scheduledTimeSeconds":"1785621600",
          "status":"SCHEDULED_PUBLISHING_STATUS_SCHEDULED"}]}}
        '''
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            parse_scheduled_publish_readback(
                html, expected_schedule=datetime(2026, 8, 2, 7, 0), timezone="Asia/Shanghai"
            )

    def test_readback_rejects_structured_processing_failure_marker(self):
        # Studio may keep SCHEDULED status while the video failed processing;
        # the readback must not declare success in that case (#8).
        html = '''
        {"entity_id":"QMiJvZPJJv0", "scheduledPublishingDetails":
          {"scheduledPublishings":[{"scheduledTimeSeconds":"1785621600",
          "status":"SCHEDULED_PUBLISHING_STATUS_SCHEDULED"}]},
         "processingStatus":"FAILED", "processingFailureCode":"BAD_VIDEO_TOO_LONG"}
        '''
        with self.assertRaisesRegex(RuntimeError, "processing failure"):
            parse_scheduled_publish_readback(
                html, expected_schedule=datetime(2026, 8, 2, 6, 0), timezone="Asia/Shanghai"
            )

    def test_readback_rejects_chinese_processing_failure_banner(self):
        # The failure is reported as a Studio UI banner, not structured payload data.
        html = '''
        {"entity_id":"QMiJvZPJJv0", "scheduledPublishingDetails":
          {"scheduledPublishings":[{"scheduledTimeSeconds":"1785621600",
          "status":"SCHEDULED_PUBLISHING_STATUS_SCHEDULED"}]}}
        <div class="banner">处理中断 · 视频过长</div>
        '''
        with self.assertRaisesRegex(RuntimeError, "false success"):
            parse_scheduled_publish_readback(
                html, expected_schedule=datetime(2026, 8, 2, 6, 0), timezone="Asia/Shanghai"
            )

    def test_find_processing_failure_returns_none_on_clean_evidence(self):
        html = '''
        {"entity_id":"QMiJvZPJJv0", "scheduledPublishingDetails":
          {"scheduledPublishings":[{"scheduledTimeSeconds":"1785621600",
          "status":"SCHEDULED_PUBLISHING_STATUS_SCHEDULED"}]}}
        '''
        self.assertIsNone(find_processing_failure(html.replace(r'\"', '"'), html))


    def test_readback_reopens_studio_edit_page_when_upload_dialog_lacks_metadata(self):
        scheduled_html = '''
        {"entity_id":"QMiJvZPJJv0", "scheduledPublishingDetails":
          {"scheduledPublishings":[{"scheduledTimeSeconds":"1785621600",
          "status":"SCHEDULED_PUBLISHING_STATUS_SCHEDULED"}]}}
        '''

        class FakePage:
            def __init__(self):
                self.html = '<a href="https://youtu.be/QMiJvZPJJv0">link</a>'
                self.gotos = []

            async def content(self):
                return self.html

            async def goto(self, url, wait_until):
                self.gotos.append((url, wait_until))
                self.html = scheduled_html

            async def wait_for_timeout(self, milliseconds):
                return None

        page = FakePage()
        result = asyncio.run(
            readback_scheduled_publication(
                page,
                expected_schedule=datetime(2026, 8, 2, 6, 0),
                timezone="Asia/Shanghai",
                max_polls=2,
                poll_ms=1,
            )
        )

        self.assertEqual(page.gotos, [("https://studio.youtube.com/video/QMiJvZPJJv0/edit", "domcontentloaded")])
        self.assertEqual(result["videoId"], "QMiJvZPJJv0")

    def test_readback_uses_hidden_upload_dialog_video_id(self):
        scheduled_html = '''
        {"videoId":"QMiJvZPJJv0","scheduledPublishingDetails":
          {"scheduledPublishings":[{"scheduledTimeSeconds":"1785621600",
          "status":"SCHEDULED_PUBLISHING_STATUS_SCHEDULED"}]}}
        '''

        class FakePage:
            def __init__(self):
                self.html = '<ytcp-uploads-dialog hidden video-id="QMiJvZPJJv0"></ytcp-uploads-dialog>'
                self.gotos = []

            async def content(self):
                return self.html

            async def goto(self, url, wait_until):
                self.gotos.append((url, wait_until))
                self.html = scheduled_html

            async def wait_for_timeout(self, _milliseconds):
                return None

        page = FakePage()
        result = asyncio.run(readback_scheduled_publication(
            page, expected_schedule=datetime(2026, 8, 2, 6, 0), timezone="Asia/Shanghai", max_polls=2, poll_ms=1
        ))
        self.assertEqual(result["videoId"], "QMiJvZPJJv0")

    def test_done_button_click_targets_native_inner_button(self):
        class Locator:
            def __init__(self, count=1):
                self.first = self
                self.count_value = count
                self.clicks = 0
                self.inner = None

            async def wait_for(self, **_kwargs):
                return None

            def locator(self, _selector):
                return self.inner

            async def count(self):
                return self.count_value

            async def click(self):
                self.clicks += 1

        host = Locator()
        host.inner = Locator()
        page = type("Page", (), {"locator": lambda _self, _selector: host})()
        self.assertTrue(asyncio.run(_click_if_present(page, "#done-button")))
        self.assertEqual(host.clicks, 0)
        self.assertEqual(host.inner.clicks, 1)

    def test_missing_final_button_is_a_hard_failure(self):
        page = type("Page", (), {"wait_for_timeout": AsyncMock()})()
        with patch(
            "uploader.youtube_uploader.main._click_if_present",
            new=AsyncMock(return_value=False),
        ):
            with self.assertRaisesRegex(RuntimeError, "final Publish button"):
                asyncio.run(_click_required_final_button(page, "Publish", timeout_ms=1, poll_ms=1))

    def test_final_schedule_button_waits_until_processing_enables_it(self):
        page = type("Page", (), {"wait_for_timeout": AsyncMock()})()
        click = AsyncMock(side_effect=[False, False, False, True])
        with patch("uploader.youtube_uploader.main._click_if_present", new=click):
            asyncio.run(_click_required_final_button(page, "Schedule", timeout_ms=2, poll_ms=1))
        self.assertEqual(click.await_count, 4)
        page.wait_for_timeout.assert_awaited_once_with(1)

    def test_schedule_button_falls_back_to_chinese_yuding(self):
        class Button:
            def __init__(self, enabled=True):
                self.first = self
                self.enabled = enabled
                self.clicked = False

            async def wait_for(self, **_kwargs):
                return None

            async def count(self):
                return 1

            async def is_enabled(self):
                return self.enabled

            async def click(self):
                self.clicked = True

        done = Button(enabled=False)
        chinese = Button()

        class Page:
            def locator(self, selector):
                if selector == "#done-button":
                    return done
                if "预定" in selector:
                    return chinese
                return Button(enabled=False)

        asyncio.run(_click_required_final_button(Page(), "Schedule"))
        self.assertFalse(done.clicked)
        self.assertTrue(chinese.clicked)

    def test_disabled_button_is_not_clicked(self):
        class Disabled:
            first = None

            async def wait_for(self, **_kwargs):
                return None

            async def is_enabled(self):
                return False

            async def click(self):
                raise AssertionError("disabled button was clicked")

        disabled = Disabled()
        disabled.first = disabled
        page = type("Page", (), {"locator": lambda _self, _selector: disabled})()
        self.assertFalse(asyncio.run(_click_if_present(page, "#done-button")))


class ScheduleControlWaitTests(unittest.TestCase):
    def test_schedule_time_blurs_after_fill(self):
        date_trigger, date_input, time_input = MagicMock(), MagicMock(), MagicMock()
        for locator in (date_trigger, date_input, time_input):
            locator.first = locator
            locator.wait_for = AsyncMock()
        date_trigger.click = AsyncMock()
        date_input.fill, date_input.press = AsyncMock(), AsyncMock()
        time_input.fill, time_input.blur = AsyncMock(), AsyncMock()
        page = MagicMock()
        page.locator.side_effect = [date_trigger, date_input, time_input]

        with patch("uploader.youtube_uploader.main.wait_for_schedule_control", new=AsyncMock()):
            asyncio.run(_configure_scheduled_publication(page, datetime(2099, 9, 1, 16, 0), "Asia/Shanghai"))

        time_input.fill.assert_awaited_once_with("16:00")
        time_input.blur.assert_awaited_once_with()

    def test_schedule_selector_covers_studio_expand_control(self):
        self.assertIn("second-container-expand-button", SCHEDULE_BUTTON_SELECTOR)

    def test_wait_for_schedule_control_retries_until_button_appears(self):
        class FakeButton:
            def __init__(self, page):
                self.page = page

            @property
            def first(self):
                return self

            async def wait_for(self, state, timeout):
                self.page.wait_attempts += 1
                if self.page.wait_attempts < 3:
                    raise TimeoutError("not ready")

            async def click(self):
                self.page.clicks += 1

        class FakePage:
            def __init__(self):
                self.wait_attempts = 0
                self.clicks = 0
                self.sleeps = []

            def locator(self, selector):
                self.selector = selector
                return FakeButton(self)

            async def wait_for_timeout(self, milliseconds):
                self.sleeps.append(milliseconds)

        page = FakePage()
        asyncio.run(wait_for_schedule_control(page, timeout_ms=50, poll_ms=4))

        self.assertEqual(page.selector, SCHEDULE_BUTTON_SELECTOR)
        self.assertEqual(page.clicks, 1)
        self.assertEqual(page.sleeps, [3, 3])


class YouTubeRecoverableFailureTests(unittest.TestCase):
    def test_scheduled_success_preserves_submitted_true_in_final_receipt(self):
        class Locator:
            first = None

            def __init__(self):
                self.first = self

            async def wait_for(self, **_kwargs):
                return None

            async def set_input_files(self, _path):
                return None

        class Page:
            url = "https://studio.youtube.com/channel/UC1234567890123456789012/videos"

            def __init__(self):
                self.keyboard = MagicMock()

            async def content(self):
                return '<script>{"channelId":"UC1234567890123456789012"}</script>'

            async def goto(self, *_args, **_kwargs):
                return None

            async def wait_for_timeout(self, _milliseconds):
                return None

            def set_default_timeout(self, _timeout):
                return None

            def locator(self, _selector):
                return Locator()

        class Session:
            context = MagicMock()
            focus_fallback_used = False
            new_task_page = AsyncMock()

        page = Page()
        session = Session()
        session.new_task_page.return_value = page
        app = __import__("uploader.youtube_uploader.main", fromlist=["YouTubeVideo"]).YouTubeVideo(
            "title", __file__, [], "account.json", cdp_url="http://127.0.0.1:9225",
            schedule=datetime(2099, 8, 2, 6, 0), browser_name="managed", cdp_port=9225,
        )
        scheduled = {
            "videoId": "QMiJvZPJJv0",
            "publishUrl": "https://www.youtube.com/watch?v=QMiJvZPJJv0",
            "visibility": "scheduled",
            "scheduledAt": "2099-08-02T06:00:00+08:00",
        }
        with patch("uploader.youtube_uploader.main.open_browser_session", new=AsyncMock(return_value=session)), patch(
            "uploader.youtube_uploader.main.set_init_script", new=AsyncMock(return_value=session.context)
        ), patch("uploader.youtube_uploader.main._fill_editable", new=AsyncMock()), patch(
            "uploader.youtube_uploader.main._wait_upload_complete", new=AsyncMock(return_value=True)
        ), patch("uploader.youtube_uploader.main.advance_to_visibility", new=AsyncMock()), patch(
            "uploader.youtube_uploader.main._configure_scheduled_publication", new=AsyncMock()
        ), patch("uploader.youtube_uploader.main.assert_youtube_publish_identity", new=AsyncMock()), patch(
            "uploader.youtube_uploader.main._click_if_present", new=AsyncMock(return_value=True)
        ), patch("uploader.youtube_uploader.main._click_required_final_button", new=AsyncMock()), patch(
            "uploader.youtube_uploader.main.readback_scheduled_publication", new=AsyncMock(return_value=scheduled)
        ), patch("uploader.youtube_uploader.main.save_storage_state_if_owned", new=AsyncMock()):
            result = asyncio.run(app.upload(MagicMock()))

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["submitted"])
        self.assertEqual(result["videoId"], "QMiJvZPJJv0")

    def test_missing_schedule_button_returns_draft_evidence_without_success(self):
        class Locator:
            first = None

            def __init__(self):
                self.first = self

            async def wait_for(self, **_kwargs):
                return None

            async def set_input_files(self, _path):
                return None

        class Page:
            url = "https://studio.youtube.com/channel/UC1234567890123456789012/videos"

            def __init__(self):
                self.contents = [
                    '<script>{"channelId":"UC1234567890123456789012"}</script>',
                    '<ytcp-uploads-dialog video-id="QMiJvZPJJv0"></ytcp-uploads-dialog>',
                ]
                self.keyboard = MagicMock()

            async def content(self):
                return self.contents.pop(0)

            async def goto(self, *_args, **_kwargs):
                return None

            async def wait_for_timeout(self, _milliseconds):
                return None

            def set_default_timeout(self, _timeout):
                return None

            def locator(self, _selector):
                return Locator()

        class Session:
            context = MagicMock()
            focus_fallback_used = False
            new_task_page = AsyncMock()

        page = Page()
        session = Session()
        session.new_task_page.return_value = page
        app = __import__("uploader.youtube_uploader.main", fromlist=["YouTubeVideo"]).YouTubeVideo(
            "title", __file__, [], "account.json", cdp_url="http://127.0.0.1:9225",
            schedule=datetime(2099, 8, 2, 6, 0), browser_name="managed", cdp_port=9225,
        )
        with patch("uploader.youtube_uploader.main.open_browser_session", new=AsyncMock(return_value=session)), patch(
            "uploader.youtube_uploader.main.set_init_script", new=AsyncMock(return_value=session.context)
        ), patch("uploader.youtube_uploader.main._fill_editable", new=AsyncMock()), patch(
            "uploader.youtube_uploader.main._wait_upload_complete", new=AsyncMock(return_value=True)
        ), patch("uploader.youtube_uploader.main.advance_to_visibility", new=AsyncMock()), patch(
            "uploader.youtube_uploader.main._configure_scheduled_publication", new=AsyncMock()
        ), patch("uploader.youtube_uploader.main.assert_youtube_publish_identity", new=AsyncMock()), patch(
            "uploader.youtube_uploader.main._click_if_present", new=AsyncMock(return_value=True)
        ), patch("uploader.youtube_uploader.main._click_required_final_button", new=AsyncMock(side_effect=RuntimeError("missing"))):
            result = asyncio.run(app.upload(MagicMock()))

        self.assertEqual(result["status"], "interaction_required")
        self.assertEqual(result["reason"], "final_schedule_button_missing")
        self.assertTrue(result["recoverable"])
        self.assertFalse(result["submitted"])
        self.assertEqual(result["videoId"], "QMiJvZPJJv0")
        self.assertEqual(result["stable_id"], "UC1234567890123456789012")
        self.assertFalse(app._upload_succeeded)


class VisibilityNavigationTests(unittest.TestCase):
    def test_advance_to_visibility_clicks_next_after_checks_finish(self):
        class FakeNext:
            def __init__(self, page):
                self.page = page

            @property
            def first(self):
                return self

            async def wait_for(self, state, timeout):
                return None

            async def click(self):
                self.page.next_clicks += 1

        class FakeVisibility:
            def __init__(self, page):
                self.page = page

            async def count(self):
                return 1

            @property
            def first(self):
                return self

            async def is_visible(self):
                return self.page.next_clicks >= 2

        class FakePage:
            def __init__(self):
                self.next_clicks = 0

            def locator(self, selector):
                if "name='PUBLIC'" in selector:
                    return FakeVisibility(self)
                if selector == "#next-button":
                    return FakeNext(self)
                raise AssertionError(selector)

            async def wait_for_timeout(self, milliseconds):
                return None

        page = FakePage()
        asyncio.run(advance_to_visibility(page, timeout_ms=12, poll_ms=4))

        self.assertEqual(page.next_clicks, 2)


class CdpUploadRoutingTests(unittest.TestCase):
    def test_large_cdp_upload_uses_browser_local_file_path(self):
        limit = 50 * 1024 * 1024
        self.assertFalse(requires_local_cdp_file_input(None, limit + 1))
        self.assertFalse(requires_local_cdp_file_input("http://127.0.0.1:9223", limit))
        self.assertTrue(requires_local_cdp_file_input("http://127.0.0.1:9223", limit + 1))


class DirectCdpFileInputTests(unittest.TestCase):
    def test_set_local_file_input_sends_path_to_browser_cdp(self):
        class FakeCdpSession:
            def __init__(self):
                self.calls = []

            async def send(self, method, params=None):
                self.calls.append((method, params or {}))
                responses = {
                    "DOM.getDocument": {"root": {"nodeId": 1}},
                    "DOM.querySelector": {"nodeId": 2},
                    "DOM.describeNode": {"node": {"backendNodeId": 3}},
                    "DOM.setFileInputFiles": {},
                }
                return responses[method]

        class FakeContext:
            def __init__(self, session):
                self.session = session

            async def new_cdp_session(self, _page):
                return self.session

        class FakePage:
            def __init__(self, context):
                self.context = context

        session = FakeCdpSession()
        page = FakePage(FakeContext(session))
        file_path = Path(__file__).resolve()
        asyncio.run(set_local_file_input_via_cdp(page, "input[type='file']", file_path))

        self.assertEqual(
            session.calls[-1],
            ("DOM.setFileInputFiles", {"backendNodeId": 3, "files": [str(file_path)]}),
        )

    def test_set_local_file_input_raises_when_selector_is_missing(self):
        class FakeCdpSession:
            async def send(self, method, params=None):
                if method == "DOM.getDocument":
                    return {"root": {"nodeId": 1}}
                if method == "DOM.querySelector":
                    return {"nodeId": 0}
                raise AssertionError(method)

        class FakeContext:
            async def new_cdp_session(self, _page):
                return FakeCdpSession()

        class FakePage:
            context = FakeContext()

        with self.assertRaisesRegex(RuntimeError, "not found"):
            asyncio.run(set_local_file_input_via_cdp(FakePage(), "input[type='file']", Path(__file__).resolve()))


if __name__ == "__main__":
    unittest.main()
