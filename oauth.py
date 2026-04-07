"""
oauth.py — One-click OAuth flows for external platform connections.
Spins up a temporary local callback server, opens the browser,
captures the token, saves to .env. User clicks one button.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

try:
    import requests
except ImportError:
    requests = None

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"
ENV_PATH = BASE_DIR / ".env"

CALLBACK_PORT = 8888
CALLBACK_URL = f"http://localhost:{CALLBACK_PORT}/callback"

# Instagram Graph API via Facebook Business Login
IG_AUTH_URL = "https://www.facebook.com/dialog/oauth"
IG_TOKEN_URL = "https://graph.facebook.com/v21.0/oauth/access_token"
IG_LONG_LIVED_URL = "https://graph.facebook.com/v21.0/oauth/access_token"
IG_SCOPES = "pages_show_list,pages_read_engagement,instagram_basic,instagram_content_publish"


def _log_decision(action: str, detail: str, confidence: float = 1.0):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO agent_log (module, action, detail, confidence) "
            "VALUES (?, ?, ?, ?)",
            ("oauth", action, detail, confidence),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    with open(BASE_DIR / "agent_decisions.md", "a") as f:
        f.write(f"- **oauth**: {action} — {detail} (confidence: {confidence})\n")


def _read_env() -> dict:
    """Read .env file into a dict."""
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip()
    return env


def _write_env(key: str, value: str):
    """Add or update a key in .env."""
    env = _read_env()
    env[key] = value
    lines = [f"{k}={v}" for k, v in env.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n")


def _env_get(key: str) -> str:
    return _read_env().get(key, "")


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth redirect."""

    auth_code: str | None = None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            if code:
                _OAuthCallbackHandler.auth_code = code
                self._respond(
                    200,
                    "<h2 style='font-family:sans-serif;text-align:center;"
                    "margin-top:80px;color:#e06438'>"
                    "Connected! You can close this tab.</h2>",
                )
            else:
                error = params.get("error_description", ["Unknown error"])[0]
                self._respond(400, f"<h2>Error: {error}</h2>")
        else:
            self._respond(404, "Not found")

    def _respond(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, fmt, *args):
        pass  # suppress console noise


def _run_callback_server(timeout: int = 120) -> str | None:
    """Start a temporary HTTP server, wait for the OAuth redirect."""
    _OAuthCallbackHandler.auth_code = None
    server = HTTPServer(("localhost", CALLBACK_PORT), _OAuthCallbackHandler)
    server.timeout = timeout

    deadline = time.time() + timeout
    while time.time() < deadline and _OAuthCallbackHandler.auth_code is None:
        server.handle_request()

    server.server_close()
    return _OAuthCallbackHandler.auth_code


def _exchange_ig_code(code: str) -> dict:
    """Exchange a Facebook OAuth code for an access token via Graph API."""
    if requests is None:
        return {"error": "requests library not installed"}

    app_id = _env_get("INSTAGRAM_APP_ID")
    app_secret = _env_get("INSTAGRAM_APP_SECRET")

    from retry_ext import retry_call
    # Step 1: Exchange code for short-lived token (GET for Graph API)
    resp = retry_call(requests.get, IG_TOKEN_URL, params={
        "client_id": app_id, "client_secret": app_secret,
        "redirect_uri": CALLBACK_URL, "code": code,
    }, timeout=15, label="ig-token-exchange")

    if resp.status_code != 200:
        return {"error": f"Token exchange failed: {resp.text[:200]}"}

    data = resp.json()
    short_token = data.get("access_token", "")

    # Step 2: Exchange for long-lived token (60 days)
    if short_token and app_secret:
        ll_resp = retry_call(requests.get, IG_LONG_LIVED_URL, params={
            "grant_type": "fb_exchange_token", "client_id": app_id,
            "client_secret": app_secret, "fb_exchange_token": short_token,
        }, timeout=15, label="ig-long-lived-token")
        if ll_resp.status_code == 200:
            ll_data = ll_resp.json()
            short_token = ll_data.get("access_token", short_token)

    # Step 3: Get Instagram Business Account ID via pages
    ig_user_id = ""
    pages_resp = retry_call(requests.get,
        "https://graph.facebook.com/v21.0/me/accounts",
        params={"access_token": short_token}, timeout=15,
        label="ig-pages")
    if pages_resp.status_code == 200:
        pages = pages_resp.json().get("data", [])
        if pages:
            page_id = pages[0]["id"]
            ig_resp = retry_call(requests.get,
                f"https://graph.facebook.com/v21.0/{page_id}",
                params={"fields": "instagram_business_account",
                        "access_token": short_token},
                timeout=15, label="ig-biz-account")
            if ig_resp.status_code == 200:
                ig_data = ig_resp.json()
                ig_biz = ig_data.get("instagram_business_account", {})
                ig_user_id = ig_biz.get("id", "")

    return {"access_token": short_token, "user_id": ig_user_id}


def check_instagram_ready() -> dict:
    """Check if Instagram credentials are configured."""
    app_id = _env_get("INSTAGRAM_APP_ID")
    app_secret = _env_get("INSTAGRAM_APP_SECRET")
    token = _env_get("INSTAGRAM_ACCESS_TOKEN")
    return {
        "app_configured": bool(app_id and app_secret),
        "connected": bool(token),
        "app_id": app_id,
    }


def connect_instagram() -> str:
    """Full Instagram OAuth flow. Returns status message."""
    status = check_instagram_ready()

    if not status["app_configured"]:
        return (
            "Instagram App ID and Secret are needed first.\n\n"
            "One-time setup: go to developers.facebook.com, create an app, "
            "add Instagram Basic Display, and paste the two values below.\n\n"
            "Once saved, click Connect again — you'll never need to do this again."
        )

    if status["connected"]:
        return "Instagram is already connected."

    app_id = _env_get("INSTAGRAM_APP_ID")

    # Build authorization URL
    auth_url = (
        f"{IG_AUTH_URL}"
        f"?client_id={app_id}"
        f"&redirect_uri={CALLBACK_URL}"
        f"&scope={IG_SCOPES}"
        f"&response_type=code"
    )

    _log_decision("opening Instagram OAuth", auth_url[:80])

    # Open browser
    webbrowser.open(auth_url)

    # Start callback server in this thread (blocks until redirect or timeout)
    code = _run_callback_server(timeout=120)

    if not code:
        _log_decision("Instagram OAuth timed out", "no callback received", 0.5)
        return "Connection timed out. Try again."

    # Exchange code for token
    result = _exchange_ig_code(code)

    if "error" in result:
        _log_decision("Instagram token exchange failed", result["error"], 0.3)
        return f"Connection failed: {result['error']}"

    # Save token
    _write_env("INSTAGRAM_ACCESS_TOKEN", result["access_token"])
    if result.get("user_id"):
        _write_env("INSTAGRAM_USER_ID", str(result["user_id"]))

    _log_decision(
        "Instagram connected",
        f"user_id={result.get('user_id')}, "
        f"expires_in={result.get('expires_in', 'unknown')}s",
    )

    return "Instagram connected successfully."


def save_app_credentials(app_id: str, app_secret: str) -> str:
    """Save Instagram app credentials to .env."""
    if not app_id.strip() or not app_secret.strip():
        return "Both App ID and App Secret are required."
    _write_env("INSTAGRAM_APP_ID", app_id.strip())
    _write_env("INSTAGRAM_APP_SECRET", app_secret.strip())
    _log_decision("Instagram app credentials saved", f"app_id={app_id[:8]}...")
    return "Saved. Now click 'Connect Instagram' to authorize."


def self_test() -> bool:
    """Verify OAuth helpers."""
    status = check_instagram_ready()
    assert isinstance(status, dict) and "app_configured" in status
    env = _read_env(); assert isinstance(env, dict)
    assert save_app_credentials("", "") == "Both App ID and App Secret are required."
    return True
