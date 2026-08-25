"""Resolve a registered browser name or port to a validated local CDP target."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class BrowserTarget:
    name: str | None
    port: int
    cdp_url: str


_FLEET_SCRIPT = Path.home() / ".codex" / "skills" / "browser-fleet-manager" / "scripts" / "browser_fleet.py"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _fleet_json(*args: str) -> dict:
    try:
        result = subprocess.run(
            [sys.executable, str(_FLEET_SCRIPT), *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("browser fleet command failed") from exc
    if result.returncode != 0:
        raise RuntimeError("browser fleet command rejected the target")
    try:
        payload = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("browser fleet returned invalid target data") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("browser fleet returned invalid target data")
    return payload


def _port(value: object) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("browser target port is invalid") from exc
    if not 1 <= port <= 65535:
        raise ValueError("browser target port must be between 1 and 65535")
    return port


def _local_cdp_url(raw_url: str) -> tuple[str, int]:
    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("browser CDP URL is invalid") from exc
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in _LOCAL_HOSTS or port is None:
        raise ValueError("browser CDP URL must target localhost")
    return raw_url, _port(port)


def _target_from_resolve(payload: dict, expected_name: str | None = None) -> BrowserTarget:
    name = payload.get("name")
    if not isinstance(name, str) or not name:
        raise RuntimeError("browser fleet target has no name")
    if expected_name is not None and name != expected_name:
        raise RuntimeError("browser fleet name conflict")
    if payload.get("status") != "running" or payload.get("health") != "ok":
        raise RuntimeError("browser target is not healthy and running")
    if payload.get("problems") not in (None, []):
        raise RuntimeError("browser target has anchor conflicts")
    port = _port(payload.get("port"))
    cdp_url = payload.get("cdp_url")
    if not isinstance(cdp_url, str):
        raise RuntimeError("browser fleet target has no CDP URL")
    cdp_url, cdp_port = _local_cdp_url(cdp_url)
    if cdp_port != port:
        raise RuntimeError("browser target port and CDP URL conflict")
    return BrowserTarget(name, port, cdp_url)


def _resolve_registered_entry(item: dict) -> BrowserTarget:
    name = item.get("name")
    if not isinstance(name, str) or not name:
        raise RuntimeError("browser target has no name")
    if item.get("status") not in {"running", "stopped"} or item.get("health") != "ok" or item.get("problems", []) != []:
        raise RuntimeError("browser target is not healthy and registered")
    if item["status"] == "stopped":
        _fleet_json("start", "--name", name)
    return _target_from_resolve(_fleet_json("resolve", "--name", name), name)


def _registered_match(audit: dict, *, name: str | None = None, port: int | None = None) -> dict:
    matches = [
        item for item in audit.get("registered", [])
        if (name is None or item.get("name") == name) and (port is None or item.get("port") == port)
    ]
    if len(matches) != 1:
        raise RuntimeError("browser target is not uniquely registered")
    return matches[0]


def _resolve_name(name: str) -> BrowserTarget:
    return _resolve_registered_entry(_registered_match(_fleet_json("audit"), name=name))


def _resolve_legacy_cdp(raw_url: str) -> BrowserTarget:
    cdp_url, port = _local_cdp_url(raw_url)
    return _resolve_registered_entry(_registered_match(_fleet_json("audit"), port=port))


def resolve_browser_target(selector: str | None, legacy_cdp_url: str | None = None) -> BrowserTarget | None:
    """Resolve one registered browser selector or localhost CDP URL."""
    selector = selector.strip() if isinstance(selector, str) and selector.strip() else None
    legacy_cdp_url = legacy_cdp_url.strip() if isinstance(legacy_cdp_url, str) and legacy_cdp_url.strip() else None
    if selector and legacy_cdp_url:
        raise ValueError("--browser and --cdp-url cannot be used together")
    if selector:
        if selector.isdigit():
            port = _port(selector)
            return _resolve_registered_entry(_registered_match(_fleet_json("audit"), port=port))
        return _resolve_name(selector)
    if legacy_cdp_url:
        return _resolve_legacy_cdp(legacy_cdp_url)
    return None


def resolve_browser_targets(
    selectors: Sequence[str] | None,
    legacy_cdp_url: str | None = None,
) -> list[BrowserTarget]:
    """Resolve ordered, unique local browser targets through the single resolver."""
    if isinstance(selectors, str):
        selectors = [selectors]
    cleaned = [selector.strip() for selector in (selectors or ()) if isinstance(selector, str) and selector.strip()]
    if cleaned and legacy_cdp_url:
        raise ValueError("--browsers and --cdp-url cannot be used together")
    if not cleaned:
        target = resolve_browser_target(None, legacy_cdp_url)
        return [target] if target is not None else []

    resolved: list[BrowserTarget] = []
    by_port: dict[int, BrowserTarget] = {}
    for selector in cleaned:
        target = resolve_browser_target(selector)
        if target is None:
            continue
        previous = by_port.get(target.port)
        if previous is not None:
            if (previous.name, previous.cdp_url) != (target.name, target.cdp_url):
                raise RuntimeError("browser targets with the same port have conflicting anchors")
            continue
        by_port[target.port] = target
        resolved.append(target)
    return resolved
