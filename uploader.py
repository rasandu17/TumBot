"""
uploader.py — Upload media to Tumblr via pytumblr
"""

import os
import logging
from pathlib import Path

import pytumblr

logger = logging.getLogger("TumblerBot.uploader")

# ── Tumblr credentials (loaded from .env via bot.py's load_dotenv call) ───────
TUMBLR_CONSUMER_KEY    = os.getenv("TUMBLR_CONSUMER_KEY", "")
TUMBLR_CONSUMER_SECRET = os.getenv("TUMBLR_CONSUMER_SECRET", "")
TUMBLR_OAUTH_TOKEN     = os.getenv("TUMBLR_OAUTH_TOKEN", "")
TUMBLR_OAUTH_SECRET    = os.getenv("TUMBLR_OAUTH_SECRET", "")
TUMBLR_BLOG_NAME       = os.getenv("TUMBLR_BLOG_NAME", "")   # e.g. "myblog"

# Optional tags applied to every post (comma-separated in .env)
_raw_tags = os.getenv("TUMBLR_POST_TAGS", "")
DEFAULT_TAGS = [t.strip() for t in _raw_tags.split(",") if t.strip()]

# Default caption appended to every post after the Instagram caption
DEFAULT_CAPTION = os.getenv("TUMBLR_DEFAULT_CAPTION", "").strip()


def _client() -> pytumblr.TumblrRestClient:
    """Create and return an authenticated Tumblr client."""
    if not all([TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET,
                TUMBLR_OAUTH_TOKEN, TUMBLR_OAUTH_SECRET, TUMBLR_BLOG_NAME]):
        raise RuntimeError(
            "One or more Tumblr credentials are missing. "
            "Check TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET, "
            "TUMBLR_OAUTH_TOKEN, TUMBLR_OAUTH_SECRET, and TUMBLR_BLOG_NAME in .env."
        )
    return pytumblr.TumblrRestClient(
        TUMBLR_CONSUMER_KEY,
        TUMBLR_CONSUMER_SECRET,
        TUMBLR_OAUTH_TOKEN,
        TUMBLR_OAUTH_SECRET,
    )


def upload_to_tumblr(
    media_path: str,
    media_type: str,
    caption: str,
    source_url: str,
) -> str:
    """
    Upload *media_path* to Tumblr and return the public post URL.

    Parameters
    ----------
    media_path  : local path to the downloaded file
    media_type  : "video" or "image"
    caption     : Instagram post description used as the Tumblr caption
    source_url  : original Instagram URL
    """
    client = _client()

    full_caption = _build_caption(caption)
    logger.info("Posting with tags: %s", DEFAULT_TAGS)

    if media_type == "video":
        response = client.create_video(
            TUMBLR_BLOG_NAME,
            caption=full_caption,
            data=media_path,
            tags=DEFAULT_TAGS,
        )
    else:
        response = client.create_photo(
            TUMBLR_BLOG_NAME,
            caption=full_caption,
            data=[media_path],
            tags=DEFAULT_TAGS,
        )

    _check_response(response)

    post_id = response.get("id") or response.get("id_string")
    post_url = f"https://www.tumblr.com/blog/view/{TUMBLR_BLOG_NAME}/{post_id}"
    logger.info("Tumblr post created: %s", post_url)
    return post_url



def _build_caption(instagram_caption: str) -> str:
    """
    Build the final Tumblr post caption.
    Structure: [Instagram caption] on one line, then [Default caption] on a new line below.
    Uses HTML <p> tags so Tumblr renders them as separate paragraphs.
    """
    parts = []
    if instagram_caption and instagram_caption.strip():
        parts.append(f"<p>{instagram_caption.strip()}</p>")
    if DEFAULT_CAPTION:
        parts.append(f"<p>{DEFAULT_CAPTION}</p>")
    return "\n".join(parts)


def _check_response(response: dict) -> None:
    """Raise a descriptive error if the Tumblr API returned an error."""
    if "meta" in response:
        status = response["meta"].get("status", 0)
        if status not in (200, 201):
            msg = response["meta"].get("msg", "Unknown error")
            raise RuntimeError(f"Tumblr API error {status}: {msg}")
    if "errors" in response:
        raise RuntimeError(f"Tumblr API errors: {response['errors']}")
    if "id" not in response and "id_string" not in response:
        raise RuntimeError(f"Unexpected Tumblr response: {response}")
