"""vibe_brain.py — Vibe Brain memory layer for OpenClay.
Plain markdown memory. No databases. No embeddings. No cloud.
L0→SOUL.md (identity) L1→BRAIN.md (<500w) L2→SESSION.md (<200w) L3→DECISIONS.md (on demand)
Compression: every 10 tasks, SESSION→BRAIN. Idle processing after 10min.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
SOUL_PATH = BASE_DIR / "SOUL.md"
BRAIN_PATH = BASE_DIR / "BRAIN.md"
SESSION_PATH = BASE_DIR / "SESSION.md"
DECISIONS_PATH = BASE_DIR / "DECISIONS.md"
HEALING_LOG = BASE_DIR / "healing_log.md"
BOOT_POLICY = BASE_DIR / "boot_load_policy.md"
_task_count = 0
_COMPRESS_EVERY = 10
_IDLE_MINUTES = 10
_last_activity = None
_idle_thread = None

def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M")
def _read(p): return p.read_text(encoding="utf-8") if p.exists() else ""
def _write(p, text): p.write_text(text, encoding="utf-8")
def _append(p, text):
    with open(p, "a", encoding="utf-8") as f: f.write(text)
def _word_count(text): return len(text.split())

# ── Boot load (3 files only) ────────────────────────────────────────

def boot_load() -> dict:
    """Cold boot: load exactly 3 files — SOUL.md, BRAIN.md, boot_load_policy.md."""
    return {"soul": _read(SOUL_PATH), "brain": _read(BRAIN_PATH),
            "policy": _read(BOOT_POLICY), "files_loaded": ["SOUL.md", "BRAIN.md", "boot_load_policy.md"]}

def load_on_demand(task_type: str) -> dict:
    """Load context files for a specific task type (on demand, not at boot)."""
    ctx_dir = BASE_DIR / "context"
    mapping = {"clinical": "clinical_context.md", "research": "research_context.md",
               "grant": "grant_context.md", "billing": "billing_context.md",
               "veterinary": "vet_context.md"}
    extra = {}
    fname = mapping.get(task_type, "")
    if fname and (ctx_dir / fname).exists(): extra["task_context"] = _read(ctx_dir / fname)
    if task_type in ("clinical", "research", "grant", "billing", "veterinary", "review"):
        extra["decisions"] = _read(DECISIONS_PATH)
    if task_type in ("admin", "general", "review"): extra["session"] = _read(SESSION_PATH)
    return extra

# ── L0: Identity ────────────────────────────────────────────────────

def load_l0() -> str:
    if not SOUL_PATH.exists(): return "I am OpenClay, a local-first AI agent."
    lines, in_s = [], False
    for line in SOUL_PATH.read_text(encoding="utf-8").splitlines():
        if "## What OpenClay Is" in line: in_s = True; continue
        if in_s and line.startswith("## "): break
        if in_s and line.strip() and not line.startswith("---"): lines.append(line.strip())
    return "\n".join(lines[:10]) if lines else "I am OpenClay, a local-first AI agent."

# ── L1: BRAIN.md ────────────────────────────────────────────────────

def load_brain() -> str: return _read(BRAIN_PATH)

def update_brain(entry: str):
    current = _read(BRAIN_PATH)
    if entry.strip() not in current: _append(BRAIN_PATH, f"\n{entry.strip()}\n")
    _trim_brain()

def _trim_brain():
    text = _read(BRAIN_PATH)
    if _word_count(text) <= 500: return
    lines = text.splitlines()
    header = [l for i, l in enumerate(lines) if i < 3 or l.startswith("# ") or l.startswith("<!-- ")]
    body = [l for i, l in enumerate(lines) if not (i < 3 or l.startswith("# ") or l.startswith("<!-- "))]
    while body and _word_count("\n".join(header + body)) > 500:
        body.pop(0)
        while body and not body[0].strip(): body.pop(0)
    _write(BRAIN_PATH, "\n".join(header + body) + "\n")

# ── L2: SESSION.md ──────────────────────────────────────────────────

def load_session() -> str: return _read(SESSION_PATH)

def record_task(task: str, outcome: str = ""):
    global _task_count
    _touch_activity()
    entry = f"- [{_now()}] {task}" + (f" → {outcome}" if outcome else "")
    _append(SESSION_PATH, entry + "\n")
    text = _read(SESSION_PATH)
    if _word_count(text) > 200:
        lines = text.splitlines()
        while lines and _word_count("\n".join(lines)) > 200: lines.pop(0)
        _write(SESSION_PATH, "\n".join(lines) + "\n")
    _task_count += 1
    if _task_count >= _COMPRESS_EVERY: compress(); _task_count = 0

def clear_session():
    if SESSION_PATH.exists(): _write(SESSION_PATH, f"<!-- Session cleared {_now()} -->\n")

# ── L3: DECISIONS.md ────────────────────────────────────────────────

def load_decisions(query: str = "") -> str:
    text = _read(DECISIONS_PATH)
    if not text or not query: return text
    q_words = [w.lower() for w in query.split() if len(w) > 3]
    if not q_words: return text
    blocks = text.split("\n\n")
    relevant = [b for b in blocks if any(w in b.lower() for w in q_words)]
    return "\n\n".join(relevant[-10:]) if relevant else ""

def record_decision(task: str, decision: str, outcome: str = ""):
    entry = f"\n### {_now()} — {task}\n**Decision:** {decision}\n"
    if outcome: entry += f"**Outcome:** {outcome}\n"
    _append(DECISIONS_PATH, entry)

# ── Compression cycle ────────────────────────────────────────────────

def compress():
    session_text = _read(SESSION_PATH).strip()
    if not session_text or session_text.startswith("<!-- Session cleared"): return
    entries = [ln.strip() for ln in session_text.splitlines()
               if ln.strip() and not ln.strip().startswith("<!--")]
    if not entries: return
    ts = _now()
    _append(BRAIN_PATH, f"\n## Session {ts}\n" + "\n".join(entries[-10:]) + "\n")
    _trim_brain()
    _write(SESSION_PATH, f"<!-- Compressed into BRAIN.md at {ts} -->\n")
    _append(HEALING_LOG, f"- `{ts}` **vibe_brain** compress — "
            f"{len(entries)} entries → BRAIN.md ({_word_count(_read(BRAIN_PATH))} words)\n")

# ── Context builder ──────────────────────────────────────────────────

def build_context(query: str = "") -> str:
    parts = []
    l0 = load_l0()
    if l0: parts.append(f"IDENTITY:\n{l0}")
    l1 = load_brain()
    if l1: parts.append(f"BRAIN:\n{l1}")
    l2 = load_session()
    if l2: parts.append(f"SESSION:\n{l2}")
    if query:
        dw = ("why", "before", "last time", "previous", "decided", "chose", "history", "again", "repeat", "changed")
        if any(w in query.lower() for w in dw):
            l3 = load_decisions(query)
            if l3: parts.append(f"PAST DECISIONS:\n{l3}")
    return "\n\n---\n\n".join(parts)

def needs_wiki(query: str) -> bool:
    combined = (load_brain() + " " + load_session()).lower()
    q_words = [w for w in query.lower().split() if len(w) > 3]
    if not q_words: return True
    hits = sum(1 for w in q_words if w in combined)
    return hits < len(q_words) * 0.5

def status() -> dict:
    return {"brain_words": _word_count(_read(BRAIN_PATH)), "session_words": _word_count(_read(SESSION_PATH)),
            "decisions_entries": _read(DECISIONS_PATH).count("### "),
            "tasks_since_compress": _task_count, "compress_threshold": _COMPRESS_EVERY}

# ── Seed BRAIN.md ────────────────────────────────────────────────────

def seed_brain():
    if BRAIN_PATH.exists() and _word_count(_read(BRAIN_PATH)) > 20: return
    parts = ["# Brain\n", "<!-- Long-term knowledge. Updated by compression cycle. -->",
             f"<!-- Last updated: {_now()} -->\n"]
    agents = _read(BASE_DIR / "AGENTS.md")
    if "Machine Profile" in agents:
        parts.append("## Machine")
        for line in agents.splitlines():
            if line.startswith("- OS:") or line.startswith("- RAM:") or line.startswith("- Tier:"):
                parts.append(line)
    parts += ["\n## Patterns", "- Primary model tier: gemma4 (e4b fast, 26b smart)",
              "- Self-build loop works — applied wiki_engine fix successfully",
              "\n## User", "- Solo builder automating from their machine",
              "- Values: local-first, privacy, reliability over features",
              "- Profile: creator archetype, content pipeline focus"]
    _write(BRAIN_PATH, "\n".join(parts) + "\n")

# ── Idle-time auto processing ────────────────────────────────────────

def _touch_activity():
    global _last_activity; _last_activity = datetime.now()

def minutes_idle() -> float:
    if _last_activity is None: return 0
    return (datetime.now() - _last_activity).total_seconds() / 60

def idle_process() -> dict:
    """Process files + compress after 10min idle."""
    if minutes_idle() < _IDLE_MINUTES: return {"actions": [], "files_processed": 0}
    actions, files_processed = [], 0
    if _task_count >= _COMPRESS_EVERY: compress(); actions.append("compression cycle")
    raw_dir = BASE_DIR / "raw"
    if raw_dir.exists():
        import time; cutoff = time.time() - 86400
        new_files = [f for f in raw_dir.rglob("*") if f.is_file()
                     and f.stat().st_mtime > cutoff and f.suffix in (".txt", ".pdf", ".md")]
        if new_files:
            try:
                from biotech_review_agent import extract_fields, _add_to_index
                for f in new_files[:5]:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    if text.strip():
                        extract_fields(text, f.name); _add_to_index(extract_fields(text, f.name), f.name)
                        files_processed += 1
            except Exception: pass
            if files_processed: actions.append(f"analyzed {files_processed} papers")
    load_brain(); load_session(); actions.append("memory ready")
    if actions: _append(HEALING_LOG, f"- `{_now()}` **vibe_brain** Idle: {', '.join(actions)}\n")
    return {"actions": actions, "files_processed": files_processed}

def idle_greeting(lang: str = "en") -> str:
    result = idle_process()
    if not result["actions"]: return ""
    n = result["files_processed"]
    if lang == "es" and n: return f"Mientras esperaba, analice {n} archivos nuevos. Quieres ver el resumen?"
    return f"While waiting, I analyzed {n} new files. Want to see the summary?" if n else ""

def idle_monitor(check_interval: int = 60):
    """Background thread: checks idle state, processes when idle > 10min."""
    import time
    _touch_activity()
    while True:
        time.sleep(check_interval)
        if minutes_idle() >= _IDLE_MINUTES: idle_process()

def start_idle_monitor():
    """Start the idle monitor in a daemon thread."""
    global _idle_thread
    import threading
    if _idle_thread and _idle_thread.is_alive(): return
    _idle_thread = threading.Thread(target=idle_monitor, args=(60,), daemon=True)
    _idle_thread.start()

# ── Self test ────────────────────────────────────────────────────────

def self_test() -> bool:
    l0 = load_l0()
    assert isinstance(l0, str) and "OpenClay" in l0, "L0 identity failed"
    assert isinstance(load_brain(), str), "L1 brain not string"
    record_task("test_task_alpha", "passed")
    assert "test_task_alpha" in load_session(), "session recording failed"
    record_decision("test_choice", "chose option A", "worked")
    assert "option A" in load_decisions("test_choice"), "decision recording failed"
    ctx = build_context("test")
    assert "IDENTITY:" in ctx, "context missing identity"
    for i in range(10): record_task(f"compress_test_{i}", "ok")
    brain_after = load_brain()
    assert "compress_test" in brain_after, "compression failed"
    assert _word_count(brain_after) <= 500, f"BRAIN over 500 words"
    assert isinstance(needs_wiki("random query"), bool)
    st = status()
    assert "brain_words" in st and "compress_threshold" in st
    assert callable(idle_process) and callable(idle_greeting)
    # #50 — cold boot loads exactly 3 files
    bl = boot_load()
    assert len(bl["files_loaded"]) == 3, f"Boot should load exactly 3 files, got {len(bl['files_loaded'])}"
    assert "SOUL.md" in bl["files_loaded"] and "BRAIN.md" in bl["files_loaded"]
    assert "boot_load_policy.md" in bl["files_loaded"]
    # On-demand loading
    od = load_on_demand("clinical")
    assert isinstance(od, dict)
    od2 = load_on_demand("general")
    assert isinstance(od2, dict)
    # #58 — idle_monitor thread starts without error
    import threading
    start_idle_monitor()
    assert _idle_thread is not None and _idle_thread.is_alive(), "idle_monitor thread should be running"
    # #59 — idle greeting
    ig = idle_greeting("es")
    assert isinstance(ig, str)
    return True
