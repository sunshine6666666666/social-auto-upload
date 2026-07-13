from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from patchright.async_api import Browser, BrowserContext, Playwright


@dataclass(slots=True)
class BrowserSession:
    browser: Browser
    context: BrowserContext
    should_close_context: bool

    async def close(self) -> None:
        if self.should_close_context:
            await self.context.close()
        # For CDP connections this closes the Playwright connection, not the user's Chrome app.
        await self.browser.close()


async def open_browser_session(
    playwright: Playwright,
    *,
    cdp_url: str | None = None,
    launch_kwargs: dict[str, Any] | None = None,
    context_kwargs: dict[str, Any] | None = None,
    use_existing_context: bool = True,
) -> BrowserSession:
    """Open a browser context either by launching Chromium or connecting to Agent Chrome via CDP.

    When cdp_url is set, prefer the existing persistent context from Agent Chrome so the
    uploader can reuse that profile's login state. If no context exists, create a new one.
    """

    launch_kwargs = launch_kwargs or {}
    context_kwargs = context_kwargs or {}

    if cdp_url:
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        if use_existing_context and browser.contexts:
            return BrowserSession(browser=browser, context=browser.contexts[0], should_close_context=False)
        context = await browser.new_context(**context_kwargs)
        return BrowserSession(browser=browser, context=context, should_close_context=True)

    browser = await playwright.chromium.launch(**launch_kwargs)
    context = await browser.new_context(**context_kwargs)
    return BrowserSession(browser=browser, context=context, should_close_context=True)
