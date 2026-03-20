# TumblerBot 🤖📸➡️🌀

A Telegram bot that accepts Instagram links and automatically downloads the media using **yt-dlp**, then uploads it directly to your **Tumblr** blog.

---

## Features

- ✅ Supports Instagram **Posts**, **Reels**, and **Videos** (`/p/`, `/reel/`, `/tv/`)
- ✅ Downloads best-quality MP4 using **yt-dlp**
- ✅ Uploads **video** and **photo** posts to Tumblr
- ✅ Preserves the original Instagram caption
- ✅ Adds a source link back to the original post
- ✅ Configurable tags per post
- ✅ Optional Instagram cookies support for improved reliability

---

## Project Structure

```
TumblerBot/
├── bot.py            ← Main Telegram bot
├── downloader.py     ← yt-dlp Instagram downloader
├── uploader.py       ← Tumblr upload logic
├── tumblr_auth.py    ← One-time OAuth helper
├── requirements.txt  ← Python dependencies
├── .env.example      ← Configuration template
└── .env              ← Your secrets (DO NOT commit)
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

> You also need **ffmpeg** installed and on your PATH for yt-dlp to merge video+audio streams.
> Download from https://ffmpeg.org/download.html

### 2. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the **Bot Token**

### 3. Create a Tumblr App

1. Go to https://www.tumblr.com/oauth/apps
2. Click **Register application**
3. Fill in the details (the callback URL can be `https://localhost`)
4. Copy your **Consumer Key** and **Consumer Secret**

### 4. Get Tumblr OAuth Tokens

```bash
# First, put your Consumer Key/Secret in .env
cp .env.example .env
# Edit .env and fill TUMBLR_CONSUMER_KEY and TUMBLR_CONSUMER_SECRET

# Then run the auth helper
python tumblr_auth.py
```

Follow the prompts — it will open your browser, you authorize the app, paste the verifier code, and your `OAUTH_TOKEN` and `OAUTH_SECRET` will be printed.

### 5. Configure .env

```bash
cp .env.example .env
```

Fill in all values:

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TUMBLR_CONSUMER_KEY` | From Tumblr app registration |
| `TUMBLR_CONSUMER_SECRET` | From Tumblr app registration |
| `TUMBLR_OAUTH_TOKEN` | From `tumblr_auth.py` |
| `TUMBLR_OAUTH_SECRET` | From `tumblr_auth.py` |
| `TUMBLR_BLOG_NAME` | Your blog subdomain (e.g. `myblog`) |
| `TUMBLR_POST_TAGS` | Comma-separated tags (optional) |
| `INSTAGRAM_COOKIES_FILE` | Path to cookies.txt (optional) |

### 6. Run the bot

```bash
python bot.py
```

---

## Usage

1. Start a chat with your bot on Telegram
2. Send `/start` to see the welcome message
3. Paste any Instagram URL:
   - `https://www.instagram.com/p/ABC123/`
   - `https://www.instagram.com/reel/ABC123/`
4. The bot downloads and uploads automatically! 🎉

---

## Instagram Cookies (Optional)

Some Instagram content requires a logged-in session. To provide cookies:

1. Install the [cookies.txt browser extension](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
2. Log into Instagram in your browser
3. Export cookies as `instagram_cookies.txt` (Netscape format)
4. Set `INSTAGRAM_COOKIES_FILE=instagram_cookies.txt` in `.env`

---

## Notes

- Tumblr has a **100MB video file size limit** for direct uploads
- yt-dlp updates frequently; run `pip install -U yt-dlp` if downloads break
- Instagram may rate-limit or block scraping — use cookies for best results
