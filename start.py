"""
start.py — Koyeb/server entrypoint

1. Decodes the base64-encoded Instagram cookies from the environment variable
   INSTAGRAM_COOKIES_B64 and writes them to cookies.txt
2. Then launches bot.py
"""

import os
import base64
import subprocess
import sys

COOKIES_B64 = os.getenv("INSTAGRAM_COOKIES_B64", "").strip()
COOKIES_FILE = os.getenv("INSTAGRAM_COOKIES_FILE", "cookies.txt")

if COOKIES_B64:
    try:
        decoded = base64.b64decode(COOKIES_B64).decode("utf-8")
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            f.write(decoded)
        print(f"[start.py] ✅ Instagram cookies written to {COOKIES_FILE}")
    except Exception as e:
        print(f"[start.py] ⚠️  Failed to decode cookies: {e}")
else:
    print("[start.py] ℹ️  No INSTAGRAM_COOKIES_B64 found — skipping cookie setup.")

# Launch the actual bot
print("[start.py] 🚀 Starting TumblerBot...")
result = subprocess.run([sys.executable, "bot.py"])
sys.exit(result.returncode)
