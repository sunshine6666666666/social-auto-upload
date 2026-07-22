from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from patchright.async_api import Browser, BrowserContext, Playwright

CDP_FILE_TRANSFER_LIMIT_BYTES = 50 * 1024 * 1024


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


def requires_local_cdp_file_input(cdp_url: str | None, file_size: int) -> bool:
    return bool(cdp_url) and file_size > CDP_FILE_TRANSFER_LIMIT_BYTES


async def set_local_file_input_via_cdp(page, selector: str, file_path: str | Path) -> None:
    """Assign a same-Mac file path through Chrome CDP without streaming the bytes via Patchright.

    Patchright's regular ``set_input_files`` transfer is capped at 50MB for a browser attached
    over CDP. ``DOM.setFileInputFiles`` makes the already-local Chrome open the local path itself.
    """
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Local upload file not found: {path}")

    cdp = await page.context.new_cdp_session(page)
    document = await cdp.send("DOM.getDocument", {"depth": 1, "pierce": True})
    root_id = document["root"]["nodeId"]
    selected = await cdp.send("DOM.querySelector", {"nodeId": root_id, "selector": selector})
    node_id = selected.get("nodeId", 0)
    if not node_id:
        raise RuntimeError(f"CDP file input not found for selector: {selector}")
    node = await cdp.send("DOM.describeNode", {"nodeId": node_id})
    backend_node_id = node.get("node", {}).get("backendNodeId")
    if not backend_node_id:
        raise RuntimeError(f"CDP file input has no backend node ID for selector: {selector}")
    await cdp.send("DOM.setFileInputFiles", {"backendNodeId": backend_node_id, "files": [str(path)]})
