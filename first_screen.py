"""first_screen.py — Conversational entry point for OpenClay.
Loads memory, greets with context, shows predictions, routes input.
Trust onboarding on first launch. Under 3 seconds, no LLM calls.
"""
from __future__ import annotations
import re, time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = Path.home() / "Desktop" / "OpenClay Output"

def _read(p: Path) -> str: return p.read_text(encoding="utf-8") if p.exists() else ""
def _now() -> str: return datetime.now().strftime("%Y-%m-%d %H:%M")
def _hour_greeting() -> str:
    h = datetime.now().hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"

# ── Unfinished work + watched folders ────────────────────────────────

def check_unfinished() -> list[str]:
    if not OUTPUT_DIR.exists(): return []
    cutoff = time.time() - 86400
    return sorted([f.name for f in OUTPUT_DIR.iterdir() if f.is_file() and f.stat().st_mtime > cutoff])[:5]

def check_new_papers() -> list[str]:
    raw_dir = BASE_DIR / "raw"
    if not raw_dir.exists(): return []
    cutoff = time.time() - 86400
    return sorted([f.name for f in raw_dir.rglob("*") if f.is_file() and f.stat().st_mtime > cutoff])[:10]

# ── Memory loader ────────────────────────────────────────────────────

def load_memory() -> dict:
    brain, session = _read(BASE_DIR / "BRAIN.md"), _read(BASE_DIR / "SESSION.md")
    return {"brain": brain, "session": session, "user_name": _extract_user_name(brain),
            "last_task": _extract_last_task(session, brain),
            "unfinished": check_unfinished(), "new_files": check_new_papers()}

def _extract_user_name(brain: str) -> str:
    for line in brain.splitlines():
        m = re.match(r"^-\s*(?:Name|User|name|user)\s*:\s*(.+)", line)
        if m:
            val = m.group(1).strip()
            if val and len(val.split()) <= 3 and not any(
                w in val.lower() for w in ("builder", "creator", "archetype", "solo", "profile", "values")):
                return val
    return ""

def _extract_last_task(session: str, brain: str) -> str:
    for text in (session, brain):
        for line in reversed(text.strip().splitlines()):
            m = re.match(r"^-\s*\[[\d\-\s:]+\]\s*(.+?)(?:\s*→.*)?$", line.strip())
            if m:
                task = m.group(1).strip()
                if not task.startswith("compress_test") and task != "test_task_alpha": return task
    return ""

# ── Greeting builder ─────────────────────────────────────────────────

def build_greeting(memory: dict | None = None) -> str:
    if memory is None: memory = load_memory()
    parts = []
    name = memory.get("user_name", "")
    parts.append(f"{_hour_greeting()}, {name}." if name else f"{_hour_greeting()}.")
    unfinished = memory.get("unfinished", [])
    if unfinished: parts.append(f"You left unfinished: {unfinished[0]}. Continue?")
    new_files = memory.get("new_files", [])
    if new_files: parts.append(f"Found {len(new_files)} new file(s) in your papers folder. Analyze them now?")
    last = memory.get("last_task", "")
    if last and not unfinished: parts.append(f"Last time you were working on: {last}")
    try:
        from predict_engine import predict
        suggestions = predict()
        if suggestions:
            parts.append("\nSuggested next steps:")
            for i, s in enumerate(suggestions, 1): parts.append(f"  [{i}] {s}")
    except Exception: pass
    parts.append("\nWhat are we working on?")
    return "\n".join(parts)

# ── Intent routing ───────────────────────────────────────────────────

_ROUTES: list[tuple[str, list[str], str, str]] = [
    ("tweet", [r"\b(?:post|send|write)\s+(?:a\s+)?(?:\w+\s+)*tweet\b", r"\btweet\s+(that|about|saying|on|something)\b",
               r"^tweet\s+", r"^post\s+(?:about|something|this)\b"], "panel", "_detect_intent"),
    ("wiki_init", [r"\b(?:build|create|init(?:ialize)?|setup)\s+(?:my\s+)?wiki\b"], "wiki_engine", "wiki_init"),
    ("wiki_ingest", [r"\bingest\s+", r"\badd\s+to\s+wiki\b", r"\bimport\s+(?:into\s+wiki)?\b"], "wiki_engine", "build_ingest_prompt"),
    ("wiki_query", [r"\bquery\s*:", r"\bwiki\s*:", r"\bsearch\s+(?:my\s+)?wiki\b",
                    r"\bwhat\s+does\s+(?:my\s+)?wiki\s+(?:say|know)\b"], "wiki_engine", "build_query_prompt"),
    ("wiki_lint", [r"^lint\b", r"^check\s+wiki\b", r"\bwiki\s+health\b"], "wiki_engine", "build_lint_prompt"),
    ("clean", [r"\bclean\b", r"\bstorage\b", r"\bdisk\s+(?:usage|space)\b", r"\brotate\s+logs?\b"], "panel", "_clean"),
    ("summarize", [r"\bsummariz\w+\b", r"\bsummary\b", r"\boverview\b"], "agent_backend", "generate"),
    ("plan", [r"\bplan\s+(?:my\s+)?(?:day|today|week)\b", r"\bhelp\s+me\s+plan\b", r"\borganize\b", r"\bschedule\b"], "agent_backend", "generate"),
    ("test", [r"\brun\s+(?:all\s+)?(?:self[_\s]?)?tests?\b", r"\bself[_\s]?test\b"], "watchdog", "run"),
    ("approve", [r"^approve\s+"], "permissions", "approve"),
    ("deny", [r"^deny\s+"], "permissions", "deny"),
]
_CLARIFY = ("I'm not sure what you'd like to do. Could you tell me: "
            "are you looking to **write something**, **organize files**, **search your wiki**, or **something else**?")

def route_input(text: str) -> dict:
    low = text.lower().strip()
    if not low: return {"intent": "empty", "module": None, "function": None, "args": "", "clarify": None}
    for intent, patterns, module, func in _ROUTES:
        for pat in patterns:
            m = re.search(pat, low)
            if m:
                after = text[m.end():].strip().lstrip(":\"'")
                return {"intent": intent, "module": module, "function": func, "args": after or text, "clarify": None}
    words = low.split()
    if len(words) <= 2 and not any(w in low for w in ("help", "hi", "hello", "hey", "start")):
        return {"intent": "unclear", "module": None, "function": None, "args": text, "clarify": _CLARIFY}
    return {"intent": "general", "module": "agent_backend", "function": "generate", "args": text, "clarify": None}

# ── Trust onboarding (first launch only) ────────────────────────────

_ONBOARD_SCREENS = [
    {"es": "Bienvenido a OpenClay.\nAntes de empezar, queremos ser honestos contigo.",
     "en": "Welcome to OpenClay.\nBefore we begin, we want to be honest with you."},
    {"es": ("✓ Todo queda en tu computadora.\n✓ Nada va a internet.\n✓ Puedes apagarlo cuando quieras.\n\n"
            "A diferencia de ChatGPT u otras herramientas en la nube:\n"
            "✓ Tus archivos no entrenan ningun modelo de IA.\n"
            "✓ Tu empleador no ve lo que haces con OpenClay.\n"
            "✓ OpenClay recuerda tu trabajo — sin empezar de cero."),
     "en": ("✓ Everything stays on your computer.\n✓ Nothing goes to the internet.\n✓ You can turn it off anytime.\n\n"
            "Unlike ChatGPT or other cloud tools:\n"
            "✓ Your files never train any AI model.\n"
            "✓ Your employer cannot see what you do with OpenClay.\n"
            "✓ OpenClay remembers your work — no starting from zero.")},
    {"es": "Empezamos con permisos minimos.\nTe pedimos permiso antes de hacer algo nuevo.\nTu decides que puede y que no puede hacer OpenClay.",
     "en": "We start with minimal permissions.\nWe ask before doing anything new.\nYou decide what OpenClay can and cannot do."},
    {"es": "Como te llamas? (opcional)\nCual es tu area de trabajo? (opcional)",
     "en": "What's your name? (optional)\nWhat's your field of work? (optional)"},
]

def needs_onboarding() -> bool:
    brain = _read(BASE_DIR / "BRAIN.md")
    return "## Identity" not in brain and (not brain.strip() or len(brain.strip()) < 30)

def get_onboard_screen(index: int, lang: str = "en") -> str:
    if 0 <= index < len(_ONBOARD_SCREENS): return _ONBOARD_SCREENS[index].get(lang, _ONBOARD_SCREENS[index]["en"])
    return ""

def complete_onboarding(name: str = "", field: str = ""):
    brain_path = BASE_DIR / "BRAIN.md"
    brain = _read(brain_path)
    if "## Identity" not in brain:
        entry = "\n## Identity\n"
        if name.strip(): entry += f"- User name: {name.strip()}\n"
        if field.strip(): entry += f"- Field: {field.strip()}\n"
        with open(brain_path, "a", encoding="utf-8") as f: f.write(entry)

# ── Launch sequence ──────────────────────────────────────────────────

def launch() -> str:
    memory = load_memory()
    return build_greeting(memory)

# ── Self test ────────────────────────────────────────────────────────

def self_test() -> bool:
    mem = load_memory()
    assert isinstance(mem, dict) and "brain" in mem and "session" in mem
    assert "user_name" in mem and "last_task" in mem and "unfinished" in mem and "new_files" in mem
    assert isinstance(check_unfinished(), list) and isinstance(check_new_papers(), list)
    greeting = build_greeting(mem)
    assert isinstance(greeting, str) and "working on" in greeting.lower()
    assert any(w in greeting for w in ("Good morning", "Good afternoon", "Good evening"))
    for txt, exp in [("post a tweet about OpenClay", "tweet"), ("build my wiki", "wiki_init"),
                     ("ingest report.md", "wiki_ingest"), ("search my wiki for agents", "wiki_query"),
                     ("run all self tests", "test"), ("help me plan my day", "plan"),
                     ("summarize the project files", "summarize")]:
        assert route_input(txt)["intent"] == exp, f"{exp} route failed"
    assert route_input("explain how the wiki engine works in detail")["intent"] == "general"
    assert route_input("um")["intent"] == "unclear" and route_input("um")["clarify"] is not None
    assert route_input("")["intent"] == "empty"
    assert isinstance(launch(), str) and len(launch()) > 0
    # Onboarding
    assert callable(needs_onboarding) and callable(get_onboard_screen) and callable(complete_onboarding)
    for i in range(4):
        s = get_onboard_screen(i, "es")
        assert isinstance(s, str) and len(s) > 10, f"screen {i} empty"
    assert "ChatGPT" in get_onboard_screen(1, "es"), "Part P missing from screen 2"
    return True
