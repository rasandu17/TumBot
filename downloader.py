"""
downloader.py — Instagram media downloader using yt-dlp
"""

import os
import glob
import logging
from pathlib import Path

import yt_dlp

# Use bundled ffmpeg from imageio-ffmpeg if available (no system install needed)
try:
    import imageio_ffmpeg
    _FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    _FFMPEG_PATH = None

logger = logging.getLogger("TumblerBot.downloader")

# Instagram cookies file (optional — improves success rate for private/login-walled content)
COOKIES_FILE = os.getenv("INSTAGRAM_COOKIES_FILE", "")  # path to a Netscape cookies.txt


def _ydl_opts(output_dir: str) -> dict:
    """Build yt-dlp options for Instagram downloads."""
    outtmpl = os.path.join(output_dir, "%(id)s.%(ext)s")

    opts: dict = {
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": False,
        "writeinfojson": True,          # we parse this for the caption
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
        "socket_timeout": 60,
        "retries": 5,
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }
        ],
    }

    if _FFMPEG_PATH:
        opts["ffmpeg_location"] = _FFMPEG_PATH
        logger.info("Using bundled ffmpeg: %s", _FFMPEG_PATH)

    if COOKIES_FILE and Path(COOKIES_FILE).is_file():
        opts["cookiefile"] = COOKIES_FILE
        logger.info("Using cookies file: %s", COOKIES_FILE)
    
    # Read cookies directly from a specific browser (e.g., "chrome", "edge", "firefox")
    browser = os.getenv("INSTAGRAM_BROWSER", "").lower().strip()
    if browser:
        opts["cookiesfrombrowser"] = (browser, )
        logger.info("Using cookies from browser: %s", browser)

    return opts


def download_instagram(url: str, output_dir: str) -> tuple[str, str, str]:
    """
    Download an Instagram post/reel using yt-dlp.

    Returns
    -------
    (media_path, media_type, caption)
        media_path : absolute path to the downloaded file
        media_type : "video" | "image"
        caption    : post description (may be empty)
    """
    opts = _ydl_opts(output_dir)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # ── Resolve the downloaded file ────────────────────────────────────────
    # yt-dlp may merge streams, so scan for the real file
    media_path = _find_media_file(output_dir)
    if not media_path:
        raise FileNotFoundError("yt-dlp did not produce a media file in: " + output_dir)

    ext = Path(media_path).suffix.lower()
    media_type = "video" if ext in {".mp4", ".mkv", ".webm", ".mov", ".avi"} else "image"

    caption = _extract_caption(info)
    logger.info("Downloaded %s (%s) — caption length: %d", media_path, media_type, len(caption))

    return media_path, media_type, caption


def _find_media_file(directory: str) -> str | None:
    """Return the first media file found in *directory* (ignoring .json files)."""
    media_extensions = (
        "*.mp4", "*.mkv", "*.webm", "*.mov", "*.avi",
        "*.jpg", "*.jpeg", "*.png", "*.webp",
    )
    for pattern in media_extensions:
        matches = glob.glob(os.path.join(directory, pattern))
        if matches:
            # Prefer the largest file (avoids tiny thumbnails)
            return max(matches, key=os.path.getsize)
    return None


def _extract_caption(info: dict | None) -> str:
    """Pull the best available caption / title from yt-dlp info dict."""
    if not info:
        return ""
    return (
        info.get("description")
        or info.get("title")
        or info.get("fulltitle")
        or ""
    ).strip()
