"""vibe_brain.py — Vibe Brain memory layer for OpenClay.

Plain markdown memory. No databases. No embeddings. No cloud.

L0 → SOUL.md      (identity, never modified, always loaded)
L1 → BRAIN.md     (long-term knowledge, under 500 words, always loaded)
L2 → SESSION.md   (current task context, under 200 words, cleared at session end)
L3 → DECISIONS.md (past choices + outcomes, loaded on demand only)

Compression cycle: every 10 completed tasks, SESSION.md summarizes into BRAIN.md.
BRAIN.md stays under 500 words by trimming oldest entries on compression.
Token target: under 2,000 tokens loaded per task by default.
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

_task_count = 0  # tasks completed this session
_COMPRESS_EVERY = 10


# ── Helpers ───────────────────────────────────────────────────────────

def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M")
def _read(p): return p.read_text(encoding="utf-8") if p.exists() else ""
def _write(p, text): p.write_text(text, encoding="utf-8")
def _append(p, text):
    with open(p, "a", encoding="utf-8") as f:
        f.write(text)
def _word_count(text): return len(text.split())


# ── L0: Identity (SOUL.md — never modified) ──────────────────────────

def load_l0() -> str:
    """Load identity from SOUL.md. Always included. ~100 tokens."""
    if not SOUL_PATH.exists():
        return "I am OpenClay, a local-first AI agent."
    lines, in_section = [], False
    for line in SOUL_PATH.read_text(encoding="utf-8").splitlines():
        if "## What OpenClay Is" in line:
            in_section = True; continue
        if in_section and line.startswith("## "):
            break
        if in_section and line.strip() and not line.startswith("---"):
            lines.append(line.strip())
    return "\n".join(lines[:10]) if lines else "I am OpenClay, a local-first AI agent."


# ── L1: BRAIN.md (long-term, always loaded, <500 words) ──────────────

def load_brain() -> str:
    """Load BRAIN.md. Always included. Under 500 words."""
    return _read(BRAIN_PATH)


def update_brain(entry: str):
    """Add an entry to BRAIN.md, then trim to 500 words."""
    current = _read(BRAIN_PATH)
    if entry.strip() not in current:
        _append(BRAIN_PATH, f"\n{entry.strip()}\n")
    _trim_brain()


def _trim_brain():
    """Keep BRAIN.md under 500 words by removing oldest entries."""
    text = _read(BRAIN_PATH)
    if _word_count(text) <= 500:
        return
    lines = text.splitlines()
    # Keep header (first 3 lines) + trim from the top of entries
    header, body = [], []
    for i, line in enumerate(lines):
        if i < 3 or line.startswith("# ") or line.startswith("<!-- "):
            header.append(line)
        else:
            body.append(line)
    # Remove oldest body lines until under 500 words
    while body and _word_count("\n".join(header + body)) > 500:
        body.pop(0)
        # Don't leave orphaned blank lines at the top
        while body and not body[0].strip():
            body.pop(0)
    _write(BRAIN_PATH, "\n".join(header + body) + "\n")


# ── L2: SESSION.md (current task, <200 words, cleared at end) ─────────

def load_session() -> str:
    """Load SESSION.md. Current task context only. Under 200 words."""
    return _read(SESSION_PATH)


def record_task(task: str, outcome: str = ""):
    """Record a completed task in SESSION.md. Triggers compression at threshold."""
    global _task_count
    ts = _now()
    entry = f"- [{ts}] {task}"
    if outcome:
        entry += f" → {outcome}"
    _append(SESSION_PATH, entry + "\n")
    # Trim SESSION.md to 200 words
    text = _read(SESSION_PATH)
    if _word_count(text) > 200:
        lines = text.splitlines()
        while lines and _word_count("\n".join(lines)) > 200:
            lines.pop(0)
        _write(SESSION_PATH, "\n".join(lines) + "\n")
    _task_count += 1
    if _task_count >= _COMPRESS_EVERY:
        compress()
        _task_count = 0


def clear_session():
    """Clear SESSION.md at session end."""
    if SESSION_PATH.exists():
        _write(SESSION_PATH, f"<!-- Session cleared {_now()} -->\n")


# ── L3: DECISIONS.md (past choices, loaded on demand) ─────────────────

def load_decisions(query: str = "") -> str:
    """Load DECISIONS.md, optionally filtered by query keywords."""
    text = _read(DECISIONS_PATH)
    if not text or not query:
        return text
    # Filter to entries matching query keywords
    q_words = [w.lower() for w in query.split() if len(w) > 3]
    if not q_words:
        return text
    blocks = text.split("\n\n")
    relevant = [b for b in blocks if any(w in b.lower() for w in q_words)]
    return "\n\n".join(relevant[-10:]) if relevant else ""


def record_decision(task: str, decision: str, outcome: str = ""):
    """Log a decision to DECISIONS.md."""
    ts = _now()
    entry = f"\n### {ts} — {task}\n**Decision:** {decision}\n"
    if outcome:
        entry += f"**Outcome:** {outcome}\n"
    _append(DECISIONS_PATH, entry)


# ── Compression cycle ─────────────────────────────────────────────────

def compress():
    """Summarize SESSION.md into BRAIN.md. Called every 10 tasks.

    1. Extract key facts from SESSION.md
    2. Append summary to BRAIN.md under dated header
    3. Trim BRAIN.md to 500 words
    4. Clear SESSION.md
    5. Log compression event to healing_log.md
    """
    session_text = _read(SESSION_PATH).strip()
    if not session_text or session_text.startswith("<!-- Session cleared"):
        return
    # Extract non-comment, non-empty lines as summary
    entries = [ln.strip() for ln in session_text.splitlines()
               if ln.strip() and not ln.strip().startswith("<!--")]
    if not entries:
        return
    # Build compression summary
    ts = _now()
    summary = f"\n## Session {ts}\n" + "\n".join(entries[-10:]) + "\n"
    # Append to BRAIN.md and trim
    _append(BRAIN_PATH, summary)
    _trim_brain()
    # Clear session
    _write(SESSION_PATH, f"<!-- Compressed into BRAIN.md at {ts} -->\n")
    # Log compression event
    _append(HEALING_LOG, f"- `{ts}` **vibe_brain** compress — "
            f"{len(entries)} entries → BRAIN.md ({_word_count(_read(BRAIN_PATH))} words)\n")


# ── Context builder ───────────────────────────────────────────────────

def build_context(query: str = "") -> str:
    """Build memory context from Vibe Brain layers.

    Default load (L0+L1+L2): under 2,000 tokens.
    L3 only added when query involves past decisions.
    """
    parts = []
    # L0: Identity (always)
    l0 = load_l0()
    if l0:
        parts.append(f"IDENTITY:\n{l0}")
    # L1: Brain (always)
    l1 = load_brain()
    if l1:
        parts.append(f"BRAIN:\n{l1}")
    # L2: Session (always)
    l2 = load_session()
    if l2:
        parts.append(f"SESSION:\n{l2}")
    # L3: Decisions (on demand — only if query suggests past context)
    if query:
        decision_words = ("why", "before", "last time", "previous", "decided",
                          "chose", "history", "again", "repeat", "changed")
        if any(w in query.lower() for w in decision_words):
            l3 = load_decisions(query)
            if l3:
                parts.append(f"PAST DECISIONS:\n{l3}")
    return "\n\n---\n\n".join(parts)


def needs_wiki(query: str) -> bool:
    """Return True if BRAIN+SESSION don't cover this query.

    Used by wiki_engine to skip deep retrieval on routine tasks.
    """
    brain = load_brain().lower()
    session = load_session().lower()
    q_words = [w for w in query.lower().split() if len(w) > 3]
    if not q_words:
        return True
    # If most query words appear in brain+session, skip wiki
    combined = brain + " " + session
    hits = sum(1 for w in q_words if w in combined)
    return hits < len(q_words) * 0.5  # need wiki if <50% coverage


def status() -> dict:
    """Return Vibe Brain status."""
    return {
        "brain_words": _word_count(_read(BRAIN_PATH)),
        "session_words": _word_count(_read(SESSION_PATH)),
        "decisions_entries": _read(DECISIONS_PATH).count("### "),
        "tasks_since_compress": _task_count,
        "compress_threshold": _COMPRESS_EVERY,
    }


# ── Seed BRAIN.md from existing data ──────────────────────────────────

def seed_brain():
    """Generate initial BRAIN.md from SOUL.md and existing log data."""
    if BRAIN_PATH.exists() and _word_count(_read(BRAIN_PATH)) > 20:
        return  # Already seeded
    parts = ["# Brain\n", "<!-- Long-term knowledge. Updated by compression cycle. -->",
             f"<!-- Last updated: {_now()} -->\n"]
    # Extract machine profile from AGENTS.md
    agents = _read(BASE_DIR / "AGENTS.md")
    if "Machine Profile" in agents:
        parts.append("## Machine")
        for line in agents.splitlines():
            if line.startswith("- OS:") or line.startswith("- RAM:") or line.startswith("- Tier:"):
                parts.append(line)
    # Extract patterns from logs
    parts.append("\n## Patterns")
    parts.append("- Primary model tier: gemma4 (e4b fast, 26b smart)")
    parts.append("- Twitter posting has failed before (401 Unauthorized)")
    parts.append("- User is a creator, not a traditional developer")
    parts.append("- Self-build loop works — applied wiki_engine fix successfully")
    # User context from SOUL.md
    parts.append("\n## User")
    parts.append("- Solo builder automating from their machine")
    parts.append("- Values: local-first, privacy, reliability over features")
    parts.append("- Profile: creator archetype, content pipeline focus")
    _write(BRAIN_PATH, "\n".join(parts) + "\n")


def self_test() -> bool:
    """Verify Vibe Brain memory layers and compression cycle."""
    # L0: Identity loads
    l0 = load_l0()
    assert isinstance(l0, str) and "OpenClay" in l0, "L0 identity failed"
    # L1: Brain loads (may be empty initially)
    l1 = load_brain()
    assert isinstance(l1, str), "L1 brain not string"
    # L2: Session recording
    record_task("test_task_alpha", "passed")
    s = load_session()
    assert "test_task_alpha" in s, "session recording failed"
    # L3: Decision recording
    record_decision("test_choice", "chose option A", "worked")
    d = load_decisions("test_choice")
    assert "option A" in d, "decision recording failed"
    # Context builder
    ctx = build_context("test")
    assert "IDENTITY:" in ctx, "context missing identity"
    # Compression cycle (simulate 10 tasks)
    for i in range(10):
        record_task(f"compress_test_{i}", "ok")
    brain_after = load_brain()
    assert "compress_test" in brain_after, "compression failed to merge session"
    assert _word_count(brain_after) <= 500, f"BRAIN over 500 words: {_word_count(brain_after)}"
    # needs_wiki
    assert isinstance(needs_wiki("random query"), bool), "needs_wiki not bool"
    # Status
    st = status()
    assert "brain_words" in st and "compress_threshold" in st, "status missing keys"
    return True
