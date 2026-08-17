from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
XHS_SERVER = "http://127.0.0.1:11901"  # only used by xhs-related flows
LOCAL_CHROME_PATH = ""  # optional, e.g. C:/Program Files/Google/Chrome/Application/chrome.exe
LOCAL_CHROME_HEADLESS = True  # default headless behavior for uploader/examples
DEBUG_MODE = True  # default debug behavior
# Optional proxy for the YouTube uploader. Where youtube.com is blocked, direct
# connections time out and the (patchright) chromium does NOT use the system proxy.
# Point this at your local proxy port, e.g. "http://127.0.0.1:7890". None = no proxy.
YT_PROXY = None

# YouTube upload duration cap in seconds. Unverified accounts reject videos longer
# than 15 minutes during processing, after a wasted full upload. The CLI now probes
# the file with ffprobe before uploading and aborts early when it exceeds this cap.
# Keep 900 (15 min) for unverified accounts; verified accounts may raise it to
# 43200 (12 hours). When ffprobe is unavailable the check is skipped with a warning.
YT_MAX_DURATION_SECONDS = 900
