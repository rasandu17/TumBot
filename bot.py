import os
import re
import logging
import asyncio
import tempfile
import shutil
from pathlib import Path

# ── Load env FIRST — before any local imports so module-level os.getenv() calls work ──
from dotenv import load_dotenv
load_dotenv()

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from downloader import download_instagram
from uploader import upload_to_tumblr

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("TumblerBot")

# ── Regex: detect Instagram URLs ───────────────────────────────────────────────
INSTAGRAM_PATTERN = re.compile(
    r"(https?://)?(www\.)?instagram\.com/(p|reel|tv)/[A-Za-z0-9_\-]+/?(\?[^\s]*)?"
)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 *TumblerBot* is ready!\n\n"
        "Send me any *Instagram* post, reel, or video link and I'll automatically "
        "download it and upload it to your Tumblr blog. 🚀\n\n"
        "Just paste the URL — that's it!",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *How to use TumblerBot*\n\n"
        "1️⃣  Paste an Instagram URL (post, reel, or video)\n"
        "2️⃣  The bot downloads the media with *yt-dlp*\n"
        "3️⃣  It uploads the result straight to your *Tumblr* blog\n\n"
        "Supported URL formats:\n"
        "• `https://www.instagram.com/p/ABC123/`\n"
        "• `https://www.instagram.com/reel/ABC123/`\n"
        "• `https://www.instagram.com/tv/ABC123/`",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    match = INSTAGRAM_PATTERN.search(text)

    if not match:
        await update.message.reply_text(
            "⚠️  That doesn't look like an Instagram link.\n"
            "Please send a valid Instagram post/reel URL."
        )
        return

    url = match.group(0)
    if not url.startswith("http"):
        url = "https://" + url

    status_msg = await update.message.reply_text(
        f"⏳ Downloading from Instagram…\n`{url}`",
        parse_mode="Markdown",
    )

    # Work inside a temp directory so we clean up automatically
    tmp_dir = tempfile.mkdtemp(prefix="tumblerbot_")
    try:
        # ── Download ──────────────────────────────────────────────────────
        logger.info("Downloading: %s", url)
        media_path, media_type, caption = await asyncio.to_thread(
            download_instagram, url, tmp_dir
        )

        await status_msg.edit_text(
            f"✅ Downloaded!  Uploading to Tumblr… 📤",
        )

        # ── Upload ────────────────────────────────────────────────────────
        logger.info("Uploading %s (%s) to Tumblr", media_path, media_type)
        post_url = await asyncio.to_thread(
            upload_to_tumblr, media_path, media_type, caption, url
        )

        await status_msg.edit_text(
            f"🎉 *Successfully posted to Tumblr!*\n\n🔗 {post_url}",
            parse_mode="Markdown",
        )

    except Exception as exc:
        logger.exception("Pipeline failed for %s", url)
        await status_msg.edit_text(
            f"❌ Error: {exc}\n\nMake sure the post is public and the URL is correct."
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("TumblerBot is running — waiting for messages…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
