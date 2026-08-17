"""Focused tests for CDP session identity selection (issue #6).

When an uploader connects to an existing browser over CDP and requests an
explicit account identity via ``context_kwargs["storage_state"]``, the
upload must NOT reuse the browser's active context (whose active account
could be a different channel). A dedicated context with the account cookies
must be created instead. Flows that do not pass a storage_state (interactive
login) keep reusing the existing context.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from utils.browser_runtime import open_browser_session


def _await_session(playwright, **kwargs):
    return asyncio.run(open_browser_session(playwright, **kwargs))


class FakeChromium:
    def __init__(self):
        self.launched = False
        self.connected = False
        self.launch = AsyncMock()
        self.connect_over_cdp = AsyncMock()


def _fake_browser(has_contexts: bool = True) -> MagicMock:
    browser = MagicMock()
    browser.contexts = [MagicMock()] if has_contexts else []
    browser.new_context = AsyncMock(return_value=MagicMock())
    return browser


class OpenBrowserSessionCdpIdentityTests(unittest.TestCase):
    def test_cdp_with_storage_state_creates_dedicated_context(self):
        """Explicit account identity must win over the CDP active context (issue #6)."""
        chromium = FakeChromium()
        browser = _fake_browser(has_contexts=True)
        chromium.connect_over_cdp.return_value = browser
        playwright = MagicMock()
        playwright.chromium = chromium

        session = _await_session(
            playwright,
            cdp_url="http://127.0.0.1:9241",
            context_kwargs={"storage_state": "/tmp/youtube_shuimitao-english.json"},
        )

        self.assertTrue(isinstance(session, object))
        # A new context with the requested cookies was created...
        browser.new_context.assert_awaited_once_with(
            storage_state="/tmp/youtube_shuimitao-english.json"
        )
        # ...and the browser's active context was NOT reused.
        self.assertNotEqual(session.context, browser.contexts[0])
        self.assertTrue(session.should_close_context)
        chromium.connect_over_cdp.assert_awaited_once_with("http://127.0.0.1:9241")
        chromium.launch.assert_not_awaited()

    def test_cdp_without_storage_state_reuses_existing_context(self):
        """Interactive login without an account identity keeps the current behavior."""
        chromium = FakeChromium()
        browser = _fake_browser(has_contexts=True)
        chromium.connect_over_cdp.return_value = browser
        playwright = MagicMock()
        playwright.chromium = chromium

        session = _await_session(playwright, cdp_url="http://127.0.0.1:9223")

        self.assertEqual(session.context, browser.contexts[0])
        self.assertFalse(session.should_close_context)
        browser.new_context.assert_not_awaited()

    def test_cdp_no_existing_context_creates_new_context(self):
        chromium = FakeChromium()
        browser = _fake_browser(has_contexts=False)
        chromium.connect_over_cdp.return_value = browser
        playwright = MagicMock()
        playwright.chromium = chromium

        session = _await_session(
            playwright,
            cdp_url="http://127.0.0.1:9223",
            context_kwargs={"storage_state": "/tmp/a.json"},
        )

        browser.new_context.assert_awaited_once_with(storage_state="/tmp/a.json")
        self.assertTrue(session.should_close_context)

    def test_local_launch_still_uses_storage_state(self):
        """Non-CDP path is unchanged: launch + new context with cookies."""
        chromium = FakeChromium()
        chromium.launch.return_value = _fake_browser(has_contexts=False)
        playwright = MagicMock()
        playwright.chromium = chromium

        session = _await_session(
            playwright,
            context_kwargs={"storage_state": "/tmp/a.json"},
        )

        chromium.launch.assert_awaited_once()
        chromium.launch.return_value.new_context.assert_awaited_once_with(
            storage_state="/tmp/a.json"
        )
        self.assertTrue(session.should_close_context)


if __name__ == "__main__":
    unittest.main()