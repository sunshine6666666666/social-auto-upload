from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.parse
import zipfile
from pathlib import Path

import requests
from patchright.async_api import async_playwright

from utils.account_identity import AccountIdentity
from utils.browser_runtime import open_browser_session


GITHUB_RELEASE_API = "https://api.github.com/repos/biliup/biliup/releases/latest"

BILI_COLLECTION_LIST_API = "https://member.bilibili.com/x2/creative/web/seasons"
BILIBILI_ACCOUNT_HOME_URL = "https://account.bilibili.com/account/home"
_BILITV_APP_KEY = "4409e2ce8ffd12b8"
_BILITV_APP_SECRET = "59b43e04ad6965f34319062b478f83dd"
_BILITV_AUTH_URL = "https://passport.bilibili.com/x/passport-tv-login/qrcode/auth_code"
_BILITV_CONFIRM_URL = "https://passport.bilibili.com/x/passport-tv-login/h5/qrcode/confirm"
_BILITV_POLL_URL = "https://passport.bilibili.com/x/passport-tv-login/qrcode/poll"


def _bilibili_visible_name(body_text: str) -> str | None:
    labels = {"个人中心", "账号设置", "我的空间", "退出登录", "登录", "首页"}
    lines = [re.sub(r"\s+", " ", line).strip() for line in body_text.splitlines()]
    for line in lines:
        match = re.fullmatch(r"(.{1,80}?)\s+(?:正式会员|大会员|年度大会员|注册会员)", line)
        if match:
            return match.group(1).strip()
    center_indexes = [index for index, line in enumerate(lines) if line in {"个人中心", "账号设置"}]
    indexes = center_indexes or list(range(len(lines)))
    for center in indexes:
        for offset in (1, -1, 2, -2, 3, -3):
            index = center + offset
            if index < 0 or index >= len(lines):
                continue
            candidate = lines[index].strip(" \t:-：")
            if not candidate or candidate in labels or "UID" in candidate.upper():
                continue
            if "space.bilibili.com" in candidate or len(candidate) > 80:
                continue
            return candidate
    return None


def extract_bilibili_dom_identity(body_text: str, space_links: list[str]) -> tuple[str | None, str | None]:
    """Extract the visible account header and numeric UID from account-home DOM."""
    profile_counts: dict[str, int] = {}
    fallback_ids = set()
    for link in space_links:
        value = str(link)
        match = re.fullmatch(r"https?://space\.bilibili\.com/(\d+)/?(?:\?[^#]*)?", value)
        if match:
            uid = match.group(1)
            profile_counts[uid] = profile_counts.get(uid, 0) + 1
            continue
        match = re.search(r"https?://space\.bilibili\.com/(\d+)", value)
        if match:
            fallback_ids.add(match.group(1))
    if profile_counts:
        highest = max(profile_counts.values())
        ids = {uid for uid, count in profile_counts.items() if count == highest}
    else:
        ids = fallback_ids
    if len(ids) > 1:
        raise RuntimeError("blocked Bilibili identity: conflicting space UIDs")
    return next(iter(ids), None), _bilibili_visible_name(body_text)


def _bilibili_identity_from_observation(body_text: str, space_links: list[str], nav: object, target=None) -> AccountIdentity:
    dom_mid, dom_name = extract_bilibili_dom_identity(body_text, space_links)
    data = nav.get("data") if isinstance(nav, dict) else None
    api_mid = None
    api_name = None
    if isinstance(data, dict):
        try:
            candidate = int(data.get("mid"))
            api_mid = candidate if candidate > 0 else None
        except (TypeError, ValueError):
            api_mid = None
        api_name = data.get("uname") if isinstance(data.get("uname"), str) else None
    if dom_mid and api_mid and dom_mid != str(api_mid):
        raise RuntimeError("blocked Bilibili identity: DOM/API UIDs conflict")
    logged_in = bool(isinstance(data, dict) and data.get("isLogin") and api_mid)
    stable_id = str(api_mid) if logged_in else None
    return AccountIdentity(
        platform="bilibili",
        logged_in=logged_in,
        stable_id=stable_id,
        display_name=dom_name or api_name,
        profile_url=f"https://space.bilibili.com/{stable_id}" if stable_id else None,
        browser_name=getattr(target, "name", None),
        cdp_port=getattr(target, "port", None),
        extra={},
    )


def _normalize_bilibili_cookies(cookies: list[dict]) -> tuple[list[dict], set[str]]:
    normalized = []
    names = set()
    for cookie in cookies:
        if not isinstance(cookie, dict) or not cookie.get("name"):
            continue
        domain = str(cookie.get("domain", ""))
        if domain and domain != "bilibili.com" and not domain.endswith(".bilibili.com"):
            continue
        name = str(cookie["name"])
        names.add(name)
        normalized.append(
            {
                "name": name,
                "value": str(cookie.get("value", "")),
                "domain": domain or ".bilibili.com",
                "path": cookie.get("path", "/"),
                "expires": cookie.get("expires", 0),
                "http_only": cookie.get("http_only", cookie.get("httpOnly", False)),
                "secure": cookie.get("secure", False),
                "same_site": cookie.get("same_site", cookie.get("sameSite", "Lax")),
            }
        )
    return normalized, names


def _signed_bilitv_form(values: dict[str, str | int]) -> dict[str, str | int]:
    encoded = urllib.parse.urlencode(values)
    return {**values, "sign": hashlib.md5(f"{encoded}{_BILITV_APP_SECRET}".encode()).hexdigest()}


def _exchange_bilibili_web_cookies(
    cookies: list[dict], expected_mid: int, cdp_url: str | None = None, timeout: int = 20
) -> dict:
    normalized, names = _normalize_bilibili_cookies(cookies)
    if not {"SESSDATA", "bili_jct"}.issubset(names):
        raise RuntimeError("Bilibili CDP session lacks required login cookies")
    values = {cookie["name"]: cookie["value"] for cookie in normalized}
    cookie_header = "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in normalized)
    session = requests.Session()
    session.headers.update(
        {
            "Referer": "https://www.bilibili.com/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) BiliApp",
        }
    )
    auth = session.post(
        _BILITV_AUTH_URL,
        data=_signed_bilitv_form({"appkey": _BILITV_APP_KEY, "local_id": "0", "ts": int(time.time())}),
        timeout=timeout,
    )
    auth.raise_for_status()
    auth_payload = auth.json()
    auth_code = (auth_payload.get("data") or {}).get("auth_code") if auth_payload.get("code") == 0 else None
    if not auth_code:
        raise RuntimeError(f"Bilibili TV authorization failed: code={auth_payload.get('code')}")
    if cdp_url:
        from utils.direct_cdp import evaluate_cdp

        confirm_result = evaluate_cdp(
            cdp_url,
            BILIBILI_ACCOUNT_HOME_URL,
            f"""(async () => {{
                const response = await fetch({json.dumps(_BILITV_CONFIRM_URL)}, {{
                    method: 'POST',
                    credentials: 'include',
                    headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
                    body: new URLSearchParams({{
                        auth_code: {json.dumps(auth_code)},
                        csrf: {json.dumps(values['bili_jct'])},
                        scanning_type: '3',
                    }}).toString(),
                }});
                return {{status: response.status, payload: await response.json()}};
            }})()""",
        )
        confirm_payload = confirm_result.get("payload", {}) if isinstance(confirm_result, dict) else {}
    else:
        confirm = session.post(
            _BILITV_CONFIRM_URL,
            headers={"Cookie": cookie_header, "User-Agent": "Mozilla/5.0 BiliApp"},
            data={"auth_code": auth_code, "csrf": values["bili_jct"], "scanning_type": 3},
            timeout=timeout,
        )
        confirm.raise_for_status()
        confirm_payload = confirm.json()
    if confirm_payload.get("code") != 0:
        raise RuntimeError(f"Bilibili TV confirmation failed: code={confirm_payload.get('code')}")
    for _ in range(10):
        poll = session.post(
            _BILITV_POLL_URL,
            data=_signed_bilitv_form(
                {"appkey": _BILITV_APP_KEY, "auth_code": auth_code, "local_id": "0", "ts": int(time.time())}
            ),
            timeout=timeout,
        )
        poll.raise_for_status()
        poll_payload = poll.json()
        if poll_payload.get("code") == 0 and isinstance(poll_payload.get("data"), dict):
            payload = poll_payload["data"]
            token_info = payload.get("token_info") if isinstance(payload.get("token_info"), dict) else {}
            if str(token_info.get("mid")) != str(expected_mid):
                raise RuntimeError("blocked Bilibili identity: CDP/TV token MIDs conflict")
            if not all(token_info.get(key) for key in ("access_token", "refresh_token", "mid")):
                raise RuntimeError("Bilibili TV authorization returned incomplete token info")
            return {**payload, "platform": "BiliTV"}
        if poll_payload.get("code") != 86039:
            raise RuntimeError(f"Bilibili TV poll failed: code={poll_payload.get('code')}")
        time.sleep(1)
    raise RuntimeError("Bilibili TV authorization confirmation timed out")


def _write_bilibili_account(account_path: Path, payload: dict, mid: int, uname: str | None, target=None) -> AccountIdentity:
    token_info = payload.get("token_info") if isinstance(payload.get("token_info"), dict) else {}
    if str(token_info.get("mid")) != str(mid):
        raise RuntimeError("blocked Bilibili identity: exported token MID changed")
    cookie_info = payload.get("cookie_info") if isinstance(payload.get("cookie_info"), dict) else {}
    _, names = _normalize_bilibili_cookies(cookie_info.get("cookies", []))
    if not {"SESSDATA", "bili_jct"}.issubset(names):
        raise RuntimeError("Bilibili exported account lacks required login cookies")
    if payload.get("platform") not in {"BiliTV", "Android"} or not all(
        token_info.get(key) for key in ("access_token", "refresh_token", "mid")
    ):
        raise RuntimeError("Bilibili exported account has incomplete app credentials")
    json.dumps(payload, ensure_ascii=False)
    fd, temp_name = tempfile.mkstemp(prefix=f".{account_path.name}.", suffix=".tmp", dir=account_path.parent)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
            json.dump(payload, temp_file, ensure_ascii=False)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, account_path)
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
    return AccountIdentity(
        platform="bilibili",
        logged_in=True,
        stable_id=str(mid),
        display_name=uname,
        profile_url=f"https://space.bilibili.com/{mid}",
        browser_name=getattr(target, "name", None),
        cdp_port=getattr(target, "port", None),
        extra={},
    )


async def _export_bilibili_direct(cdp_url: str, account_path: Path, target=None) -> AccountIdentity:
    from utils.direct_cdp import evaluate_cdp, read_cdp_cookies

    expression = """(async () => {
        const navResponse = await fetch(`https://api.bilibili.com/x/web-interface/nav?t=${Date.now()}`, {
            credentials: 'include', cache: 'no-store'
        });
        const nav = await navResponse.json();
        return {
            url: location.href,
            body: document.body ? document.body.innerText : '',
            spaceLinks: Array.from(document.querySelectorAll('a[href*="space.bilibili.com/"]')).map(a => a.href),
            nav,
        };
    })()"""
    page_data = await asyncio.to_thread(evaluate_cdp, cdp_url, BILIBILI_ACCOUNT_HOME_URL, expression)
    if not isinstance(page_data, dict):
        raise RuntimeError("Bilibili direct CDP page data is unavailable")
    identity = _bilibili_identity_from_observation(
        str(page_data.get("body", "")),
        [str(link) for link in page_data.get("spaceLinks", []) if isinstance(link, str)],
        page_data.get("nav"),
        target,
    )
    if not identity.logged_in or not identity.stable_id:
        raise RuntimeError("Bilibili direct CDP session is not freshly authenticated")
    mid = int(identity.stable_id)
    cookies = await asyncio.to_thread(read_cdp_cookies, cdp_url)
    payload = await asyncio.to_thread(_exchange_bilibili_web_cookies, cookies, mid, cdp_url)
    result = _write_bilibili_account(account_path, payload, mid, identity.display_name, target)
    result.extra["identity_transport"] = "direct-cdp"
    result.extra["focus_fallback_used"] = False
    return result


async def get_bilibili_cdp_identity(cdp_url: str, target=None) -> AccountIdentity:
    """Read Bilibili's current login identity without exchanging or writing credentials."""
    try:
        async with async_playwright() as playwright:
            session = await open_browser_session(playwright, cdp_url=cdp_url)
            read_success = False
            try:
                new_task_page = getattr(session, "new_task_page", None)
                page = await new_task_page() if callable(new_task_page) else await session.context.new_page()
                await page.goto(BILIBILI_ACCOUNT_HOME_URL, wait_until="domcontentloaded", timeout=90000)
                body_text = ""
                space_links: list[str] = []
                try:
                    body_text = await page.locator("body").inner_text()
                except Exception:
                    pass
                try:
                    space_links = await page.locator('a[href*="space.bilibili.com/"]').evaluate_all(
                        "elements => elements.map(element => element.href)"
                    )
                except Exception:
                    pass
                nav = await page.evaluate(
                    """async () => {
                        const response = await fetch(`https://api.bilibili.com/x/web-interface/nav?t=${Date.now()}`, {
                            credentials: 'include', cache: 'no-store'
                        });
                        return await response.json();
                    }"""
                )
                identity = _bilibili_identity_from_observation(body_text, space_links, nav, target)
                identity.extra["focus_fallback_used"] = bool(
                    getattr(session, "focus_fallback_used", False)
                )
                read_success = True
                return identity
            finally:
                await session.close(success=read_success)
    except Exception:
        try:
            from utils.direct_cdp import evaluate_cdp

            expression = """(async () => {
                const response = await fetch(`https://api.bilibili.com/x/web-interface/nav?t=${Date.now()}`, {
                    credentials: 'include', cache: 'no-store'
                });
                return {
                    body: document.body ? document.body.innerText : '',
                    spaceLinks: Array.from(document.querySelectorAll('a[href*="space.bilibili.com/"]')).map(a => a.href),
                    nav: await response.json(),
                };
            })()"""
            page_data = await asyncio.to_thread(evaluate_cdp, cdp_url, BILIBILI_ACCOUNT_HOME_URL, expression)
            if not isinstance(page_data, dict):
                raise RuntimeError("Bilibili direct CDP page data is unavailable")
            identity = _bilibili_identity_from_observation(
                str(page_data.get("body", "")),
                [str(link) for link in page_data.get("spaceLinks", []) if isinstance(link, str)],
                page_data.get("nav"),
                target,
            )
            identity.extra["identity_transport"] = "direct-cdp"
            identity.extra["focus_fallback_used"] = False
            return identity
        except Exception as direct_exc:
            raise RuntimeError("Bilibili identity could not be read from Patchright or direct CDP") from direct_exc


async def export_bilibili_cdp_account(cdp_url: str, account_file: Path, target=None) -> AccountIdentity:
    """Export Bilibili cookies/identity from CDP, with a direct-CDP identity fallback."""
    account_path = Path(account_file)
    account_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with async_playwright() as playwright:
            try:
                session = await open_browser_session(playwright, cdp_url=cdp_url)
            except Exception:
                return await _export_bilibili_direct(cdp_url, account_path, target)
            export_success = False
            try:
                new_task_page = getattr(session, "new_task_page", None)
                page = await new_task_page() if callable(new_task_page) else await session.context.new_page()
                await page.goto(BILIBILI_ACCOUNT_HOME_URL, wait_until="domcontentloaded", timeout=90000)
                body_text = ""
                space_links: list[str] = []
                try:
                    body_text = await page.locator("body").inner_text()
                except Exception:
                    pass
                try:
                    space_links = await page.locator('a[href*="space.bilibili.com/"]').evaluate_all(
                        "elements => elements.map(element => element.href)"
                    )
                except Exception:
                    pass
                if not body_text and not space_links:
                    try:
                        dom_data = await page.evaluate(
                            "() => ({body: document.body ? document.body.innerText : '', spaceLinks: Array.from(document.querySelectorAll('a[href*=\"space.bilibili.com/\"]')).map(a => a.href)})"
                        )
                        if isinstance(dom_data, dict):
                            body_text = str(dom_data.get("body", ""))
                            space_links = [str(link) for link in dom_data.get("spaceLinks", []) if isinstance(link, str)]
                    except Exception:
                        pass
                nav = None
                try:
                    nav = await page.evaluate(
                        """async () => {
                            const response = await fetch(`https://api.bilibili.com/x/web-interface/nav?t=${Date.now()}`, {
                                credentials: 'include', cache: 'no-store'
                            });
                            return await response.json();
                        }"""
                    )
                except Exception:
                    pass
                identity = _bilibili_identity_from_observation(body_text, space_links, nav, target)
                if not identity.logged_in or not identity.stable_id:
                    raise RuntimeError("Bilibili CDP session is not freshly authenticated")
                context = session.context
                cookies = await context.cookies(["https://account.bilibili.com", "https://member.bilibili.com", "https://www.bilibili.com"])
                mid = int(identity.stable_id)
                payload = await asyncio.to_thread(_exchange_bilibili_web_cookies, cookies, mid, cdp_url)
                result = _write_bilibili_account(account_path, payload, mid, identity.display_name, target)
                result.extra["focus_fallback_used"] = bool(
                    getattr(session, "focus_fallback_used", False)
                )
                export_success = True
                return result
            finally:
                await session.close(success=export_success)
    except RuntimeError as exc:
        if "DOM/API UIDs conflict" not in str(exc):
            raise
        try:
            return await _export_bilibili_direct(cdp_url, account_path, target)
        except Exception:
            raise exc
    except Exception as exc:
        raise RuntimeError("Bilibili CDP identity/export failed") from exc


def read_bilibili_account_identity(account_file: Path, target=None) -> AccountIdentity:
    account_path = Path(account_file)
    try:
        payload = json.loads(account_path.read_text(encoding="utf-8"))
        mid = int((payload.get("token_info") or {}).get("mid"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Bilibili account file has no stable MID") from exc
    if mid <= 0:
        raise RuntimeError("Bilibili account file has no stable MID")
    return AccountIdentity(
        platform="bilibili",
        logged_in=True,
        stable_id=str(mid),
        display_name=(payload.get("user") or {}).get("uname") if isinstance(payload.get("user"), dict) else None,
        profile_url=f"https://space.bilibili.com/{mid}",
        browser_name=getattr(target, "name", None),
        cdp_port=getattr(target, "port", None),
        extra={},
    )


def _read_biliup_cookie_str(account_file: Path) -> str:
    """Build a Cookie header string from a biliup account JSON file (never printed)."""
    import json

    data = json.loads(Path(account_file).read_text(encoding="utf-8"))
    cookie_info = data.get("cookie_info", {})
    raw_cookies = cookie_info.get("cookies", [])
    if isinstance(raw_cookies, dict):
        raw_cookies = [raw_cookies]
    pairs = []
    for entry in raw_cookies:
        if isinstance(entry, dict) and entry.get("name"):
            pairs.append(f"{entry['name']}={entry.get('value', '')}")
        elif isinstance(entry, str):
            pairs.append(entry)
    return "; ".join(p for p in pairs if p)


def resolve_bilibili_season_id(account_file: Path, collection_name: str, timeout: int = 20) -> int:
    """Resolve a Bilibili collection (合集/series) name to its season id using the account cookie.

    Raises RuntimeError when the account is missing, the API fails, or no collection
    matches the requested name.
    """
    import json

    account_path = Path(account_file)
    if not account_path.exists():
        raise RuntimeError(f"Bilibili account file is missing: {account_path}")
    if not collection_name or not collection_name.strip():
        raise RuntimeError("collection name must not be empty")

    cookie_str = _read_biliup_cookie_str(account_path)
    if not cookie_str:
        raise RuntimeError(f"Bilibili account file contains no cookies: {account_path}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
        "Cookie": cookie_str,
        "Referer": "https://member.bilibili.com/platform/upload-manager/ep",
        "Origin": "https://member.bilibili.com",
        "Accept": "application/json, text/plain, */*",
    }
    params = {"pn": 1, "ps": 50, "order": "", "sort": "", "draft": 1, "source": 0}
    response = requests.get(BILI_COLLECTION_LIST_API, headers=headers, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Bilibili collection list API failed: code={payload.get('code')} msg={payload.get('message')}")

    seasons = (payload.get("data") or {}).get("seasons") or []
    needle = collection_name.strip()
    for item in seasons:
        inner = item.get("season") or {}
        if inner.get("title") == needle:
            season_id = inner.get("id")
            if not season_id:
                raise RuntimeError(f"Bilibili collection '{needle}' has no season id")
            return int(season_id)

    available = [str((item.get("season") or {}).get("title")) for item in seasons]
    raise RuntimeError(
        f"Bilibili collection '{needle}' not found. Available collections: {', '.join(a for a in available if a) or 'none'}"
    )


def resolve_bilibili_section_id(account_file: Path, season_id: int, timeout: int = 20) -> int:
    """Resolve the default section id of a Bilibili collection (needed by episodes/add)."""
    account_path = Path(account_file)
    cookie_str = _read_biliup_cookie_str(account_path)
    if not cookie_str:
        raise RuntimeError(f"Bilibili account file contains no cookies: {account_path}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/151.0 Safari/537.36",
        "Cookie": cookie_str,
        "Referer": "https://member.bilibili.com/platform/upload-manager/ep",
        "Origin": "https://member.bilibili.com",
        "Accept": "application/json, text/plain, */*",
    }
    response = requests.get(
        f"https://member.bilibili.com/x2/creative/web/season?id={season_id}",
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Bilibili season detail API failed: code={payload.get('code')} msg={payload.get('message')}")
    sections = (payload.get("data") or {}).get("sections") or {}
    if isinstance(sections, dict):
        sections = sections.get("sections") or []
    for sec in sections:
        if isinstance(sec, dict):
            sid = sec.get("id") or sec.get("section_id")
            if sid:
                return int(sid)
    raise RuntimeError(f"Bilibili season {season_id} has no section")


def read_bilibili_archive_matches(account_file: Path, title: str, timeout: int = 20, attempts: int = 8) -> list[dict]:
    """Read exact-title archive evidence without returning cookies or page text."""
    import time

    account_path = Path(account_file)
    cookie_str = _read_biliup_cookie_str(account_path)
    if not cookie_str:
        raise RuntimeError(f"Bilibili account file contains no cookies: {account_path}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/151.0 Safari/537.36",
        "Cookie": cookie_str,
        "Referer": "https://member.bilibili.com/platform/upload-manager/ep",
        "Origin": "https://member.bilibili.com",
        "Accept": "application/json, text/plain, */*",
    }
    params = {"pn": 1, "ps": 10}
    needle = title.strip()
    last_error = ""
    for attempt in range(attempts):
        response = requests.get(
            "https://member.bilibili.com/x2/creative/web/archives/sp",
            headers=headers,
            params=params,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            last_error = f"code={payload.get('code')} msg={payload.get('message')}"
            time.sleep(3)
            continue
        archives = (payload.get("data") or {}).get("arc_audits") or []
        matches = []
        for archive in archives:
            if isinstance(archive, dict):
                inner = archive.get("Archive") or archive
                if (inner.get("title") or "").strip() == needle:
                    aid = inner.get("aid") or inner.get("id")
                    if aid:
                        matches.append(
                            {
                                "aid": int(aid),
                                "title": str(inner.get("title") or ""),
                                "state": inner.get("state") or inner.get("status") or inner.get("audit_status"),
                                "dtime": inner.get("dtime") or inner.get("pubtime") or None,
                                "cover_present": bool(inner.get("cover") or inner.get("pic") or inner.get("cover_url")),
                            }
                        )
        if matches:
            return matches
        if attempt + 1 < attempts:
            time.sleep(3)
    if attempts == 1:
        return []
    raise RuntimeError(
        f"Bilibili archive with title '{needle}' not found in creator archive list"
        + (f" ({last_error})" if last_error else "")
    )


def find_bilibili_archive_aid(account_file: Path, title: str, timeout: int = 20, attempts: int = 8) -> int:
    matches = read_bilibili_archive_matches(account_file, title, timeout=timeout, attempts=attempts)
    if len(matches) != 1:
        raise RuntimeError(f"Bilibili archive title matched {len(matches)} records; expected exactly one")
    return int(matches[0]["aid"])


def fetch_bilibili_archive_cid(account_file: Path, aid: int, timeout: int = 20) -> int:
    """Fetch the first cid of an archive (needed by the collection episodes/add API)."""
    account_path = Path(account_file)
    cookie_str = _read_biliup_cookie_str(account_path)
    if not cookie_str:
        raise RuntimeError(f"Bilibili account file contains no cookies: {account_path}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/151.0 Safari/537.36",
        "Cookie": cookie_str,
        "Referer": "https://member.bilibili.com/platform/upload-manager/ep",
        "Origin": "https://member.bilibili.com",
        "Accept": "application/json, text/plain, */*",
    }
    response = requests.get(
        f"https://member.bilibili.com/x/web/archive/videos?aid={aid}",
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Bilibili archive videos API failed: code={payload.get('code')} msg={payload.get('message')}")
    videos = (payload.get("data") or {}).get("videos") or []
    for video in videos:
        if isinstance(video, dict) and video.get("cid"):
            return int(video["cid"])
    raise RuntimeError(f"Bilibili archive {aid} has no videos")


def add_archive_to_season(
    account_file: Path,
    aid: int,
    cid: int,
    title: str,
    section_id: int,
    timeout: int = 20,
) -> None:
    """Add an archive to a Bilibili collection via the creator episodes/add API."""
    import json as _json

    account_path = Path(account_file)
    cookie_str = _read_biliup_cookie_str(account_path)
    if not cookie_str:
        raise RuntimeError(f"Bilibili account file contains no cookies: {account_path}")
    csrf = ""
    for entry in _json.loads(Path(account_path).read_text(encoding="utf-8")).get("cookie_info", {}).get("cookies", []):
        if isinstance(entry, dict) and entry.get("name") == "bili_jct":
            csrf = entry.get("value", "")
            break
    if not csrf:
        raise RuntimeError("Bilibili account file has no bili_jct csrf cookie")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/151.0 Safari/537.36",
        "Cookie": cookie_str,
        "Referer": "https://member.bilibili.com/platform/upload-manager/ep",
        "Origin": "https://member.bilibili.com",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
    }
    body = {
        "sectionId": section_id,
        "episodes": [
            {
                "title": title,
                "aid": aid,
                "cid": cid,
                "charging_pay": 0,
                "member_first": 0,
                "limited_free": False,
            }
        ],
    }
    response = requests.post(
        f"https://member.bilibili.com/x2/creative/web/season/section/episodes/add?csrf={csrf}",
        headers=headers,
        json=body,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(
            f"Bilibili add-to-collection API failed: code={payload.get('code')} msg={payload.get('message')}"
        )


def get_biliup_runtime_root() -> Path:
    return Path.home() / ".social-auto-upload" / "tools" / "biliup"


def _normalize_system(system_name: str | None = None) -> str:
    system_value = (system_name or platform.system()).strip().lower()
    if system_value == "darwin":
        return "macos"
    return system_value


def _normalize_machine(machine_name: str | None = None) -> str:
    machine_value = (machine_name or platform.machine()).strip().lower()
    aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "arm64": "aarch64",
    }
    return aliases.get(machine_value, machine_value)


def _build_platform_key(system_name: str | None = None, machine_name: str | None = None) -> str:
    return f"{_normalize_system(system_name)}-{_normalize_machine(machine_name)}"


def build_biliup_runtime_path(system_name: str | None = None) -> Path:
    executable_name = "biliup.exe" if _normalize_system(system_name) == "windows" else "biliup"
    return get_biliup_runtime_root() / _build_platform_key(system_name) / executable_name


def _build_biliup_version_path(system_name: str | None = None) -> Path:
    return build_biliup_runtime_path(system_name).with_name("version.txt")


def _select_release_asset(assets: list[dict]) -> dict:
    platform_key = _build_platform_key()
    preferred_patterns = {
        "windows-x86_64": ("x86_64-windows.zip",),
        "linux-x86_64": ("x86_64-linux.tar.xz",),
        "linux-aarch64": ("aarch64-linux.tar.xz",),
        "linux-arm": ("arm-linux.tar.xz",),
        "macos-x86_64": ("x86_64-macos.tar.xz",),
        "macos-aarch64": ("aarch64-macos.tar.xz",),
    }
    patterns = preferred_patterns.get(platform_key)
    if not patterns:
        raise RuntimeError(f"Unsupported biliup platform: {platform_key}")

    for asset in assets:
        asset_name = asset.get("name", "")
        if any(pattern in asset_name for pattern in patterns):
            return {
                "asset_name": asset_name,
                "asset_url": asset.get("browser_download_url", ""),
            }

    raise RuntimeError(f"No matching biliup release asset found for platform: {platform_key}")


def fetch_latest_release() -> dict:
    response = requests.get(
        GITHUB_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "social-auto-upload",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    selected_asset = _select_release_asset(payload.get("assets", []))
    return {
        "tag_name": payload.get("tag_name", ""),
        "asset_name": selected_asset["asset_name"],
        "asset_url": selected_asset["asset_url"],
    }


def read_local_biliup_version() -> str | None:
    version_path = _build_biliup_version_path()
    if not version_path.exists():
        return None
    return version_path.read_text(encoding="utf-8").strip() or None


def write_local_biliup_version(version: str) -> None:
    version_path = _build_biliup_version_path()
    version_path.parent.mkdir(parents=True, exist_ok=True)
    version_path.write_text(version, encoding="utf-8")


def _pick_executable(extract_root: Path) -> Path:
    candidates = []
    for path in extract_root.rglob("*"):
        if not path.is_file():
            continue
        lower_name = path.name.lower()
        if lower_name in {"biliup", "biliup.exe", "biliupr", "biliupr.exe"}:
            candidates.append(path)
    if not candidates:
        raise RuntimeError("Downloaded biliup archive does not contain a runnable executable")
    candidates.sort(key=lambda item: len(str(item)))
    return candidates[0]


def download_biliup_asset(release: dict, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="biliup-download-") as temp_dir:
        temp_root = Path(temp_dir)
        archive_path = temp_root / release["asset_name"]
        with requests.get(release["asset_url"], stream=True, timeout=120) as response:
            response.raise_for_status()
            with archive_path.open("wb") as file_obj:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file_obj.write(chunk)

        extract_root = temp_root / "extract"
        extract_root.mkdir(parents=True, exist_ok=True)
        if archive_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive_path) as zip_file:
                zip_file.extractall(extract_root)
        else:
            with tarfile.open(archive_path, "r:xz") as tar_file:
                tar_file.extractall(extract_root)

        extracted_binary = _pick_executable(extract_root)
        temp_binary = destination.with_suffix(f"{destination.suffix}.tmp")
        shutil.copy2(extracted_binary, temp_binary)
        temp_binary.replace(destination)
        if _normalize_system() != "windows":
            destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return destination


def ensure_biliup_binary(force_check: bool = True) -> Path:
    binary_path = build_biliup_runtime_path()
    local_version = read_local_biliup_version()

    # 默认优先复用本地已存在的 biliup，避免每次执行都去请求 GitHub latest release。
    if binary_path.exists() and not force_check:
        return binary_path

    try:
        release = fetch_latest_release()
    except Exception:
        # 如果本地已经有可执行的 biliup，就在 GitHub 限流/网络失败时直接复用本地版本。
        if binary_path.exists():
            return binary_path
        raise

    latest_version = release["tag_name"]
    if binary_path.exists() and local_version == latest_version:
        return binary_path

    download_biliup_asset(release, binary_path)
    write_local_biliup_version(latest_version)
    return binary_path


def run_biliup_command(arguments: list[str], interactive: bool = False) -> subprocess.CompletedProcess[str]:
    binary_path = ensure_biliup_binary(force_check=False)
    command = [str(binary_path), *arguments]
    if interactive:
        return subprocess.run(command, check=False)
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
