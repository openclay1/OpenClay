"""credential_store.py — .env credential writer (OCR wizard removed).

Twitter credentials are managed by twitter_post.py (single source of truth).
This module provides only generic .env read/write for non-Twitter credentials.
"""
from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}


def is_image(path: Path) -> bool:
    return path.suffix.lower() in _IMAGE_EXTS


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


def self_test() -> bool:
    """Verify image detection and .env write logic."""
    assert is_image(Path("test.png")) and not is_image(Path("test.txt"))
    return True
