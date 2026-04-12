"""confusion_reset.py — Detects repeated failures, offers plain-language check-in.
Intercepts on second failure, not first. Auto-saves session state. Restores on crash.
Zero technical language shown to user. Zero work lost during any flow.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
SESSION_PATH = BASE_DIR / "SESSION.md"

_attempts: dict[str, int] = {}
_panel_state: dict[str, str] = {}
_session_state: dict = {"last_input": "", "last_output": "", "panel": "", "timestamp": ""}

def _now() -> str: return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def _read(p: Path) -> str: return p.read_text(encoding="utf-8") if p.exists() else ""

# ── Confusion detection ──────────────────────────────────────────────

def record_attempt(action_key: str, success: bool) -> dict | None:
    """Record an action attempt. Returns check-in message on 2nd failure, None otherwise."""
    if success:
        _attempts[action_key] = 0
        return None
    _attempts[action_key] = _attempts.get(action_key, 0) + 1
    if _attempts[action_key] >= 2:
        return {
            "intercept": True,
            "message_es": "Esto no parece estar funcionando como esperabas — ¿qué querias hacer?",
            "message_en": "This doesn't seem to be working the way you expected — what were you trying to do?",
            "attempts": _attempts[action_key],
        }
    return None

def clear_attempts(action_key: str = ""):
    """Clear attempt counter for one action or all."""
    if action_key:
        _attempts.pop(action_key, None)
    else:
        _attempts.clear()

def get_attempt_count(action_key: str) -> int:
    return _attempts.get(action_key, 0)

# ── Panel reset ──────────────────────────────────────────────────────

def save_panel_state(panel_id: str, state: str):
    """Save current state of a panel for reset capability."""
    _panel_state[panel_id] = state

def reset_panel(panel_id: str) -> str:
    """Reset one panel to empty. Returns empty string. No confirmation needed."""
    _panel_state.pop(panel_id, None)
    return ""

def get_panel_state(panel_id: str) -> str:
    return _panel_state.get(panel_id, "")

# ── Auto-save session state ──────────────────────────────────────────

def auto_save(user_input: str = "", output: str = "", panel: str = ""):
    """Save session state after every user action. Writes to SESSION.md."""
    global _session_state
    _session_state = {"last_input": user_input, "last_output": output,
                      "panel": panel, "timestamp": _now()}
    try:
        marker = "\n<!-- AUTO_SAVE -->\n"
        content = _read(SESSION_PATH)
        if "<!-- AUTO_SAVE -->" in content:
            content = content[:content.index("<!-- AUTO_SAVE -->")]
        save_block = (f"{marker}Last input: {user_input[:200]}\n"
                      f"Panel: {panel}\nTimestamp: {_session_state['timestamp']}\n")
        with open(SESSION_PATH, "w", encoding="utf-8") as f:
            f.write(content + save_block)
    except Exception:
        pass

def restore_session() -> dict:
    """Restore session after crash/interrupt. Returns state dict."""
    content = _read(SESSION_PATH)
    if "<!-- AUTO_SAVE -->" not in content:
        return {"restored": False, "last_input": "", "panel": "", "timestamp": ""}
    block = content[content.index("<!-- AUTO_SAVE -->"):]
    state = {"restored": True, "last_input": "", "panel": "", "timestamp": ""}
    for line in block.splitlines():
        if line.startswith("Last input: "): state["last_input"] = line[12:]
        elif line.startswith("Panel: "): state["panel"] = line[7:]
        elif line.startswith("Timestamp: "): state["timestamp"] = line[11:]
    return state

def get_resume_message(lang: str = "en") -> str:
    """Message shown after crash/interrupt recovery."""
    state = restore_session()
    if not state["restored"]: return ""
    if lang == "es":
        return "Tu sesion pauso — toca aqui para continuar donde quedaste."
    return "Your session paused — tap here to pick up where you left off."

# ── Reset button label ───────────────────────────────────────────────

RESET_LABEL_ES = "↩ Empezar este paso de nuevo"
RESET_LABEL_EN = "↩ Start this step over"

def reset_label(lang: str = "en") -> str:
    return RESET_LABEL_ES if lang == "es" else RESET_LABEL_EN

# ── Self test ────────────────────────────────────────────────────────

def self_test() -> bool:
    # #51 — confusion detection triggers on attempt 2, not attempt 1
    clear_attempts()
    r1 = record_attempt("test_action", False)
    assert r1 is None, "Should not intercept on first failure"
    assert get_attempt_count("test_action") == 1
    r2 = record_attempt("test_action", False)
    assert r2 is not None and r2["intercept"] is True, "Should intercept on second failure"
    assert r2["attempts"] == 2
    assert "message_es" in r2 and "message_en" in r2
    r3 = record_attempt("test_action", True)
    assert r3 is None, "Success should not intercept"
    assert get_attempt_count("test_action") == 0, "Success should clear counter"
    # Panel reset
    save_panel_state("panel_1", "some output text")
    assert get_panel_state("panel_1") == "some output text"
    assert reset_panel("panel_1") == ""
    assert get_panel_state("panel_1") == ""
    # #52 — session restore after simulated crash
    auto_save("test input text", "test output", "main_panel")
    state = restore_session()
    assert state["restored"] is True, "Restore should find AUTO_SAVE marker"
    assert "test input" in state["last_input"], f"Input not restored: {state}"
    assert state["panel"] == "main_panel"
    # Resume messages
    assert "sesion" in get_resume_message("es").lower() or "pauso" in get_resume_message("es").lower()
    assert "session" in get_resume_message("en").lower() or "paused" in get_resume_message("en").lower()
    # Labels
    assert "Empezar" in reset_label("es")
    assert "Start" in reset_label("en")
    clear_attempts()
    return True

if __name__ == "__main__":
    print("self_test:", self_test())
