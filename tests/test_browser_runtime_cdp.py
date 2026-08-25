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

from utils.browser_runtime import BrowserSession, open_browser_session, save_storage_state_if_owned


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


class _ExpectedPage:
    def __init__(self, page):
        self._page = page

    async def _get_page(self):
        return self._page

    @property
    def value(self):
        return self._get_page()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class BrowserSessionLifecycleTests(unittest.TestCase):
    def test_storage_state_is_saved_only_for_owned_context(self):
        owned_context = MagicMock()
        owned_context.storage_state = AsyncMock()
        owned = BrowserSession(MagicMock(), owned_context, True)
        self.assertTrue(asyncio.run(save_storage_state_if_owned(owned, "/tmp/account.json")))
        owned_context.storage_state.assert_awaited_once_with(path="/tmp/account.json")

        shared_context = MagicMock()
        shared_context.storage_state = AsyncMock()
        shared = BrowserSession(MagicMock(), shared_context, False)
        self.assertFalse(asyncio.run(save_storage_state_if_owned(shared, "/tmp/account.json")))
        shared_context.storage_state.assert_not_awaited()

    def test_cdp_session_records_initial_pages_and_creates_background_page(self):
        initial = MagicMock()
        task_page = MagicMock()
        cdp = MagicMock()
        cdp.send = AsyncMock(return_value={"targetId": "target-1"})
        browser = MagicMock()
        browser.new_browser_cdp_session = AsyncMock(return_value=cdp)
        context = MagicMock()
        context.pages = [initial, task_page]
        context.expect_page.return_value = _ExpectedPage(task_page)

        session = BrowserSession(browser, context, False, (initial,), True)
        page = asyncio.run(session.new_task_page())

        self.assertIs(page, task_page)
        self.assertEqual(session.initial_pages, (initial,))
        cdp.send.assert_awaited_once_with(
            "Target.createTarget", {"url": "about:blank", "background": True}
        )
        context.new_page.assert_not_called()

    def test_cdp_failure_uses_one_foreground_fallback(self):
        fallback = MagicMock()
        browser = MagicMock()
        browser.new_browser_cdp_session = AsyncMock(side_effect=RuntimeError("background failed"))
        context = MagicMock()
        context.pages = []
        context.new_page = AsyncMock(return_value=fallback)
        context.expect_page.return_value = _ExpectedPage(MagicMock())

        session = BrowserSession(browser, context, False, (), True)
        self.assertIs(asyncio.run(session.new_task_page()), fallback)
        self.assertTrue(session.focus_fallback_used)
        context.new_page.assert_awaited_once_with()

    def test_success_close_closes_only_new_pages(self):
        initial = MagicMock()
        first = MagicMock()
        last = MagicMock()
        first.close = AsyncMock()
        last.close = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        context = MagicMock()
        context.pages = [initial, first, last]
        context.close = AsyncMock()

        session = BrowserSession(browser, context, False, (initial,), True)
        asyncio.run(session.close(success=True))

        first.close.assert_awaited_once_with()
        last.close.assert_awaited_once_with()
        initial.close.assert_not_called()
        context.close.assert_not_awaited()
        browser.close.assert_not_awaited()

    def test_failure_close_leaves_last_new_page(self):
        initial = MagicMock()
        first = MagicMock()
        last = MagicMock()
        first.close = AsyncMock()
        last.close = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        context = MagicMock()
        context.pages = [initial, first, last]

        session = BrowserSession(browser, context, False, (initial,), True)
        asyncio.run(session.close(success=False))

        first.close.assert_awaited_once_with()
        last.close.assert_not_awaited()
        initial.close.assert_not_called()
        browser.close.assert_not_awaited()

    def test_cdp_dedicated_context_closes_context_but_not_browser(self):
        page = MagicMock()
        page.close = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        context = MagicMock()
        context.pages = [page]
        context.close = AsyncMock()

        session = BrowserSession(browser, context, True, (), True)
        asyncio.run(session.close(success=True))

        page.close.assert_awaited_once_with()
        context.close.assert_awaited_once_with()
        browser.close.assert_not_awaited()

    def test_local_launch_closes_owned_context_and_browser(self):
        page = MagicMock()
        page.close = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        context = MagicMock()
        context.pages = [page]
        context.close = AsyncMock()

        session = BrowserSession(browser, context, True, (), False)
        asyncio.run(session.close(success=True))

        page.close.assert_awaited_once_with()
        context.close.assert_awaited_once_with()
        browser.close.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
