import os
import re
import logging
import asyncio
import tempfile
import shutil
import uuid
from pathlib import Path

# ── Load env FIRST ────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
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
from profile_reviewer import is_profile_url, fetch_profile_post_urls, extract_username, download_images_to_files

BATCH_SIZE = 5

# ── In-memory stores ──────────────────────────────────────────────────────────
pending_uploads: dict = {}         # single-post multi-photo selection
profile_sessions: dict = {}        # active profile review sessions
waiting_for_start_post: dict = {}  # chat_id -> profile url

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("TumblerBot")

# ── Regex: detect Instagram post URLs ─────────────────────────────────────────
INSTAGRAM_POST_PATTERN = re.compile(
    r"(https?://)?(www\.)?instagram\.com/(p|reel|tv)/[A-Za-z0-9_\-]+/?(\?[^\s]*)?"
)


# ─────────────────────────────────────────────────────────────────────────────
#  Commands
# ─────────────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 *TumblerBot* is ready!\n\n"
        "• Send an *Instagram post/reel URL* → download & upload it directly.\n"
        "• Send an *Instagram profile URL* (e.g. `instagram.com/username`) → "
        "review that profile's photo posts one-by-one and upload the ones you like. 📸\n\n"
        "Just paste the URL — that's it!",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *How to use TumblerBot*\n\n"
        "*Single post mode:*\n"
        "Paste a post/reel URL → bot downloads & uploads it.\n\n"
        "*Profile review mode:*\n"
        "Paste a profile URL → bot fetches photo posts 5 at a time.\n"
        "  • `instagram.com/username` → start from post 1\n"
        "  • `instagram.com/username 20` → start from post 20\n\n"
        "For each post you see:\n"
        "  • ✅ *Select* (single photo) — uploads immediately\n"
        "  • *Photo 1 / Photo 2 …* (carousels) — pick & upload one\n"
        "  • *Upload All* — upload every photo in that post\n"
        "  • ⏭️ *Skip* — next post\n"
        "  • 🛑 *Stop* — end the session\n"
        "  • 🔄 *Load Next 5* — fetch next batch",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Message router
# ─────────────────────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()

    chat_id = update.effective_chat.id

    # ── Check if we're waiting for a start number
    if chat_id in waiting_for_start_post:
        if text.isdigit():
            start_num = max(1, int(text))
            profile_url = waiting_for_start_post.pop(chat_id)
            username = extract_username(profile_url) or profile_url
            await update.message.reply_text(f"🔍 Starting from post {start_num} for @{username}...")
            await handle_profile_review_start(update, context, profile_url, post_offset=start_num - 1)
            return
        elif is_profile_url(text) or INSTAGRAM_POST_PATTERN.search(text):
            # User sent something else (another link), cancel the wait and process naturally
            waiting_for_start_post.pop(chat_id, None)
        else:
            await update.message.reply_text("⚠️ Please enter a valid number, or send a new link to cancel.")
            return

    # ── Profile URL: ask where to start
    if is_profile_url(text):
        profile_url = re.sub(r"[\s,]+[0-9]+\s*$", "", text).strip()
        username = extract_username(profile_url) or profile_url

        waiting_for_start_post[chat_id] = profile_url
        await update.message.reply_text(
            f"📍 Profile: @{username}\n\n"
            "What post number would you like to start reviewing from? "
            "(e.g., send `1` for the beginning, `20` to start from the 20th post)",
            parse_mode="Markdown",
        )
        return

    match = INSTAGRAM_POST_PATTERN.search(text)
    if not match:
        await update.message.reply_text(
            "⚠️  That doesn't look like an Instagram link.\n"
            "Send a post URL like `instagram.com/p/ABC123/` "
            "or a profile URL like `instagram.com/username/`.",
            parse_mode="Markdown",
        )
        return

    # ── Single post flow ───────────────────────────────────────────────────────
    url = match.group(0)
    if not url.startswith("http"):
        url = "https://" + url

    status_msg = await update.message.reply_text(
        f"⏳ Downloading from Instagram…\n`{url}`",
        parse_mode="Markdown",
    )

    tmp_dir = tempfile.mkdtemp(prefix="tumblerbot_")
    cleanup_needed = True
    try:
        media_path, media_type, caption = await asyncio.to_thread(
            download_instagram, url, tmp_dir
        )

        if isinstance(media_path, list) and len(media_path) > 1:
            # Multi-photo: let user pick which photo(s)
            cleanup_needed = False
            upload_id = str(uuid.uuid4())[:12]
            pending_uploads[upload_id] = {
                "media_path": media_path,
                "media_type": media_type,
                "caption": caption,
                "url": url,
                "tmp_dir": tmp_dir,
            }

            await status_msg.edit_text("🖼️ Sending photo previews, please wait…")
            preview_ids = []
            try:
                m_list = list(media_path)
                for i in range(0, len(m_list), 10):
                    batch = m_list[i:i+10]
                    offset = i
                    group = []
                    for j, p in enumerate(batch):
                        with open(str(p), "rb") as f:
                            group.append(InputMediaPhoto(f.read(), caption=f"Photo {offset+j+1}"))
                    msgs = await update.message.reply_media_group(media=group)
                    preview_ids.extend([m.message_id for m in msgs])
            except Exception as e:
                logger.warning("Preview send failed: %s", e)

            pending_uploads[upload_id]["preview_ids"] = preview_ids

            keyboard = _photo_select_keyboard(upload_id, len(media_path), prefix="up")
            await status_msg.edit_text(
                f"📸 This post has {len(media_path)} photos.\n"
                "Pick which one to upload (or upload all as a carousel):",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return

        # Single file → upload directly
        await status_msg.edit_text("✅ Downloaded! Uploading to Tumblr… 📤")
        post_url = await asyncio.to_thread(
            upload_to_tumblr, media_path, media_type, caption, url
        )
        await status_msg.edit_text(
            f"🎉 *Successfully posted to Tumblr!*\n\n🔗 {post_url}",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

    except Exception as exc:
        logger.exception("Pipeline failed for %s", url)
        await status_msg.edit_text(
            f"❌ Error: {exc}\n\nMake sure the post is public and the URL is correct."
        )
    finally:
        if cleanup_needed:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Helper: build per-photo selection keyboard
# ─────────────────────────────────────────────────────────────────────────────

def _photo_select_keyboard(session_or_upload_id: str, count: int, prefix: str) -> list:
    """
    Build a keyboard with Photo 1 … Photo N buttons + Upload All.
    prefix = "up"  → callback_data = "up_<id>_<idx|all>"  (single-post mode)
    prefix = "pr"  → callback_data = "pr_photo_<id>_<idx>" + "pr_all_<id>" (profile mode)
    """
    keyboard = []
    row = []
    for i in range(count):
        if prefix == "up":
            cd = f"up_{session_or_upload_id}_{i}"
        else:
            cd = f"pr_photo_{session_or_upload_id}_{i}"
        row.append(InlineKeyboardButton(f"Photo {i+1}", callback_data=cd))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    if prefix == "up":
        keyboard.append([InlineKeyboardButton("Upload All (Carousel)", callback_data=f"up_{session_or_upload_id}_all")])
    else:
        keyboard.append([InlineKeyboardButton("Upload All (Carousel)", callback_data=f"pr_all_{session_or_upload_id}")])

    return keyboard


# ─────────────────────────────────────────────────────────────────────────────
#  Single-post multi-photo callback  (prefix "up_")
# ─────────────────────────────────────────────────────────────────────────────

async def handle_upload_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data  # "up_<id>_<idx|all>"

    parts = data.split("_")
    upload_id = parts[1]
    selection = parts[2]

    if upload_id not in pending_uploads:
        await query.edit_message_text("❌ Session expired. Send the link again.")
        return

    session = pending_uploads.pop(upload_id)

    # Delete previews
    for mid in session.get("preview_ids", []):
        try:
            await context.bot.delete_message(chat_id=query.message.chat_id, message_id=mid)
        except Exception:
            pass

    await query.edit_message_text("📤 Uploading to Tumblr…")

    try:
        paths = session["media_path"]
        selected = paths if selection == "all" else list(paths)[int(selection)]
        post_url = await asyncio.to_thread(
            upload_to_tumblr, selected, str(session["media_type"]),
            str(session["caption"]), str(session["url"]),
        )
        await query.edit_message_text(
            f"🎉 *Successfully posted to Tumblr!*\n\n🔗 {post_url}",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.exception("Upload callback failed")
        await query.edit_message_text(f"❌ Upload error: {exc}")
    finally:
        shutil.rmtree(str(session["tmp_dir"]), ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Profile Review Mode
# ─────────────────────────────────────────────────────────────────────────────

async def handle_profile_review_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    profile_url: str,
    post_offset: int = 0,
    session_id: str | None = None,
    chat_id: int | None = None,
) -> None:
    """Start or resume a profile review session."""
    username = extract_username(profile_url) or profile_url
    if not profile_url.startswith("http"):
        profile_url = "https://www.instagram.com/" + profile_url.lstrip("/")

    _chat_id = chat_id or update.effective_chat.id

    # Status message — only send new message on first call
    if post_offset == 0:
        status_msg = await update.message.reply_text(
            f"🔍 Fetching first {BATCH_SIZE} photo posts from @{username}...\n"
            "This may take a moment ⏳",
        )
    else:
        status_msg = await context.bot.send_message(
            chat_id=_chat_id,
            text=f"🔍 Fetching next {BATCH_SIZE} posts from @{username}... ⏳",
        )

    try:
        posts, tmp_dir = await asyncio.to_thread(
            fetch_profile_post_urls, profile_url, BATCH_SIZE, post_offset
        )
    except Exception as exc:
        logger.exception("Failed to fetch profile posts for %s", profile_url)
        await status_msg.edit_text(
            f"❌ Could not fetch posts from @{username}:\n{exc}\n\n"
            "Make sure the profile is public and the URL is correct."
        )
        return

    if not posts:
        await status_msg.edit_text(
            f"😕 No {'more ' if post_offset else ''}photo posts found for @{username}.",
        )
        return

    # Create or update the session
    if session_id is None:
        session_id = str(uuid.uuid4())[:12]

    profile_sessions[session_id] = {
        "username": username,
        "profile_url": profile_url,
        "posts": posts,
        "tmp_dirs": [tmp_dir] if tmp_dir else [],  # instaloader returns None (no files)
        "current_index": 0,
        "post_offset": post_offset + len(posts),  # offset for the NEXT batch
        "chat_id": _chat_id,
        "preview_msg_ids": [],
    }

    await status_msg.edit_text(
        f"✅ Loaded {len(posts)} post(s) from @{username}"
        + (f" (posts {post_offset+1}-{post_offset+len(posts)})" if post_offset else "") +
        "\n\n"
        "\u2022 Select / Photo N  →  upload immediately & go to next\n"
        "\u2022 Skip  →  next post without uploading\n"
        "\u2022 Stop  →  end the review\n"
        "\u2022 Load Next 5  →  appears when batch is done",
    )

    await _show_profile_post(_chat_id, session_id, context)


async def _show_profile_post(
    chat_id: int,
    session_id: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Send the current post preview with action buttons."""
    if session_id not in profile_sessions:
        return

    session = profile_sessions[session_id]
    idx = session["current_index"]
    posts = session["posts"]

    if idx >= len(posts):
        # Reached end of this batch — offer to load next 20 or stop
        keyboard = [[
            InlineKeyboardButton("🔄 Load Next 5", callback_data=f"pr_more_{session_id}"),
            InlineKeyboardButton("🛑 Stop",         callback_data=f"pr_stop_{session_id}"),
        ]]
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🔚 *Batch done!* Reviewed all {len(posts)} posts from this batch.\n\n"
                "Load the next 20 posts or stop here?"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    post = posts[idx]
    image_urls = post.get("image_urls", [])
    caption = post.get("caption", "")
    post_url = post.get("post_url", "")
    total = len(posts)

    # Download images for this post on-demand
    image_paths = post.get("image_paths")
    if not image_paths and image_urls:
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ Preparing post preview...",
            disable_notification=True
        )
        tmp_img_dir = tempfile.mkdtemp(prefix="tumblerbot_img_")
        if tmp_img_dir not in session["tmp_dirs"]:
            session["tmp_dirs"].append(tmp_img_dir)
        image_paths = await asyncio.to_thread(download_images_to_files, image_urls, tmp_img_dir)
        post["image_paths"] = image_paths
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        except Exception:
            pass

    # ── Send photo preview(s) ──────────────────────────────────────────────────
    preview_ids = []
    try:
        batch = image_paths[:10]
        if len(batch) == 1:
            with open(batch[0], "rb") as f:
                msg = await context.bot.send_photo(chat_id=chat_id, photo=f.read())
            preview_ids.append(msg.message_id)
        else:
            group = []
            for p in batch:
                with open(p, "rb") as f:
                    group.append(InputMediaPhoto(f.read()))
            msgs = await context.bot.send_media_group(chat_id=chat_id, media=group)
            preview_ids.extend([m.message_id for m in msgs])
    except Exception as e:
        logger.warning("Photo preview failed: %s", e)

    session["preview_msg_ids"] = preview_ids

    # ── Build keyboard ─────────────────────────────────────────────────────────
    if len(image_paths) > 1:
        # Multi-photo: individual photo buttons + Upload All + Skip + Stop
        keyboard = _photo_select_keyboard(session_id, len(image_paths), prefix="pr")
        keyboard.append([
            InlineKeyboardButton("⏭️ Skip", callback_data=f"pr_skip_{session_id}"),
            InlineKeyboardButton("🛑 Stop",  callback_data=f"pr_stop_{session_id}"),
        ])
        photo_label = f"({len(image_paths)} photos)"
    else:
        # Single photo: simple Select / Skip / Stop
        keyboard = [[
            InlineKeyboardButton("✅ Select & Upload", callback_data=f"pr_sel_{session_id}"),
            InlineKeyboardButton("⏭️ Skip",            callback_data=f"pr_skip_{session_id}"),
            InlineKeyboardButton("🛑 Stop",             callback_data=f"pr_stop_{session_id}"),
        ]]
        photo_label = ""

    caption_preview = (caption[:120] + "\u2026") if len(caption) > 120 else caption
    text = (
        f"\U0001f4f8 Post {idx+1} of {total} {photo_label}\n"
        + (f"{caption_preview}\n" if caption_preview else "")
        + (f"\U0001f517 {post_url}" if post_url else "")
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def _delete_previews(chat_id: int, msg_ids: list, context: ContextTypes.DEFAULT_TYPE) -> None:
    for mid in msg_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass


async def _upload_profile_post_photos(
    query,
    image_paths: list,
    caption: str,
    post_url: str,
    label: str = "",
) -> None:
    """Upload photo(s) from a profile post immediately and edit result message."""
    try:
        tumblr_url = await asyncio.to_thread(
            upload_to_tumblr, image_paths, "image", caption, post_url
        )
        await query.edit_message_text(
            text=f"🎉 *Uploaded to Tumblr!*{(' ' + label) if label else ''}\n\n🔗 {tumblr_url}",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.exception("Profile post upload failed")
        await query.edit_message_text(
            text=f"❌ Upload failed: {exc}",
        )


def _cleanup_profile_session(session: dict) -> None:
    for d in session.get("tmp_dirs", []):
        if d:
            shutil.rmtree(d, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Unified callback router
# ─────────────────────────────────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    # ── Single-post multi-photo ────────────────────────────────────────────────
    if data.startswith("up_"):
        await handle_upload_callback(update, context)
        return

    # ── Profile review ─────────────────────────────────────────────────────────
    if not data.startswith("pr_"):
        return

    # Possible formats:
    #   pr_sel_<session_id>           — select single photo post
    #   pr_skip_<session_id>          — skip
    #   pr_stop_<session_id>          — stop session
    #   pr_photo_<session_id>_<idx>   — select specific photo from carousel
    #   pr_all_<session_id>           — upload all photos from carousel
    #   pr_more_<session_id>          — load next batch of posts

    parts = data.split("_")
    # parts[0] = "pr"
    action = parts[1]   # sel | skip | stop | photo | all | more

    # Extract session_id — it's always right after the action word
    # For "pr_photo_<sid>_<idx>": parts = ["pr","photo","<sid>","<idx>"]
    if action == "photo":
        session_id = parts[2]
        photo_idx = int(parts[3])
    elif action in ("sel", "skip", "stop", "all", "more"):
        session_id = parts[2]
        photo_idx = None
    else:
        return

    if session_id not in profile_sessions:
        await query.edit_message_text(
            "❌ This review session has expired. Send the profile URL again."
        )
        return

    session = profile_sessions[session_id]
    chat_id = query.message.chat_id
    preview_ids = session.get("preview_msg_ids", [])
    # NOTE: do NOT access session["posts"][current_index] here — it may be out of range
    # for the "more" action (current_index == len(posts)). Access it only when needed.

    if action == "stop":
        await _delete_previews(chat_id, preview_ids, context)
        profile_sessions.pop(session_id, None)
        try:
            await query.edit_message_text(text="🛑 *Review stopped.*", parse_mode="Markdown")
        except Exception:
            pass
        _cleanup_profile_session(session)
        return

    if action == "more":
        try:
            await query.message.delete()
        except Exception:
            pass
        # Load next batch — reuse session_id so it gets overwritten
        await handle_profile_review_start(
            update=update,
            context=context,
            profile_url=session["profile_url"],
            post_offset=session["post_offset"],
            session_id=session_id,
            chat_id=chat_id,
        )
        return

    if action == "skip":
        await _delete_previews(chat_id, preview_ids, context)
        try:
            await query.message.delete()
        except Exception:
            pass
        session["current_index"] += 1
        await _show_profile_post(chat_id, session_id, context)
        return

    # ── Upload actions (sel / photo / all) ─────────────────────────────────────
    await _delete_previews(chat_id, preview_ids, context)
    post = session["posts"][session["current_index"]]  # safe here — skip/more/stop already returned

    if action == "sel":
        # Single-photo post → upload that photo
        paths = post["image_paths"][0]
        label = f"(Post {session['current_index']+1})"
        await query.edit_message_text("📤 Uploading...")
        await _upload_profile_post_photos(
            query, paths, post.get("caption", ""), post.get("post_url", ""), label
        )

    elif action == "photo":
        # Specific photo from carousel
        paths = post["image_paths"][photo_idx]
        label = f"(Post {session['current_index']+1} — Photo {photo_idx+1})"
        await query.edit_message_text(f"📤 Uploading Photo {photo_idx+1}...")
        await _upload_profile_post_photos(
            query, paths, post.get("caption", ""), post.get("post_url", ""), label
        )

    elif action == "all":
        # All photos in this carousel
        paths = post["image_paths"]
        label = f"(Post {session['current_index']+1} — All {len(paths)} photos)"
        await query.edit_message_text(f"📤 Uploading all {len(paths)} photos...")
        await _upload_profile_post_photos(
            query, paths, post.get("caption", ""), post.get("post_url", ""), label
        )

    # Advance to next post after upload
    session["current_index"] += 1
    await _show_profile_post(chat_id, session_id, context)


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
