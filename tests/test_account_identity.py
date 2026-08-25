import json
import unittest

from utils.account_identity import (
    AccountIdentity,
    assert_same_publish_identity,
    identity_matches,
    require_publish_identity,
)


class AccountIdentityTests(unittest.TestCase):
    def identity(self, **overrides):
        values = {
            "platform": "youtube",
            "logged_in": True,
            "stable_id": "UC123",
            "display_name": "Creator",
            "handle": "@creator",
            "profile_url": "https://youtube.com/@creator",
            "browser_name": "managed",
            "cdp_port": 9225,
            "extra": {},
        }
        values.update(overrides)
        return AccountIdentity(**values)

    def test_to_dict_is_json_serializable_and_utc(self):
        payload = self.identity().to_dict()
        json.dumps(payload)
        self.assertTrue(payload["observed_at"].endswith("Z"))
        self.assertNotIn("cookie", json.dumps(payload).lower())

    def test_logged_out_or_missing_stable_id_is_blocked(self):
        for identity in (self.identity(logged_in=False), self.identity(stable_id=None)):
            with self.assertRaisesRegex(RuntimeError, "(blocked|阻止)"):
                require_publish_identity(identity)

    def test_stable_id_change_is_blocked(self):
        with self.assertRaisesRegex(RuntimeError, "(blocked|阻止)"):
            assert_same_publish_identity(self.identity(), self.identity(stable_id="UC999"))

    def test_display_name_and_handle_change_does_not_block(self):
        observed = self.identity(display_name="New name", handle="@new-name")
        self.assertIsNone(assert_same_publish_identity(self.identity(), observed))

    def test_secret_keys_are_rejected_from_extra(self):
        for key in (
            "cookie",
            "TOKEN",
            "access_token",
            "refreshToken",
            "Authorization",
            "csrf",
            "password",
            "client_secret",
            "api-key",
            "sessionId",
        ):
            with self.assertRaises(ValueError):
                self.identity(extra={key: "redacted"})

    def test_identity_matches_exact_stable_id_handle_or_name_only(self):
        identity = self.identity()
        self.assertTrue(identity_matches(identity, "UC123"))
        self.assertTrue(identity_matches(identity, "creator"))
        self.assertTrue(identity_matches(identity, " Creator "))
        self.assertFalse(identity_matches(identity, "creat"))
        self.assertFalse(identity_matches(identity, "other-creator"))
        with self.assertRaises(ValueError):
            identity_matches(identity, " ")


if __name__ == "__main__":
    unittest.main()
