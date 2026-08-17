import asyncio
from datetime import datetime
from pathlib import Path
import unittest

from uploader.youtube_uploader.main import (
    SCHEDULE_BUTTON_SELECTOR,
    advance_to_visibility,
    find_processing_failure,
    parse_scheduled_publish_readback,
    readback_scheduled_publication,
    wait_for_schedule_control,
)
from utils.browser_runtime import requires_local_cdp_file_input, set_local_file_input_via_cdp


class YouTubeScheduleReadbackTests(unittest.TestCase):
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


class ScheduleControlWaitTests(unittest.TestCase):
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
