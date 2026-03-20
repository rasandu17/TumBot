"""
start.py — Koyeb/server entrypoint

Supports two strategies for providing Instagram cookies:

Strategy A — Chunked env vars (RECOMMENDED for Koyeb):
   Split the base64 cookie string across multiple env vars:
     INSTAGRAM_COOKIES_B64_1=<first ~50 000 chars>
     INSTAGRAM_COOKIES_B64_2=<next  ~50 000 chars>
     ...
   The script reassembles them in order before decoding.

Strategy B — Single env var (may hit ARG_MAX on some platforms):
   INSTAGRAM_COOKIES_B64=<entire base64 string>

After writing cookies.txt the script launches bot.py.
"""

import os
import base64
import subprocess
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

COOKIES_FILE = os.getenv("INSTAGRAM_COOKIES_FILE", "cookies.txt")
PORT = int(os.getenv("PORT", "8000"))

# ── Health check server (keeps Koyeb happy) ──────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *args):
        pass  # silence health check logs

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()

threading.Thread(target=start_health_server, daemon=True).start()
print(f"[start.py] 💓 Health check server running on port {PORT}")

# ── Strategy A: chunked vars ─────────────────────────────────────────────────
chunks = []
i = 1
while True:
    chunk = os.getenv(f"INSTAGRAM_COOKIES_B64_{i}", "").strip()
    if not chunk:
        break
    chunks.append(chunk)
    i += 1

# ── Strategy B: single var (fallback) ────────────────────────────────────────
if not chunks:
    single = os.getenv("INSTAGRAM_COOKIES_B64", "").strip()
    if single:
        chunks = [single]

# ── Write cookies if we got any data ─────────────────────────────────────────
if chunks:
    cookies_b64 = "".join(chunks)
    try:
        decoded = base64.b64decode(cookies_b64).decode("utf-8")
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            f.write(decoded)
        print(f"[start.py] ✅ Instagram cookies written to {COOKIES_FILE} "
              f"({len(chunks)} chunk(s), {len(cookies_b64)} chars)")
    except Exception as e:
        print(f"[start.py] ⚠️  Failed to decode cookies: {e}")
else:
    print("[start.py] ℹ️  No INSTAGRAM_COOKIES_B64 / INSTAGRAM_COOKIES_B64_N found — "
          "skipping cookie setup.")

# ── Launch the actual bot ─────────────────────────────────────────────────────
print("[start.py] 🚀 Starting TumblerBot...")
result = subprocess.run([sys.executable, "bot.py"])
sys.exit(result.returncode)
