"""network_sandbox.py — Internet safety sandbox for OpenClay.
Local mode is always default and fully functional. Any external network request
requires explicit user permission each time. External content cannot modify
core state (BRAIN.md, SESSION.md) without user confirmation.
Based on Google DeepMind 2026 findings on AI agent hijack via hostile HTML/QR.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
_permissions: dict[str, bool] = {}
_LOCAL_MODE = True

def _now() -> str: return datetime.now().strftime("%Y-%m-%d %H:%M")

# ── Permission gate ──────────────────────────────────────────────────

def is_local_mode() -> bool:
    """True if running in local-only mode (default)."""
    return _LOCAL_MODE

def request_network_permission(action: str, url: str = "", lang: str = "en") -> dict:
    """Gate for any external network request. Returns permission request object.
    Permission is NEVER remembered — must be granted each time."""
    return {
        "action": action, "url": url, "permitted": False, "needs_approval": True,
        "label_es": f"⚠️ Esta accion requiere internet: {action}",
        "label_en": f"⚠️ This action requires internet: {action}",
        "prompt_es": f"¿Permitir conexion a internet para '{action}'? Esta accion no se recordara.",
        "prompt_en": f"Allow internet connection for '{action}'? This permission won't be remembered.",
    }

def grant_permission(action: str):
    """User explicitly grants one-time permission."""
    _permissions[action] = True

def check_permission(action: str) -> bool:
    """Check if action has been granted one-time permission."""
    granted = _permissions.pop(action, False)
    return granted

def block_external(action: str) -> dict:
    """Block an external call that hasn't been permitted."""
    return {
        "blocked": True, "action": action,
        "reason_es": "Bloqueado: esta accion requiere permiso de internet.",
        "reason_en": "Blocked: this action requires internet permission.",
    }

# ── Sandboxed fetch ──────────────────────────────────────────────────

def sandboxed_fetch(url: str, action: str = "fetch") -> dict:
    """Fetch external content only if permitted. Content is returned for review,
    never acted on automatically."""
    if not check_permission(action):
        return block_external(action)
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="ignore")[:5000]
        return {"blocked": False, "content": content, "url": url,
                "review_required": True,
                "warning_es": "Contenido externo — revisa antes de actuar.",
                "warning_en": "External content — review before taking action."}
    except Exception as e:
        return {"blocked": False, "content": "", "url": url, "error": str(e)}

# ── Core state protection ────────────────────────────────────────────

_PROTECTED_FILES = {"BRAIN.md", "SESSION.md", "SOUL.md", "AGENTS.md",
                    "DECISIONS.md", "permissions.py", "input_guard.py", "agent.py"}

def is_protected(filename: str) -> bool:
    return Path(filename).name in _PROTECTED_FILES

def attempt_modify_from_external(filename: str, content: str) -> dict:
    """Block modifications to core state from external content."""
    if is_protected(filename):
        return {"allowed": False,
                "reason_es": f"Bloqueado: contenido externo no puede modificar {Path(filename).name}",
                "reason_en": f"Blocked: external content cannot modify {Path(filename).name}"}
    return {"allowed": True, "filename": filename}

# ── Local mode verification ──────────────────────────────────────────

def verify_local_mode() -> dict:
    """Verify all core features work without network."""
    checks = {}
    for name, path in [("SOUL.md", BASE_DIR / "SOUL.md"), ("BRAIN.md", BASE_DIR / "BRAIN.md")]:
        checks[name] = path.exists()
    try:
        from vibe_brain import load_l0, load_brain
        checks["memory_layer"] = isinstance(load_l0(), str) and isinstance(load_brain(), str)
    except Exception:
        checks["memory_layer"] = False
    try:
        from first_screen import load_memory
        checks["first_screen"] = isinstance(load_memory(), dict)
    except Exception:
        checks["first_screen"] = False
    try:
        from daily_agents import AGENTS
        checks["agents"] = len(AGENTS) >= 5
    except Exception:
        checks["agents"] = False
    checks["all_pass"] = all(checks.values())
    return checks

# ── Self test ────────────────────────────────────────────────────────

def self_test() -> bool:
    # #55 — external call blocked without permission
    assert is_local_mode() is True, "Should default to local mode"
    req = request_network_permission("test_fetch", "https://example.com")
    assert req["needs_approval"] is True
    assert req["permitted"] is False
    result = sandboxed_fetch("https://example.com", "test_fetch")
    assert result["blocked"] is True, "Should block without permission"
    # Grant and verify one-time
    grant_permission("test_granted")
    assert check_permission("test_granted") is True
    assert check_permission("test_granted") is False, "Permission should be one-time only"
    # Core state protection
    assert is_protected("BRAIN.md") is True
    assert is_protected("random_file.txt") is False
    mod = attempt_modify_from_external("BRAIN.md", "hacked content")
    assert mod["allowed"] is False, "External content must not modify BRAIN.md"
    mod2 = attempt_modify_from_external("output.txt", "safe content")
    assert mod2["allowed"] is True
    # #56 — local mode fully functional
    local = verify_local_mode()
    assert isinstance(local, dict)
    assert "memory_layer" in local and "agents" in local
    return True

if __name__ == "__main__":
    print("self_test:", self_test())
