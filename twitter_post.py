"""twitter_post.py — Single source of truth for Twitter credentials and posting.

All Twitter credential loading, validation, and posting goes through this file.
No other module should read Twitter keys from .env directly.
"""
from __future__ import annotations

import os, re
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"

# ── Verified app identity ──────────────────────────────────────────────
# The ONLY verified working Twitter app is: 2040419672282087424anomalia939
# OPC 2 is NOT the verified working app. Do NOT use OPC 2 credentials.
# All four Twitter keys in .env MUST come from the app above.
# If you regenerate keys, do it inside this app's dashboard — not OPC 2.
VERIFIED_APP = "2040419672282087424anomalia939"

_TWITTER_KEYS = [
    "TWITTER_API_KEY", "TWITTER_API_SECRET",
    "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_TOKEN_SECRET",
]

# Patterns that indicate placeholder / fake credentials
_PLACEHOLDERS = [
    r"^your[_-]", r"^xxx", r"^placeholder", r"^CHANGE[_-]ME", r"^TODO",
    r"^[0-9a-f]{8}-[0-9a-f]{4}-",  # UUID format — not a real Twitter key
]


def _read_env_key(key: str) -> str:
    """Read a key from .env, fall back to os.environ."""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            l = line.strip()
            if l and not l.startswith("#") and "=" in l:
                k, _, v = l.partition("=")
                if k.strip() == key:
                    return v.strip()
    return os.environ.get(key, "")


def _is_placeholder(value: str) -> bool:
    """Return True if value looks like a placeholder, not a real key."""
    return any(re.match(p, value, re.IGNORECASE) for p in _PLACEHOLDERS)


def get_credentials() -> dict[str, str]:
    """Load all four Twitter credentials from .env. Single source of truth."""
    return {k: _read_env_key(k) for k in _TWITTER_KEYS}


def check_twitter_ready() -> bool:
    """Return True if all four Twitter credentials are set and non-placeholder."""
    creds = get_credentials()
    return all(v and not _is_placeholder(v) for v in creds.values())


def validate_twitter_credentials() -> dict:
    """Full end-to-end validation of Twitter OAuth1 credentials.

    Returns {"status": str, "detail": str, "username": str | None}.
    Statuses: ready | invalid | bad_signature | wrong_app | error
    """
    creds = get_credentials()
    # 1. Check missing
    missing = [k for k, v in creds.items() if not v]
    if missing:
        return {"status": "invalid", "detail": f"Missing: {', '.join(missing)}",
                "username": None}
    # 2. Check placeholders
    for k, v in creds.items():
        if _is_placeholder(v):
            return {"status": "invalid", "username": None,
                    "detail": f"{k} is a placeholder — paste real keys from {VERIFIED_APP}"}
    # 3. Live auth check: GET /2/users/me
    try:
        import tweepy
    except ImportError:
        return {"status": "error", "detail": "tweepy not installed (pip3 install tweepy)",
                "username": None}
    try:
        client = tweepy.Client(
            consumer_key=creds["TWITTER_API_KEY"],
            consumer_secret=creds["TWITTER_API_SECRET"],
            access_token=creds["TWITTER_ACCESS_TOKEN"],
            access_token_secret=creds["TWITTER_ACCESS_TOKEN_SECRET"],
        )
        me = client.get_me()
        if me and me.data:
            return {"status": "ready", "detail": f"@{me.data.username}",
                    "username": me.data.username}
        return {"status": "invalid", "detail": "Auth OK but no user data returned",
                "username": None}
    except Exception as e:
        err = str(e).lower()
        if "401" in err or "unauthorized" in err:
            return {"status": "invalid", "username": None,
                    "detail": "401 Unauthorized — credentials are wrong or app is "
                              f"suspended. Regenerate all four keys in {VERIFIED_APP}."}
        if "403" in err or "forbidden" in err:
            return {"status": "wrong_app", "username": None,
                    "detail": "403 Forbidden — app lacks Read/Write permissions. "
                              f"Check settings for {VERIFIED_APP}."}
        if "signature" in err:
            return {"status": "bad_signature", "username": None,
                    "detail": "OAuth signature mismatch — keys are from different "
                              f"apps. All four must come from {VERIFIED_APP}."}
        return {"status": "error", "detail": str(e), "username": None}


def write_credentials(api_key: str, api_secret: str, token: str, token_secret: str):
    """Write all four Twitter credentials to .env. Single writer."""
    creds = {"TWITTER_API_KEY": api_key, "TWITTER_API_SECRET": api_secret,
             "TWITTER_ACCESS_TOKEN": token, "TWITTER_ACCESS_TOKEN_SECRET": token_secret}
    lines, existing = [], {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                existing[s.partition("=")[0].strip()] = len(lines)
            lines.append(line)
    for k, v in creds.items():
        if k in existing: lines[existing[k]] = f"{k}={v}"
        else: lines.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def post_tweet(text: str) -> dict:
    """Post a tweet. Hard guard: validates credentials first.

    Returns {"success": True, "tweet_id": "..."} or {"error": "..."}.
    """
    v = validate_twitter_credentials()
    if v["status"] != "ready":
        return {"error": f"Twitter not ready: {v['detail']}"}
    try:
        import tweepy
        from retry_ext import retry_call
        creds = get_credentials()
        client = tweepy.Client(
            consumer_key=creds["TWITTER_API_KEY"],
            consumer_secret=creds["TWITTER_API_SECRET"],
            access_token=creds["TWITTER_ACCESS_TOKEN"],
            access_token_secret=creds["TWITTER_ACCESS_TOKEN_SECRET"],
        )
        resp = retry_call(client.create_tweet, text=text[:280], label="twitter-post")
        tid = resp.data.get("id", "")
        return {"success": True, "tweet_id": str(tid)}
    except Exception as e:
        return {"error": f"Failed to post: {e}"}


def post_and_log(text: str) -> str:
    """Post a tweet, log to wiki + memory, return formatted result string."""
    result = post_tweet(text.strip())
    if result.get("success"):
        tid = result.get("tweet_id", "")
        try: __import__("wiki_engine").log_posted_tweet(text.strip(), tweet_id=tid)
        except Exception: pass
        try: __import__("memory").record_success("tweet_post", "tweepy", f"id:{tid}")
        except Exception: pass
        return f"**Posted.** Tweet ID: {tid}"
    err = result.get("error", "Unknown error")
    try: __import__("memory").record_failure("tweet_post", err)
    except Exception: pass
    return f"**Error:** {err}"


def self_test() -> bool:
    """Verify config reading, placeholder detection, and validation shape."""
    assert isinstance(check_twitter_ready(), bool), "check not bool"
    assert isinstance(_read_env_key("NONEXISTENT_KEY_XYZ"), str), "env read failed"
    # Placeholder detection
    assert _is_placeholder("your_key_here"), "missed placeholder"
    assert _is_placeholder("4f89b71d-56a9-43e0-abfb-cafe"), "missed UUID placeholder"
    assert not _is_placeholder("M7EyEvH9UsJUkGrEMqMlBh7c5"), "real key flagged"
    # Validation returns expected shape
    v = validate_twitter_credentials()
    assert v["status"] in ("ready", "invalid", "bad_signature", "wrong_app", "error")
    assert "detail" in v and "username" in v
    return True
