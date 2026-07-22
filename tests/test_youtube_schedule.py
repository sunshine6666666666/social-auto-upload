from datetime import datetime
import unittest

from uploader.youtube_uploader.main import parse_scheduled_publish_readback


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


if __name__ == "__main__":
    unittest.main()
