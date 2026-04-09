"""mem_palace.py — MemPalace 4-level memory architecture for OpenClay.

Integrates github.com/milla-jovovich/mempalace into OpenClay's wiki layer.

L0 → Identity  (SOUL.md core traits, always loaded, ~100 tokens)
L1 → Session   (current task + recent decisions, in-process)
L2 → Recent    (last 7 days of ingested wiki docs)
L3 → Archive   (full wiki, semantic search via ChromaDB, on demand only)

Dependencies: mempalace (chromadb, pyyaml)
Degrades gracefully if mempalace is not installed — falls back to keyword search.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
PALACE_PATH = BASE_DIR / "data" / "palace"
IDENTITY_PATH = BASE_DIR / "SOUL.md"
WIKI_DIR = BASE_DIR / "wiki"

# Session memory (L1) — in-process, not persisted to disk
_session: list[dict] = []
_session_start: float = time.time()

try:
    from mempalace.layers import MemoryStack
    from mempalace.miner import get_collection, add_drawer
    HAS_MEMPALACE = True
except ImportError:
    HAS_MEMPALACE = False


# ── L0: Identity (always loaded) ──────────────────────────────────────

def _extract_soul_identity() -> str:
    """Extract the 'What OpenClay Is' section from SOUL.md."""
    if not IDENTITY_PATH.exists():
        return "I am OpenClay, a local-first AI agent."
    lines, in_section = [], False
    for line in IDENTITY_PATH.read_text(encoding="utf-8").splitlines():
        if "## What OpenClay Is" in line:
            in_section = True; continue
        if in_section and line.startswith("## "):
            break
        if in_section and line.strip() and not line.startswith("---"):
            lines.append(line.strip())
    return "\n".join(lines[:10]) if lines else "I am OpenClay, a local-first AI agent."


def load_l0() -> str:
    """L0: Identity. Always loaded. ~100 tokens from SOUL.md."""
    return _extract_soul_identity()


# ── L1: Session context (in-process) ──────────────────────────────────

def record_session(task: str, decision: str = ""):
    """Record a session event. Kept in memory, not persisted."""
    _session.append({"time": datetime.now().isoformat(),
                     "task": task, "decision": decision})
    while len(_session) > 20:
        _session.pop(0)


def load_l1() -> str:
    """L1: Session context. Current task + recent decisions. ~500 tokens."""
    if not _session:
        return ""
    lines = ["SESSION CONTEXT:"]
    for evt in _session[-10:]:
        line = f"- [{evt['time'][-8:]}] {evt['task']}"
        if evt.get("decision"):
            line += f" → {evt['decision']}"
        lines.append(line)
    return "\n".join(lines)


# ── L2: Recent wiki (last 7 days) ─────────────────────────────────────

def load_l2(days: int = 7) -> str:
    """L2: Recent wiki pages modified in the last N days. ~500 tokens."""
    if not WIKI_DIR.exists():
        return ""
    cutoff = time.time() - days * 86400
    recent = []
    for f in WIKI_DIR.rglob("*.md"):
        try:
            if f.stat().st_mtime >= cutoff:
                content = f.read_text(encoding="utf-8")[:300]
                recent.append((f.stat().st_mtime,
                               f"### {f.relative_to(WIKI_DIR)}\n{content}"))
        except Exception:
            continue
    recent.sort(key=lambda x: x[0], reverse=True)
    return "\n\n".join(text for _, text in recent[:8]) if recent else ""


# ── L3: Deep archive (semantic search) ────────────────────────────────

def search_l3(query: str, n_results: int = 5) -> str:
    """L3: Semantic search across full wiki via MemPalace ChromaDB."""
    if not HAS_MEMPALACE:
        return _fallback_search(query, n_results)
    try:
        _ensure_palace()
        stack = MemoryStack(
            palace_path=str(PALACE_PATH),
            identity_path=str(PALACE_PATH.parent / "identity.txt"),
        )
        results = stack.search(query, n_results=n_results)
        return results if results else _fallback_search(query, n_results)
    except Exception:
        return _fallback_search(query, n_results)


def _fallback_search(query: str, n: int = 5) -> str:
    """Keyword fallback when MemPalace is unavailable."""
    if not WIKI_DIR.exists():
        return ""
    q_words = [w for w in query.lower().split() if len(w) > 3]
    hits = []
    for dname in ("concepts", "entities", "sources", "comparisons", "topics"):
        dpath = WIKI_DIR / dname
        if not dpath.exists():
            continue
        for f in sorted(dpath.glob("*.md")):
            content = f.read_text(encoding="utf-8")
            if (query.lower() in content.lower()
                    or any(w in f.stem.lower() for w in q_words)):
                hits.append(f"### {f.relative_to(WIKI_DIR)}\n{content[:600]}")
            if len(hits) >= n:
                break
    return "\n\n".join(hits) if hits else "_No matching pages._"


# ── Palace management ─────────────────────────────────────────────────

def _ensure_palace():
    """Create palace directory and write identity file for L0."""
    PALACE_PATH.mkdir(parents=True, exist_ok=True)
    id_path = PALACE_PATH.parent / "identity.txt"
    if IDENTITY_PATH.exists() and not id_path.exists():
        id_path.write_text(_extract_soul_identity(), encoding="utf-8")


def ingest_to_palace(filepath: Path, content: str, wing: str = "openclay"):
    """Store content in MemPalace ChromaDB after wiki ingest."""
    if not HAS_MEMPALACE:
        return
    try:
        _ensure_palace()
        col = get_collection(str(PALACE_PATH))
        room = filepath.parent.name if filepath.parent != WIKI_DIR else "general"
        add_drawer(collection=col, wing=wing, room=room,
                   content=content[:800],
                   source_file=str(filepath.relative_to(BASE_DIR)),
                   chunk_index=0, agent="openclay")
    except Exception:
        pass  # Never break ingest if MemPalace fails


# ── Unified context builder ───────────────────────────────────────────

def build_context(query: str = "", include_l3: bool = True) -> str:
    """Build full memory context from all 4 levels.

    Returns a formatted string ready for LLM prompt injection.
    L0 + L1 always included. L2 always included. L3 only if query provided.
    """
    parts = []
    l0 = load_l0()
    if l0:
        parts.append(f"IDENTITY:\n{l0}")
    l1 = load_l1()
    if l1:
        parts.append(l1)
    l2 = load_l2()
    if l2:
        parts.append(f"RECENT WIKI:\n{l2}")
    if include_l3 and query:
        l3 = search_l3(query)
        if l3 and l3 != "_No matching pages._":
            parts.append(f"DEEP ARCHIVE:\n{l3}")
    return "\n\n---\n\n".join(parts)


def status() -> dict:
    """Return memory system status."""
    wiki_count = len(list(WIKI_DIR.rglob("*.md"))) if WIKI_DIR.exists() else 0
    return {
        "mempalace_installed": HAS_MEMPALACE,
        "palace_exists": PALACE_PATH.exists(),
        "wiki_pages": wiki_count,
        "session_events": len(_session),
        "session_uptime_min": round((time.time() - _session_start) / 60, 1),
    }


# ── Roadmap: predict_engine.py ────────────────────────────────────────
# MemPalace provides the memory foundation that predict_engine.py needs.
# predict_engine is planned but not yet built — it will use L1+L2+L3
# to anticipate what the user needs next based on patterns in past sessions.


def self_test() -> bool:
    """Verify 4-level memory system."""
    # L0: Identity loads from SOUL.md
    l0 = load_l0()
    assert isinstance(l0, str) and len(l0) > 10, "L0 identity too short"
    assert "OpenClay" in l0, "L0 missing OpenClay identity"
    # L1: Session recording works
    record_session("test_task", "test_decision")
    l1 = load_l1()
    assert "test_task" in l1, "L1 missing session event"
    _session.pop()  # clean up
    # L2: Recent wiki (may be empty, must not crash)
    l2 = load_l2()
    assert isinstance(l2, str), "L2 not string"
    # L3: Fallback search works
    l3 = _fallback_search("test query")
    assert isinstance(l3, str), "L3 fallback failed"
    # Full context builds
    ctx = build_context("test")
    assert "IDENTITY:" in ctx, "context missing identity"
    # Status returns expected keys
    s = status()
    assert all(k in s for k in ("wiki_pages", "session_events", "mempalace_installed"))
    return True
