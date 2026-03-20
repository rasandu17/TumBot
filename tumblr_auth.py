"""
tumblr_auth.py — One-time OAuth1 authentication helper for Tumblr.

Run this script ONCE to get your TUMBLR_OAUTH_TOKEN and TUMBLR_OAUTH_SECRET,
then paste them into your .env file.

Usage:
    python tumblr_auth.py
"""

import os
import webbrowser
from dotenv import load_dotenv

load_dotenv()

try:
    import pytumblr
    from requests_oauthlib import OAuth1Session
except ImportError:
    print("Run: pip install pytumblr requests_oauthlib")
    raise

CONSUMER_KEY    = os.getenv("TUMBLR_CONSUMER_KEY", "")
CONSUMER_SECRET = os.getenv("TUMBLR_CONSUMER_SECRET", "")

if not CONSUMER_KEY or not CONSUMER_SECRET:
    print("❌  Please set TUMBLR_CONSUMER_KEY and TUMBLR_CONSUMER_SECRET in your .env first.")
    raise SystemExit(1)

REQUEST_TOKEN_URL = "https://www.tumblr.com/oauth/request_token"
AUTHORIZE_URL     = "https://www.tumblr.com/oauth/authorize"
ACCESS_TOKEN_URL  = "https://www.tumblr.com/oauth/access_token"

print("Step 1 — Requesting temporary token…")
oauth = OAuth1Session(CONSUMER_KEY, client_secret=CONSUMER_SECRET)
fetch_response = oauth.fetch_request_token(REQUEST_TOKEN_URL)
resource_owner_key    = fetch_response.get("oauth_token")
resource_owner_secret = fetch_response.get("oauth_token_secret")

authorize_url = f"{AUTHORIZE_URL}?oauth_token={resource_owner_key}"
print(f"\nStep 2 — Opening Tumblr authorization in your browser…\n  {authorize_url}")
webbrowser.open(authorize_url)

verifier = input("\nStep 3 — Paste the OAuth verifier from Tumblr here: ").strip()

oauth = OAuth1Session(
    CONSUMER_KEY,
    client_secret=CONSUMER_SECRET,
    resource_owner_key=resource_owner_key,
    resource_owner_secret=resource_owner_secret,
    verifier=verifier,
)

print("\nStep 4 — Fetching access token…")
access_token_response = oauth.fetch_access_token(ACCESS_TOKEN_URL)
oauth_token  = access_token_response["oauth_token"]
oauth_secret = access_token_response["oauth_token_secret"]

print("\n✅  Success! Add these lines to your .env file:\n")
print(f"TUMBLR_OAUTH_TOKEN={oauth_token}")
print(f"TUMBLR_OAUTH_SECRET={oauth_secret}")
