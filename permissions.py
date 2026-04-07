"""permissions.py — Action tiers + outbound domain allowlist.

GREEN  — fully autonomous (read files, write queue, post to approved APIs)
YELLOW — auto-execute but log every call (web search, local scripts, public URLs)
RED    — requires explicit one-tap approval before executing

Outbound allowlist lives in config.json → "allowed_domains".
Any HTTP call to a domain not on the list is blocked + logged.
"""
from __future__ import annotations

import json, re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
SECURITY_LOG = BASE_DIR / "security_log.md"
PENDING_DIR = BASE_DIR / "pending_approvals"

# ── Tier constants ──
GREEN = "GREEN"
YELLOW = "YELLOW"
RED = "RED"

# ── Action → tier map ──
# Every action recognised by agent.py is listed here.
ACTION_TIERS: dict[str, str] = {
    # GREEN — fully autonomous
    "scan_queue":        GREEN,
    "read_file":         GREEN,
    "list_files":        GREEN,
    "write_queue":       GREEN,
    "write_file_local":  GREEN,
    "load_stack":        GREEN,
    "load_profile":      GREEN,
    "complete_task":     GREEN,
    "log_decision":      GREEN,
    "select_profile":    GREEN,
    "start_agent":       GREEN,
    "wiki_init":         GREEN,
    "wiki_query":        GREEN,
    "wiki_ingest":       GREEN,
    "wiki_lint":         GREEN,
    "generate_local":    GREEN,   # local LLM via Ollama
    "model_route_local": GREEN,   # model_router LOCAL tier
    "model_route_cloud": YELLOW,  # model_router CLOUD escalation
    "browser_navigate":  GREEN,   # read-only page fetch
    "browser_screenshot":GREEN,   # passive screenshot
    "browser_ingest":    GREEN,   # read URL → wiki raw/
    "mobile_message":    GREEN,   # text from mobile web app
    "mobile_upload":     GREEN,   # file upload from mobile

    # YELLOW — auto-execute, always logged
    "run_local_script":  YELLOW,
    "install_stack":     YELLOW,
    "pull_model":        YELLOW,
    "read_public_url":   YELLOW,
    "web_search":        YELLOW,
    "generate_text":     YELLOW,  # when output written to file
    "credential_read":   YELLOW,  # reading creds from screenshots

    # RED — needs approval
    "post_tweet":        RED,
    "post_instagram":    RED,
    "direct_post":       RED,
    "profile_action":    RED,     # arbitrary plugin code
    "form_submission":   RED,
    "external_api_call": RED,     # any non-allowlisted HTTP call
    "run_command":       RED,     # shell command execution
    "send_email":        RED,
    "purchase":          RED,
    "delete_data":       RED,
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log_security(msg: str) -> None:
    line = f"- `{_now()}` **permissions** {msg}\n"
    try:
        with open(SECURITY_LOG, "a") as f:
            if f.tell() == 0:
                f.write("# Security Log\n\nFlagged inputs caught by input_guard.\n\n")
            f.write(line)
    except FileNotFoundError:
        with open(SECURITY_LOG, "w") as f:
            f.write("# Security Log\n\nFlagged inputs caught by input_guard.\n\n")
            f.write(line)


# ── Config helpers ──

def _load_config() -> dict:
    try: return json.loads(CONFIG_PATH.read_text())
    except Exception: return {}


def allowed_domains() -> set[str]:
    """Return the set of approved outbound domains from config.json."""
    cfg = _load_config()
    return set(cfg.get("allowed_domains", []))


# ── Tier check ──

def get_tier(action: str) -> str:
    """Return GREEN, YELLOW, or RED for a named action."""
    return ACTION_TIERS.get(action, RED)


def check(action: str, detail: str = "") -> tuple[bool, str]:
    """Check if *action* may proceed.

    Returns (allowed: bool, reason: str).
    GREEN  → always (True, "green")
    YELLOW → always + logged (True, "yellow:logged")
    RED    → only if a matching approval exists (False, "red:pending")
    """
    tier = get_tier(action)
    if tier == GREEN:
        return True, "green"
    if tier == YELLOW:
        _log_security(f"YELLOW action `{action}` — {detail[:80]}")
        return True, "yellow:logged"
    # RED — look for pre-existing approval
    if _has_approval(action, detail):
        _log_security(f"RED action `{action}` APPROVED — {detail[:80]}")
        return True, "red:approved"
    # No approval → write pending
    _write_pending(action, detail)
    _log_security(f"RED action `{action}` BLOCKED pending approval — {detail[:80]}")
    return False, "red:pending"


# ── Pending approvals ──

def _approval_id(action: str, detail: str) -> str:
    """Deterministic short ID for an approval request."""
    import hashlib
    h = hashlib.sha256(f"{action}:{detail}".encode()).hexdigest()[:10]
    return f"{action}-{h}"


def _write_pending(action: str, detail: str) -> Path:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    aid = _approval_id(action, detail)
    path = PENDING_DIR / f"{aid}.json"
    data = {"action": action, "detail": detail, "requested_at": _now(),
            "status": "pending", "id": aid}
    path.write_text(json.dumps(data, indent=2))
    return path


def _has_approval(action: str, detail: str) -> bool:
    aid = _approval_id(action, detail)
    path = PENDING_DIR / f"{aid}.json"
    if not path.exists(): return False
    try:
        data = json.loads(path.read_text())
        return data.get("status") == "approved"
    except Exception: return False


def approve(approval_id: str) -> bool:
    """Mark a pending approval as approved. Called by panel button."""
    path = PENDING_DIR / f"{approval_id}.json"
    if not path.exists(): return False
    try:
        data = json.loads(path.read_text())
        data["status"] = "approved"
        data["approved_at"] = _now()
        path.write_text(json.dumps(data, indent=2))
        _log_security(f"APPROVED `{data.get('action')}` id={approval_id}")
        return True
    except Exception: return False


def deny(approval_id: str) -> bool:
    """Mark a pending approval as denied + remove file."""
    path = PENDING_DIR / f"{approval_id}.json"
    if not path.exists(): return False
    try:
        data = json.loads(path.read_text())
        _log_security(f"DENIED `{data.get('action')}` id={approval_id}")
        path.unlink()
        return True
    except Exception: return False


def list_pending() -> list[dict]:
    """Return all pending approval requests."""
    if not PENDING_DIR.is_dir(): return []
    pending = []
    for f in sorted(PENDING_DIR.iterdir()):
        if f.suffix != ".json": continue
        try:
            data = json.loads(f.read_text())
            if data.get("status") == "pending": pending.append(data)
        except Exception: pass
    return pending


# ── Outbound domain allowlist ──

def check_domain(url: str) -> bool:
    """Return True if *url*'s domain is on the allowlist. Block + log otherwise."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        host = ""
    if not host: return False
    allowed = allowed_domains()
    # Match exact or parent domain (e.g. api.twitter.com matches twitter.com)
    for d in allowed:
        if host == d or host.endswith(f".{d}"):
            return True
    _log_security(f"BLOCKED outbound to `{host}` (url: `{url[:100]}`) — not in allowlist")
    return False


def self_test() -> bool:
    """Verify tier checks and domain allowlist."""
    assert get_tier("scan_queue") == GREEN, "scan_queue not GREEN"
    assert get_tier("install_stack") == YELLOW, "install_stack not YELLOW"
    assert get_tier("post_tweet") == RED, "post_tweet not RED"
    assert get_tier("xyz_unknown") == RED, "unknown not RED"
    ok, r = check("scan_queue"); assert ok and r == "green"
    ok, r = check("install_stack", "t"); assert ok and "yellow" in r
    assert check_domain("http://localhost:11434"), "localhost blocked"
    assert check_domain("https://api.twitter.com/2/tweets"), "twitter blocked"
    assert not check_domain("https://evil.com/x"), "evil.com allowed"
    return True
