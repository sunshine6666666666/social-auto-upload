"""Small, dependency-free CDP reader used when Patchright cannot attach.

The project declares ``websocket-client`` for normal installations.  The
managed runtime used by the CLI may not have that optional wheel installed,
so this helper uses Node's built-in WebSocket implementation as a local
fallback.  It talks only to the caller-supplied localhost CDP endpoint and
never logs protocol results (which may contain cookies).
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
import warnings
from typing import Any


_NODE_RPC = r"""
import { readFileSync } from "node:fs";

const request = JSON.parse(readFileSync(0, "utf8"));
const socket = new WebSocket(request.ws_url);
let done = false;
const finish = (code, value) => {
  if (done) return;
  done = true;
  if (value !== undefined) process.stdout.write(JSON.stringify(value));
  try { socket.close(); } catch (_) {}
  process.exit(code);
};
const timer = setTimeout(() => finish(2), request.timeout_ms || 15000);
socket.addEventListener("open", () => {
  socket.send(JSON.stringify({
    id: 1,
    method: request.method,
    params: request.params || {},
    ...(request.session_id ? {sessionId: request.session_id} : {}),
  }));
});
socket.addEventListener("message", (event) => {
  let message;
  try { message = JSON.parse(String(event.data)); } catch (_) { return; }
  if (message.id !== 1) return;
  clearTimeout(timer);
  finish(0, message);
});
socket.addEventListener("error", () => finish(3));
"""


def _get_json(url: str) -> dict[str, Any] | list[Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _rpc(ws_url: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = json.dumps(
        {
            "ws_url": ws_url,
            "method": method,
            "params": params or {},
            "timeout_ms": 15000,
        },
        ensure_ascii=False,
    )
    try:
        result = subprocess.run(
            ["node", "--no-warnings", "--input-type=module", "-e", _NODE_RPC],
            input=payload,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("direct CDP transport unavailable") from exc
    if result.returncode != 0:
        raise RuntimeError("direct CDP request failed")
    try:
        message = json.loads(result.stdout)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("direct CDP returned invalid response") from exc
    if message.get("error"):
        raise RuntimeError(f"direct CDP method failed: {method}")
    value = message.get("result")
    return value if isinstance(value, dict) else {}


def _targets(cdp_url: str) -> list[dict[str, Any]]:
    value = _get_json(f"{cdp_url.rstrip('/')}/json/list")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _browser_ws(cdp_url: str) -> str:
    value = _get_json(f"{cdp_url.rstrip('/')}/json/version")
    ws_url = value.get("webSocketDebuggerUrl") if isinstance(value, dict) else None
    if not isinstance(ws_url, str) or not ws_url:
        raise RuntimeError("CDP browser websocket is unavailable")
    return ws_url


def _close_target_quietly(cdp_url: str, target_id: str) -> None:
    try:
        _rpc(_browser_ws(cdp_url), "Target.closeTarget", {"targetId": target_id})
    except Exception as exc:
        warnings.warn(f"direct CDP could not close task target {target_id}: {exc}", RuntimeWarning)


def _target_for_url(cdp_url: str, target_url: str) -> tuple[dict[str, Any], bool]:
    target = None
    target_id = None
    for candidate in _targets(cdp_url):
        if candidate.get("type") != "page" or not candidate.get("webSocketDebuggerUrl"):
            continue
        if candidate.get("url", "").rstrip("/") == target_url.rstrip("/"):
            target = candidate
            break
    if target is None:
        browser_ws = _browser_ws(cdp_url)
        created = _rpc(
            browser_ws,
            "Target.createTarget",
            {"url": target_url, "background": True},
        )
        target_id = created.get("targetId")
        if not target_id:
            raise RuntimeError("direct CDP could not create an identity tab")
        for _ in range(20):
            target = next((item for item in _targets(cdp_url) if item.get("id") == target_id), None)
            if target and target.get("webSocketDebuggerUrl"):
                break
            time.sleep(0.1)
    if not target or not target.get("webSocketDebuggerUrl"):
        if target_id:
            _close_target_quietly(cdp_url, target_id)
        raise RuntimeError("direct CDP identity tab is unavailable")
    return target, target_id is not None


def evaluate_cdp(cdp_url: str, target_url: str, expression: str) -> Any:
    """Evaluate a value in a page selected by URL, without exposing the value."""
    target, created_by_call = _target_for_url(cdp_url, target_url)
    try:
        current_url = str(target.get("url", ""))
        if current_url.rstrip("/") != target_url.rstrip("/"):
            _rpc(target["webSocketDebuggerUrl"], "Page.navigate", {"url": target_url})
            time.sleep(2)
        result = _rpc(
            target["webSocketDebuggerUrl"],
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        remote = result.get("result") if isinstance(result, dict) else None
        if not isinstance(remote, dict):
            raise RuntimeError("direct CDP evaluation returned no value")
        if remote.get("subtype") == "error" or remote.get("type") == "undefined":
            raise RuntimeError("direct CDP evaluation failed")
        return remote.get("value")
    finally:
        if created_by_call:
            _close_target_quietly(cdp_url, target["id"])


def read_cdp_cookies(cdp_url: str) -> list[dict[str, Any]]:
    """Read browser cookies for an internal caller; the function never prints them."""
    result = _rpc(_browser_ws(cdp_url), "Storage.getCookies")
    cookies = result.get("cookies") if isinstance(result, dict) else None
    return [item for item in cookies if isinstance(item, dict)] if isinstance(cookies, list) else []


def read_page_snapshot(cdp_url: str, target_url: str) -> dict[str, Any]:
    """Return only DOM metadata needed by identity extractors."""
    value = evaluate_cdp(
        cdp_url,
        target_url,
        """(() => ({
            url: location.href,
            title: document.title || '',
            body: document.body ? document.body.innerText : '',
            html: document.documentElement ? document.documentElement.outerHTML : '',
            spaceLinks: Array.from(document.querySelectorAll('a[href*="space.bilibili.com/"]')).map(a => a.href),
            douyinHeaderName: (() => {
                const handle = Array.from(document.querySelectorAll('*')).find(
                    element => (element.innerText || '').trim().match(/^抖音号\s*[:：]\s*[A-Za-z0-9_-]+$/)
                );
                const lines = (handle?.parentElement?.innerText || '').split(/\n/).map(item => item.trim()).filter(Boolean);
                return lines.find(item => !/^抖音号\s*[:：]\s*[A-Za-z0-9_-]+$/.test(item)) || null;
            })(),
            youtubeChannelName: (() => {
                const lines = (document.querySelector('.thumbnail-wrapper-channel')?.innerText || '')
                    .split(/\n/).map(item => item.trim()).filter(Boolean);
                return lines.reverse().find(item => !['我的频道', 'Your channel'].includes(item)) || null;
            })(),
        }))()""",
    )
    return value if isinstance(value, dict) else {}
