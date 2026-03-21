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

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from downloader import download_instagram
from uploader import upload_to_tumblr

# Temporary storage for multi-photo selection (in-memory)
pending_uploads = {}
import uuid

# Parse environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

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
    cleanup_needed = True
    try:
        # ── Download ──────────────────────────────────────────────────────
        logger.info("Downloading: %s", url)
        media_path, media_type, caption = await asyncio.to_thread(
            download_instagram, url, tmp_dir
        )

        # ── Multi-Media Selection ─────────────────────────────────────────
        if isinstance(media_path, list) and len(media_path) > 1:
            cleanup_needed = False
            upload_id = str(uuid.uuid4())[:12]  # short ID to fit in callback_data
            pending_uploads[upload_id] = {
                "media_path": media_path,
                "media_type": media_type,
                "caption": caption,
                "url": url,
                "tmp_dir": tmp_dir
            }
            
            from telegram import InputMediaPhoto
            await status_msg.edit_text("🖼️ Sending photo previews, please wait...")
            preview_message_ids = []
            try:
                # Telegram allows max 10 photos per media group
                m_list = list(media_path)
                media_batches = [m_list[i : i + 10] for i in range(0, len(m_list), 10)]
                offset = 0
                for batch in media_batches:
                    media_group = []
                    for i, p in enumerate(batch):
                        num = offset + i + 1
                        with open(str(p), 'rb') as f:
                            # Read file fully to memory to avoid open file handles blocking deletion
                            media_group.append(InputMediaPhoto(f.read(), caption=f"Photo {num}"))
                    msgs = await update.message.reply_media_group(media=media_group)
                    preview_message_ids.extend([m.message_id for m in msgs])
                    offset += len(batch)
            except Exception as tg_err:
                logger.warning("Could not send media group preview: %s", tg_err)
                
            pending_uploads[upload_id]["preview_message_ids"] = preview_message_ids

            keyboard = []
            row = []
            for i in range(len(media_path)):
                row.append(InlineKeyboardButton(f"Photo {i+1}", callback_data=f"up_{upload_id}_{i}"))
                if len(row) == 3:  # 3 buttons per row
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton("Upload All (Carousel)", callback_data=f"up_{upload_id}_all")])
            
            await status_msg.edit_text(
                f"📸 This post contains {len(media_path)} photos.\n\n"
                "Please view the photo previews sent above and select which one to upload to Tumblr:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

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
            disable_web_page_preview=True
        )

    except Exception as exc:
        logger.exception("Pipeline failed for %s", url)
        await status_msg.edit_text(
            f"❌ Error: {exc}\n\nMake sure the post is public and the URL is correct."
        )
    finally:
        if cleanup_needed:
            shutil.rmtree(tmp_dir, ignore_errors=True)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data.startswith("up_"):
        return
        
    parts = data.split("_")
    upload_id = parts[1]
    selection = parts[2]
    
    if upload_id not in pending_uploads:
        await query.edit_message_text("❌ This upload session has expired. Please send the link again.")
        return
        
    session = pending_uploads[upload_id]
    
    # ── Clean up previews immediately to clear the chat ──
    for msg_id in session.get("preview_message_ids", []):
        try:
            if query.message:
                await context.bot.delete_message(chat_id=query.message.chat_id, message_id=msg_id)
        except Exception as e:
            logger.warning("Failed to delete preview message %s: %s", msg_id, e)
            
    await query.edit_message_text("✅ Processing selection! Uploading to Tumblr… 📤")
    
    try:
        paths = session["media_path"]
        if selection == "all":
            selected_path = paths
        else:
            selected_path = list(paths)[int(selection)]
            
        post_url = await asyncio.to_thread(
            upload_to_tumblr, selected_path, str(session["media_type"]), str(session["caption"]), str(session["url"])
        )

        await query.edit_message_text(
            f"🎉 *Successfully posted to Tumblr!*\n\n🔗 {post_url}",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception as exc:
        logger.exception("Callback Pipeline failed")
        await query.edit_message_text(f"❌ Error during upload: {exc}")
    finally:
        pending_uploads.pop(upload_id, None)
        shutil.rmtree(str(session["tmp_dir"]), ignore_errors=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("TumblerBot is running — waiting for messages…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
