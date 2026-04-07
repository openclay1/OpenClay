"""credential_store.py — Detect and store API credentials from screenshots."""
from __future__ import annotations
import base64, re
from pathlib import Path

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"

# Maps screenshot labels → .env key names
_CREDENTIAL_MAP = {
    "consumer key": "TWITTER_API_KEY",
    "api key": "TWITTER_API_KEY",
    "consumer secret": "TWITTER_API_SECRET",
    "consumer key secret": "TWITTER_API_SECRET",
    "api secret": "TWITTER_API_SECRET",
    "api key secret": "TWITTER_API_SECRET",
    "access token": "TWITTER_ACCESS_TOKEN",
    "access token secret": "TWITTER_ACCESS_TOKEN_SECRET",
    "bearer token": "TWITTER_BEARER_TOKEN",
    "instagram app id": "INSTAGRAM_APP_ID",
    "instagram app secret": "INSTAGRAM_APP_SECRET",
    "instagram access token": "INSTAGRAM_ACCESS_TOKEN",
    "anthropic api key": "ANTHROPIC_API_KEY",
    "openai api key": "OPENAI_API_KEY",
}

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}

def is_image(path: Path) -> bool:
    return path.suffix.lower() in _IMAGE_EXTS


def _read_image_with_vision(image_path: Path) -> str:
    """Send image to local Ollama vision model, ask it to extract credentials."""
    try:
        import requests
    except ImportError:
        return ""
    b64 = base64.standard_b64encode(image_path.read_bytes()).decode("ascii")
    prompt = (
        "This screenshot contains API credentials. "
        "Extract EVERY credential you see. For each one, output exactly:\n"
        "LABEL: [the label shown, e.g. 'Consumer Key']\n"
        "VALUE: [the actual key/token value]\n\n"
        "Output ONLY the LABEL/VALUE pairs. Nothing else. No commentary.\n"
        "Do not truncate or abbreviate the values — copy them in full.\n"
    )
    # Try llava models
    from retry_ext import retry_call
    for model in ["llava-llama3", "llava", "llava:7b"]:
        try:
            resp = retry_call(
                requests.post, "http://localhost:11434/api/generate",
                json={"model": model, "prompt": prompt,
                      "images": [b64], "stream": False},
                timeout=120, label=f"cred-vision-{model}",
            )
            if resp.status_code == 200:
                return resp.json().get("response", "")
        except Exception:
            continue
    return ""


def _parse_credentials(vision_output: str) -> dict[str, str]:
    """Parse LABEL/VALUE pairs from vision model output into env vars."""
    creds = {}
    lines = vision_output.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        label_match = re.match(r"(?:LABEL|Label)\s*:\s*(.+)", line)
        if label_match and i + 1 < len(lines):
            label = label_match.group(1).strip().strip('"').strip("'")
            value_line = lines[i + 1].strip()
            value_match = re.match(r"(?:VALUE|Value)\s*:\s*(.+)", value_line)
            if value_match:
                value = value_match.group(1).strip().strip('"').strip("'")
                # Map label to env var name
                label_lower = label.lower().strip()
                for pattern, env_key in _CREDENTIAL_MAP.items():
                    if pattern in label_lower:
                        creds[env_key] = value
                        break
                i += 2
                continue
        i += 1
    return creds


def _write_env(creds: dict[str, str]) -> int:
    """Write credentials to .env. Updates existing keys, appends new ones."""
    existing = {}
    lines = []
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, v = stripped.partition("=")
                existing[k.strip()] = len(lines)
            lines.append(line)
    written = 0
    for key, value in creds.items():
        if key in existing:
            lines[existing[key]] = f"{key}={value}"
        else:
            lines.append(f"{key}={value}")
        written += 1
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return written


def _detect_platform(creds: dict[str, str]) -> str:
    """Identify which platform the credentials belong to."""
    keys = set(creds.keys())
    if keys & {"TWITTER_API_KEY", "TWITTER_API_SECRET",
               "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_TOKEN_SECRET"}:
        return "twitter"
    if keys & {"INSTAGRAM_APP_ID", "INSTAGRAM_APP_SECRET"}:
        return "instagram"
    if "ANTHROPIC_API_KEY" in keys:
        return "anthropic"
    if "OPENAI_API_KEY" in keys:
        return "openai"
    return "unknown"


def _validate_twitter(creds: dict[str, str]) -> str:
    """Test Twitter auth. Returns status string."""
    try:
        import tweepy
    except ImportError:
        return "Saved. Install tweepy to verify: pip3 install tweepy"
    try:
        client = tweepy.Client(
            consumer_key=creds.get("TWITTER_API_KEY", ""),
            consumer_secret=creds.get("TWITTER_API_SECRET", ""),
            access_token=creds.get("TWITTER_ACCESS_TOKEN", ""),
            access_token_secret=creds.get("TWITTER_ACCESS_TOKEN_SECRET", ""),
        )
        me = client.get_me()
        if me and me.data:
            return f"Connected as @{me.data.username}"
        return "Saved but could not verify account."
    except Exception as e:
        return f"Saved but auth check failed: {e}"


def store_credentials_from_images(image_paths: list[Path]) -> str:
    """Main entry: read credential screenshots, store, validate."""
    all_creds = {}
    for img in image_paths:
        if not is_image(img):
            continue
        raw = _read_image_with_vision(img)
        if raw:
            parsed = _parse_credentials(raw)
            all_creds.update(parsed)
    if not all_creds:
        return ("Could not read credentials from the screenshot. "
                "Make sure the full key values are visible.")
    count = _write_env(all_creds)
    platform = _detect_platform(all_creds)
    parts = [f"**{count} credential{'s' if count != 1 else ''} saved** to .env."]
    # Validate if we have enough for a platform
    if platform == "twitter":
        from twitter_post import _read_env_key
        full_creds = {
            "TWITTER_API_KEY": _read_env_key("TWITTER_API_KEY"),
            "TWITTER_API_SECRET": _read_env_key("TWITTER_API_SECRET"),
            "TWITTER_ACCESS_TOKEN": _read_env_key("TWITTER_ACCESS_TOKEN"),
            "TWITTER_ACCESS_TOKEN_SECRET": _read_env_key("TWITTER_ACCESS_TOKEN_SECRET"),
        }
        status = _validate_twitter(full_creds)
        parts.append(f"Twitter: {status}")
    elif platform != "unknown":
        parts.append(f"Platform: {platform}")
    # Clean up — don't keep credential images around
    for img in image_paths:
        try:
            img.unlink()
        except Exception:
            pass
    return " ".join(parts)


def self_test() -> bool:
    """Verify parsing and mapping logic."""
    assert is_image(Path("test.png")) and not is_image(Path("test.txt"))
    parsed = _parse_credentials("LABEL: Consumer Key\nVALUE: abc123")
    assert parsed.get("TWITTER_API_KEY") == "abc123", f"parse failed: {parsed}"
    assert _detect_platform({"TWITTER_API_KEY": "x"}) == "twitter"
    assert _detect_platform({"OPENAI_API_KEY": "x"}) == "openai"
    assert _detect_platform({}) == "unknown"
    return True
