"""first_screen.py — Conversational entry point for OpenClay.

On launch, loads BRAIN.md + SESSION.md silently, greets the user with
context from memory, shows 2-3 predicted next actions, checks for
unfinished work in ~/Desktop/OpenClay Output/, and routes plain-language
input to the correct module. No slash commands needed.

Entire launch sequence targets under 3 seconds.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = Path.home() / "Desktop" / "OpenClay Output"


# ── Helpers ──────────────────────────────────────────────────────────

def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _hour_greeting() -> str:
    h = datetime.now().hour
    if h < 12:
        return "Good morning"
    if h < 17:
        return "Good afternoon"
    return "Good evening"


# ── Unfinished work + watched folders ────────────────────────────────

def check_unfinished() -> list[str]:
    """Check ~/Desktop/OpenClay Output/ for files modified in last 24h."""
    if not OUTPUT_DIR.exists():
        return []
    cutoff = time.time() - 86400
    recent = []
    for f in OUTPUT_DIR.iterdir():
        if f.is_file() and f.stat().st_mtime > cutoff:
            recent.append(f.name)
    return sorted(recent)[:5]


def check_new_papers() -> list[str]:
    """Check raw/ for new files added in last 24h."""
    raw_dir = BASE_DIR / "raw"
    if not raw_dir.exists():
        return []
    cutoff = time.time() - 86400
    new_files = []
    for f in raw_dir.rglob("*"):
        if f.is_file() and f.stat().st_mtime > cutoff:
            new_files.append(f.name)
    return sorted(new_files)[:10]


# ── Memory loader ────────────────────────────────────────────────────

def load_memory() -> dict:
    """Load BRAIN.md + SESSION.md. Returns parsed context dict."""
    brain = _read(BASE_DIR / "BRAIN.md")
    session = _read(BASE_DIR / "SESSION.md")
    return {
        "brain": brain,
        "session": session,
        "user_name": _extract_user_name(brain),
        "last_task": _extract_last_task(session, brain),
        "unfinished": check_unfinished(),
        "new_files": check_new_papers(),
    }


def _extract_user_name(brain: str) -> str:
    """Pull user name from BRAIN.md. Falls back to empty string."""
    for line in brain.splitlines():
        # Match "- Name: Frank" or "- User: Frank" patterns
        m = re.match(r"^-\s*(?:Name|User|name|user)\s*:\s*(.+)", line)
        if m:
            val = m.group(1).strip()
            # Skip generic descriptions, only return actual names
            if val and len(val.split()) <= 3 and not any(
                w in val.lower() for w in ("builder", "creator", "archetype",
                                            "solo", "profile", "values")
            ):
                return val
    return ""


def _extract_last_task(session: str, brain: str) -> str:
    """Find the most recent task entry from SESSION or BRAIN."""
    # Check session first (most recent)
    for text in (session, brain):
        lines = text.strip().splitlines()
        for line in reversed(lines):
            m = re.match(
                r"^-\s*\[[\d\-\s:]+\]\s*(.+?)(?:\s*→.*)?$", line.strip()
            )
            if m:
                task = m.group(1).strip()
                # Skip test/compress artifacts from self_test
                if not task.startswith("compress_test") and task != "test_task_alpha":
                    return task
    return ""


# ── Greeting builder ─────────────────────────────────────────────────

def build_greeting(memory: dict | None = None) -> str:
    """Build a personalized greeting from loaded memory.

    Format: time-of-day greeting + name + last task context + suggestions.
    """
    if memory is None:
        memory = load_memory()

    parts = []

    # Greeting line
    greeting = _hour_greeting()
    name = memory.get("user_name", "")
    if name:
        parts.append(f"{greeting}, {name}.")
    else:
        parts.append(f"{greeting}.")

    # Unfinished work alert
    unfinished = memory.get("unfinished", [])
    if unfinished:
        parts.append(f"You left unfinished: {unfinished[0]}. Continue?")

    # New files in watched folders
    new_files = memory.get("new_files", [])
    if new_files:
        parts.append(f"Found {len(new_files)} new file(s) in your papers folder. "
                     f"Analyze them now?")

    # Last task context
    last = memory.get("last_task", "")
    if last and not unfinished:
        parts.append(f"Last time you were working on: {last}")

    # Predicted next actions (as actionable items)
    try:
        from predict_engine import predict
        suggestions = predict()
        if suggestions:
            parts.append("")
            parts.append("Suggested next steps:")
            for i, s in enumerate(suggestions, 1):
                parts.append(f"  [{i}] {s}")
    except Exception:
        pass

    parts.append("")
    parts.append("What are we working on?")

    return "\n".join(parts)


# ── Intent routing ───────────────────────────────────────────────────

# Route patterns: (intent_name, patterns, target_module, target_function)
_ROUTES: list[tuple[str, list[str], str, str]] = [
    ("tweet", [
        r"\b(?:post|send|write)\s+(?:a\s+)?(?:\w+\s+)*tweet\b",
        r"\btweet\s+(that|about|saying|on|something)\b",
        r"^tweet\s+", r"^post\s+(?:about|something|this)\b",
    ], "panel", "_detect_intent"),
    ("wiki_init", [
        r"\b(?:build|create|init(?:ialize)?|setup)\s+(?:my\s+)?wiki\b",
    ], "wiki_engine", "wiki_init"),
    ("wiki_ingest", [
        r"\bingest\s+", r"\badd\s+to\s+wiki\b", r"\bimport\s+(?:into\s+wiki)?\b",
    ], "wiki_engine", "build_ingest_prompt"),
    ("wiki_query", [
        r"\bquery\s*:", r"\bwiki\s*:", r"\bsearch\s+(?:my\s+)?wiki\b",
        r"\bwhat\s+does\s+(?:my\s+)?wiki\s+(?:say|know)\b",
    ], "wiki_engine", "build_query_prompt"),
    ("wiki_lint", [
        r"^lint\b", r"^check\s+wiki\b", r"\bwiki\s+health\b",
    ], "wiki_engine", "build_lint_prompt"),
    ("clean", [
        r"\bclean\b", r"\bstorage\b", r"\bdisk\s+(?:usage|space)\b",
        r"\brotate\s+logs?\b",
    ], "panel", "_clean"),
    ("summarize", [
        r"\bsummariz\w+\b", r"\bsummary\b", r"\boverview\b",
    ], "agent_backend", "generate"),
    ("plan", [
        r"\bplan\s+(?:my\s+)?(?:day|today|week)\b", r"\bhelp\s+me\s+plan\b",
        r"\borganize\b", r"\bschedule\b",
    ], "agent_backend", "generate"),
    ("test", [
        r"\brun\s+(?:all\s+)?(?:self[_\s]?)?tests?\b", r"\bself[_\s]?test\b",
    ], "watchdog", "run"),
    ("approve", [r"^approve\s+"], "permissions", "approve"),
    ("deny", [r"^deny\s+"], "permissions", "deny"),
]

# Questions for unclear intents
_CLARIFY = (
    "I'm not sure what you'd like to do. Could you tell me: "
    "are you looking to **write something**, **organize files**, "
    "**search your wiki**, or **something else**?"
)


def route_input(text: str) -> dict:
    """Route plain-language input to the correct module.

    Returns: {intent, module, function, args, clarify}
    """
    low = text.lower().strip()
    if not low:
        return {"intent": "empty", "module": None, "function": None,
                "args": "", "clarify": None}

    for intent, patterns, module, func in _ROUTES:
        for pat in patterns:
            m = re.search(pat, low)
            if m:
                # Extract the meaningful part after the command pattern
                after = text[m.end():].strip().lstrip(":\"'")
                args = after if after else text
                return {"intent": intent, "module": module,
                        "function": func, "args": args, "clarify": None}

    # Check if it's a very short or vague input
    words = low.split()
    if len(words) <= 2 and not any(
        w in low for w in ("help", "hi", "hello", "hey", "start")
    ):
        return {"intent": "unclear", "module": None, "function": None,
                "args": text, "clarify": _CLARIFY}

    # Default: treat as general task for the agent
    return {"intent": "general", "module": "agent_backend",
            "function": "generate", "args": text, "clarify": None}


# ── Launch sequence ──────────────────────────────────────────────────

def launch() -> str:
    """Full launch sequence: load memory → build greeting → return.

    Designed to complete in under 3 seconds (no LLM calls).
    """
    memory = load_memory()
    return build_greeting(memory)


# ── Self test ────────────────────────────────────────────────────────

def self_test() -> bool:
    """Verify first_screen greeting, routing, memory, and unfinished work."""
    # Memory loads without error
    mem = load_memory()
    assert isinstance(mem, dict), "load_memory must return dict"
    assert "brain" in mem and "session" in mem, "missing memory keys"
    assert "user_name" in mem and "last_task" in mem, "missing parsed keys"
    assert "unfinished" in mem and "new_files" in mem, "missing new keys"
    assert isinstance(mem["unfinished"], list), "unfinished not list"
    assert isinstance(mem["new_files"], list), "new_files not list"

    # Unfinished work detection
    uf = check_unfinished()
    assert isinstance(uf, list), "check_unfinished not list"
    nf = check_new_papers()
    assert isinstance(nf, list), "check_new_papers not list"

    # Greeting builds
    greeting = build_greeting(mem)
    assert isinstance(greeting, str), "greeting must be string"
    assert "working on" in greeting.lower(), "greeting missing prompt"
    assert any(w in greeting for w in ("Good morning", "Good afternoon",
                                        "Good evening")), "missing time greeting"

    # Routing: known intents
    for txt, exp in [("post a tweet about OpenClay", "tweet"), ("build my wiki", "wiki_init"),
                     ("ingest report.md", "wiki_ingest"), ("search my wiki for agents", "wiki_query"),
                     ("run all self tests", "test"), ("help me plan my day", "plan"),
                     ("summarize the project files", "summarize")]:
        assert route_input(txt)["intent"] == exp, f"{exp} route failed"
    assert route_input("explain how the wiki engine works in detail")["intent"] == "general"
    assert route_input("um")["intent"] == "unclear"
    assert route_input("um")["clarify"] is not None
    assert route_input("")["intent"] == "empty"
    # Launch completes
    assert isinstance(launch(), str) and len(launch()) > 0, "launch failed"
    return True
