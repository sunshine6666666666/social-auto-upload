# -*- coding: utf-8 -*-
"""YouTube uploader (browser automation via YouTube Studio).

Unlike the other platforms here, YouTube also offers an official Data API. We deliberately
use browser automation instead, because videos uploaded through an *unaudited* API project
are force-locked to private and cannot be made public without passing Google's compliance
audit (which is impractical for personal/single-channel use). Browser automation has no such
restriction and can publish public videos right away, and it matches the cookie-based pattern
used by every other uploader in this project.

Login is interactive (Google account, no QR code): the browser opens, the user signs in, and
the storage_state is saved. Reuse it afterwards for fully unattended uploads.
"""
import asyncio
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from patchright.async_api import Page, Playwright, async_playwright

from conf import DEBUG_MODE
from uploader.base_video import BaseVideoUploader
from utils.base_social_media import set_init_script
from utils.log import youtube_logger
from utils.browser_runtime import (
    open_browser_session,
    requires_local_cdp_file_input,
    save_storage_state_if_owned,
    set_local_file_input_via_cdp,
)
from utils.account_identity import AccountIdentity, assert_same_publish_identity, identity_matches, require_publish_identity

try:
    # 国内直连 youtube.com 会超时，且 patchright 启的 chromium 不吃系统代理。
    # 在 conf.py 设 YT_PROXY = "http://127.0.0.1:7890"（本地代理端口）即可；不设则不走代理。
    from conf import YT_PROXY
except Exception:
    YT_PROXY = None

STUDIO_URL = "https://studio.youtube.com"
UPLOAD_URL = "https://www.youtube.com/upload"
VISIBILITY = {"public": "PUBLIC", "unlisted": "UNLISTED", "private": "PRIVATE"}
SCHEDULE_BUTTON_SELECTOR = (
    "ytcp-video-visibility-select #second-container-expand-button, "
    "#schedule-button, ytcp-button#schedule-button, "
    "ytcp-button:has-text('Schedule'), ytcp-button:has-text('安排时间'), "
    "ytcp-button:has-text('预定'), ytcp-button:has-text('安排'), "
    "[aria-label*='Schedule'], [aria-label*='安排'], [aria-label*='预定']"
)


def _youtube_context_kwargs(account_file: str, cdp_url: str | None) -> dict[str, str]:
    return {} if cdp_url else {"storage_state": account_file}


def _msg(emoji: str, text: str) -> str:
    return f"{emoji} {text}"


def _normalize_schedule(expected_schedule: datetime, timezone: str) -> datetime:
    zone = ZoneInfo(timezone)
    if expected_schedule.tzinfo is None:
        return expected_schedule.replace(tzinfo=zone)
    return expected_schedule.astimezone(zone)


# Explicit processing-failure markers that must poison an otherwise "scheduled" readback.
# Studio may keep showing a scheduled time while the video itself failed processing
# (e.g. "处理中断 · 视频过长"); treating only SCHEDULED_PUBLISHING_STATUS_SCHEDULED as
# success then yields a false success receipt. Markers cover both Studio UI strings
# (zh/en) and structured CreatorVideoData fields (unescaped after html.replace(r'\"', '"')).
PROCESSING_FAILURE_MARKERS: tuple[str, ...] = (
    # UI / banner text
    "处理中断",
    "处理失败",
    "处理出错",
    "视频过长",
    "无法处理",
    "processing interrupted",
    "processing failed",
    "video too long",
    "failed to process",
    # structured CreatorVideoData fields
    "processingFailureCode",
    "PROCESSING_STATUS_FAILED",
    '"processingStatus":"FAILED"',
)


def find_processing_failure(payload: str, html: str = "") -> str | None:
    """Return the first recognized processing-failure marker, else None.

    `payload` is the unescaped Studio evidence; `html` is the raw page content and is
    checked as a fallback for UI text that does not survive the unescape step.
    """
    for marker in PROCESSING_FAILURE_MARKERS:
        if marker in payload or marker in html:
            return marker
    return None


def parse_scheduled_publish_readback(
    html: str, *, expected_schedule: datetime, timezone: str
) -> dict[str, str | int]:
    """Read Studio's embedded CreatorVideoData and reject incomplete/mismatched scheduling evidence."""
    payload = html.replace(r'\"', '"')
    video_match = re.search(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"', payload)
    if not video_match:
        # Legacy upload-dialog payloads expose entity_id; constrain it to a video ID
        # so a preceding 24-char channel ID cannot be returned as the publish URL.
        video_match = re.search(r'"entity_id"\s*:\s*"([A-Za-z0-9_-]{11})"', payload)
    seconds_match = re.search(r'"scheduledTimeSeconds"\s*:\s*"?(\d+)"?', payload)
    if not video_match:
        raise RuntimeError("YouTube Studio readback did not include a video ID")
    if not seconds_match:
        raise RuntimeError("YouTube Studio readback did not include scheduledTimeSeconds")
    if "SCHEDULED_PUBLISHING_STATUS_SCHEDULED" not in payload:
        raise RuntimeError("YouTube Studio readback did not confirm scheduled visibility")

    failure_marker = find_processing_failure(payload, html)
    if failure_marker is not None:
        raise RuntimeError(
            "YouTube Studio reports video processing failure "
            f"({failure_marker!r}); scheduled readback is a false success"
        )

    scheduled_seconds = int(seconds_match.group(1))
    actual = datetime.fromtimestamp(scheduled_seconds, tz=ZoneInfo(timezone))
    expected = _normalize_schedule(expected_schedule, timezone)
    if actual != expected:
        raise RuntimeError(
            f"YouTube Studio scheduled time {actual.isoformat()} does not match requested {expected.isoformat()}"
        )

    video_id = video_match.group(1)
    return {
        "videoId": video_id,
        "publishUrl": f"https://www.youtube.com/watch?v={video_id}",
        "visibility": "scheduled",
        "scheduledTimeSeconds": scheduled_seconds,
        "scheduledAt": actual.isoformat(),
        "timezone": timezone,
    }


def extract_youtube_draft_reference(html: str) -> dict[str, str]:
    """Extract a video-only draft reference without mistaking a channel ID for it."""
    patterns = (
        r"(?:[\"']video-id[\"']|\bvideo-id)\s*[:=]\s*[\"']([A-Za-z0-9_-]{11})[\"']",
        r"[\"']videoId[\"']\s*:\s*[\"']([A-Za-z0-9_-]{11})[\"']",
        r"(?:youtu\.be/|watch\?v=)([A-Za-z0-9_-]{11})",
    )
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            video_id = match.group(1)
            return {
                "videoId": video_id,
                "publishUrl": f"https://www.youtube.com/watch?v={video_id}",
            }
    return {}


async def readback_scheduled_publication(
    page: Page,
    *,
    expected_schedule: datetime,
    timezone: str,
    max_polls: int = 24,
    poll_ms: int = 2500,
) -> dict[str, str | int]:
    """Read back scheduling from the edit page when the upload wizard lacks CreatorVideoData."""
    navigated_to_edit = False
    last_error: RuntimeError | None = None
    for attempt in range(max_polls):
        html = await page.content()
        try:
            return parse_scheduled_publish_readback(
                html, expected_schedule=expected_schedule, timezone=timezone
            )
        except RuntimeError as exc:
            last_error = exc

        if not navigated_to_edit:
            video_match = re.search(
                r"(?:youtu\.be/|watch\?v=)([A-Za-z0-9_-]{11})|video-id=[\"']([A-Za-z0-9_-]{11})[\"']",
                html,
            )
            if video_match:
                video_id = video_match.group(1) or video_match.group(2)
                await page.goto(
                    f"{STUDIO_URL}/video/{video_id}/edit", wait_until="domcontentloaded"
                )
                navigated_to_edit = True
                continue
        if attempt + 1 < max_polls:
            await page.wait_for_timeout(poll_ms)

    raise last_error or RuntimeError("YouTube Studio scheduled readback did not become available")


def _build_login_result(success, status, message, account_file, current_url=""):
    return {
        "success": success,
        "status": status,
        "message": message,
        "account_file": str(account_file),
        "current_url": current_url,
    }


async def cookie_auth(account_file, cdp_url: str | None = None) -> bool:
    """登录态是否仍有效：打开 Studio，没被踢到 Google 登录页且进入了频道页即有效。"""
    async with async_playwright() as playwright:
        session = await open_browser_session(
            playwright,
            cdp_url=cdp_url,
            launch_kwargs={"headless": True, "channel": "chrome"},
            context_kwargs=_youtube_context_kwargs(account_file, cdp_url),
        )
        try:
            context = session.context
            context = await set_init_script(context)
            page = await session.new_task_page()
            await page.goto(STUDIO_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            identity = await extract_youtube_identity(page)
            return identity.logged_in and bool(identity.stable_id)
        except Exception:
            return False
        finally:
            await session.close()


async def extract_youtube_identity(page: Page, *, browser_name: str | None = None, cdp_port: int | None = None) -> AccountIdentity:
    """Extract channel identity from the current Studio page, never from an account filename."""
    html = await page.content()
    url = page.url
    stable_id = None
    for pattern, source in (
        (r"/channel/(UC[A-Za-z0-9_-]+)", url),
        (r'"(?:channelId|externalId|ownerChannelId)"\s*:\s*"(UC[A-Za-z0-9_-]+)"', html),
    ):
        match = re.search(pattern, source)
        if match:
            stable_id = match.group(1)
            break
    handle_match = re.search(r"/@([A-Za-z0-9._-]+)", url)
    display_name = None
    try:
        channel_text = await page.locator(".thumbnail-wrapper-channel").first.inner_text()
        names = [line.strip() for line in channel_text.splitlines() if line.strip()]
        display_name = next((line for line in reversed(names) if line not in {"我的频道", "Your channel"}), None)
    except Exception:
        pass
    logged_in = bool(stable_id) and "accounts.google.com" not in url and "/signin" not in url.lower()
    return AccountIdentity(
        platform="youtube",
        logged_in=logged_in,
        stable_id=stable_id,
        display_name=display_name,
        handle=f"@{handle_match.group(1)}" if handle_match else None,
        profile_url=f"https://www.youtube.com/channel/{stable_id}" if stable_id else None,
        browser_name=browser_name,
        cdp_port=cdp_port,
        extra={},
    )


async def get_youtube_account_identity(
    cdp_url: str | None = None,
    *,
    browser_name: str | None = None,
    cdp_port: int | None = None,
) -> AccountIdentity:
    try:
        async with async_playwright() as playwright:
            session = await open_browser_session(
                playwright,
                cdp_url=cdp_url,
                launch_kwargs={"headless": True, "channel": "chrome"},
            )
            try:
                context = await set_init_script(session.context)
                page = await session.new_task_page()
                await page.goto(STUDIO_URL, wait_until="domcontentloaded")
                await page.wait_for_timeout(2500)
                return await extract_youtube_identity(page, browser_name=browser_name, cdp_port=cdp_port)
            finally:
                await session.close()
    except Exception:
        if not cdp_url:
            raise
        from utils.direct_cdp import read_page_snapshot

        try:
            snapshot = await asyncio.to_thread(read_page_snapshot, cdp_url, STUDIO_URL)
            url = str(snapshot.get("url", ""))
            html = str(snapshot.get("html", ""))
            stable_id = None
            for pattern, source in (
                (r"/channel/(UC[A-Za-z0-9_-]+)", url),
                (r'"(?:channelId|externalId|ownerChannelId)"\s*:\s*"(UC[A-Za-z0-9_-]+)"', html),
            ):
                match = re.search(pattern, source)
                if match:
                    stable_id = match.group(1)
                    break
            handle_match = re.search(r"/@([A-Za-z0-9._-]+)", url)
            return AccountIdentity(
                platform="youtube",
                logged_in=bool(stable_id) and "accounts.google.com" not in url and "/signin" not in url.lower(),
                stable_id=stable_id,
                display_name=str(snapshot.get("youtubeChannelName", "")).strip() or None,
                handle=f"@{handle_match.group(1)}" if handle_match else None,
                profile_url=f"https://www.youtube.com/channel/{stable_id}" if stable_id else None,
                browser_name=browser_name,
                cdp_port=cdp_port,
                extra={"identity_transport": "direct-cdp"},
            )
        except Exception as direct_exc:
            raise RuntimeError("YouTube identity could not be read from Patchright or direct CDP") from direct_exc


async def assert_youtube_publish_identity(page: Page, expected: AccountIdentity) -> AccountIdentity:
    observed = await extract_youtube_identity(
        page,
        browser_name=expected.browser_name,
        cdp_port=expected.cdp_port,
    )
    assert_same_publish_identity(expected, observed)
    return observed


async def youtube_cookie_gen(account_file, headless: bool = False, cdp_url: str | None = None):
    """交互式登录：在指定浏览器登录 Google/YouTube，进入频道页后保存 storage_state。"""
    async with async_playwright() as playwright:
        session = await open_browser_session(
            playwright,
            cdp_url=cdp_url,
            launch_kwargs={"headless": False, "channel": "chrome"},
        )
        context = session.context
        context = await set_init_script(context)
        page = await session.new_task_page()
        await page.goto(STUDIO_URL, wait_until="domcontentloaded")
        youtube_logger.info(_msg("🔐", "请在浏览器里登录 Google / YouTube 账号，登录后会自动保存"))
        ok = False
        for _ in range(600):  # 最多等 10 分钟
            if "/channel/" in page.url:
                await page.wait_for_timeout(2000)  # 让 cookie 落定
                ok = True
                break
            await asyncio.sleep(1)
        if ok:
            if await save_storage_state_if_owned(session, account_file):
                youtube_logger.success(_msg("✅", f"YouTube 登录态已保存: {account_file}"))
            else:
                youtube_logger.success(_msg("✅", "YouTube 登录态由当前 CDP 浏览器 Profile 持久保存"))
        else:
            youtube_logger.error(_msg("😵", "等待登录超时，未保存登录态"))
        await session.close(success=ok)
        return _build_login_result(ok, "logged_in" if ok else "timeout",
                                   "登录成功" if ok else "登录超时", account_file, page.url)


async def youtube_setup(
    account_file,
    handle: bool = False,
    return_detail: bool = False,
    headless: bool = False,
    cdp_url: str | None = None,
):
    """校验登录态，失效且 handle=True 时拉起交互式登录。"""
    if (not cdp_url and not Path(account_file).exists()) or not await cookie_auth(account_file, cdp_url=cdp_url):
        if not handle:
            result = _build_login_result(False, "cookie_invalid", "登录态不存在或已失效", account_file)
            return result if return_detail else False
        youtube_logger.info(_msg("🥹", "YouTube 登录态不存在或失效，准备打开浏览器登录"))
        result = await youtube_cookie_gen(account_file, headless=headless, cdp_url=cdp_url)
        return result if return_detail else result["success"]
    result = _build_login_result(True, "cookie_valid", "登录态有效", account_file)
    return result if return_detail else True


async def _dismiss_autocomplete(page: Page):
    """关掉 # 话题 / @ 提及 自动补全下拉浮层（会挡住后续“继续/发布”按钮）。

    先 blur 失焦；若浮层仍可见再补一次 Escape——仅在检测到浮层时才按，
    避免在没有浮层时误关掉整个上传对话框。"""
    try:
        await page.evaluate("() => { const a = document.activeElement; if (a && a.blur) a.blur(); }")
    except Exception:
        pass
    try:
        dropdown = page.locator("tp-yt-iron-dropdown:visible")
        if await dropdown.count() > 0:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(200)
    except Exception:
        pass


async def _fill_editable(page: Page, selector: str, text: str):
    """填 YouTube Studio 的 contenteditable 富文本框（标题/简介），先清空再输入。

    用 fill() 一次性灌入而非逐字 type()：标题/简介里的 # 字符（如 #Shorts）会触发
    YouTube 的话题自动补全下拉浮层；逐字输入会让浮层持续跟随光标弹出、盖住输入框与
    后续“继续/发布”按钮，导致上传流程卡死。fill() 一次性写入不会逐字触发补全。"""
    box = page.locator(selector).first
    await box.wait_for(state="visible", timeout=30000)
    await box.click()
    await page.keyboard.press("Control+A")
    await page.keyboard.press("Delete")
    try:
        await box.fill(text)            # 一次性灌入，不逐字触发 # 话题自动补全
    except Exception:
        await box.type(text, delay=6)   # 个别 contenteditable 不支持 fill 时退回逐字输入
    await page.wait_for_timeout(400)
    await _dismiss_autocomplete(page)   # 收尾关掉可能弹出的补全浮层


async def _click_if_present(page: Page, selector: str, timeout: int = 4000) -> bool:
    try:
        el = page.locator(selector).first
        await el.wait_for(state="visible", timeout=timeout)
        if selector == "#done-button":
            inner = el.locator("button").first
            if await inner.count():
                el = inner
        if hasattr(el, "is_enabled") and not await el.is_enabled():
            return False
        await el.click()
        return True
    except Exception:
        return False


async def _click_required_final_button(page: Page, action: str) -> None:
    selectors = ["#done-button"]
    if action == "Schedule":
        selectors.extend(("button:has-text('预定')", "button:has-text('Schedule')"))
    else:
        selectors.append(f"button:has-text('{action}')")
    for selector in selectors:
        if await _click_if_present(page, selector, 15000):
            return
    raise RuntimeError(f"YouTube Studio did not expose the final {action} button")


async def wait_for_schedule_control(page: Page, *, timeout_ms: int = 30 * 60 * 1000, poll_ms: int = 5000) -> None:
    """Wait until Studio exposes the collapsed native scheduling section within one time budget."""
    attempts = max(1, (timeout_ms + poll_ms - 1) // poll_ms)
    click_timeout = max(1, min(1000, poll_ms // 4))
    wait_after_failure = max(0, poll_ms - click_timeout)
    for attempt in range(attempts):
        if await _click_if_present(page, SCHEDULE_BUTTON_SELECTOR, click_timeout):
            return
        if attempt + 1 < attempts:
            await page.wait_for_timeout(wait_after_failure)
    raise RuntimeError("YouTube Studio did not expose the schedule controls after processing wait")


async def advance_to_visibility(
    page: Page, *, timeout_ms: int = 30 * 60 * 1000, poll_ms: int = 2000
) -> None:
    """Advance through post-upload processing until Studio exposes the visibility radios."""
    public = page.locator("tp-yt-paper-radio-button[name='PUBLIC']")
    attempts = max(1, (timeout_ms + poll_ms - 1) // poll_ms)
    click_timeout = max(1, min(1000, poll_ms // 4))
    wait_after_failure = max(0, poll_ms - click_timeout)
    for attempt in range(attempts):
        try:
            if await public.count() and await public.first.is_visible():
                return
        except Exception:
            pass
        await _click_if_present(page, "#next-button", click_timeout)
        if attempt + 1 < attempts:
            await page.wait_for_timeout(wait_after_failure)
    raise RuntimeError("YouTube Studio did not reach the visibility step after processing")


async def _wait_upload_complete(page: Page, max_polls: int = 360) -> bool:
    """等网页上传从 X% 跑到 100% 再发布。浏览器上传靠窗口开着才传得完，
    若上传到一半就点发布并关闭浏览器，上传会被掐断卡在中途（如 76%）。
    出现“处理/检查/上传完成”或不再“正在上传”即视为传完。max_polls*5s=30min 上限。"""
    last = ""
    for _ in range(max_polls):
        txt = ""
        for sel in (".progress-label", "span.progress-label", "ytcp-video-upload-progress"):
            loc = page.locator(sel).first
            try:
                if await loc.count():
                    txt = (await loc.inner_text()).strip()
                    if txt:
                        break
            except Exception:
                pass
        if txt:
            if any(k in txt for k in ("处理", "检查", "上传完成", "已上传", "Processing", "complete", "Checks", "Finished")):
                youtube_logger.info(_msg("✅", f"上传完成: {txt[:40]}"))
                return True
            if txt != last:
                youtube_logger.info(_msg("⏳", f"上传中: {txt[:40]}"))
                last = txt
        await page.wait_for_timeout(5000)
    youtube_logger.warning(_msg("⚠️", "等上传超时(30min)，仍尝试发布"))
    return False


async def _configure_scheduled_publication(page: Page, schedule: datetime, timezone: str) -> None:
    local_time = _normalize_schedule(schedule, timezone)
    if local_time <= datetime.now(ZoneInfo(timezone)):
        raise ValueError(f"YouTube scheduled time must be in the future: {local_time.isoformat()}")

    await wait_for_schedule_control(page)

    date_trigger = page.locator("ytcp-video-visibility-select #datepicker-trigger").first
    await date_trigger.wait_for(state="visible", timeout=10000)
    await date_trigger.click()
    date_input = page.locator("ytcp-date-picker input").first
    time_input = page.locator("ytcp-video-visibility-select #time-of-day-container input").first
    await date_input.wait_for(state="visible", timeout=10000)
    await time_input.wait_for(state="visible", timeout=10000)
    # Studio's Chinese locale exposes this same human-readable date in the picker input.
    await date_input.fill(f"{local_time.year}年{local_time.month}月{local_time.day}日")
    await date_input.press("Enter")
    await time_input.fill(local_time.strftime("%H:%M"))
    youtube_logger.info(_msg("🗓️", f"设置 Studio 原生预约: {local_time.isoformat()}"))


class YouTubeVideo(BaseVideoUploader):
    def __init__(self, title, file_path, tags, account_file, *,
                 description="", thumbnail_path=None, playlist=None,
                 visibility="public", debug=DEBUG_MODE, headless=False, cdp_url: str | None = None,
                 submit: bool = True, schedule: datetime | None = None, timezone: str = "Asia/Shanghai",
                 browser_name: str | None = None, cdp_port: int | None = None,
                 target_account: str | None = None):
        self.title = title
        self.file_path = str(file_path)
        self.tags = tags or []
        self.account_file = str(account_file)
        self.description = description or ""
        self.thumbnail_path = str(thumbnail_path) if thumbnail_path else None
        self.playlist = playlist
        self.visibility = visibility if visibility in VISIBILITY else "public"
        self.debug = debug
        self.headless = headless
        self.cdp_url = cdp_url
        self.submit = submit
        self.schedule = schedule
        self.timezone = timezone
        self.browser_name = browser_name
        self.cdp_port = cdp_port
        self.target_account = target_account
        self._active_session = None
        self._upload_succeeded = False

    async def upload(self, playwright: Playwright) -> dict[str, str | int | bool]:
        session = await open_browser_session(
            playwright,
            cdp_url=self.cdp_url,
            launch_kwargs={
                "headless": self.headless,
                "channel": "chrome",
                "proxy": {"server": YT_PROXY} if YT_PROXY else None,
            },
            context_kwargs=_youtube_context_kwargs(self.account_file, self.cdp_url),
        )
        self._active_session = session
        context = await set_init_script(session.context)
        page = await session.new_task_page()
        page.set_default_timeout(60000)

        youtube_logger.info(_msg("🎬", f"开始上传: {Path(self.file_path).name}"))
        await page.goto(STUDIO_URL, wait_until="domcontentloaded")
        expected_identity = await extract_youtube_identity(
            page, browser_name=self.browser_name, cdp_port=self.cdp_port
        )
        require_publish_identity(expected_identity)
        if self.target_account and not identity_matches(expected_identity, self.target_account):
            raise RuntimeError("blocked publish identity: target account does not match YouTube page")
        await page.goto(UPLOAD_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        if "accounts.google.com" in page.url or "signin" in page.url.lower():
            raise RuntimeError("YouTube 登录态失效，请重新执行 login")

        # 1) 选择视频文件
        file_input = page.locator('input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=60000)
        if requires_local_cdp_file_input(self.cdp_url, Path(self.file_path).stat().st_size):
            await set_local_file_input_via_cdp(page, 'input[type="file"]', self.file_path)
        else:
            await file_input.set_input_files(self.file_path)

        # 2) 等详情对话框
        await page.locator("#title-textarea").wait_for(state="visible", timeout=120000)

        # 3) 标题
        youtube_logger.info(_msg("✍️", "填写标题"))
        await _fill_editable(page, "#title-textarea #textbox", self.title[:100])

        # 4) 简介
        if self.description.strip():
            youtube_logger.info(_msg("✍️", "填写简介"))
            await _fill_editable(page, "#description-textarea #textbox", self.description)

        # 5) 封面（处理到一定进度才允许传，失败不致命）
        if self.thumbnail_path and Path(self.thumbnail_path).exists():
            try:
                thumb_input = page.locator(
                    "#file-loader input[type='file'], ytcp-thumbnail-uploader input[type='file']"
                ).first
                await thumb_input.wait_for(state="attached", timeout=20000)
                await thumb_input.set_input_files(self.thumbnail_path)
                await page.wait_for_timeout(2000)
                youtube_logger.info(_msg("🖼️", "封面已上传"))
            except Exception as exc:
                youtube_logger.warning(_msg("⚠️", f"封面上传跳过（不影响发布）: {exc}"))

        # 6) 加入播放列表（连载/系列追更）。弹窗务必关闭，否则挡住后续步骤。
        if self.playlist:
            try:
                await _click_if_present(
                    page, "#basics ytcp-text-dropdown-trigger, ytcp-video-metadata-playlists ytcp-dropdown-trigger", 8000)
                await page.wait_for_timeout(1200)
                existing = page.locator(
                    f"tp-yt-paper-checkbox:has-text('{self.playlist}'), "
                    f"ytcp-checkbox-group:has-text('{self.playlist}')").first
                if await existing.count():
                    await existing.click()
                else:
                    if await _click_if_present(page, "ytcp-button:has-text('New playlist'), ytcp-button:has-text('创建播放列表')", 4000):
                        await page.wait_for_timeout(800)
                        await _click_if_present(page, "tp-yt-paper-item:has-text('New playlist'), tp-yt-paper-item:has-text('新建播放列表')", 3000)
                        title_box = page.locator("ytcp-playlist-metadata-editor #textbox, #create-playlist-form #textbox").first
                        if await title_box.count():
                            await title_box.click()
                            await title_box.type(self.playlist, delay=6)
                            await _click_if_present(page, "ytcp-button#create-button, tp-yt-paper-dialog ytcp-button:has-text('Create'), tp-yt-paper-dialog ytcp-button:has-text('创建')", 4000)
            except Exception as exc:
                youtube_logger.warning(_msg("⚠️", f"播放列表处理跳过（不影响发布）: {exc}"))
            finally:
                await _click_if_present(page, "ytcp-playlist-dialog #save-button, ytcp-button:has-text('Done'), ytcp-button:has-text('完成')", 3000)
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(600)

        # 7) 受众：非儿童向（必填）
        if not await _click_if_present(page, "tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']", 10000):
            await _click_if_present(page, "tp-yt-paper-radio-button:has-text('not made for kids'), tp-yt-paper-radio-button:has-text('不是面向儿童')", 6000)

        # 8) 标签（“显示更多”里）
        if self.tags:
            try:
                await _click_if_present(page, "#toggle-button", 6000)
                await page.wait_for_timeout(800)
                tag_input = page.locator("#tags-container #text-input, ytcp-form-input-container#tags-container input").first
                await tag_input.click()
                await tag_input.type(",".join(self.tags)[:500] + ",", delay=4)
            except Exception as exc:
                youtube_logger.warning(_msg("⚠️", f"标签填写跳过（不影响发布）: {exc}"))

        # 9) 可见性由上传/处理完成后的 wizard 步骤设置；此处不提前点击 Next。

        # 10) 可见性需在处理完成、向导进入公开范围步骤后设置。
        if self.schedule:
            self.visibility = "public"

        # 10.5) 关键：等上传真正传完再发布。浏览器上传靠窗口开着传，
        #       传到一半就点发布+关浏览器 = 上传被掐断卡在中途（如 76%）。
        youtube_logger.info(_msg("📤", "等待上传完成（传完才发布）…"))
        await _wait_upload_complete(page)
        await advance_to_visibility(page)
        youtube_logger.info(_msg("🌐", f"设置可见性 = {self.visibility}"))
        if not await _click_if_present(
            page, f"tp-yt-paper-radio-button[name='{VISIBILITY[self.visibility]}']", 10000
        ):
            raise RuntimeError("YouTube Studio did not expose the requested visibility control")

        # 11) 发布 / Studio 原生预约
        result: dict[str, str | int | bool] = {"visibility": self.visibility, "submitted": self.submit}
        if not self.submit:
            youtube_logger.success(_msg("🛑", "已到达发布前页面，按 --no-submit 停止"))
        elif self.schedule:
            await _configure_scheduled_publication(page, self.schedule, self.timezone)
            await assert_youtube_publish_identity(page, expected_identity)
            try:
                await _click_required_final_button(page, "Schedule")
            except RuntimeError:
                draft = {}
                try:
                    draft = extract_youtube_draft_reference(await page.content())
                except Exception:
                    pass
                return {
                    "status": "interaction_required",
                    "platform": "youtube",
                    "reason": "final_schedule_button_missing",
                    "recoverable": True,
                    "submitted": False,
                    "browser_name": self.browser_name,
                    "cdp_port": self.cdp_port,
                    "stable_id": expected_identity.stable_id,
                    "focus_fallback_used": session.focus_fallback_used,
                    **draft,
                }
            await page.locator("ytcp-uploads-dialog").first.wait_for(state="hidden", timeout=20000)
            await page.wait_for_timeout(4000)
            result = await readback_scheduled_publication(
                page, expected_schedule=self.schedule, timezone=self.timezone
            )
            youtube_logger.success(_msg("🗓️", f"Studio 原生预约已核验: {result['publishUrl']}"))
            await _click_if_present(page, "ytcp-button:has-text('Close'), ytcp-button:has-text('关闭'), #close-button", 8000)
        else:
            await assert_youtube_publish_identity(page, expected_identity)
            await page.wait_for_timeout(1200)
            await _click_required_final_button(page, "Publish")
            await page.locator("ytcp-uploads-dialog").first.wait_for(state="hidden", timeout=20000)
            await page.wait_for_timeout(4000)
            video_url = ""
            try:
                link = page.locator("a[href*='youtu.be'], a[href*='watch?v=']").first
                if await link.count():
                    video_url = await link.get_attribute("href") or ""
            except Exception:
                pass
            result["publishUrl"] = video_url
            await _click_if_present(page, "ytcp-button:has-text('Close'), ytcp-button:has-text('关闭'), #close-button", 8000)
            youtube_logger.success(_msg("🥳", f"发布完成（{self.visibility}）{(' ' + video_url) if video_url else ''}"))

        # 刷新 cookie
        try:
            await save_storage_state_if_owned(session, self.account_file)
        except Exception:
            pass
        await page.wait_for_timeout(2000)
        result.update(
            {
                "status": "success",
                "platform": "youtube",
                "submitted": self.submit,
                "browser_name": self.browser_name,
                "cdp_port": self.cdp_port,
                "stable_id": expected_identity.stable_id,
                "focus_fallback_used": session.focus_fallback_used,
            }
        )
        self._upload_succeeded = True
        return result

    async def main(self):
        async with async_playwright() as playwright:
            try:
                return await self.upload(playwright)
            finally:
                if self._active_session is not None:
                    await self._active_session.close(success=self._upload_succeeded)
