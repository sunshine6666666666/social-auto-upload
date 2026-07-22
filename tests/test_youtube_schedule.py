import asyncio
from datetime import datetime
from pathlib import Path
import unittest

from uploader.youtube_uploader.main import parse_scheduled_publish_readback
from utils.browser_runtime import requires_local_cdp_file_input, set_local_file_input_via_cdp


class YouTubeScheduleReadbackTests(unittest.TestCase):
    def test_readback_returns_machine_readable_scheduled_result(self):
        html = '''
        <script>
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
