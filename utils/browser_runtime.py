from __future__ import annotations

import contextlib
import datetime as _datetime
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import warnings

from patchright.async_api import Browser, BrowserContext, Playwright

CDP_FILE_TRANSFER_LIMIT_BYTES = 50 * 1024 * 1024
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_DEFAULT_TASK_STATE_DIR = Path("/private/tmp/social-auto-upload-task-state")


def _task_state_dir() -> Path:
    return Path(os.environ.get("SAU_TASK_STATE_DIR") or _DEFAULT_TASK_STATE_DIR)


def _task_timestamp() -> str:
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _atomic_json_create(path: Path, payload: dict[str, Any]) -> bool:
    """Publish one complete JSON file only when the final path is still absent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_name, path)
        except FileExistsError:
            return False
        return True
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False
    return True


@contextlib.contextmanager
def browser_task_lock(port: int):
    """Hold one process lock for a browser CDP port."""
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("browser port is invalid")
    state_dir = _task_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / f"browser-{port}.lock"
    fd = None
    # ponytail: process-local file locks are enough for one Mac; use a lock service only if distributed workers are introduced.
    try:
        for attempt in range(2):
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, str(os.getpid()).encode("ascii"))
                break
            except FileExistsError:
                if attempt:
                    raise RuntimeError(f"browser {port} is already in use by another SAU task")
                try:
                    owner = int(lock_path.read_text(encoding="ascii").strip())
                except (OSError, ValueError):
                    owner = None
                if owner is not None and _pid_alive(owner):
                    raise RuntimeError(f"browser {port} is already in use by another SAU task")
                lock_path.unlink(missing_ok=True)
        yield
    finally:
        if fd is not None:
            os.close(fd)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def _task_receipt_path(task_id: str) -> Path:
    if not isinstance(task_id, str) or not _TASK_ID_RE.fullmatch(task_id):
        raise ValueError("task ID must match [A-Za-z0-9._-]{1,128}")
    return _task_state_dir() / f"{task_id}.json"


def _argv_hash(argv) -> str:
    canonical = json.dumps(list(argv), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def begin_task(task_id: str, argv) -> dict[str, Any]:
    """Start an idempotent task or return its existing terminal state."""
    path = _task_receipt_path(task_id)
    argv_hash = _argv_hash(argv)
    receipt = {
        "task_id": task_id,
        "argv_sha256": argv_hash,
        "state": "started",
        "started_at": _task_timestamp(),
        "result": {},
    }
    if not _atomic_json_create(path, receipt):
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("task receipt is invalid") from exc
        if receipt.get("argv_sha256") != argv_hash:
            raise RuntimeError("same task ID was used with different arguments")
        state = receipt.get("state")
        if state == "complete":
            return {"state": "skipped_duplicate", "result": receipt.get("result", {})}
        if state in {"started", "uncertain"}:
            return {"state": "uncertain", "result": receipt.get("result", {})}
        if state == "failed":
            return {"state": "failed", "result": receipt.get("result", {})}
        raise RuntimeError("task receipt has an invalid state")
    return {"state": "started", "result": {}}


def finish_task(task_id: str, result: dict[str, Any]) -> None:
    path = _task_receipt_path(task_id)
    if not path.exists():
        raise RuntimeError("task receipt does not exist")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["state"] = result.get("task_state", "complete")
    receipt["finished_at"] = _task_timestamp()
    receipt["result"] = {key: value for key, value in result.items() if key != "task_state"}
    _atomic_json_write(path, receipt)


@dataclass(slots=True)
class BrowserSession:
    browser: Browser
    context: BrowserContext
    should_close_context: bool
    initial_pages: tuple[Any, ...] = ()
    connected_over_cdp: bool = False
    focus_fallback_used: bool = False

    async def new_task_page(self):
        if not (self.connected_over_cdp and not self.should_close_context):
            return await self.context.new_page()

        target_id = None
        cdp = None
        try:
            async with self.context.expect_page() as page_info:
                cdp = await self.browser.new_browser_cdp_session()
                created = await cdp.send(
                    "Target.createTarget",
                    {"url": "about:blank", "background": True},
                )
                target_id = created.get("targetId") if isinstance(created, dict) else None
            return await page_info.value
        except Exception:
            if cdp is not None and target_id:
                try:
                    await cdp.send("Target.closeTarget", {"targetId": target_id})
                except Exception as exc:
                    warnings.warn(f"failed to close fallback target: {exc}", RuntimeWarning)
            self.focus_fallback_used = True
            return await self.context.new_page()

    async def close(self, *, success: bool = True) -> None:
        initial_ids = {id(page) for page in self.initial_pages}
        new_pages = [page for page in getattr(self.context, "pages", ()) if id(page) not in initial_ids]
        pages_to_close = new_pages if success else new_pages[:-1]
        for page in pages_to_close:
            try:
                await page.close()
            except Exception as exc:
                warnings.warn(f"failed to close task page: {exc}", RuntimeWarning)
        try:
            if self.should_close_context:
                await self.context.close()
        except Exception as exc:
            warnings.warn(f"failed to close browser context: {exc}", RuntimeWarning)
        finally:
            if not self.connected_over_cdp:
                try:
                    await self.browser.close()
                except Exception as exc:
                    warnings.warn(f"failed to close browser connection: {exc}", RuntimeWarning)


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
    When an explicit account identity is requested (``context_kwargs["storage_state"]``),
    always create a dedicated context with those cookies instead of reusing the browser's
    active context: the active account of a shared CDP browser must never decide the
    upload identity (issue #6 — uploads could land on the wrong channel).
    """

    launch_kwargs = launch_kwargs or {}
    context_kwargs = context_kwargs or {}

    if cdp_url:
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        if context_kwargs.get("storage_state") is not None:
            # Explicit account identity wins over the CDP browser's active account:
            # create a fresh context with the requested cookies so uploads run as
            # the target account, and close only that context afterwards.
            context = await browser.new_context(**context_kwargs)
            return BrowserSession(
                browser=browser,
                context=context,
                should_close_context=True,
                initial_pages=tuple(getattr(context, "pages", ())),
                connected_over_cdp=True,
            )
        if use_existing_context and browser.contexts:
            context = browser.contexts[0]
            return BrowserSession(
                browser=browser,
                context=context,
                should_close_context=False,
                initial_pages=tuple(getattr(context, "pages", ())),
                connected_over_cdp=True,
            )
        context = await browser.new_context(**context_kwargs)
        return BrowserSession(
            browser=browser,
            context=context,
            should_close_context=True,
            initial_pages=tuple(getattr(context, "pages", ())),
            connected_over_cdp=True,
        )

    browser = await playwright.chromium.launch(**launch_kwargs)
    context = await browser.new_context(**context_kwargs)
    return BrowserSession(
        browser=browser,
        context=context,
        should_close_context=True,
        initial_pages=tuple(getattr(context, "pages", ())),
        connected_over_cdp=False,
    )


async def save_storage_state_if_owned(session: BrowserSession, path: str | Path) -> bool:
    """Persist login state only for a context created and owned by this task.

    A reused CDP context may contain unrelated accounts from the whole managed
    browser profile. Exporting that context into one platform cookie file would
    unnecessarily duplicate those secrets.
    """
    if not session.should_close_context:
        return False
    await session.context.storage_state(path=str(path))
    return True


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
