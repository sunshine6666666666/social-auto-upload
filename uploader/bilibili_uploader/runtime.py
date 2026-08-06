from __future__ import annotations

import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

import requests


GITHUB_RELEASE_API = "https://api.github.com/repos/biliup/biliup/releases/latest"

BILI_COLLECTION_LIST_API = "https://member.bilibili.com/x2/creative/web/seasons"


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


def find_bilibili_archive_aid(account_file: Path, title: str, timeout: int = 20, attempts: int = 8) -> int:
    """Find the aid of the newest archive matching an exact title via the creator archive list.

    Retries up to ``attempts`` times with a short delay because a freshly submitted
    archive may not appear in the creator list immediately.
    """
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
        for archive in archives:
            if isinstance(archive, dict):
                inner = archive.get("Archive") or archive
                if (inner.get("title") or "").strip() == needle:
                    aid = inner.get("aid") or inner.get("id")
                    if aid:
                        return int(aid)
        time.sleep(3)
    raise RuntimeError(
        f"Bilibili archive with title '{needle}' not found in creator archive list"
        + (f" ({last_error})" if last_error else "")
    )


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
