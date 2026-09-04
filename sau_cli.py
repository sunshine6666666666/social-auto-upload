from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from conf import BASE_DIR

try:
    from conf import YT_MAX_DURATION_SECONDS
except Exception:
    # 保守默认：未验证账号 YouTube 上传上限 15 分钟；已验证账号可在 conf.py 覆写为 43200（12 小时）。
    YT_MAX_DURATION_SECONDS = 900
from uploader.bilibili_uploader.runtime import (
    add_archive_to_season,
    export_bilibili_cdp_account,
    get_bilibili_cdp_identity,
    fetch_bilibili_archive_cid,
    find_bilibili_archive_aid,
    read_bilibili_archive_matches,
    resolve_bilibili_season_id,
    resolve_bilibili_section_id,
    run_biliup_command,
    read_bilibili_account_identity,
)
from uploader.douyin_uploader.main import (
    DOUYIN_PUBLISH_STRATEGY_IMMEDIATE,
    DOUYIN_PUBLISH_STRATEGY_SCHEDULED,
    DouYinNote,
    DouYinVideo,
    cookie_auth as douyin_cookie_auth,
    douyin_setup,
    get_douyin_account_identity,
)
from uploader.ks_uploader.main import (
    KUAISHOU_PUBLISH_STRATEGY_IMMEDIATE,
    KUAISHOU_PUBLISH_STRATEGY_SCHEDULED,
    KSNote,
    KSVideo,
    cookie_auth as kuaishou_cookie_auth,
    ks_setup,
)
from uploader.tencent_uploader.main import (
    TENCENT_PUBLISH_STRATEGY_IMMEDIATE,
    TENCENT_PUBLISH_STRATEGY_SCHEDULED,
    TencentVideo,
    cookie_auth as tencent_cookie_auth,
    tencent_setup,
)
from uploader.xiaohongshu_uploader.main import (
    XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE,
    XIAOHONGSHU_PUBLISH_STRATEGY_SCHEDULED,
    XiaoHongShuNote,
    XiaoHongShuVideo,
    cookie_auth as xiaohongshu_cookie_auth,
    xiaohongshu_setup,
)
from uploader.douyin_uploader.paid_video import DouyinPaidVideoSettings, parse_peach_douyin_target
from uploader.youtube_uploader.main import (
    YouTubeVideo,
    cookie_auth as youtube_cookie_auth,
    get_youtube_account_identity,
    youtube_setup,
)
from utils.browser_selector import resolve_browser_target, resolve_browser_targets
from utils.browser_runtime import begin_task, browser_task_lock, finish_task
from utils.account_identity import (
    assert_same_publish_identity,
    identity_matches,
    observation_status,
    require_publish_identity,
)

SCHEDULE_FORMAT = "%Y-%m-%d %H:%M"


@dataclass(slots=True)
class DouyinVideoUploadRequest:
    account_name: str
    video_file: Path
    title: str
    description: str
    tags: list[str]
    publish_date: datetime | int
    thumbnail_file: Path | None = None
    thumbnail_landscape_file: Path | None = None
    thumbnail_portrait_file: Path | None = None
    product_link: str = ""
    product_title: str = ""
    publish_strategy: str = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE
    debug: bool = True
    headless: bool = True
    cdp_url: str | None = None
    declaration: str = "无需添加自主声明"
    collection: str | None = None
    browser_name: str | None = None
    cdp_port: int | None = None
    target_account: str | None = None
    paid_target_config: Path | None = None
    paid_video: DouyinPaidVideoSettings | None = None
    submit: bool = True


@dataclass(slots=True)
class DouyinNoteUploadRequest:
    account_name: str
    image_files: list[Path]
    title: str
    note: str
    tags: list[str]
    publish_date: datetime | int
    publish_strategy: str = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE
    debug: bool = True
    headless: bool = True
    cdp_url: str | None = None
    bgm: str = ""

@dataclass(slots=True)
class KuaishouVideoUploadRequest:
    account_name: str
    video_file: Path
    title: str
    description: str
    tags: list[str]
    publish_date: datetime | int
    thumbnail_file: Path | None = None
    publish_strategy: str = KUAISHOU_PUBLISH_STRATEGY_IMMEDIATE
    debug: bool = True
    headless: bool = True
    cdp_url: str | None = None


@dataclass(slots=True)
class KuaishouNoteUploadRequest:
    account_name: str
    image_files: list[Path]
    title: str
    note: str
    tags: list[str]
    publish_date: datetime | int
    publish_strategy: str = KUAISHOU_PUBLISH_STRATEGY_IMMEDIATE
    debug: bool = True
    headless: bool = True
    cdp_url: str | None = None


@dataclass(slots=True)
class XiaohongshuVideoUploadRequest:
    account_name: str
    video_file: Path
    title: str
    description: str
    tags: list[str]
    publish_date: datetime | int
    thumbnail_file: Path | None = None
    publish_strategy: str = XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE
    debug: bool = True
    headless: bool = True
    cdp_url: str | None = None
    submit: bool = True


@dataclass(slots=True)
class XiaohongshuNoteUploadRequest:
    account_name: str
    image_files: list[Path]
    title: str
    note: str
    tags: list[str]
    publish_date: datetime | int
    publish_strategy: str = XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE
    debug: bool = True
    headless: bool = True
    cdp_url: str | None = None


@dataclass(slots=True)
class BilibiliVideoUploadRequest:
    account_name: str
    video_file: Path
    title: str
    description: str
    tid: int
    tags: list[str]
    publish_date: datetime | int
    line: str = "cnbd"
    thumbnail_file: Path | None = None
    charging_pay: bool = False
    collection: str | None = None
    cdp_url: str | None = None
    browser_name: str | None = None
    cdp_port: int | None = None
    target_account: str | None = None
    focus_fallback_used: bool = False


@dataclass(slots=True)
class TencentVideoUploadRequest:
    account_name: str
    video_file: Path
    title: str
    description: str
    tags: list[str]
    publish_date: datetime | int
    thumbnail_file: Path | None = None
    thumbnail_landscape_file: Path | None = None
    thumbnail_portrait_file: Path | None = None
    short_title: str | None = None
    category: str | None = None
    is_draft: bool = False
    publish_strategy: str = TENCENT_PUBLISH_STRATEGY_IMMEDIATE
    debug: bool = True
    headless: bool = True
    cdp_url: str | None = None


@dataclass(slots=True)
class YouTubeVideoUploadRequest:
    account_name: str
    video_file: Path
    title: str
    description: str
    tags: list[str]
    thumbnail_file: Path | None = None
    playlist: str | None = None
    visibility: str = "public"
    debug: bool = True
    headless: bool = False
    cdp_url: str | None = None
    submit: bool = True
    schedule: datetime | None = None
    timezone: str = "Asia/Shanghai"
    browser_name: str | None = None
    cdp_port: int | None = None
    target_account: str | None = None


def has_interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def resolve_runtime_home() -> Path:
    return Path(BASE_DIR)


def resolve_account_file(platform: str, account_name: str) -> Path:
    if not account_name or account_name in {".", ".."} or Path(account_name).name != account_name or "\\" in account_name:
        raise ValueError("account name must be a single safe path component")
    bilibili_dir = os.environ.get("SAU_BILIBILI_ACCOUNT_DIR") if platform == "bilibili" else None
    account_file = (
        Path(bilibili_dir).expanduser() / f"{account_name}.json"
        if bilibili_dir
        else resolve_runtime_home() / "cookies" / f"{platform}_{account_name}.json"
    )
    account_file.parent.mkdir(parents=True, exist_ok=True)
    return account_file


def parse_tags(raw_tags: str | None) -> list[str]:
    if not raw_tags:
        return []

    tags: list[str] = []
    for item in raw_tags.split(","):
        cleaned = item.strip().lstrip("#")
        if cleaned:
            tags.append(cleaned)
    return tags


def parse_image_files(raw_files: Iterable[Path]) -> list[Path]:
    return [Path(file) for file in raw_files]


def parse_schedule(raw_schedule: str | None) -> datetime | int:
    if not raw_schedule:
        return 0
    return datetime.strptime(raw_schedule, SCHEDULE_FORMAT)


def _sanitized_identity_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if re.search(r"cookie|token|csrf|authorization|password", message, re.IGNORECASE):
        return "identity extraction failed"
    return re.sub(r"\s+", " ", message)[:240]


async def _read_platform_identity(platform: str, target):
    if platform == "douyin":
        return await get_douyin_account_identity(
            cdp_url=target.cdp_url, browser_name=target.name, cdp_port=target.port
        )
    if platform == "youtube":
        return await get_youtube_account_identity(
            cdp_url=target.cdp_url, browser_name=target.name, cdp_port=target.port
        )
    if platform == "bilibili":
        return await get_bilibili_cdp_identity(target.cdp_url, target)
    raise ValueError(f"unsupported scan platform: {platform}")


async def _scan_identity(platform: str, target) -> dict:
    try:
        identity = await _read_platform_identity(platform, target)
        return {
            "status": observation_status(identity),
            "platform": platform,
            "browser_name": target.name,
            "cdp_port": target.port,
            "identity": identity.to_dict(),
            "reason": None if identity.logged_in else "login_required",
        }
    except Exception as exc:
        return {
            "status": "error",
            "platform": platform,
            "browser_name": target.name,
            "cdp_port": target.port,
            "identity": {},
            "reason": _sanitized_identity_error(exc),
        }


async def scan_accounts(selectors: Sequence[str], platforms: Sequence[str]) -> dict:
    targets = resolve_browser_targets(selectors)
    items = []
    for target in targets:
        for platform in platforms:
            items.append(await _scan_identity(platform, target))
    summary = {status: sum(item["status"] == status for item in items) for status in ("logged_in", "interaction_required", "error")}
    summary["total"] = len(items)
    return {"items": items, "summary": summary}


async def _resolve_upload_target(args):
    selectors = [item.strip() for item in (getattr(args, "browsers", "") or "").split(",") if item.strip()]
    if not selectors:
        return resolve_browser_target(getattr(args, "browser", None), getattr(args, "cdp_url", None))
    targets = resolve_browser_targets(selectors)
    if not targets:
        raise RuntimeError("no browser target resolved")
    selector = getattr(args, "target_account", None)
    if len(targets) > 1 and not selector:
        raise ValueError("multiple browser targets require --target-account")
    if not selector:
        return targets[0]
    matches = []
    for candidate in targets:
        identity = await _read_platform_identity(args.platform, candidate)
        if identity.logged_in and identity_matches(identity, selector):
            matches.append(candidate)
    if len(matches) != 1:
        raise RuntimeError(f"target account matched {len(matches)} browser targets; expected exactly one")
    return matches[0]


def _batch_output(stdout: str, stderr: str, exit_code: int) -> dict:
    combined = "\n".join(part for part in (stdout, stderr) if part).strip()
    if re.search(r"cookie|token|csrf|authorization|password", combined, re.IGNORECASE):
        message = "child output redacted"
    else:
        message = combined.splitlines()[-1][:400] if combined else ""
    return {"status": "success" if exit_code == 0 else "error", "exit_code": exit_code, "message": message}


def _validate_batch_manifest(path: Path) -> list[tuple[str, list[str], argparse.Namespace]]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("batch manifest is not valid JSON") from exc
    if not isinstance(manifest, dict) or set(manifest) != {"tasks"} or not isinstance(manifest["tasks"], list):
        raise ValueError("batch manifest must contain only a tasks list")
    parser = build_parser()
    seen = set()
    tasks = []
    for item in manifest["tasks"]:
        if not isinstance(item, dict) or set(item) != {"id", "argv"}:
            raise ValueError("each batch task must contain only id and argv")
        task_id = item["id"]
        argv = item["argv"]
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", task_id) or task_id in seen:
            raise ValueError("batch task IDs must be unique and match [A-Za-z0-9._-]{1,128}")
        if not isinstance(argv, list) or not argv or any(not isinstance(value, str) for value in argv):
            raise ValueError("batch task argv must be a nonempty string list")
        if argv[0] == "batch":
            raise ValueError("nested batch tasks are not allowed")
        try:
            child_args = parser.parse_args(argv)
        except SystemExit as exc:
            raise ValueError(f"invalid argv for batch task {task_id}") from exc
        if child_args.platform == "batch":
            raise ValueError("nested batch tasks are not allowed")
        seen.add(task_id)
        tasks.append((task_id, argv, child_args))
    return tasks


def _batch_ports(args) -> list[int]:
    browser = getattr(args, "browser", None)
    browsers = getattr(args, "browsers", None)
    cdp_url = getattr(args, "cdp_url", None)
    if sum(bool(value) for value in (browser, browsers, cdp_url)) > 1:
        raise ValueError("--browser, --browsers and --cdp-url cannot be used together")
    if browsers:
        targets = resolve_browser_targets(
            [value.strip() for value in browsers.split(",") if value.strip()]
        )
    else:
        target = resolve_browser_target(browser, cdp_url)
        targets = [target] if target is not None else []
    return list(dict.fromkeys(target.port for target in targets))


async def dispatch_batch(path: Path) -> int:
    tasks = _validate_batch_manifest(path)
    items = []
    has_failed = False
    for task_id, argv, child_args in tasks:
        prior = begin_task(task_id, argv)
        if prior["state"] != "started":
            if prior["state"] == "failed":
                has_failed = True
            items.append({"id": task_id, "state": prior["state"], "result": prior["result"]})
            continue
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with contextlib.ExitStack() as stack:
                for port in _batch_ports(child_args):
                    stack.enter_context(browser_task_lock(port))
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    exit_code = await dispatch(child_args)
            result = _batch_output(stdout.getvalue(), stderr.getvalue(), exit_code)
            if exit_code:
                has_failed = True
                finish_task(task_id, {**result, "task_state": "failed"})
                state = "failed"
            else:
                finish_task(task_id, result)
                state = "complete"
        except asyncio.TimeoutError as exc:
            result = {"status": "error", "message": "task outcome is uncertain"}
            finish_task(task_id, {**result, "task_state": "uncertain"})
            state = "uncertain"
        except Exception as exc:
            message = _sanitized_identity_error(exc)
            result = {"status": "error", "message": message}
            finish_task(task_id, {**result, "task_state": "failed"})
            has_failed = True
            state = "failed"
        items.append({"id": task_id, "state": state, "result": result})
    print(json.dumps({"items": items, "failed": has_failed}, ensure_ascii=False, sort_keys=True))
    return 1 if has_failed else 0


async def login_douyin_account(account_name: str, headless: bool = True, cdp_url: str | None = None) -> dict:
    account_file = resolve_account_file("douyin", account_name)
    return await douyin_setup(str(account_file), handle=True, return_detail=True, headless=headless, cdp_url=cdp_url)


async def check_douyin_account(account_name: str, cdp_url: str | None = None) -> bool:
    account_file = resolve_account_file("douyin", account_name)
    if not cdp_url and not account_file.exists():
        return False
    return await douyin_cookie_auth(str(account_file), cdp_url=cdp_url)


async def login_kuaishou_account(account_name: str, headless: bool = True, cdp_url: str | None = None) -> dict:
    account_file = resolve_account_file("kuaishou", account_name)
    return await ks_setup(str(account_file), handle=True, return_detail=True, headless=headless, cdp_url=cdp_url)


async def check_kuaishou_account(account_name: str) -> bool:
    account_file = resolve_account_file("kuaishou", account_name)
    if not account_file.exists():
        return False
    return await kuaishou_cookie_auth(str(account_file))


async def login_xiaohongshu_account(account_name: str, headless: bool = True, cdp_url: str | None = None) -> dict:
    account_file = resolve_account_file("xiaohongshu", account_name)
    return await xiaohongshu_setup(str(account_file), handle=True, return_detail=True, headless=headless, cdp_url=cdp_url)


async def check_xiaohongshu_account(account_name: str, cdp_url: str | None = None) -> bool:
    account_file = resolve_account_file("xiaohongshu", account_name)
    if not account_file.exists():
        return False
    return await xiaohongshu_cookie_auth(str(account_file), cdp_url=cdp_url)


async def login_bilibili_account(account_name: str, cdp_url: str | None = None, target=None) -> dict:
    account_file = resolve_account_file("bilibili", account_name)
    if cdp_url:
        identity = await export_bilibili_cdp_account(cdp_url, account_file, target)
        return {"success": True, "message": "Bilibili CDP account exported", "account_file": str(account_file), "identity": identity.to_dict()}
    if not has_interactive_terminal():
        return {
            "success": False,
            "message": (
                "Bilibili login requires a local interactive terminal. "
                f"Please run `sau bilibili login --account {account_name}` yourself in a local terminal. "
                "If the terminal QR code does not render completely, open `./qrcode.png` and scan that image."
            ),
            "account_file": str(account_file),
        }

    result = run_biliup_command(["-u", str(account_file), "login"], interactive=True)
    success = result.returncode == 0
    return {
        "success": success,
        "message": (result.stderr or result.stdout or "").strip() or "Bilibili login completed" if success else (result.stderr or result.stdout or "").strip() or "Bilibili login failed",
        "account_file": str(account_file),
    }


async def check_bilibili_account(account_name: str, cdp_url: str | None = None, target=None) -> bool:
    account_file = resolve_account_file("bilibili", account_name)
    if not account_file.exists():
        return False
    expected = None
    if cdp_url:
        expected = await get_bilibili_cdp_identity(cdp_url, target)
        require_publish_identity(expected)
        assert_same_publish_identity(expected, read_bilibili_account_identity(account_file, target))
    result = run_biliup_command(["-u", str(account_file), "renew"])
    if result.returncode != 0:
        return False
    if expected is not None:
        observed = read_bilibili_account_identity(account_file, target)
        assert_same_publish_identity(expected, observed)
    return True


async def login_tencent_account(account_name: str, headless: bool = True) -> dict:
    account_file = resolve_account_file("tencent", account_name)
    return await tencent_setup(str(account_file), handle=True, return_detail=True, headless=headless)


async def check_tencent_account(account_name: str) -> bool:
    account_file = resolve_account_file("tencent", account_name)
    if not account_file.exists():
        return False
    return await tencent_cookie_auth(str(account_file))


async def login_youtube_account(
    account_name: str, headless: bool = False, cdp_url: str | None = None
) -> dict:
    account_file = resolve_account_file("youtube", account_name)
    return await youtube_setup(
        str(account_file), handle=True, return_detail=True, headless=headless, cdp_url=cdp_url
    )


async def check_youtube_account(account_name: str, cdp_url: str | None = None) -> bool:
    account_file = resolve_account_file("youtube", account_name)
    if not cdp_url and not account_file.exists():
        return False
    return await youtube_cookie_auth(str(account_file), cdp_url=cdp_url)


def probe_video_duration_seconds(file_path: Path) -> float | None:
    """Probe media duration with ffprobe; None when duration cannot be determined.

    Uses the same best-effort contract as the upload pipeline: a missing/unusable
    ffprobe returns None instead of raising, so uploads that cannot be probed keep
    their previous behavior (YouTube still enforces its own limit server-side).
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def assert_video_duration_within_limit(file_path: Path, max_duration_seconds: float) -> float | None:
    """Raise before upload when a known duration exceeds the account cap.

    Returns the probed duration, or None when it could not be determined
    (best-effort: warn-and-continue rather than block unprobeable files).
    """
    duration = probe_video_duration_seconds(file_path)
    if duration is None:
        print(f"提醒：无法用 ffprobe 读取视频时长，跳过时长上限预检（{file_path}）", file=sys.stderr)
        return None
    if duration > max_duration_seconds:
        raise ValueError(
            f"YouTube 视频时长 {duration:.1f}s（{duration / 60:.1f} 分钟）超过账号上传上限 "
            f"{max_duration_seconds:.0f}s（{max_duration_seconds / 60:.0f} 分钟），已提前终止，未发起上传。"
            f"\n如需调整上限，可在 conf.py 中设置 YT_MAX_DURATION_SECONDS（已验证账号常用 43200 = 12 小时）。"
        )
    return duration


async def upload_youtube_video(request: YouTubeVideoUploadRequest) -> dict | Path:
    if request.schedule and not request.submit:
        raise ValueError("YouTube --schedule cannot be combined with --no-submit")
    if request.schedule and request.visibility != "public":
        raise ValueError("YouTube scheduled publishing requires --visibility public")

    # 上传前预检：视频时长超过账号上限（默认 15 分钟）时提前终止，避免白传大文件。
    assert_video_duration_within_limit(request.video_file, YT_MAX_DURATION_SECONDS)

    account_file = resolve_account_file("youtube", request.account_name)
    is_ready = await youtube_setup(str(account_file), handle=False, cdp_url=request.cdp_url)
    if not is_ready:
        raise RuntimeError(
            f"YouTube cookie is missing or expired: {account_file}. Run `sau youtube login --account {request.account_name}` first."
        )

    app = YouTubeVideo(
        request.title,
        str(request.video_file),
        request.tags,
        str(account_file),
        description=request.description,
        thumbnail_path=str(request.thumbnail_file) if request.thumbnail_file else None,
        playlist=request.playlist,
        visibility=request.visibility,
        debug=request.debug,
        headless=request.headless,
        cdp_url=request.cdp_url,
        submit=request.submit,
        schedule=request.schedule,
        timezone=request.timezone,
        browser_name=request.browser_name,
        cdp_port=request.cdp_port,
        target_account=request.target_account,
    )
    result = await app.main()
    return result if result is not None else account_file


async def upload_video(request: DouyinVideoUploadRequest) -> dict:
    account_file = resolve_account_file("douyin", request.account_name)
    is_ready = await douyin_setup(str(account_file), handle=False, cdp_url=request.cdp_url)
    if not is_ready:
        raise RuntimeError(
            f"Douyin cookie is missing or expired: {account_file}. Run `sau douyin login --account {request.account_name}` first."
        )

    app = DouYinVideo(
        request.title,
        str(request.video_file),
        request.tags,
        request.publish_date,
        str(account_file),
        desc=request.description,
        thumbnail_landscape_path=(
            str(request.thumbnail_landscape_file) if request.thumbnail_landscape_file else None
        ),
        thumbnail_portrait_path=str(
            request.thumbnail_portrait_file or request.thumbnail_file
        ) if request.thumbnail_portrait_file or request.thumbnail_file else None,
        productLink=request.product_link,
        productTitle=request.product_title,
        publish_strategy=request.publish_strategy,
        debug=request.debug,
        headless=request.headless,
        cdp_url=request.cdp_url,
        declaration=request.declaration,
        collection=request.collection,
        browser_name=request.browser_name,
        cdp_port=request.cdp_port,
        target_account=request.target_account,
        paid_video=request.paid_video,
        submit=request.submit,
    )
    return await app.douyin_upload_video()

async def upload_note(request: DouyinNoteUploadRequest) -> Path:
    account_file = resolve_account_file("douyin", request.account_name)
    is_ready = await douyin_setup(str(account_file), handle=False, cdp_url=request.cdp_url)
    if not is_ready:
        raise RuntimeError(
            f"Douyin cookie is missing or expired: {account_file}. Run `sau douyin login --account {request.account_name}` first."
        )

    app = DouYinNote(
        image_paths=[str(path) for path in request.image_files],
        title=request.title,
        note=request.note,
        tags=request.tags,
        publish_date=request.publish_date,
        account_file=str(account_file),
        publish_strategy=request.publish_strategy,
        debug=request.debug,
        headless=request.headless,
        cdp_url=request.cdp_url,
        bgm=request.bgm,
    )
    await app.douyin_upload_note()
    return account_file


async def upload_kuaishou_video(request: KuaishouVideoUploadRequest) -> Path:
    account_file = resolve_account_file("kuaishou", request.account_name)
    is_ready = await ks_setup(str(account_file), handle=False)
    if not is_ready:
        raise RuntimeError(
            f"Kuaishou cookie is missing or expired: {account_file}. Run `sau kuaishou login --account {request.account_name}` first."
        )

    app = KSVideo(
        title=request.title,
        file_path=str(request.video_file),
        desc=request.description,
        tags=request.tags,
        publish_date=request.publish_date,
        account_file=str(account_file),
        thumbnail_path=str(request.thumbnail_file) if request.thumbnail_file else None,
        publish_strategy=request.publish_strategy,
        debug=request.debug,
        headless=request.headless,
        cdp_url=request.cdp_url,
    )
    await app.main()
    return account_file


async def upload_kuaishou_note(request: KuaishouNoteUploadRequest) -> Path:
    account_file = resolve_account_file("kuaishou", request.account_name)
    is_ready = await ks_setup(str(account_file), handle=False)
    if not is_ready:
        raise RuntimeError(
            f"Kuaishou cookie is missing or expired: {account_file}. Run `sau kuaishou login --account {request.account_name}` first."
        )

    app = KSNote(
        image_paths=[str(path) for path in request.image_files],
        title=request.title,
        note=request.note,
        tags=request.tags,
        publish_date=request.publish_date,
        account_file=str(account_file),
        publish_strategy=request.publish_strategy,
        debug=request.debug,
        headless=request.headless,
        cdp_url=request.cdp_url,
    )
    await app.main()
    return account_file


async def upload_xiaohongshu_video(request: XiaohongshuVideoUploadRequest) -> Path:
    account_file = resolve_account_file("xiaohongshu", request.account_name)
    is_ready = await xiaohongshu_setup(str(account_file), handle=False, cdp_url=request.cdp_url)
    if not is_ready:
        raise RuntimeError(
            f"Xiaohongshu cookie is missing or expired: {account_file}. Run `sau xiaohongshu login --account {request.account_name}` first."
        )

    app = XiaoHongShuVideo(
        title=request.title,
        file_path=str(request.video_file),
        desc=request.description,
        tags=request.tags,
        publish_date=request.publish_date,
        account_file=str(account_file),
        thumbnail_path=str(request.thumbnail_file) if request.thumbnail_file else None,
        publish_strategy=request.publish_strategy,
        debug=request.debug,
        headless=request.headless,
        cdp_url=request.cdp_url,
        submit=request.submit,
    )
    await app.main()
    return account_file


async def upload_xiaohongshu_note(request: XiaohongshuNoteUploadRequest) -> Path:
    account_file = resolve_account_file("xiaohongshu", request.account_name)
    is_ready = await xiaohongshu_setup(str(account_file), handle=False)
    if not is_ready:
        raise RuntimeError(
            f"Xiaohongshu cookie is missing or expired: {account_file}. Run `sau xiaohongshu login --account {request.account_name}` first."
        )

    app = XiaoHongShuNote(
        image_paths=[str(path) for path in request.image_files],
        title=request.title,
        desc=request.note,
        note=request.note,
        tags=request.tags,
        publish_date=request.publish_date,
        account_file=str(account_file),
        publish_strategy=request.publish_strategy,
        debug=request.debug,
        headless=request.headless,
        cdp_url=request.cdp_url,
    )
    await app.main()
    return account_file


async def upload_bilibili_video(request: BilibiliVideoUploadRequest) -> dict:
    account_file = resolve_account_file("bilibili", request.account_name)
    if not account_file.exists():
        raise RuntimeError(
            f"Bilibili account file is missing: {account_file}. Run `sau bilibili login --account {request.account_name}` first."
        )

    renewed = run_biliup_command(["-u", str(account_file), "renew"])
    if renewed.returncode != 0:
        raise RuntimeError(
            "BILIBILI_AUTH_REQUIRED: fixed biliup account could not be renewed; "
            "refresh it once from the matching browser before upload"
        )

    try:
        credential_identity = read_bilibili_account_identity(account_file)
    except RuntimeError:
        if request.target_account or request.cdp_url:
            raise
        credential_identity = None
    if request.target_account and credential_identity and not identity_matches(credential_identity, request.target_account):
        raise RuntimeError("blocked publish identity: target account does not match Bilibili credentials")
    focus_fallback_used = request.focus_fallback_used
    if request.cdp_url:
        live_identity = await get_bilibili_cdp_identity(request.cdp_url)
        focus_fallback_used = focus_fallback_used or bool(
            live_identity.extra.get("focus_fallback_used")
        )
        require_publish_identity(live_identity)
        if credential_identity is None:
            raise RuntimeError("Bilibili credential identity is unavailable")
        assert_same_publish_identity(live_identity, credential_identity)
        final_identity = await get_bilibili_cdp_identity(request.cdp_url)
        focus_fallback_used = focus_fallback_used or bool(
            final_identity.extra.get("focus_fallback_used")
        )
        assert_same_publish_identity(live_identity, final_identity)

    arguments = [
        "-u",
        str(account_file),
        "upload",
        str(request.video_file),
        "--line",
        request.line,
        "--title",
        request.title,
        "--desc",
        request.description,
        "--tid",
        str(request.tid),
    ]
    if request.tags:
        arguments.extend(["--tag", ",".join(request.tags)])
    if request.thumbnail_file:
        arguments.extend(["--cover", str(request.thumbnail_file)])
    if request.charging_pay:
        arguments.extend(["--charging-pay", "1"])
    season_id: int | None = None
    section_id: int | None = None
    if request.collection:
        season_id = resolve_bilibili_season_id(account_file, request.collection)
        section_id = resolve_bilibili_section_id(account_file, season_id)
        arguments.extend(["--extra-fields", json.dumps({"season_id": season_id})])
    if isinstance(request.publish_date, datetime):
        schedule = request.publish_date
        if schedule.tzinfo is None:
            schedule = schedule.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        else:
            schedule = schedule.astimezone(ZoneInfo("Asia/Shanghai"))
        arguments.extend(["--dtime", str(int(schedule.timestamp()))])
    else:
        schedule = None

    try:
        account_payload = json.loads(account_file.read_text(encoding="utf-8"))
        has_cookie_data = isinstance(account_payload.get("cookie_info"), dict)
    except (OSError, ValueError, json.JSONDecodeError):
        has_cookie_data = False
    existing_aids: set[int] = set()
    if has_cookie_data:
        existing_matches = read_bilibili_archive_matches(account_file, request.title, attempts=1)
        existing_aids = {int(item["aid"]) for item in existing_matches}

    result = run_biliup_command(arguments)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "").strip() or "Bilibili upload failed")

    matches = []
    if has_cookie_data:
        matches = read_bilibili_archive_matches(
            account_file, request.title, exclude_aids=existing_aids
        )
        if len(matches) != 1:
            raise RuntimeError(
                f"Bilibili new archive title matched {len(matches)} records; expected exactly one"
            )
    evidence = matches[0] if matches else {}
    if request.collection and season_id is not None and section_id is not None:
        # biliup's APP submit ignores season_id; attach the newly created archive afterwards.
        aid = int(evidence["aid"]) if evidence.get("aid") else find_bilibili_archive_aid(
            account_file, request.title
        )
        cid = fetch_bilibili_archive_cid(account_file, aid)
        add_archive_to_season(account_file, aid, cid, request.title, section_id)
    if schedule and evidence.get("dtime") is not None:
        try:
            observed_dtime = int(evidence["dtime"])
        except (TypeError, ValueError):
            observed_dtime = None
        if observed_dtime is not None and observed_dtime != int(schedule.timestamp()):
            raise RuntimeError("Bilibili archive schedule does not match requested time")
    return {
        "status": "success",
        "platform": "bilibili",
        "browser_name": request.browser_name,
        "cdp_port": request.cdp_port,
        "stable_id": credential_identity.stable_id if credential_identity else None,
        "submitted": True,
        "work_id": str(evidence.get("aid", "")),
        "scheduled_at": schedule.isoformat() if schedule else None,
        "cover_present": evidence.get("cover_present", bool(request.thumbnail_file and request.thumbnail_file.exists())),
        "focus_fallback_used": focus_fallback_used,
        "message": "scheduled upload verified" if schedule else "upload verified",
    }


async def upload_tencent_video(request: TencentVideoUploadRequest) -> Path:
    account_file = resolve_account_file("tencent", request.account_name)
    is_ready = await tencent_setup(str(account_file), handle=False)
    if not is_ready:
        raise RuntimeError(
            f"Tencent/WeChat Channels cookie is missing or expired: {account_file}. "
            f"Run `sau tencent login --account {request.account_name}` first."
        )

    app = TencentVideo(
        title=request.title,
        file_path=str(request.video_file),
        tags=request.tags,
        publish_date=request.publish_date,
        account_file=str(account_file),
        category=request.category,
        is_draft=request.is_draft,
        desc=request.description,
        thumbnail_path=str(request.thumbnail_file) if request.thumbnail_file else None,
        thumbnail_landscape_path=(
            str(request.thumbnail_landscape_file) if request.thumbnail_landscape_file else None
        ),
        thumbnail_portrait_path=(
            str(request.thumbnail_portrait_file) if request.thumbnail_portrait_file else None
        ),
        short_title=request.short_title,
        publish_strategy=request.publish_strategy,
        debug=request.debug,
        headless=request.headless,
    )
    await app.tencent_upload_video()
    return account_file


def existing_file_path(value: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"File not found: {value}")
    return path


def schedule_value(value: str):
    try:
        return parse_schedule(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid schedule '{value}'. Expected format: {SCHEDULE_FORMAT}"
        ) from exc


def timezone_value(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise argparse.ArgumentTypeError(f"Invalid IANA timezone: {value}") from exc
    return value


def add_runtime_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    headless_group = parser.add_mutually_exclusive_group()
    headless_group.add_argument("--headed", dest="headless", action="store_false", help="Run with browser UI")
    headless_group.add_argument("--headless", dest="headless", action="store_true", help="Run in headless mode")
    runtime_selector_group = parser.add_mutually_exclusive_group()
    runtime_selector_group.add_argument(
        "--browser",
        default=os.environ.get("SAU_BROWSER"),
        help="Registered browser name or port; resolves to a healthy local CDP target",
    )
    runtime_selector_group.add_argument(
        "--browsers",
        help="Comma-separated registered browser names or ports",
    )
    runtime_selector_group.add_argument(
        "--cdp-url",
        default=os.environ.get("SAU_CDP_URL"),
        help="Connect to an existing Agent Chrome/Chromium over CDP, e.g. http://127.0.0.1:9223",
    )
    parser.set_defaults(headless=True)


def build_parser() -> argparse.ArgumentParser:
    schedule_help = SCHEDULE_FORMAT.replace("%", "%%")
    parser = argparse.ArgumentParser(
        prog="sau",
        description="CLI for social-auto-upload.",
    )
    platform_parsers = parser.add_subparsers(dest="platform", required=True)

    accounts_parser = platform_parsers.add_parser("accounts", help="Account operations")
    accounts_actions = accounts_parser.add_subparsers(dest="action", required=True)
    accounts_scan_parser = accounts_actions.add_parser("scan", help="Scan platform identities in browser pool")
    accounts_scan_parser.add_argument("--browsers", required=True, help="Comma-separated registered browser names or ports")
    accounts_scan_parser.add_argument(
        "--platforms",
        required=True,
        help="Comma-separated platforms: douyin,youtube,bilibili",
    )

    batch_parser = platform_parsers.add_parser("batch", help="Run a sequential task manifest")
    batch_parser.add_argument("--file", required=True, type=existing_file_path, help="JSON batch manifest")

    douyin_parser = platform_parsers.add_parser("douyin", help="Douyin operations")
    douyin_actions = douyin_parser.add_subparsers(dest="action", required=True)

    for action_name in ("login", "check", "identity"):
        action_parser = douyin_actions.add_parser(action_name, help=f"Douyin {action_name}")
        action_parser.add_argument("--account", required=True, help="Douyin user-defined account_name")
        if action_name == "identity":
            action_parser.add_argument("--target-account", help="Exact stable ID, handle, or display name to verify")
        add_runtime_flags(action_parser)

    upload_video_parser = douyin_actions.add_parser("upload-video", help="Upload one video to Douyin")
    upload_video_parser.add_argument("--account", required=True, help="Douyin user-defined account_name")
    upload_video_parser.add_argument("--file", required=True, type=existing_file_path, help="Video file path")
    upload_video_parser.add_argument("--title", required=True, help="Video title")
    upload_video_parser.add_argument("--desc", default="", help="Optional video description")
    upload_video_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    upload_video_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    upload_video_parser.add_argument(
        "--no-submit",
        dest="submit",
        action="store_false",
        help="Fill metadata and schedule then stop before final publish",
    )
    upload_video_parser.add_argument(
        "--paid-target-config",
        type=existing_file_path,
        help="Peach publish target config JSON for paid-video settings",
    )
    upload_video_parser.add_argument("--thumbnail", type=existing_file_path, help="Optional 3:4 portrait thumbnail path")
    upload_video_parser.add_argument("--thumbnail-landscape", type=existing_file_path, help="Optional 4:3 landscape thumbnail path")
    upload_video_parser.add_argument("--thumbnail-portrait", type=existing_file_path, help="Optional 3:4 portrait thumbnail path")
    upload_video_parser.add_argument("--product-link", default="", help="Optional product link")
    upload_video_parser.add_argument("--product-title", default="", help="Optional product title")
    upload_video_parser.add_argument(
        "--declaration",
        default="无需添加自主声明",
        choices=[
            "无需添加自主声明",
            "内容由AI生成",
            "内容为个人观点或见解",
            "内容为转载信息",
            "内容含营销推广信息",
            "虚构演绎，仅供娱乐",
        ],
        help="Douyin 自主声明 (default: 无需添加自主声明)",
    )
    upload_video_parser.add_argument(
        "--collection",
        default=None,
        help="Optional Douyin collection (合集) name to select during publishing",
    )
    upload_video_parser.add_argument("--target-account", help="Exact stable ID, handle, or display name to route to")
    upload_video_parser.add_argument("--task-id", help="Idempotency key for this upload task")
    add_runtime_flags(upload_video_parser)

    upload_note_parser = douyin_actions.add_parser("upload-note", help="Upload one note to Douyin")
    upload_note_parser.add_argument("--account", required=True, help="Douyin user-defined account_name")
    upload_note_parser.add_argument("--images", required=True, nargs="+", type=existing_file_path, help="Image file paths")
    upload_note_parser.add_argument("--title", required=True, help="Note title")
    upload_note_parser.add_argument("--note", default="", help="Optional note content")
    upload_note_parser.add_argument("--notef", default="", help="Read note content from file (txt/md)")
    upload_note_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    upload_note_parser.add_argument("--bgm", default="", help="BGM music name to search and select")
    upload_note_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    add_runtime_flags(upload_note_parser)

    kuaishou_parser = platform_parsers.add_parser("kuaishou", help="Kuaishou operations")
    kuaishou_actions = kuaishou_parser.add_subparsers(dest="action", required=True)

    for action_name in ("login", "check"):
        action_parser = kuaishou_actions.add_parser(action_name, help=f"Kuaishou {action_name}")
        action_parser.add_argument("--account", required=True, help="Kuaishou user-defined account_name")
        if action_name == "login":
            add_runtime_flags(action_parser)

    kuaishou_upload_video_parser = kuaishou_actions.add_parser("upload-video", help="Upload one video to Kuaishou")
    kuaishou_upload_video_parser.add_argument("--account", required=True, help="Kuaishou user-defined account_name")
    kuaishou_upload_video_parser.add_argument("--file", required=True, type=existing_file_path, help="Video file path")
    kuaishou_upload_video_parser.add_argument("--title", required=True, help="Video title")
    kuaishou_upload_video_parser.add_argument("--desc", default="", help="Optional video description")
    kuaishou_upload_video_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    kuaishou_upload_video_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    kuaishou_upload_video_parser.add_argument("--thumbnail", type=existing_file_path, help="Optional thumbnail path")
    add_runtime_flags(kuaishou_upload_video_parser)

    kuaishou_upload_note_parser = kuaishou_actions.add_parser("upload-note", help="Upload one note to Kuaishou")
    kuaishou_upload_note_parser.add_argument("--account", required=True, help="Kuaishou user-defined account_name")
    kuaishou_upload_note_parser.add_argument("--images", required=True, nargs="+", type=existing_file_path, help="Image file paths")
    kuaishou_upload_note_parser.add_argument("--title", required=True, help="Note title")
    kuaishou_upload_note_parser.add_argument("--note", default="", help="Optional note content")
    kuaishou_upload_note_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    kuaishou_upload_note_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    add_runtime_flags(kuaishou_upload_note_parser)

    xiaohongshu_parser = platform_parsers.add_parser("xiaohongshu", help="Xiaohongshu operations")
    xiaohongshu_actions = xiaohongshu_parser.add_subparsers(dest="action", required=True)

    for action_name in ("login", "check"):
        action_parser = xiaohongshu_actions.add_parser(action_name, help=f"Xiaohongshu {action_name}")
        action_parser.add_argument("--account", required=True, help="Xiaohongshu user-defined account_name")
        if action_name == "login":
            add_runtime_flags(action_parser)

    xiaohongshu_upload_video_parser = xiaohongshu_actions.add_parser("upload-video", help="Upload one video to Xiaohongshu")
    xiaohongshu_upload_video_parser.add_argument("--account", required=True, help="Xiaohongshu user-defined account_name")
    xiaohongshu_upload_video_parser.add_argument("--file", required=True, type=existing_file_path, help="Video file path")
    xiaohongshu_upload_video_parser.add_argument("--title", required=True, help="Video title")
    xiaohongshu_upload_video_parser.add_argument("--desc", default="", help="Optional video description")
    xiaohongshu_upload_video_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    xiaohongshu_upload_video_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    xiaohongshu_upload_video_parser.add_argument("--thumbnail", type=existing_file_path, help="Optional thumbnail path")
    xiaohongshu_upload_video_parser.add_argument("--no-submit", action="store_true", help="Fill/upload and stop before clicking publish; for smoke tests")
    add_runtime_flags(xiaohongshu_upload_video_parser)

    xiaohongshu_upload_note_parser = xiaohongshu_actions.add_parser("upload-note", help="Upload one note to Xiaohongshu")
    xiaohongshu_upload_note_parser.add_argument("--account", required=True, help="Xiaohongshu user-defined account_name")
    xiaohongshu_upload_note_parser.add_argument("--images", required=True, nargs="+", type=existing_file_path, help="Image file paths")
    xiaohongshu_upload_note_parser.add_argument("--title", required=True, help="Note title")
    xiaohongshu_upload_note_parser.add_argument("--note", default="", help="Optional note content")
    xiaohongshu_upload_note_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    xiaohongshu_upload_note_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    add_runtime_flags(xiaohongshu_upload_note_parser)

    bilibili_parser = platform_parsers.add_parser("bilibili", help="Bilibili operations")
    bilibili_actions = bilibili_parser.add_subparsers(dest="action", required=True)

    for action_name in ("login", "check", "identity"):
        action_parser = bilibili_actions.add_parser(action_name, help=f"Bilibili {action_name}")
        action_parser.add_argument("--account", required=True, help="Bilibili user-defined account_name")
        if action_name == "identity":
            action_parser.add_argument("--target-account", help="Exact stable ID, handle, or display name to verify")
        add_runtime_flags(action_parser)

    bilibili_upload_video_parser = bilibili_actions.add_parser("upload-video", help="Upload one video to Bilibili")
    bilibili_upload_video_parser.add_argument("--account", required=True, help="Bilibili user-defined account_name")
    bilibili_upload_video_parser.add_argument("--file", required=True, type=existing_file_path, help="Video file path")
    bilibili_upload_video_parser.add_argument("--title", required=True, help="Video title")
    bilibili_upload_video_parser.add_argument("--desc", required=True, help="Video description")
    bilibili_upload_video_parser.add_argument("--tid", required=True, type=int, help="Bilibili category id")
    bilibili_upload_video_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    bilibili_upload_video_parser.add_argument(
        "--line",
        default="cnbd",
        choices=["bldsa", "cnbldsa", "andsa", "atdsa", "bda2", "cnbd", "anbd", "atbd", "tx", "cntx", "antx", "attx", "bda", "txa", "alia"],
        help="Bilibili upload CDN line (default: cnbd)",
    )
    bilibili_upload_video_parser.add_argument("--thumbnail", type=existing_file_path, help="Optional Bilibili cover image path")
    bilibili_upload_video_parser.add_argument("--collection", default=None, help="Optional Bilibili collection (合集) name to submit the video into")
    bilibili_upload_video_parser.add_argument(
        "--charging-pay",
        action="store_true",
        help="Enable Bilibili charging-exclusive video; cannot be edited after publication",
    )
    bilibili_upload_video_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    bilibili_upload_video_parser.add_argument("--target-account", help="Exact stable ID, handle, or display name to route to")
    bilibili_upload_video_parser.add_argument("--task-id", help="Idempotency key for this upload task")
    add_runtime_flags(bilibili_upload_video_parser)

    tencent_parser = platform_parsers.add_parser("tencent", help="Tencent/WeChat Channels operations")
    tencent_actions = tencent_parser.add_subparsers(dest="action", required=True)

    for action_name in ("login", "check"):
        action_parser = tencent_actions.add_parser(action_name, help=f"Tencent/WeChat Channels {action_name}")
        action_parser.add_argument("--account", required=True, help="Tencent user-defined account_name")
        if action_name == "login":
            add_runtime_flags(action_parser)

    tencent_upload_video_parser = tencent_actions.add_parser("upload-video", help="Upload one video to WeChat Channels")
    tencent_upload_video_parser.add_argument("--account", required=True, help="Tencent user-defined account_name")
    tencent_upload_video_parser.add_argument("--file", required=True, type=existing_file_path, help="Video file path")
    tencent_upload_video_parser.add_argument("--title", required=True, help="Video title")
    tencent_upload_video_parser.add_argument("--desc", default="", help="Optional video description")
    tencent_upload_video_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    tencent_upload_video_parser.add_argument("--schedule", type=schedule_value, help=f"Schedule time in {schedule_help}")
    tencent_upload_video_parser.add_argument("--thumbnail", type=existing_file_path, help="Optional 3:4 portrait thumbnail path")
    tencent_upload_video_parser.add_argument("--thumbnail-landscape", type=existing_file_path, help="Optional 4:3 landscape thumbnail path")
    tencent_upload_video_parser.add_argument("--thumbnail-portrait", type=existing_file_path, help="Optional 3:4 portrait thumbnail path")
    tencent_upload_video_parser.add_argument("--short-title", help="Optional WeChat Channels short title")
    tencent_upload_video_parser.add_argument("--category", help="Optional original content category")
    tencent_upload_video_parser.add_argument("--draft", action="store_true", help="Save as draft instead of publishing")
    add_runtime_flags(tencent_upload_video_parser)

    youtube_parser = platform_parsers.add_parser("youtube", help="YouTube operations")
    youtube_actions = youtube_parser.add_subparsers(dest="action", required=True)

    for action_name in ("login", "check", "identity"):
        action_parser = youtube_actions.add_parser(action_name, help=f"YouTube {action_name}")
        action_parser.add_argument("--account", required=True, help="YouTube user-defined account_name")
        if action_name == "identity":
            action_parser.add_argument("--target-account", help="Exact stable ID, handle, or display name to verify")
        add_runtime_flags(action_parser)

    youtube_upload_video_parser = youtube_actions.add_parser("upload-video", help="Upload one video to YouTube")
    youtube_upload_video_parser.add_argument("--account", required=True, help="YouTube user-defined account_name")
    youtube_upload_video_parser.add_argument("--file", required=True, type=existing_file_path, help="Video file path")
    youtube_upload_video_parser.add_argument("--title", required=True, help="Video title (<=100 chars)")
    youtube_upload_video_parser.add_argument("--desc", default="", help="Optional video description")
    youtube_upload_video_parser.add_argument("--tags", default="", help="Comma-separated tags, such as tag1,tag2")
    youtube_upload_video_parser.add_argument("--thumbnail", type=existing_file_path, help="Optional thumbnail image path")
    youtube_upload_video_parser.add_argument("--playlist", help="Optional playlist name to add the video to (for series)")
    youtube_upload_video_parser.add_argument(
        "--visibility", default="public", choices=["public", "unlisted", "private"], help="Video visibility")
    youtube_submission_group = youtube_upload_video_parser.add_mutually_exclusive_group()
    youtube_submission_group.add_argument(
        "--schedule", type=schedule_value, help=f"Schedule public release time in {schedule_help}"
    )
    youtube_submission_group.add_argument(
        "--no-submit", dest="submit", action="store_false",
        help="Stop at the YouTube Studio publish page without clicking the final publish button",
    )
    youtube_upload_video_parser.add_argument(
        "--timezone", default="Asia/Shanghai", type=timezone_value,
        help="IANA timezone for --schedule (default: Asia/Shanghai)",
    )
    youtube_upload_video_parser.add_argument("--target-account", help="Exact stable ID, handle, or display name to route to")
    youtube_upload_video_parser.add_argument("--task-id", help="Idempotency key for this upload task")
    add_runtime_flags(youtube_upload_video_parser)
    return parser


async def dispatch(args: argparse.Namespace) -> int:
    if args.platform == "batch":
        return await dispatch_batch(args.file)
    if args.platform == "accounts":
        if args.action != "scan":
            raise RuntimeError(f"Unsupported accounts action: {args.action}")
        platforms = [item.strip().lower() for item in args.platforms.split(",") if item.strip()]
        if not platforms or any(item not in {"douyin", "youtube", "bilibili"} for item in platforms):
            raise ValueError("--platforms must contain only douyin,youtube,bilibili")
        result = await scan_accounts(
            [item.strip() for item in args.browsers.split(",") if item.strip()],
            platforms,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["items"] else 1

    target = None
    if not (args.platform == "douyin" and args.action == "upload-video"):
        target = await _resolve_upload_target(args)
        if target is not None:
            args.cdp_url = target.cdp_url

    if args.platform == "douyin":
        if args.action in {"upload-video", "upload-note"}:
            publish_strategy = DOUYIN_PUBLISH_STRATEGY_SCHEDULED if args.schedule else DOUYIN_PUBLISH_STRATEGY_IMMEDIATE

        if args.action == "upload-video":
            paid_target_config = getattr(args, "paid_target_config", None)
            paid_video: DouyinPaidVideoSettings | None = None
            if paid_target_config is not None:
                try:
                    raw_target = json.loads(paid_target_config.read_text(encoding="utf-8"))
                    paid_account_id, paid_video = parse_peach_douyin_target(
                        raw_target,
                        video_duration_sec=probe_video_duration_seconds(args.file),
                        base_dir=paid_target_config.parent,
                    )
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    raise ValueError(f"invalid --paid-target-config: {exc}") from exc

                requested_account = getattr(args, "target_account", None)
                if requested_account and paid_account_id != requested_account:
                    raise ValueError(
                        "paid target account does not match --target-account; keep one account source"
                    )
                args.target_account = paid_account_id
                if getattr(args, "collection", None):
                    raise ValueError("douyin paid video does not support --collection")

            args.paid_video = paid_video
            args.paid_target_config = paid_target_config
            target = await _resolve_upload_target(args)
            if target is not None:
                args.cdp_url = target.cdp_url

            request = DouyinVideoUploadRequest(
                account_name=args.account,
                video_file=args.file,
                title=args.title,
                description=args.desc,
                tags=parse_tags(args.tags),
                publish_date=args.schedule or 0,
                thumbnail_file=args.thumbnail,
                thumbnail_landscape_file=args.thumbnail_landscape,
                thumbnail_portrait_file=args.thumbnail_portrait,
                product_link=args.product_link,
                product_title=args.product_title,
                publish_strategy=publish_strategy,
                debug=args.debug,
                headless=args.headless,
                cdp_url=getattr(args, "cdp_url", None),
                declaration=args.declaration,
                collection=args.collection,
                browser_name=target.name if target else None,
                cdp_port=target.port if target else None,
                target_account=getattr(args, "target_account", None),
                paid_target_config=getattr(args, "paid_target_config", None),
                paid_video=args.paid_video,
                submit=getattr(args, "submit", True),
            )
            result = await upload_video(request)
            if not isinstance(result, dict):
                result = {
                    "status": "prepared" if not request.submit else "success",
                    "platform": "douyin",
                    "browser_name": request.browser_name,
                    "cdp_port": request.cdp_port,
                    "submitted": request.submit,
                    "paid_video": (
                        {
                            "requested": request.paid_video.to_snapshot(),
                            "observed": None,
                            "verified": False,
                        }
                        if request.paid_video
                        else None
                    ),
                }
            args._last_result = result
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0

        if args.action == "login":
            result = await login_douyin_account(args.account, headless=args.headless, cdp_url=getattr(args, "cdp_url", None))
            if not result["success"]:
                raise RuntimeError(result["message"])
            print(f"Douyin login flow completed: {result['account_file']}")
            return 0

        if args.action == "check":
            is_valid = await check_douyin_account(args.account, cdp_url=getattr(args, "cdp_url", None))
            print("valid" if is_valid else "invalid")
            return 0 if is_valid else 1

        if args.action == "identity":
            identity = await get_douyin_account_identity(
                cdp_url=getattr(args, "cdp_url", None),
                account_file=str(resolve_account_file("douyin", args.account)),
                browser_name=target.name if target else None,
                cdp_port=target.port if target else None,
            )
            if getattr(args, "target_account", None) and not identity_matches(identity, args.target_account):
                raise RuntimeError("identity does not match --target-account")
            print(json.dumps(identity.to_dict(), ensure_ascii=False, sort_keys=True))
            return 0 if identity.logged_in and identity.stable_id else 1

        if args.action == "upload-note":
            # 如果指定了 --notef，读取文件内容作为 note
            note_content = args.note
            if args.notef:
                note_file = Path(args.notef)
                if not note_file.exists():
                    print(f"错误：文件不存在: {note_file}", file=sys.stderr)
                    return 1
                note_content = note_file.read_text(encoding="utf-8")

            request = DouyinNoteUploadRequest(
                account_name=args.account,
                image_files=parse_image_files(args.images),
                title=args.title,
                note=note_content,
                tags=parse_tags(args.tags),
                publish_date=args.schedule or 0,
                publish_strategy=publish_strategy,
                debug=args.debug,
                headless=args.headless,
                cdp_url=getattr(args, "cdp_url", None),
                bgm=args.bgm or "",
            )
            await upload_note(request)
            print(f"Douyin note upload submitted: {len(request.image_files)} images")
            return 0

        raise RuntimeError(f"Unsupported Douyin action: {args.action}")

    if args.platform == "kuaishou":
        if args.action == "login":
            result = await login_kuaishou_account(args.account, headless=args.headless, cdp_url=getattr(args, "cdp_url", None))
            if not result["success"]:
                raise RuntimeError(result["message"])
            print(f"Kuaishou login flow completed: {result['account_file']}")
            return 0

        if args.action == "check":
            is_valid = await check_kuaishou_account(args.account)
            print("valid" if is_valid else "invalid")
            return 0 if is_valid else 1

        publish_strategy = KUAISHOU_PUBLISH_STRATEGY_SCHEDULED if args.schedule else KUAISHOU_PUBLISH_STRATEGY_IMMEDIATE

        if args.action == "upload-video":
            request = KuaishouVideoUploadRequest(
                account_name=args.account,
                video_file=args.file,
                title=args.title,
                description=args.desc,
                tags=parse_tags(args.tags),
                publish_date=args.schedule or 0,
                thumbnail_file=args.thumbnail,
                publish_strategy=publish_strategy,
                debug=args.debug,
                headless=args.headless,
                cdp_url=getattr(args, "cdp_url", None),
            )
            await upload_kuaishou_video(request)
            print(f"Kuaishou video upload submitted: {request.video_file}")
            return 0

        if args.action == "upload-note":
            request = KuaishouNoteUploadRequest(
                account_name=args.account,
                image_files=parse_image_files(args.images),
                title=args.title,
                note=args.note,
                tags=parse_tags(args.tags),
                publish_date=args.schedule or 0,
                publish_strategy=publish_strategy,
                debug=args.debug,
                headless=args.headless,
                cdp_url=getattr(args, "cdp_url", None),
            )
            await upload_kuaishou_note(request)
            print(f"Kuaishou note upload submitted: {len(request.image_files)} images")
            return 0

        raise RuntimeError(f"Unsupported Kuaishou action: {args.action}")

    if args.platform == "xiaohongshu":
        if args.action == "login":
            result = await login_xiaohongshu_account(args.account, headless=args.headless, cdp_url=getattr(args, "cdp_url", None))
            if not result["success"]:
                raise RuntimeError(result["message"])
            print(f"Xiaohongshu login flow completed: {result['account_file']}")
            return 0

        if args.action == "check":
            is_valid = await check_xiaohongshu_account(args.account, cdp_url=getattr(args, "cdp_url", None) or os.environ.get("SAU_CDP_URL"))
            print("valid" if is_valid else "invalid")
            return 0 if is_valid else 1

        publish_strategy = (
            XIAOHONGSHU_PUBLISH_STRATEGY_SCHEDULED if args.schedule else XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE
        )

        if args.action == "upload-video":
            parsed_tags = parse_tags(args.tags)
            if len(parsed_tags) > 10:
                print(f"错误：小红书标签最多 10 个，当前提供了 {len(parsed_tags)} 个: {parsed_tags}", file=sys.stderr)
                return 1
            request = XiaohongshuVideoUploadRequest(
                account_name=args.account,
                video_file=args.file,
                title=args.title,
                description=args.desc,
                tags=parsed_tags,
                publish_date=args.schedule or 0,
                thumbnail_file=args.thumbnail,
                publish_strategy=publish_strategy,
                debug=args.debug,
                headless=args.headless,
                cdp_url=getattr(args, "cdp_url", None),
                submit=not getattr(args, "no_submit", False),
            )
            await upload_xiaohongshu_video(request)
            action_label = "submitted" if request.submit else "prepared without submit"
            print(f"Xiaohongshu video upload {action_label}: {request.video_file}")
            return 0

        if args.action == "upload-note":
            parsed_tags = parse_tags(args.tags)
            if len(parsed_tags) > 10:
                print(f"错误：小红书标签最多 10 个，当前提供了 {len(parsed_tags)} 个: {parsed_tags}", file=sys.stderr)
                return 1
            request = XiaohongshuNoteUploadRequest(
                account_name=args.account,
                image_files=parse_image_files(args.images),
                title=args.title,
                note=args.note,
                tags=parsed_tags,
                publish_date=args.schedule or 0,
                publish_strategy=publish_strategy,
                debug=args.debug,
                headless=args.headless,
                cdp_url=getattr(args, "cdp_url", None),
            )
            await upload_xiaohongshu_note(request)
            print(f"Xiaohongshu note upload submitted: {len(request.image_files)} images")
            return 0

        raise RuntimeError(f"Unsupported Xiaohongshu action: {args.action}")

    if args.platform == "bilibili":
        if args.action == "login":
            result = await login_bilibili_account(
                args.account, cdp_url=getattr(args, "cdp_url", None), target=target
            )
            if not result["success"]:
                raise RuntimeError(result["message"])
            print(f"Bilibili login flow completed: {result['account_file']}")
            return 0

        if args.action == "check":
            is_valid = await check_bilibili_account(
                args.account, cdp_url=getattr(args, "cdp_url", None), target=target
            )
            print("valid" if is_valid else "invalid")
            return 0 if is_valid else 1

        if args.action == "identity":
            account_file = resolve_account_file("bilibili", args.account)
            identity = (
                await get_bilibili_cdp_identity(args.cdp_url, target)
                if getattr(args, "cdp_url", None)
                else read_bilibili_account_identity(account_file, target)
            )
            if getattr(args, "target_account", None) and not identity_matches(identity, args.target_account):
                raise RuntimeError("identity does not match --target-account")
            print(json.dumps(identity.to_dict(), ensure_ascii=False, sort_keys=True))
            return 0 if identity.logged_in and identity.stable_id else 1

        if args.action == "upload-video":
            live_identity = None
            if getattr(args, "cdp_url", None):
                live_identity = await get_bilibili_cdp_identity(args.cdp_url, target)
                require_publish_identity(live_identity)
                if getattr(args, "target_account", None) and not identity_matches(live_identity, args.target_account):
                    raise RuntimeError("blocked publish identity: target account does not match Bilibili page")
            request = BilibiliVideoUploadRequest(
                account_name=args.account,
                video_file=args.file,
                title=args.title,
                description=args.desc,
                tid=args.tid,
                tags=parse_tags(args.tags),
                publish_date=args.schedule or 0,
                line=args.line,
                thumbnail_file=args.thumbnail,
                charging_pay=args.charging_pay,
                collection=args.collection,
                cdp_url=getattr(args, "cdp_url", None),
                browser_name=target.name if target else None,
                cdp_port=target.port if target else None,
                target_account=getattr(args, "target_account", None),
                focus_fallback_used=bool(
                    live_identity
                    and live_identity.extra.get("focus_fallback_used")
                ),
            )
            result = await upload_bilibili_video(request)
            args._last_result = result
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0

        raise RuntimeError(f"Unsupported Bilibili action: {args.action}")

    if args.platform == "tencent":
        if args.action == "login":
            result = await login_tencent_account(args.account, headless=args.headless)
            if not result["success"]:
                raise RuntimeError(result["message"])
            print(f"Tencent/WeChat Channels login flow completed: {result['account_file']}")
            return 0

        if args.action == "check":
            is_valid = await check_tencent_account(args.account)
            print("valid" if is_valid else "invalid")
            return 0 if is_valid else 1

        publish_strategy = TENCENT_PUBLISH_STRATEGY_SCHEDULED if args.schedule else TENCENT_PUBLISH_STRATEGY_IMMEDIATE

        if args.action == "upload-video":
            request = TencentVideoUploadRequest(
                account_name=args.account,
                video_file=args.file,
                title=args.title,
                description=args.desc,
                tags=parse_tags(args.tags),
                publish_date=args.schedule or 0,
                thumbnail_file=args.thumbnail,
                thumbnail_landscape_file=args.thumbnail_landscape,
                thumbnail_portrait_file=args.thumbnail_portrait,
                short_title=args.short_title,
                category=args.category,
                is_draft=args.draft,
                publish_strategy=publish_strategy,
                debug=args.debug,
                headless=args.headless,
                cdp_url=getattr(args, "cdp_url", None),
            )
            await upload_tencent_video(request)
            print(f"Tencent/WeChat Channels video upload submitted: {request.video_file}")
            return 0

        raise RuntimeError(f"Unsupported Tencent/WeChat Channels action: {args.action}")

    if args.platform == "youtube":
        if args.action == "login":
            result = await login_youtube_account(
                args.account, headless=args.headless, cdp_url=getattr(args, "cdp_url", None)
            )
            if not result["success"]:
                raise RuntimeError(result["message"])
            print(f"YouTube login flow completed: {result['account_file']}")
            return 0

        if args.action == "check":
            is_valid = await check_youtube_account(args.account, cdp_url=getattr(args, "cdp_url", None))
            print("valid" if is_valid else "invalid")
            return 0 if is_valid else 1

        if args.action == "identity":
            identity = await get_youtube_account_identity(
                cdp_url=getattr(args, "cdp_url", None),
                browser_name=target.name if target else None,
                cdp_port=target.port if target else None,
            )
            if getattr(args, "target_account", None) and not identity_matches(identity, args.target_account):
                raise RuntimeError("identity does not match --target-account")
            print(json.dumps(identity.to_dict(), ensure_ascii=False, sort_keys=True))
            return 0 if identity.logged_in and identity.stable_id else 1

        if args.action == "upload-video":
            request = YouTubeVideoUploadRequest(
                account_name=args.account,
                video_file=args.file,
                title=args.title,
                description=args.desc,
                tags=parse_tags(args.tags),
                thumbnail_file=args.thumbnail,
                playlist=args.playlist,
                visibility=args.visibility,
                debug=args.debug,
                headless=args.headless,
                cdp_url=getattr(args, "cdp_url", None),
                submit=args.submit,
                schedule=getattr(args, "schedule", None),
                timezone=getattr(args, "timezone", "Asia/Shanghai"),
                browser_name=target.name if target else None,
                cdp_port=target.port if target else None,
                target_account=getattr(args, "target_account", None),
            )
            result = await upload_youtube_video(request)
            if isinstance(result, dict):
                args._last_result = result
                print(json.dumps(result, ensure_ascii=False, sort_keys=True))
                if request.submit and result.get("status") != "success":
                    return 1
            else:
                action_label = "submitted" if request.submit else "prepared without submit"
                print(f"YouTube video upload {action_label}: {request.video_file}")
            return 0

        raise RuntimeError(f"Unsupported YouTube action: {args.action}")

    raise RuntimeError(f"Unsupported platform: {args.platform}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    args = parser.parse_args(raw_argv)
    args._raw_argv = raw_argv

    async def run_dispatch() -> int:
        async def dispatch_with_browser_locks() -> int:
            with contextlib.ExitStack() as stack:
                for port in _batch_ports(args):
                    stack.enter_context(browser_task_lock(port))
                return await dispatch(args)

        task_id = getattr(args, "task_id", None)
        if not task_id:
            return await dispatch_with_browser_locks()
        prior = begin_task(task_id, raw_argv)
        if prior["state"] != "started":
            print(json.dumps(prior["result"], ensure_ascii=False, sort_keys=True))
            return 0 if prior["state"] == "skipped_duplicate" else 1
        try:
            exit_code = await dispatch_with_browser_locks()
        except asyncio.TimeoutError:
            finish_task(task_id, {"status": "error", "message": "task outcome is uncertain", "task_state": "uncertain"})
            raise
        except Exception as exc:
            finish_task(task_id, {"status": "error", "message": _sanitized_identity_error(exc), "task_state": "failed"})
            raise
        if isinstance(getattr(args, "_last_result", None), dict):
            finish_task(
                task_id,
                {
                    **args._last_result,
                    "exit_code": exit_code,
                    "task_state": "complete" if exit_code == 0 else "failed",
                },
            )
        else:
            finish_task(task_id, {"status": "success" if exit_code == 0 else "error", "exit_code": exit_code, "task_state": "complete" if exit_code == 0 else "failed"})
        return exit_code

    try:
        return asyncio.run(run_dispatch())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
