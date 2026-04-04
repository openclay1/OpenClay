"""twitter_post.py — Post tweets via Tweepy OAuth1."""
from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"


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


def check_twitter_ready() -> bool:
    """Return True if all four Twitter credentials are set."""
    keys = ["TWITTER_API_KEY", "TWITTER_API_SECRET",
            "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_TOKEN_SECRET"]
    return all(_read_env_key(k) for k in keys)


def post_tweet(text: str) -> dict:
    """Authenticate with OAuth1 and post a tweet.

    Returns {"success": True, "tweet_id": "..."} or {"error": "..."}.
    """
    try:
        import tweepy
    except ImportError:
        return {"error": "tweepy not installed. Run: pip3 install tweepy"}

    api_key = _read_env_key("TWITTER_API_KEY")
    api_secret = _read_env_key("TWITTER_API_SECRET")
    access_token = _read_env_key("TWITTER_ACCESS_TOKEN")
    access_secret = _read_env_key("TWITTER_ACCESS_TOKEN_SECRET")

    if not all([api_key, api_secret, access_token, access_secret]):
        return {"error": "Twitter credentials missing from .env"}

    try:
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        response = client.create_tweet(text=text[:280])
        tweet_id = response.data.get("id", "")
        return {"success": True, "tweet_id": str(tweet_id)}
    except tweepy.TweepyException as e:
        return {"error": f"Twitter API error: {e}"}
    except Exception as e:
        return {"error": f"Failed to post: {e}"}
