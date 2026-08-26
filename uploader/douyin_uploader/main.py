# -*- coding: utf-8 -*-
from decimal import Decimal
from datetime import datetime

import asyncio
import inspect
import os
import re
from pathlib import Path

from patchright.async_api import Page
from patchright.async_api import Playwright
from patchright.async_api import async_playwright

from conf import DEBUG_MODE, LOCAL_CHROME_HEADLESS, LOCAL_CHROME_PATH
from uploader.base_video import BaseVideoUploader
from utils.base_social_media import set_init_script
from utils.login_qrcode import build_login_qrcode_path
from utils.login_qrcode import decode_qrcode_from_path
from utils.login_qrcode import print_terminal_qrcode
from utils.login_qrcode import remove_qrcode_file
from utils.login_qrcode import save_data_url_image
from utils.log import douyin_logger
from utils.browser_runtime import (
    open_browser_session,
    requires_local_cdp_file_input,
    save_storage_state_if_owned,
    set_local_file_input_via_cdp,
)
from utils.account_identity import AccountIdentity, assert_same_publish_identity, identity_matches, require_publish_identity
from uploader.douyin_uploader.paid_video import DouyinPaidVideoSettings

DOUYIN_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
DOUYIN_PUBLISH_STRATEGY_SCHEDULED = "scheduled"


def _msg(emoji: str, text: str) -> str:
    return f"{emoji} {text}"


async def has_douyin_sms_challenge(page: Page) -> bool:
    sms_input = page.locator(
        'input[placeholder*="验证码"], input[type="tel"], input[placeholder*="短信"], input[placeholder*="手机号"]'
    ).first
    try:
        return bool(await sms_input.count()) and await sms_input.is_visible()
    except Exception:
        return False


async def _emit_qrcode_callback(qrcode_callback, payload: dict):
    if not qrcode_callback:
        return

    callback_result = qrcode_callback(payload)
    if inspect.isawaitable(callback_result):
        await callback_result


def _build_login_result(success: bool, status: str, message: str, account_file: str, qrcode: dict | None = None, current_url: str = "") -> dict:
    return {
        "success": success,
        "status": status,
        "message": message,
        "account_file": str(account_file),
        "qrcode": qrcode,
        "current_url": current_url,
    }


_DOUYIN_HANDLE_RE = re.compile(r"抖音号\s*[:：]\s*([A-Za-z0-9_-]+)")
_DOUYIN_ID_RE = re.compile(r"[?&](?:uid|douyin_id)=([A-Za-z0-9_-]+)", re.IGNORECASE)
_DOUYIN_JSON_ID_RE = re.compile(
    r"[\"'](?:uid|sec_uid|douyin_id)[\"']\s*:\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_DOUYIN_NAME_RE = re.compile(r"[\"'](?:nickname|nickName)[\"']\s*:\s*[\"']([^\"']+)[\"']")
_GENERIC_DOUYIN_NAMES = {
    "抖音创作者中心",
    "创作者服务中心",
    "抖音创作服务平台",
    "抖音",
}


def _visible_douyin_name(body_text: str, handle_match: re.Match[str] | None) -> str | None:
    if not body_text or not handle_match:
        return None
    before_handle = body_text[max(0, handle_match.start() - 120) : handle_match.start()]
    candidates = re.split(r"[\r\n|•·,，;；]+", before_handle)
    for candidate in reversed(candidates):
        candidate = re.sub(r"\s+", " ", candidate).strip(" \t:-：")
        if not candidate or candidate in _GENERIC_DOUYIN_NAMES:
            continue
        if "抖音号" in candidate or "创作者中心" in candidate or "服务平台" in candidate:
            continue
        if len(candidate) <= 80:
            return candidate
    return None


def _douyin_identity_sources(
    url: str,
    html: str,
    body_text: str,
    header_name: str | None = None,
) -> tuple[str | None, str | None]:
    sources: list[tuple[str, str]] = []
    url_match = _DOUYIN_ID_RE.search(url)
    if url_match:
        sources.append(("url", url_match.group(1)))
    for match in _DOUYIN_JSON_ID_RE.finditer(html):
        value = match.group(1).strip()
        if value:
            sources.append(("page-data", value))
    handle_match = _DOUYIN_HANDLE_RE.search(body_text)
    if handle_match:
        sources.append(("visible", handle_match.group(1).strip()))

    distinct = {value for _, value in sources if value}
    if len(distinct) > 1:
        source_text = ", ".join(f"{source}={value}" for source, value in sources)
        raise RuntimeError(f"blocked douyin identity: conflicting stable IDs ({source_text})")
    stable_id = next(iter(distinct), None)

    visible_name = _visible_douyin_name(body_text, handle_match)
    structured_name_match = _DOUYIN_NAME_RE.search(html)
    structured_name = structured_name_match.group(1).strip() if structured_name_match else None
    display_name = header_name or visible_name or structured_name
    if display_name in _GENERIC_DOUYIN_NAMES:
        display_name = None
    return stable_id, display_name


async def _douyin_visible_body(page: Page) -> str:
    try:
        body = await page.locator("body").inner_text()
        if isinstance(body, str):
            return body
    except Exception:
        pass
    try:
        body = await page.evaluate("() => document.body ? document.body.innerText : ''")
        return body if isinstance(body, str) else ""
    except Exception:
        return ""


async def _douyin_header_name(page: Page) -> str | None:
    try:
        value = await page.evaluate(
            """() => {
                const handle = Array.from(document.querySelectorAll('*')).find(
                    element => (element.innerText || '').trim().match(/^抖音号\\s*[:：]\\s*[A-Za-z0-9_-]+$/)
                );
                const lines = (handle?.parentElement?.innerText || '').split(/\\n/).map(item => item.trim()).filter(Boolean);
                return lines.find(item => !/^抖音号\s*[:：]\s*[A-Za-z0-9_-]+$/.test(item)) || null;
            }"""
        )
        return value.strip() if isinstance(value, str) and value.strip() in _GENERIC_DOUYIN_NAMES else (
            value.strip() if isinstance(value, str) and value.strip() else None
        )
    except Exception:
        return None


async def extract_douyin_identity(page: Page, *, browser_name: str | None = None, cdp_port: int | None = None) -> AccountIdentity:
    html = await page.content()
    url = page.url
    body_text = await _douyin_visible_body(page)
    stable_id, display_name = _douyin_identity_sources(url, html, body_text, await _douyin_header_name(page))
    login_markers = ("手机号登录", "扫码登录", "立即登录")
    logged_in = (
        bool(stable_id)
        and "creator.douyin.com/creator-micro" in url
        and not any(marker in url.lower() for marker in ("login", "signin"))
        and not any(marker in body_text for marker in login_markers)
    )
    return AccountIdentity(
        platform="douyin",
        logged_in=logged_in,
        stable_id=stable_id,
        display_name=display_name,
        profile_url=f"https://www.douyin.com/user/{stable_id}" if stable_id else None,
        browser_name=browser_name,
        cdp_port=cdp_port,
        extra={},
    )


async def extract_douyin_identity_from_context(
    context, *, session=None, browser_name: str | None = None, cdp_port: int | None = None
) -> AccountIdentity:
    """Read identity from the home page, where Douyin exposes its stable ID."""
    new_task_page = getattr(session, "new_task_page", None)
    identity_page = await new_task_page() if callable(new_task_page) else await context.new_page()
    success = False
    try:
        await identity_page.goto(
            "https://creator.douyin.com/creator-micro/home",
            wait_until="domcontentloaded",
            timeout=90000,
        )
        await identity_page.wait_for_timeout(2500)
        identity = await extract_douyin_identity(identity_page, browser_name=browser_name, cdp_port=cdp_port)
        success = True
        return identity
    finally:
        if success:
            await identity_page.close()


async def cookie_auth(account_file, cdp_url: str | None = None):
    # 抖音无头会撞反爬墙→content/upload 跳登录→误判 cookie 失效（间歇性）。校验必须有头。
    # 即便有头，页面慢/瞬时跳转仍会让 wait_for_url(精确URL,5s) 误判→重试3次+宽松判定(URL含 content/upload 且无登录文案)。
    # 允许 linux server 用户通过 env var 强制无头: DOUYIN_COOKIE_AUTH_HEADLESS=true
    use_headless = os.environ.get("DOUYIN_COOKIE_AUTH_HEADLESS", "").lower() in ("1", "true", "yes")
    launch_kwargs = {"headless": use_headless, "channel": "chrome", "args": ["--no-sandbox", "--disable-blink-features=AutomationControlled"]}
    for _attempt in range(3):
        async with async_playwright() as playwright:
            session = await open_browser_session(
                playwright,
                cdp_url=cdp_url,
                launch_kwargs=launch_kwargs,
                context_kwargs={} if cdp_url else {"storage_state": account_file},
            )
            try:
                context = session.context
                context = await set_init_script(context)
                page = await session.new_task_page()
                await page.goto("https://creator.douyin.com/creator-micro/content/upload", wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(2500)  # 等页面稳定，避免瞬时跳转误判
                has_login = await page.get_by_text("手机号登录").count() or await page.get_by_text("扫码登录").count()
                if "content/upload" in page.url and not has_login:
                    return True
            except Exception:
                pass
            finally:
                await session.close()
    return False


async def get_douyin_account_identity(
    cdp_url: str | None = None,
    account_file: str | None = None,
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
                context_kwargs={} if cdp_url else {"storage_state": account_file},
            )
            try:
                context = await set_init_script(session.context)
                page = await session.new_task_page()
                await page.goto("https://creator.douyin.com/creator-micro/home", wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(2500)
                return await extract_douyin_identity(page, browser_name=browser_name, cdp_port=cdp_port)
            finally:
                await session.close()
    except Exception:
        if not cdp_url:
            raise
        from utils.direct_cdp import read_page_snapshot

        try:
            snapshot = await asyncio.to_thread(
                read_page_snapshot,
                cdp_url,
                "https://creator.douyin.com/creator-micro/home",
            )
            url = str(snapshot.get("url", ""))
            body = str(snapshot.get("body", ""))
            stable_id, display_name = _douyin_identity_sources(
                url,
                str(snapshot.get("html", "")),
                body,
                str(snapshot.get("douyinHeaderName", "")).strip() or None,
            )
            logged_in = bool(stable_id) and "creator.douyin.com/creator-micro" in url and not any(
                marker in body for marker in ("手机号登录", "扫码登录", "立即登录")
            )
            return AccountIdentity(
                platform="douyin",
                logged_in=logged_in,
                stable_id=stable_id,
                display_name=display_name,
                profile_url=f"https://www.douyin.com/user/{stable_id}" if stable_id else None,
                browser_name=browser_name,
                cdp_port=cdp_port,
                extra={"identity_transport": "direct-cdp"},
            )
        except Exception as direct_exc:
            raise RuntimeError("Douyin identity could not be read from Patchright or direct CDP") from direct_exc


async def assert_douyin_publish_identity(page: Page, expected: AccountIdentity) -> AccountIdentity:
    observed = await extract_douyin_identity(
        page,
        browser_name=expected.browser_name,
        cdp_port=expected.cdp_port,
    )
    assert_same_publish_identity(expected, observed)
    return observed


async def douyin_setup(account_file, handle=False, return_detail=False, qrcode_callback=None, headless: bool = LOCAL_CHROME_HEADLESS, cdp_url: str | None = None):
    if (not cdp_url and not os.path.exists(account_file)) or not await cookie_auth(account_file, cdp_url=cdp_url):
        if not handle:
            result = _build_login_result(False, "cookie_invalid", "cookie文件不存在或已失效", account_file)
            return result if return_detail else False
        douyin_logger.info(_msg("🥹", "cookie 失效了，准备打开浏览器重新登录"))
        result = await douyin_cookie_gen(account_file, qrcode_callback=qrcode_callback, headless=headless, cdp_url=cdp_url)
        return result if return_detail else result["success"]

    result = _build_login_result(True, "cookie_valid", "cookie有效", account_file)
    return result if return_detail else True


async def _extract_douyin_qrcode_src(page: Page) -> str:
    # 等 SPA 加载完成（不只等"扫码登录"文字，否则抖音慢加载时 30s 就超时）。
    # 给 domcontentloaded 后足够时间让客户端 JS 注入登录卡。
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    scan_login_tab = page.get_by_text("扫码登录", exact=True).first
    # attached 状态：DOM 里出现即可，不要求 visible/渲染完整，避免 race
    await scan_login_tab.wait_for(state="attached", timeout=60000)

    # 新版抖音创作者中心 (single_tab + animate_qrcode_container) 不再用 aria-label="二维码"。
    # 按优先级兜底多个 selector，至少一个能命中即可。
    qrcode_selectors = [
        'div#animate_qrcode_container img[src^="data:image"]',
        'div[class*="animate_qrcode_container"] img[src^="data:image"]',
        'div[class*="scan_qrcode_login_content"] img[src^="data:image"]',
        'img[aria-label="二维码"]',
    ]
    last_err: Exception | None = None
    for sel in qrcode_selectors:
        qrcode_img = page.locator(sel).first
        try:
            await qrcode_img.wait_for(state="attached", timeout=10000)
        except Exception as e:
            last_err = e
            continue
        src = await qrcode_img.get_attribute("src")
        if src:
            return src
        last_err = RuntimeError(f"selector {sel} 命中但 src 为空")

    raise RuntimeError(f"未获取到抖音登录二维码地址 (last_err={last_err})")


async def _save_douyin_qrcode(page: Page, account_file: str, previous_qrcode_path: Path | None = None, qrcode_callback=None) -> dict:
    # 提取二维码 src 仅为了保存/终端显示；定位不到时不致命——有头浏览器里二维码可见，直接扫码即可
    try:
        qrcode_src = await _extract_douyin_qrcode_src(page)
    except Exception as exc:
        douyin_logger.warning(_msg("😵", f"没定位到二维码元素（{str(exc)[:50]}）——请直接在弹出的浏览器里扫码，小人继续等登录跳转"))
        return {"image_path": "", "image_data_url": ""}
    qrcode_path = save_data_url_image(qrcode_src, build_login_qrcode_path(account_file))
    if previous_qrcode_path and previous_qrcode_path != qrcode_path:
        if remove_qrcode_file(previous_qrcode_path):
            douyin_logger.info(_msg("🧹", f"临时二维码文件已清理: {previous_qrcode_path}"))
    douyin_logger.info(_msg("🖼️", f"二维码已经准备好啦，已保存到: {qrcode_path}"))
    qrcode_content = decode_qrcode_from_path(qrcode_path)
    if qrcode_content:
        print_terminal_qrcode(qrcode_content, qrcode_path, "抖音APP")
    else:
        douyin_logger.warning(_msg("😵", f"终端没法完整显示二维码，请打开 {qrcode_path} 扫码"))
    qrcode_info = {
        "image_path": str(qrcode_path),
        "image_data_url": qrcode_src,
    }
    await _emit_qrcode_callback(qrcode_callback, qrcode_info)
    return qrcode_info


async def _is_douyin_login_completed(page: Page) -> bool:
    # 登录后会跳到 creator-micro 下任意页（home/content 等）；登录页是 creator.douyin.com/ 根路径
    if "creator.douyin.com/creator-micro" not in page.url:
        return False

    login_markers = [
        page.get_by_text("扫码登录", exact=True).first,
        page.get_by_text("手机号登录", exact=True).first,
        page.get_by_text("二维码失效", exact=True).first,
        page.get_by_role("img", name="二维码").first,
    ]

    for marker in login_markers:
        if not await marker.count():
            continue
        try:
            if await marker.is_visible():
                return False
        except Exception:
            continue

    return True


async def _wait_for_douyin_login(page: Page, account_file: str, qrcode_info: dict, qrcode_callback=None, poll_interval: int = 3, max_checks: int = 100) -> dict:
    qrcode_path = Path(qrcode_info["image_path"]) if qrcode_info.get("image_path") else None
    for _ in range(max_checks):
        if await _is_douyin_login_completed(page):
            douyin_logger.info(_msg("🥳", f"扫码成功，已经跳转到登录后页面: {page.url}"))
            return _build_login_result(True, "success", "抖音扫码登录成功", account_file, qrcode_info, page.url)

        # URL 变化 + sessionid 未到位 → 二验流程，继续等
        if page.url != original_url and not await _is_douyin_login_completed(page):
            sms_input = page.locator('input[placeholder*="验证码"], input[type="tel"], input[placeholder*="短信"], input[placeholder*="手机号"]')
            if await sms_input.count() > 0:
                if not saw_2fa:
                    douyin_logger.warning(_msg("⚠️", f"检测到抖音短信/安全二次验证，请在弹出的浏览器中手动输入。等待 sessionid ({i}/{max_checks})"))
                    saw_2fa = True
            await asyncio.sleep(poll_interval)
            continue

        expired_box = page.get_by_text("二维码失效", exact=True).locator("..").first
        if await expired_box.count() and await expired_box.is_visible():
            douyin_logger.warning(_msg("😵", "二维码失效了，小人马上去刷新"))
            await expired_box.click()
            await asyncio.sleep(1)
            qrcode_info = await _save_douyin_qrcode(page, account_file, qrcode_path, qrcode_callback=qrcode_callback)
            qrcode_path = Path(qrcode_info["image_path"]) if qrcode_info.get("image_path") else None

        await asyncio.sleep(poll_interval)

    return _build_login_result(False, "timeout", "等待抖音扫码登录超时", account_file, qrcode_info, page.url)


async def douyin_cookie_gen(
    account_file,
    qrcode_callback=None,
    poll_interval: int = 2,
    max_checks: int = 60,
    headless: bool = LOCAL_CHROME_HEADLESS,
    cdp_url: str | None = None,
):
    async with async_playwright() as playwright:
        session = await open_browser_session(
            playwright,
            cdp_url=cdp_url,
            launch_kwargs={"headless": headless, "channel": "chromium"},
        )
        context = session.context
        context = await set_init_script(context)
        qrcode_path = None
        result = _build_login_result(False, "failed", "抖音登录失败", account_file)
        try:
            page = await session.new_task_page()
            await page.goto("https://creator.douyin.com/")
            qrcode_info = await _save_douyin_qrcode(page, account_file, qrcode_callback=qrcode_callback)
            qrcode_path = Path(qrcode_info["image_path"]) if qrcode_info.get("image_path") else None
            douyin_logger.info(_msg("🧍", "请扫码，小人正在耐心等待登录完成"))
            result = await _wait_for_douyin_login(
                page,
                account_file,
                qrcode_info,
                qrcode_callback=qrcode_callback,
                poll_interval=poll_interval,
                max_checks=max_checks,
            )
            if result["success"]:
                await asyncio.sleep(2)
                await save_storage_state_if_owned(session, account_file)
                if not await cookie_auth(account_file, cdp_url=cdp_url):
                    result = _build_login_result(
                        False,
                        "cookie_invalid",
                        "抖音扫码流程结束，但 cookie 校验失败",
                        account_file,
                        qrcode_info,
                        page.url,
                    )
        except Exception as exc:
            result = _build_login_result(False, "failed", str(exc), account_file, current_url=page.url if "page" in locals() else "")
        finally:
            if remove_qrcode_file(qrcode_path):
                douyin_logger.info(_msg("🧹", f"临时二维码文件已清理: {qrcode_path}"))
            if not result["success"]:
                douyin_logger.error(_msg("😢", f"登录失败: {result['message']}"))
            await session.close(success=result["success"])
        return result


class DouYinBaseUploader(BaseVideoUploader):
    def __init__(
        self,
        publish_date: datetime | int,
        account_file,
        publish_strategy: str = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
        cdp_url: str | None = None,
        browser_name: str | None = None,
        cdp_port: int | None = None,
        target_account: str | None = None,
    ):
        self.publish_date = publish_date
        self.account_file = account_file
        self.publish_strategy = publish_strategy
        self.debug = debug
        self.date_format = "%Y年%m月%d日 %H:%M"
        self.local_executable_path = LOCAL_CHROME_PATH
        self.headless = headless
        self.cdp_url = cdp_url
        self.browser_name = browser_name
        self.cdp_port = cdp_port
        self.target_account = target_account
        self._active_session = None
        self._upload_succeeded = False

    async def validate_base_args(self):
        if not self.cdp_url:
            if not os.path.exists(self.account_file):
                raise RuntimeError(f"cookie文件不存在，请先完成抖音登录: {self.account_file}")
            if not await cookie_auth(self.account_file):
                raise RuntimeError(f"cookie文件已失效，请先完成抖音登录: {self.account_file}")
        if self.publish_strategy not in {DOUYIN_PUBLISH_STRATEGY_IMMEDIATE, DOUYIN_PUBLISH_STRATEGY_SCHEDULED}:
            raise ValueError(f"不支持的发布策略: {self.publish_strategy}")

        if self.publish_strategy == DOUYIN_PUBLISH_STRATEGY_SCHEDULED:
            self.publish_date = self.validate_publish_date(self.publish_date)
        else:
            self.publish_date = 0

    async def set_schedule_time_douyin(self, page, publish_date):
        """抖音「定时发布」：点日历日期 + Semi ScrollList 滚轮选时分。

        2026-08-08 实测：Semi DatePicker 是日历面板 + 滚轮选择，
        直接键入文本或 JS click 不可靠（键入不生效、click 滚动偏移），
        可靠路径是：
          1) 点「定时发布」radio
          2) 点输入框打开面板，在日历上点目标日期（DD）
          3) 点时间 switch 打开滚轮
          4) 用滚轮把 hour/minute wheel 的选中项驱动到目标时分
          5) Escape 关闭，回读 input value 核验与请求时间一致
        """
        label_element = page.locator("[class^='radio']:has-text('定时发布')")
        await label_element.click()
        await asyncio.sleep(1)

        date_input = page.locator('.semi-input[placeholder="日期和时间"]')
        await date_input.click()
        await asyncio.sleep(1.5)

        # 1) 日历点选目标日期（DD）；月份不匹配时先点月份导航（当前实现先支持同月/相邻月场景，
        #    以页面可见月份内的日期为准；跨月由调用方保证 --schedule 在合理范围内）
        day_str = str(publish_date.day)
        day_cell = page.locator(
            ".semi-datepicker:visible span:not([class]):not(:has(*)):text-is('{}')".format(day_str)
        ).first
        await day_cell.click(timeout=6000)
        await asyncio.sleep(1)

        # 2) 打开时间滚轮
        time_switch = page.locator(".semi-datepicker-switch-text:has-text(':')").first
        await time_switch.click(timeout=6000)
        await asyncio.sleep(1.5)

        # 3) 用 wheel 驱动 hour wheel 到目标小时
        await self._spin_wheel_to(page, "hour", publish_date.hour)
        # 4) 用 wheel 驱动 minute wheel 到目标分钟
        await self._spin_wheel_to(page, "minute", publish_date.minute)

        # 5) 关闭面板并回读核验
        await page.keyboard.press("Escape")
        await asyncio.sleep(1.5)
        actual = await date_input.input_value()
        expected = publish_date.strftime("%Y-%m-%d %H:%M")
        if actual != expected:
            raise RuntimeError(
                f"抖音定时时间回读核验失败：期望 {expected}，实际 {actual}"
            )
        douyin_logger.info(_msg("📅", f"已设置定时发布 {actual}"))

    async def _spin_wheel_to(self, page, wheel_kind: str, target: int) -> None:
        """驱动 Semi ScrollList 滚轮，把选中项滚到 target。

        滚轮是循环列表（60 项两轮 / 24 项多轮），选中项由 scrollTop 取模决定。
        直接 JS click 会点到不可见元素；可靠方式是用 CDP wheel 事件滚动，
        使目标值进入视口中心（Semi 的 scrolllist-selector 对齐处）。
        """
        kind_class = "list-hour" if wheel_kind == "hour" else "list-minute"
        wheel = page.locator(f"[class*='{kind_class}']").first
        await wheel.wait_for(state="visible", timeout=6000)

        # 视口中心坐标（滚动目标）
        box = await wheel.bounding_box()
        if not box:
            raise RuntimeError(f"抖音 {wheel_kind} wheel 无边界框")
        cx = box["x"] + box["width"] / 2
        cy = box["y"] + box["height"] / 2

        # 用 JS 读取当前选中值（selected item 文本，如 "15时" / "30分"）
        current_text = await page.eval_on_selector(
            f"[class*='{kind_class}'] .semi-scrolllist-item-selected",
            "el => el.innerText.trim()",
        )
        current = int("".join(ch for ch in current_text if ch.isdigit()))
        step = 1 if target >= current else -1
        guard = 0
        # 把鼠标移到 wheel 中心，确保 wheel 事件落在 wheel 上
        await page.mouse.move(cx, cy)
        while current != target and guard < 80:
            # 每次滚动一格（约 36px），然后重读选中项；动画期间短暂等待
            await page.mouse.wheel(0, step * 36)
            await asyncio.sleep(0.25)
            current_text = await page.eval_on_selector(
                f"[class*='{kind_class}'] .semi-scrolllist-item-selected",
                "el => el.innerText.trim()",
            )
            current = int("".join(ch for ch in current_text if ch.isdigit()))
            guard += 1
        if current != target:
            raise RuntimeError(
                f"抖音 {wheel_kind} 滚轮未到达目标 {target}，当前 {current}"
            )

    async def fill_title_and_description(self, page: Page, title: str, description: str, tags: list[str] | None = None):
        # 2026-06 抖音发布页 DOM：标题=input[placeholder*=填写作品标题]，描述=div.zone-container[contenteditable]
        # version_2(post/video) 发布页要等视频上传完才渲染表单（实测约 40s），故等待超时给到 120s
        title_input = page.locator('input[placeholder*="填写作品标题"]').first
        await title_input.wait_for(state="visible", timeout=120000)
        await title_input.fill(title[:30])

        description_editor = page.locator('div.zone-container[contenteditable="true"]').first
        await description_editor.wait_for(state="visible", timeout=120000)
        await description_editor.click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.press("Delete")

        if description and description.strip():
            await page.keyboard.type(description.strip())

        for tag in tags or []:
            await page.keyboard.type(" #" + tag)
            await page.keyboard.press("Space")
        await page.keyboard.press("Escape")  # 收起话题下拉，避免浮层拦截后续点击

    async def set_location(self, page: Page, location: str = ""):
        if not location:
            return
        await page.locator('div.semi-select span:has-text("输入地理位置")').click()
        await page.keyboard.press("Backspace")
        await page.wait_for_timeout(2000)
        await page.keyboard.type(location)
        await page.wait_for_selector('div[role="listbox"] [role="option"]', timeout=5000)
        await page.locator('div[role="listbox"] [role="option"]').first.click()

    async def handle_product_dialog(self, page: Page, product_title: str):
        await page.wait_for_timeout(2000)
        await page.wait_for_selector('input[placeholder="请输入商品短标题"]', timeout=10000)
        short_title_input = page.locator('input[placeholder="请输入商品短标题"]')
        if not await short_title_input.count():
            douyin_logger.error(_msg("😵", "没找到商品短标题输入框"))
            return False

        product_title = product_title[:10]
        await short_title_input.fill(product_title)
        await page.wait_for_timeout(1000)

        finish_button = page.locator('button:has-text("完成编辑")')
        if "disabled" not in await finish_button.get_attribute("class"):
            await finish_button.click()
            douyin_logger.debug(_msg("🥳", "已点击“完成编辑”按钮"))
            await page.wait_for_selector(".semi-modal-content", state="hidden", timeout=5000)
            return True

        douyin_logger.error(_msg("😵", "“完成编辑”按钮是灰的，小人先把弹窗关掉"))
        cancel_button = page.locator('button:has-text("取消")')
        if await cancel_button.count():
            await cancel_button.click()
        else:
            close_button = page.locator(".semi-modal-close")
            await close_button.click()
        await page.wait_for_selector(".semi-modal-content", state="hidden", timeout=5000)
        return False

    async def set_product_link(self, page: Page, product_link: str, product_title: str):
        await page.wait_for_timeout(2000)
        try:
            await page.wait_for_selector("text=添加标签", timeout=10000)
            dropdown = page.get_by_text("添加标签").locator("..").locator("..").locator("..").locator(".semi-select").first
            if not await dropdown.count():
                douyin_logger.error(_msg("😵", "没找到标签下拉框"))
                return False
            douyin_logger.debug(_msg("🧍", "找到标签下拉框，小人准备选择“购物车”"))
            await dropdown.click()
            await page.wait_for_selector('[role="listbox"]', timeout=5000)
            await page.locator('[role="option"]:has-text("购物车")').click()
            douyin_logger.debug(_msg("🥳", "已经选中“购物车”"))

            await page.wait_for_selector('input[placeholder="粘贴商品链接"]', timeout=5000)
            input_field = page.locator('input[placeholder="粘贴商品链接"]')
            await input_field.fill(product_link)
            douyin_logger.debug(_msg("🔗", f"商品链接已经填好了: {product_link}"))

            add_button = page.locator('span:has-text("添加链接")')
            button_class = await add_button.get_attribute("class")
            if "disable" in button_class:
                douyin_logger.error(_msg("😵", "“添加链接”按钮现在点不了"))
                return False
            await add_button.click()
            douyin_logger.debug(_msg("🥳", "已点击“添加链接”按钮"))

            await page.wait_for_timeout(2000)
            error_modal = page.locator("text=未搜索到对应商品")
            if await error_modal.count():
                confirm_button = page.locator('button:has-text("确定")')
                await confirm_button.click()
                douyin_logger.error(_msg("😢", "这个商品链接无效"))
                return False

            if not await self.handle_product_dialog(page, product_title):
                return False

            douyin_logger.debug(_msg("🥳", "商品链接设置好了"))
            return True
        except Exception as e:
            douyin_logger.error(_msg("😢", f"设置商品链接时出错: {str(e)}"))
            return False

    async def _clear_blocking_overlays(self, page: Page) -> None:
        try:
            await page.keyboard.press("Escape")
            await page.evaluate(
                "() => { document.querySelectorAll('.shepherd-element,.shepherd-modal-overlay-container,[class*=\"mention-wrapper\"]').forEach(e => e.remove()); }"
            )
        except Exception:
            pass

    async def _native_click(self, page: Page, locator) -> bool:
        try:
            box = await locator.bounding_box()
            if box:
                x = box["x"] + box["width"] / 2
                y = box["y"] + box["height"] / 2
                await page.mouse.move(x, y)
                await page.mouse.click(x, y)
                return True
        except Exception:
            pass
        try:
            await locator.click(timeout=6000, force=True)
            return True
        except Exception:
            return False

    async def set_self_declaration(self, page: Page, declaration: str = "无需添加自主声明") -> bool:
        """抖音「自主声明」为发布必选项：打开声明弹窗 → 选指定类型 → 确定。

        默认选择「无需添加自主声明」（不声明任何内容）；调用方可通过 CLI
        --declaration 显式指定其它类型。入口和弹窗都是异步渲染，等不到就记
        warning 跳过、继续发布，绝不因此中断（与小红书话题、视频号声明原创
        的容错策略保持一致）。
        """
        try:
            # 发布页底部「自主声明」行，未选时显示占位文案「请选择自主声明」
            entry = page.get_by_text("请选择自主声明").first
            await entry.wait_for(state="visible", timeout=6000)
            await entry.click()

            # 弹窗标题「对作品内容添加声明」
            dialog = page.locator(".semi-modal-content").filter(has_text="对作品内容添加声明").first
            await dialog.wait_for(state="visible", timeout=6000)

            # 单选项：Semi 的文字是 .semi-radio-addon（常带 pointer-events:none，直接点会卡 30s 超时），
            # 要点可交互的 .semi-radio 外层；找不到外层再退回 force 强制点文字。exact 避免误命中预览「作者声明：…」。
            option = dialog.locator(".semi-radio").filter(has_text=declaration).first
            if await option.count():
                await option.click(timeout=6000)
            else:
                await dialog.get_by_text(declaration, exact=True).first.click(timeout=6000, force=True)
            await dialog.get_by_role("button", name="确定").click(timeout=6000)
            await dialog.wait_for(state="hidden", timeout=6000)
            douyin_logger.info(_msg("🧾", f"自主声明已选择「{declaration}」"))
            return True
        except Exception as exc:
            douyin_logger.warning(_msg("🧾", f"自主声明设置失败，跳过该步骤继续发布：{exc}"))
            return False

    async def apply_self_declaration(self, page: Page) -> None:
        if not self.declaration:
            return
        if not await self.set_self_declaration(page, self.declaration):
            raise RuntimeError(f"blocked Douyin declaration: {self.declaration}")

    async def set_collection(self, page: Page, collection_name: str) -> None:
        """抖音发布页选择合集（合集/系列）。

        未传 --collection 时不调用本方法。按名称在合集选择器中匹配目标合集；
        找不到目标时明确报错（不静默跳过，避免"以为入集了其实没有"）。

        2026-08-08 实测修正（issue #5）：`div:has-text(...)` 宽匹配会在发布页命中
        27 个祖先容器，`.first` 命中最外层整页容器导致下拉从未打开、误报「未找到」。
        正确入口是叶子节点「请选择合集」（div 无子 div，实测唯一命中 20px 高度）。
        """
        if not collection_name or not collection_name.strip():
            return
        needle = collection_name.strip()
        try:
            # 入口：叶子节点「请选择合集」（无子 div 的唯一 leaf），避免命中祖先容器
            entry = page.locator('div:has-text("请选择合集"):not(:has(div))').first
            if not await entry.count():
                # 兜底：已选择过合集时入口显示合集名，退而匹配「添加合集」叶子节点
                entry = page.locator('div:has-text("添加合集"):not(:has(div))').first
            await entry.click(timeout=6000)

            # 等待弹层/下拉出现
            await page.wait_for_timeout(1000)

            # 合集下拉真实 DOM（2026-08-08 实测）：选项为 .semi-select-option collection-opt，
            # 文本形如「英语新闻（训练版）\n共480个作品」；同时保留 [class*="dropdown-option"] 兼容
            option = page.locator(
                '.semi-select-option:has-text("{0}"), [class*="dropdown-option"]:has-text("{0}")'.format(
                    needle
                )
            ).first
            if not await option.count():
                douyin_logger.warning(_msg("📚", f"抖音合集「{needle}」未找到，跳过可选合集"))
                await page.keyboard.press("Escape")
                return

            await option.click(timeout=6000)
            await page.wait_for_timeout(500)
            douyin_logger.info(_msg("📚", f"已选择抖音合集「{needle}」"))
        except Exception as exc:
            douyin_logger.warning(_msg("📚", f"抖音合集选择失败，跳过可选合集：{exc}"))

    async def select_bgm(self, page: Page, bgm_name: str) -> bool:
        """为图文发布选择 BGM：可选增强功能，搜索无结果或异常均跳过不中断发布。"""
        try:
            # 点击「选择音乐」按钮
            music_entry = page.locator('text="选择音乐"').nth(1)
            if not await music_entry.count():
                music_entry = page.locator('text="选择音乐"').first
            await music_entry.wait_for(state="visible", timeout=10000)
            await music_entry.click()

            # 等待侧边栏出现并搜索
            sidesheet = page.locator(".semi-sidesheet-content").first
            await sidesheet.wait_for(state="visible", timeout=8000)
            search_input = sidesheet.locator('input.semi-input[placeholder="搜索音乐"]').first
            await search_input.wait_for(state="visible", timeout=5000)
            await search_input.fill(bgm_name)
            await search_input.press("Enter")

            # 等待搜索结果
            await asyncio.sleep(2)
            first_card = sidesheet.locator(".card-container-tmocjc").first
            try:
                await first_card.wait_for(state="visible", timeout=8000)
            except Exception:
                douyin_logger.warning(_msg("🎵", f"音乐「{bgm_name}」搜索结果为空，小人跳过"))
                await self._close_music_sidesheet(page)
                return False

            # 打印找到的音乐名称
            try:
                song_name_el = first_card.locator(".song-name-oRge4d").first
                if await song_name_el.count():
                    song_name = await song_name_el.inner_text()
                    douyin_logger.info(_msg("🎵", f"小人找到了: {song_name}"))
            except Exception:
                pass

            # JS 点击「使用」（按钮 visibility:hidden，普通 click 无效）
            apply_btn = first_card.locator(".apply-btn-LUPP0D").first
            await apply_btn.evaluate("el => el.click()")
            douyin_logger.info(_msg("🥳", f"BGM「{bgm_name}」已应用"))

            # 等待侧边栏关闭，超时则手动关闭
            try:
                await sidesheet.wait_for(state="hidden", timeout=5000)
            except Exception:
                await self._close_music_sidesheet(page)

            return True
        except Exception as exc:
            douyin_logger.warning(_msg("🎵", f"添加 BGM 时出错，跳过该步骤继续发布：{exc}"))
            try:
                await self._close_music_sidesheet(page)
            except Exception:
                pass
            return False

    async def _close_music_sidesheet(self, page: Page) -> None:
        try:
            close_btn = page.locator(".semi-sidesheet-close").first
            if await close_btn.count() and await close_btn.is_visible():
                await close_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass


class DouYinVideo(DouYinBaseUploader):
    def __init__(
        self,
        title,
        file_path,
        tags,
        publish_date: datetime | int,
        account_file,
        thumbnail_landscape_path=None,
        productLink="",
        productTitle="",
        thumbnail_portrait_path=None,
        desc: str | None = None,
        publish_strategy: str = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
        cdp_url: str | None = None,
        declaration: str = "无需添加自主声明",
        collection: str | None = None,
        browser_name: str | None = None,
        cdp_port: int | None = None,
        target_account: str | None = None,
        paid_video: DouyinPaidVideoSettings | None = None,
        submit: bool = True,
    ):
        super().__init__(
            publish_date=publish_date,
            account_file=account_file,
            publish_strategy=publish_strategy,
            debug=debug,
            headless=headless,
            cdp_url=cdp_url,
            browser_name=browser_name,
            cdp_port=cdp_port,
            target_account=target_account,
        )
        self.title = title
        self.file_path = file_path
        self.tags = tags
        self.thumbnail_landscape_path = thumbnail_landscape_path
        self.thumbnail_portrait_path = thumbnail_portrait_path
        self.productLink = productLink
        self.productTitle = productTitle
        self.desc = desc or ""
        self.declaration = declaration
        self.collection = collection
        self.paid_video = paid_video
        self.submit = submit
        self._paid_video_result = None

    async def validate_upload_args(self):
        await self.validate_base_args()
        if not self.title or not str(self.title).strip():
            raise ValueError("视频模式下，title 是必须的")
        if self.paid_video and self.paid_video.enabled and self.collection:
            raise ValueError("Douyin paid video does not support collection")

        self.file_path = str(self.validate_video_file(self.file_path))
        if self.thumbnail_landscape_path:
            self.thumbnail_landscape_path = str(self.validate_image_file(self.thumbnail_landscape_path))
        if self.thumbnail_portrait_path:
            self.thumbnail_portrait_path = str(self.validate_image_file(self.thumbnail_portrait_path))

    async def handle_upload_error(self, page):
        douyin_logger.warning(_msg("😵", "视频上传摔了一跤，小人马上重新上传"))
        await self.set_video_file_input(page, 'div.progress-div [class^="upload-btn-input"]')

    async def set_video_file_input(self, page: Page, selector: str) -> None:
        if requires_local_cdp_file_input(self.cdp_url, Path(self.file_path).stat().st_size):
            douyin_logger.info(_msg("📁", "大文件通过本机 CDP 路径交给 Chrome"))
            await set_local_file_input_via_cdp(page, selector, self.file_path)
            return
        await page.locator(selector).set_input_files(self.file_path)

    async def handle_auto_video_cover(self, page):
        if await page.get_by_text("请设置封面后再发布").first.is_visible():
            douyin_logger.info(_msg("🧍", "发布前还得先把封面弄好"))
            recommend_cover = page.locator('[class^="recommendCover-"]').first
            if await recommend_cover.count():
                douyin_logger.info(_msg("🏃", "小人去选第一个推荐封面"))
                try:
                    await recommend_cover.click()
                    await asyncio.sleep(1)
                    confirm_text = "是否确认应用此封面？"
                    if await page.get_by_text(confirm_text).first.is_visible():
                        douyin_logger.info(_msg("🪟", f"弹出确认框了: {confirm_text}"))
                        await page.get_by_role("button", name="确定").click()
                        douyin_logger.info(_msg("🥳", "推荐封面已经应用"))
                        await asyncio.sleep(1)
                    douyin_logger.info(_msg("🥳", "封面选择流程完成"))
                    return True
                except Exception as e:
                    douyin_logger.warning(_msg("😵", f"推荐封面没选成功: {e}"))
        return False

    async def set_thumbnail(self, page: Page):
        if not self.thumbnail_landscape_path and not self.thumbnail_portrait_path:
            return

        douyin_logger.info(_msg("🏃", "小人正在设置视频封面"))
        await self._clear_blocking_overlays(page)
        cover_locator_str = 'div.dy-creator-content-modal'
        cover_locator = page.locator(cover_locator_str).first
        trigger = page.get_by_text("选择封面", exact=True).first
        opened = False
        for _ in range(3):
            if await self._native_click(page, trigger):
                try:
                    await page.wait_for_selector(cover_locator_str, timeout=7000)
                    opened = True
                    break
                except Exception:
                    await self._clear_blocking_overlays(page)
        if not opened:
            raise RuntimeError("Douyin cover dialog did not open")

        await page.wait_for_timeout(1500)
        # version_2 封面弹窗有 4 个隐藏 file input：
        #   [0]/[1] 左侧“AI生成参考图”上传/替换，[2]/[3] 才是“上传封面”/替换。
        # 旧代码用 .first 传到了 AI 参考图（不会成为封面）→ 这就是“传了却没封面”的根因。
        # 取 input.semi-upload-hidden-input 的第 2 个（nth(1)），即真正的封面上传输入。
        cover_upload = cover_locator.locator("input.semi-upload-hidden-input").nth(1)

        if self.thumbnail_portrait_path:
            try:
                await cover_locator.get_by_text("设置竖封面", exact=True).first.click(timeout=3000)
                await page.wait_for_timeout(800)
            except Exception:
                pass
            await cover_upload.set_input_files(self.thumbnail_portrait_path)
            await page.wait_for_timeout(3000)
            douyin_logger.info(_msg("🖼️", "竖版封面已上传到预览"))
        if self.thumbnail_landscape_path:
            try:
                await cover_locator.get_by_text("设置横封面", exact=True).first.click(timeout=3000)
                await page.wait_for_timeout(800)
            except Exception:
                pass
            await cover_upload.set_input_files(self.thumbnail_landscape_path)
            await page.wait_for_timeout(3000)
            douyin_logger.info(_msg("🖼️", "横版封面已上传到预览"))

        finish = cover_locator.get_by_role("button", name="完成", exact=True).first
        for _ in range(20):
            if await finish.count():
                classes = await finish.get_attribute("class") or ""
                if "disabled" not in classes:
                    break
            await page.wait_for_timeout(500)
        if not await self._native_click(page, finish):
            raise RuntimeError("Douyin cover dialog finish button unavailable")
        douyin_logger.info(_msg("🥳", "视频封面设置完成"))
        await cover_locator.wait_for(state="detached", timeout=20000)

    async def _paid_switch_control(self, root, name: str):
        for role in ("switch", "checkbox"):
            control = root.get_by_role(role, name=name, exact=True).first
            if await control.count():
                return control

        label = root.get_by_text(name, exact=True).first
        if not await label.count():
            raise RuntimeError(f"blocked Douyin paid video: missing switch {name}")
        section = label.locator("xpath=ancestor::*[.//input[@role='switch']][1]")
        control = section.locator('input[role="switch"]').first
        if not await control.count():
            raise RuntimeError(f"blocked Douyin paid video: missing switch {name}")
        return control

    async def _paid_switch(self, root, name: str, checked: bool) -> None:
        control = await self._paid_switch_control(root, name)
        try:
            current = await control.is_checked()
        except Exception:
            aria_checked = await control.get_attribute("aria-checked")
            if aria_checked is None:
                raise RuntimeError(f"blocked Douyin paid video: cannot read switch {name}")
            current = aria_checked == "true"
        if current != checked:
            await control.click(force=True)

    async def _paid_textbox_control(self, root, label: str):
        aliases = {
            "价格": "请输入视频售价",
            "商品标题": "请输入付费场景下的视频标题",
            "试看时长": "请配置试看时长",
        }
        for name in (label, aliases.get(label, label)):
            control = root.get_by_role("textbox", name=name, exact=True).first
            if await control.count():
                return control
        raise RuntimeError(f"blocked Douyin paid video: missing textbox {label}")

    async def _paid_textbox(self, root, label: str, value: str) -> None:
        control = await self._paid_textbox_control(root, label)
        await control.fill(value)
        actual = await control.input_value()
        if actual.strip() != value:
            raise RuntimeError(f"blocked Douyin paid video: {label} readback mismatch")
    async def _paid_radio(self, root, value: str) -> None:
        aliases = {
            "当前封面": "使用原视频封面",
            "更改封面": "上传新封面",
        }
        actual_value = aliases.get(value, value)
        control = root.get_by_role("radio", name=actual_value, exact=True).first
        if not await control.count():
            raise RuntimeError(f"blocked Douyin paid video: missing choice {value}")
        await control.click(force=True)

    async def _paid_agreement_control(self, root):
        label = root.get_by_text("协议确认", exact=True).first
        if not await label.count():
            raise RuntimeError("blocked Douyin paid video: missing agreement checkbox")
        row = label.locator("xpath=..")
        icon = row.locator("div[class^='checkIcon']").first
        if not await icon.count():
            raise RuntimeError("blocked Douyin paid video: missing agreement checkbox")
        return icon

    async def _read_paid_agreement(self, root) -> bool:
        icon = await self._paid_agreement_control(root)
        return await icon.locator("svg").count() > 0

    async def _paid_agreement(self, root, checked: bool) -> None:
        icon = await self._paid_agreement_control(root)
        current = await self._read_paid_agreement(root)
        if current != checked:
            await icon.click()
            await asyncio.sleep(0.3)
            if await self._read_paid_agreement(root) != checked:
                raise RuntimeError("blocked Douyin paid video: agreement checkbox did not change")

    async def _paid_entry(self, page: Page):
        entry = page.get_by_text("付费或会员视频", exact=True).first
        if not await entry.count():
            raise RuntimeError("blocked Douyin paid video: missing paid-video entry")
        section = entry.locator("xpath=ancestor::*[.//input[@role='switch']][1]")
        switch = section.locator('input[role="switch"]').first
        if not await switch.count():
            raise RuntimeError("blocked Douyin paid video: missing paid-video switch")
        return section, switch

    async def _open_paid_video_panel(self, page: Page):
        section, switch = await self._paid_entry(page)
        if not await switch.is_checked():
            await switch.click(force=True)
            await page.wait_for_timeout(300)
            for _ in range(3):
                confirmations = page.get_by_role("button", name="确定", exact=True)
                clicked = False
                for index in range(await confirmations.count() - 1, -1, -1):
                    confirm = confirmations.nth(index)
                    if await confirm.is_visible():
                        await confirm.click(force=True)
                        clicked = True
                        await page.wait_for_timeout(300)
                        break
                if not clicked:
                    break
        await page.wait_for_timeout(300)
        try:
            await section.get_by_role("radio", name="单点售卖", exact=True).first.wait_for(
                state="visible", timeout=5000
            )
        except Exception as exc:
            raise RuntimeError("blocked Douyin paid video: paid controls did not open") from exc
        return section

    async def _set_paid_trial_range(self, page: Page, root, start_sec: int, end_sec: int) -> None:
        await self._paid_radio(root, "有试看")
        editor = root.get_by_role("button", name="编辑", exact=True).first
        if not await editor.count():
            raise RuntimeError("blocked Douyin paid video: missing trial editor")
        await editor.click()
        await page.wait_for_timeout(500)
        modal = page.locator('[role="modal"]').filter(has_text="付费配置").first
        await modal.wait_for(state="visible", timeout=10000)
        sliders = modal.locator(".semi-slider")
        if not await sliders.count():
            raise RuntimeError("blocked Douyin paid video: missing trial slider")
        slider = sliders.nth(await sliders.count() - 1)
        maximum = int((await slider.locator(".semi-slider-boundary-max").text_content() or "").strip())
        if maximum <= 0 or end_sec > maximum:
            raise RuntimeError("blocked Douyin paid video: invalid trial slider range")
        slider_box = await slider.bounding_box()
        handles = slider.locator(".semi-slider-handle")
        if not slider_box or await handles.count() < 2:
            raise RuntimeError("blocked Douyin paid video: missing trial slider handles")
        for index, seconds in enumerate((start_sec, end_sec)):
            handle = handles.nth(index)
            handle_box = await handle.bounding_box()
            if not handle_box:
                raise RuntimeError("blocked Douyin paid video: trial slider handle unavailable")
            target_x = slider_box["x"] + slider_box["width"] * seconds / maximum
            target_y = handle_box["y"] + handle_box["height"] / 2
            await page.mouse.move(handle_box["x"] + handle_box["width"] / 2, target_y)
            await page.mouse.down()
            await page.mouse.move(target_x, target_y)
            await page.mouse.up()
        save = modal.get_by_role("button", name="保存", exact=True).first
        if not await save.count():
            raise RuntimeError("blocked Douyin paid video: missing trial save button")
        await save.click()
        await modal.wait_for(state="hidden", timeout=10000)

    async def _set_paid_trial(self, page: Page, root, settings: DouyinPaidVideoSettings) -> None:
        if settings.trial_enabled:
            await self._set_paid_trial_range(
                page, root, settings.trial_start_sec, settings.trial_end_sec
            )
        else:
            await self._paid_radio(root, "无试看")

    async def set_paid_video_settings(self, page: Page) -> dict | None:
        if self.paid_video is None:
            return None
        requested = self.paid_video.to_snapshot()
        if not self.paid_video.enabled:
            _, switch = await self._paid_entry(page)
            if await switch.is_checked():
                raise RuntimeError("blocked Douyin paid video: paid-video entry is enabled but request disables it")
            self._paid_video_result = {
                "requested": requested,
                "observed": {"enabled": False},
                "validated_only": {
                    "subtitleModeText": self.paid_video.subtitle_mode_text,
                    "collectionId": self.paid_video.collection_id,
                },
                "verified": True,
            }
            return self._paid_video_result

        settings = self.paid_video
        root = await self._open_paid_video_panel(page)
        try:
            await self._paid_radio(root, settings.sale_mode_text)
            await self._paid_radio(root, settings.price_mode_text)
            await self._paid_textbox(root, "价格", f"{settings.price_yuan:.2f}")
            await self._paid_textbox(root, "商品标题", settings.product_title)
            await self._paid_radio(root, settings.cover_mode_text)
            if settings.cover_asset_ref is not None:
                cover_inputs = root.locator('input[type="file"]')
                if not await cover_inputs.count():
                    raise RuntimeError("blocked Douyin paid video: missing cover upload input")
                cover_input = cover_inputs.nth(await cover_inputs.count() - 1)
                await cover_input.set_input_files(str(settings.cover_asset_ref))
            await self._set_paid_trial(page, root, settings)
            await self._paid_switch(root, "营销托管", settings.marketing_managed)
            await self._paid_agreement(root, settings.agreement_confirmed)
        except Exception as exc:
            raise RuntimeError(f"blocked Douyin paid video: {exc}") from exc

        first = await self.read_paid_video_settings(root)
        await page.wait_for_timeout(1000)
        second = await self.read_paid_video_settings(root)
        expected = settings.to_ui_snapshot()
        if expected["coverAssetRef"]:
            expected["coverAssetRef"] = Path(expected["coverAssetRef"]).name
        if first != expected or second != expected or first != second:
            raise RuntimeError("blocked Douyin paid video: two readbacks do not match requested settings")

        self._paid_video_result = {
            "requested": requested,
            "observed": second,
            "validated_only": {
                "subtitleModeText": settings.subtitle_mode_text,
                "collectionId": settings.collection_id,
            },
            "verified": True,
        }
        return self._paid_video_result

    async def _read_paid_switch(self, root, name: str) -> bool:
        control = await self._paid_switch_control(root, name)
        try:
            return bool(await control.is_checked())
        except Exception:
            aria_checked = await control.get_attribute("aria-checked")
            if aria_checked is None:
                raise RuntimeError(f"blocked Douyin paid video: cannot read switch {name}")
            return aria_checked == "true"
    async def _read_paid_textbox(self, root, label: str) -> str:
        control = await self._paid_textbox_control(root, label)
        return (await control.input_value()).strip()
    async def _read_paid_trial(self, root) -> tuple[bool, int, int]:
        choice = await self._read_paid_choice(root, {"有试看", "无试看"}, "trialEnabled")
        if choice == "无试看":
            return False, 0, 0
        value = await self._read_paid_textbox(root, "试看时长")
        match = re.fullmatch(r"(\d+):(\d+)\s*~\s*(\d+):(\d+)", value)
        if not match:
            raise RuntimeError("blocked Douyin paid video: invalid trial time range")
        start_minutes, start_seconds, end_minutes, end_seconds = (
            int(part) for part in match.groups()
        )
        return (
            True,
            start_minutes * 60 + start_seconds,
            end_minutes * 60 + end_seconds,
        )
    async def _read_paid_choice(self, root, allowed: set[str], field_name: str) -> str:
        values = set()
        for value in allowed:
            radio = root.get_by_role("radio", name=value, exact=True).first
            if not await radio.count():
                continue
            label = radio.locator("xpath=ancestor::label[1]")
            classes = await label.get_attribute("class") if await label.count() else ""
            if classes and "semi-radio-checked" in classes:
                values.add(value)
        if not values:
            checked = root.get_by_role("radio", checked=True)
            for index in range(await checked.count()):
                radio = checked.nth(index)
                label = radio.locator("xpath=ancestor::label[1]")
                text = await (label if await label.count() else radio).inner_text()
                if text.strip():
                    values.add(text.strip())
        matches = values & allowed
        if len(matches) != 1:
            raise RuntimeError(f"blocked Douyin paid video: cannot read {field_name}")
        return next(iter(matches))

    async def read_paid_video_settings(self, root) -> dict:
        try:
            cover_mode = await self._read_paid_choice(
                root, {"使用原视频封面", "上传新封面"}, "coverModeText"
            )
            cover_mode_text = {
                "使用原视频封面": "当前封面",
                "上传新封面": "更改封面",
            }[cover_mode]
            cover_asset_ref = None
            if cover_mode_text == "更改封面":
                cover_inputs = root.locator('input[type="file"]')
                if await cover_inputs.count():
                    cover_input = cover_inputs.nth(await cover_inputs.count() - 1)
                    cover_files = await cover_input.evaluate(
                        "(input) => input.files && input.files[0] ? input.files[0].name : ''"
                    )
                    cover_asset_ref = cover_files or None
            trial_enabled, trial_start_sec, trial_end_sec = await self._read_paid_trial(root)
            entry_switch = root.locator('input[role="switch"]').first
            if not await entry_switch.count():
                raise RuntimeError("blocked Douyin paid video: missing paid-video switch")
            return {
                "enabled": bool(await entry_switch.is_checked()),
                "saleModeText": await self._read_paid_choice(
                    root, {"单点售卖", "组合售卖"}, "saleModeText"
                ),
                "priceModeText": await self._read_paid_choice(
                    root, {"付费视频", "付费视频（会员免费看）", "会员视频"}, "priceModeText"
                ),
                "priceYuan": f"{Decimal(await self._read_paid_textbox(root, '价格')):.2f}",
                "productTitle": await self._read_paid_textbox(root, "商品标题"),
                "coverModeText": cover_mode_text,
                "coverAssetRef": cover_asset_ref,
                "trialEnabled": trial_enabled,
                "trialStartSec": trial_start_sec,
                "trialEndSec": trial_end_sec,
                "marketingManaged": await self._read_paid_switch(root, "营销托管"),
                "agreementConfirmed": await self._read_paid_agreement(root),
            }
        except (KeyError, ValueError, TypeError) as exc:
            raise RuntimeError(f"blocked Douyin paid video: invalid readback: {exc}") from exc

    async def upload(self, playwright: Playwright) -> dict:
        douyin_logger.info(_msg("🧍", "小人先检查 cookie、视频文件、封面和发布时间"))
        await self.validate_upload_args()
        douyin_logger.info(_msg("🥳", "上传前检查通过"))

        context_kwargs = {"permissions": ["geolocation"]}
        if not self.cdp_url:
            context_kwargs["storage_state"] = f"{self.account_file}"
        session = await open_browser_session(
            playwright,
            cdp_url=self.cdp_url,
            launch_kwargs={"headless": self.headless, "channel": "chromium"},
            context_kwargs=context_kwargs,
        )
        self._active_session = session
        context = await set_init_script(session.context)

        expected_identity = await extract_douyin_identity_from_context(
            context,
            session=session,
            browser_name=self.browser_name,
            cdp_port=self.cdp_port,
        )
        require_publish_identity(expected_identity)
        if self.target_account and not identity_matches(expected_identity, self.target_account):
            raise RuntimeError("blocked publish identity: target account does not match Douyin page")
        page = await session.new_task_page()
        await page.goto("https://creator.douyin.com/creator-micro/content/upload", wait_until="domcontentloaded", timeout=90000)
        douyin_logger.info(_msg("🏃", f"小人开始搬运视频: {self.title}.mp4"))
        douyin_logger.info(_msg("🧭", "小人正在赶往上传主页"))
        await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload", timeout=90000)
        # wait_for_url 完成时上传页可能尚未渲染出文件 input（实测偶发），先等它挂载再 set_input_files
        await page.wait_for_selector("div[class^='container'] input", state="attached", timeout=60000)
        await self.set_video_file_input(page, "div[class^='container'] input")

        while True:
            current_url = page.url
            if "creator.douyin.com/creator-micro/content/post/video" in current_url:
                douyin_logger.info(_msg("🥳", "已经进入 version_2 发布页面"))
                break
            if "creator.douyin.com/creator-micro/content/publish" in current_url:
                douyin_logger.info(_msg("🥳", "已经进入 version_1 发布页面"))
                break
            try:
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/publish?enter_from=publish_page",
                    timeout=3000,
                )
                douyin_logger.info(_msg("🥳", "已经进入 version_1 发布页面"))
                break
            except Exception:
                try:
                    await page.wait_for_url(
                        "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page",
                        timeout=3000,
                    )
                    douyin_logger.info(_msg("🥳", "已经进入 version_2 发布页面"))
                    break
                except Exception:
                    douyin_logger.debug(_msg("🧍", "还没进到视频发布页面，小人继续等一会"))
                    await asyncio.sleep(0.5)

        await asyncio.sleep(1)
        douyin_logger.info(_msg("✍️", "小人开始填标题、描述和话题"))
        await self.fill_title_and_description(page, self.title, self.desc or self.title, self.tags)
        douyin_logger.info(_msg("🏷️", f"小人一共贴了 {len(self.tags)} 个话题"))

        while True:
            try:
                number = await page.locator('[class^="long-card"] div:has-text("重新上传")').count()
                if number > 0:
                    douyin_logger.success(_msg("🥳", "视频已经传完啦"))
                    break
                douyin_logger.info(_msg("🏃", "小人正在努力上传视频"))
                await asyncio.sleep(2)
                if await page.locator('div.progress-div > div:has-text("上传失败")').count():
                    douyin_logger.error(_msg("😵", "检测到上传失败，小人准备重试"))
                    await self.handle_upload_error(page)
            except Exception:
                douyin_logger.debug(_msg("🧍", "小人还在等视频上传完成"))
                await asyncio.sleep(2)

        if self.productLink and self.productTitle:
            douyin_logger.info(_msg("🛒", "小人正在设置商品链接"))
            await self.set_product_link(page, self.productLink, self.productTitle)
            douyin_logger.info(_msg("🥳", "商品链接设置完成"))

        await self.set_thumbnail(page)

        await self.apply_self_declaration(page)
        await self.set_paid_video_settings(page)

        if self.collection:
            await self.set_collection(page, self.collection)

        third_part_element = '[class^="info"] > [class^="first-part"] div div.semi-switch'
        if await page.locator(third_part_element).count():
            if "semi-switch-checked" not in await page.eval_on_selector(third_part_element, "div => div.className"):
                await page.locator(third_part_element).locator("input.semi-switch-native-control").click()

        if self.publish_strategy == DOUYIN_PUBLISH_STRATEGY_SCHEDULED and self.publish_date != 0:
            await self.set_schedule_time_douyin(page, self.publish_date)

        observed_identity = await extract_douyin_identity_from_context(context, session=session)
        assert_same_publish_identity(expected_identity, observed_identity)
        if not self.submit:
            if await save_storage_state_if_owned(session, self.account_file):
                douyin_logger.success(_msg("🥳", "cookie 更新完毕"))
            result = {
                "status": "prepared",
                "platform": "douyin",
                "browser_name": self.browser_name,
                "cdp_port": self.cdp_port,
                "has_stable_id": bool(expected_identity.stable_id),
                "account_match": True,
                "submitted": False,
                "paid_video": self._paid_video_result,
                "url": page.url,
                "scheduled_at": None,
                "focus_fallback_used": session.focus_fallback_used,
            }
            self._upload_succeeded = True
            return result

        while True:
            try:
                # 移除会拦截发布按钮点击的新手引导/话题下拉浮层
                await page.evaluate(
                    "() => { document.querySelectorAll('.shepherd-element, .shepherd-modal-overlay-container, [class*=\"mention-wrapper\"]').forEach(e => e.remove()); }"
                )
                if await has_douyin_sms_challenge(page):
                    raise RuntimeError("blocked Douyin publish: SMS verification challenge requires manual input")
                publish_button = page.get_by_role("button", name="发布", exact=True)
                if await publish_button.count():
                    observed_identity = await extract_douyin_identity_from_context(context, session=session)
                    assert_same_publish_identity(expected_identity, observed_identity)
                    await publish_button.click(force=True)
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/manage**",
                    timeout=3000,
                )
                douyin_logger.success(_msg("🥳", "视频发布成功，小人开心收工"))
                break
            except RuntimeError:
                raise
            except Exception:
                await self.handle_auto_video_cover(page)
                douyin_logger.info(_msg("🏃", "小人正在冲刺发布视频"))
                if self.debug:
                    await page.screenshot(full_page=True)
                await asyncio.sleep(0.5)
        if await save_storage_state_if_owned(session, self.account_file):
            douyin_logger.success(_msg("🥳", "cookie 更新完毕"))
        await asyncio.sleep(2)
        result = {
            "status": "success",
            "platform": "douyin",
            "browser_name": self.browser_name,
            "cdp_port": self.cdp_port,
            "has_stable_id": bool(expected_identity.stable_id),
            "account_match": True,
            "submitted": True,
            "paid_video": self._paid_video_result,
            "url": page.url if "content/manage" in page.url else "",
            "scheduled_at": self.publish_date.isoformat() if self.publish_strategy == DOUYIN_PUBLISH_STRATEGY_SCHEDULED else None,
            "focus_fallback_used": session.focus_fallback_used,
        }
        self._upload_succeeded = True
        return result

    async def douyin_upload_video(self):
        async with async_playwright() as playwright:
            try:
                return await self.upload(playwright)
            finally:
                if self._active_session is not None:
                    await self._active_session.close(success=self._upload_succeeded)

    async def main(self):
        await self.douyin_upload_video()


class DouYinNote(DouYinBaseUploader):
    def __init__(
        self,
        image_paths,
        note,
        tags,
        publish_date: datetime | int,
        account_file,
        title: str | None = None,
        publish_strategy: str = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
        cdp_url: str | None = None,
        bgm: str = "",
    ):
        super().__init__(
            publish_date=publish_date,
            account_file=account_file,
            publish_strategy=publish_strategy,
            debug=debug,
            headless=headless,
            cdp_url=cdp_url,
        )
        self.image_paths = image_paths
        self.note = note or ""
        self.title = title or (self.note[:30] if self.note else "")
        self.tags = tags or []
        self.bgm = bgm or ""

    async def validate_upload_args(self):
        await self.validate_base_args()
        if not self.title or not str(self.title).strip():
            raise ValueError("图文模式下，title 是必须的")

        if len(self.title) > 20:
            raise ValueError(f"标题不能超过20字符，当前: {len(self.title)}字符")

        if not self.image_paths:
            raise ValueError("图文模式下，图片是必须的")

        if isinstance(self.image_paths, (str, Path)):
            self.image_paths = [self.image_paths]

        if len(self.image_paths) > 35:
            raise ValueError("图文模式下最多只支持上传 35 张图片")

        note_len = len(self.note) if self.note else 0
        if note_len > 1000:
            raise ValueError(f"正文不能超过1000字符，当前: {note_len}字符")

        normalized_image_paths = []
        for image_path in self.image_paths:
            normalized_image_paths.append(str(self.validate_image_file(image_path)))
        self.image_paths = normalized_image_paths

    async def upload_note_content(self, page: Page) -> None:
        douyin_logger.info(_msg("🏃", f"小人开始搬运图文，共 {len(self.image_paths)} 张图片"))
        douyin_logger.info(_msg("🔀", "小人正在切换到图文发布"))
        await page.get_by_text("发布图文", exact=True).click()
        await page.wait_for_timeout(1000)

        douyin_logger.info(_msg("📤", "小人正在上传图片"))
        await page.locator("div[class^='container'] input[accept*='image']").set_input_files(self.image_paths)

        while True:
            try:
                await page.wait_for_url(
                    "**/creator-micro/content/post/image?**",
                    timeout=3000,
                )
                douyin_logger.info(_msg("🥳", "已经进入图文发布页面"))
                break
            except Exception:
                douyin_logger.debug(_msg("🧍", "小人还在等图片上传完成"))
                await asyncio.sleep(0.5)

        await asyncio.sleep(1)
        douyin_logger.info(_msg("✍️", "小人开始填标题、描述和话题"))
        await self.fill_title_and_description(page, self.title, self.note, self.tags)
        title_len = len(self.title) if self.title else 0
        tags_text = " ".join(f"#{t}" for t in self.tags) if self.tags else ""
        desc_and_tags_len = len(self.note or "") + (len(tags_text) + 2 if self.tags else 0)
        douyin_logger.info(_msg("📝", f"标题总字数: {title_len}，描述+话题总字数: {desc_and_tags_len}"))
        douyin_logger.info(_msg("🏷️", f"小人一共贴了 {len(self.tags)} 个话题"))

        if self.bgm:
            await self.select_bgm(page, self.bgm)

        if self.publish_strategy == DOUYIN_PUBLISH_STRATEGY_SCHEDULED and self.publish_date != 0:
            await self.set_schedule_time_douyin(page, self.publish_date)

        while True:
            try:
                publish_button = page.get_by_role("button", name="发布", exact=True)
                if await publish_button.count():
                    await publish_button.click()
                await page.wait_for_url(
                    "**/creator-micro/content/manage?enter_from=publish**",
                    timeout=3000,
                )
                douyin_logger.success(_msg("🥳", "图文发布成功，小人开心收工"))
                break
            except Exception:
                douyin_logger.info(_msg("🏃", "小人正在冲刺发布图文"))
                await asyncio.sleep(0.5)

    async def upload(self, playwright: Playwright) -> None:
        douyin_logger.info(_msg("🧍", "小人先检查 cookie、图片和发布时间"))
        await self.validate_upload_args()
        douyin_logger.info(_msg("🥳", "图文上传前检查通过"))

        session = await open_browser_session(
            playwright,
            cdp_url=self.cdp_url,
            launch_kwargs={"headless": self.headless, "channel": "chromium"},
            context_kwargs=(
                {"permissions": ["geolocation"]}
                if self.cdp_url
                else {"storage_state": f"{self.account_file}", "permissions": ["geolocation"]}
            ),
        )
        context = await set_init_script(session.context)

        upload_success = False
        try:
            page = await session.new_task_page()
            await page.goto("https://creator.douyin.com/creator-micro/content/upload", wait_until="domcontentloaded", timeout=90000)
            douyin_logger.info(_msg("🧭", "小人正在赶往图文发布页"))
            await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload", timeout=90000)

            await self.upload_note_content(page)
            upload_success = True
        finally:
            if upload_success:
                if await save_storage_state_if_owned(session, self.account_file):
                    douyin_logger.success(_msg("🥳", "cookie 更新完毕"))
                await asyncio.sleep(2)
            await session.close(success=upload_success)

    async def douyin_upload_note(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
