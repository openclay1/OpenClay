"""memory_layer.py — Mem0 local memory layer for OpenClay.
Persistent memory backend that runs fully through Ollama — no cloud, no API key.
BRAIN.md = human-readable layer. Mem0 = machine-queryable layer underneath.
Graceful fallback: if Mem0 unavailable, uses BRAIN.md only. Never crashes.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
BRAIN_PATH = BASE_DIR / "BRAIN.md"

_mem0_client = None
_mem0_available = False
_initialized = False

def _now() -> str: return datetime.now().strftime("%Y-%m-%d %H:%M")
def _read(p: Path) -> str: return p.read_text(encoding="utf-8") if p.exists() else ""

# ── Initialization ───────────────────────────────────────────────────

def init_mem0(user_id: str = "openclay_user") -> bool:
    """Initialize Mem0 with Ollama backend. Returns True if successful."""
    global _mem0_client, _mem0_available, _initialized
    _initialized = True
    try:
        from mem0 import Memory
        config = {
            "llm": {"provider": "ollama", "config": {"model": "llama3.2:1b", "temperature": 0.1}},
            "embedder": {"provider": "ollama", "config": {"model": "nomic-embed-text"}},
            "version": "v1.1",
        }
        _mem0_client = Memory.from_config(config)
        _mem0_available = True
        return True
    except ImportError:
        _mem0_available = False
        return False
    except Exception:
        _mem0_available = False
        return False

# ── Store memory ─────────────────────────────────────────────────────

def store(text: str, metadata: dict | None = None, user_id: str = "openclay_user") -> bool:
    """Store a memory. Falls back to BRAIN.md if Mem0 unavailable."""
    if not _initialized:
        init_mem0(user_id)
    if _mem0_available and _mem0_client:
        try:
            _mem0_client.add(text, user_id=user_id, metadata=metadata or {})
            return True
        except Exception:
            pass
    # Fallback: append to BRAIN.md
    try:
        from vibe_brain import update_brain
        update_brain(f"- [{_now()}] {text[:200]}")
        return True
    except Exception:
        return False

# ── Query memory ─────────────────────────────────────────────────────

def query(question: str, user_id: str = "openclay_user", limit: int = 5) -> list[str]:
    """Query memories relevant to a question. Falls back to BRAIN.md search."""
    if not _initialized:
        init_mem0(user_id)
    if _mem0_available and _mem0_client:
        try:
            results = _mem0_client.search(question, user_id=user_id, limit=limit)
            if isinstance(results, dict) and "results" in results:
                return [r.get("memory", r.get("text", "")) for r in results["results"]]
            if isinstance(results, list):
                return [r.get("memory", r.get("text", str(r))) for r in results[:limit]]
        except Exception:
            pass
    # Fallback: search BRAIN.md
    return _brain_search(question, limit)

def _brain_search(question: str, limit: int = 5) -> list[str]:
    """Keyword search in BRAIN.md as fallback."""
    brain = _read(BRAIN_PATH)
    if not brain: return []
    q_words = [w.lower() for w in question.split() if len(w) > 3]
    if not q_words: return [brain[:500]]
    lines = brain.splitlines()
    scored = []
    for line in lines:
        if not line.strip(): continue
        score = sum(1 for w in q_words if w in line.lower())
        if score > 0: scored.append((score, line.strip()))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored[:limit]]

# ── Session lifecycle ────────────────────────────────────────────────

def on_session_start(task_hint: str = "") -> list[str]:
    """Load relevant context at session start. User never sees this."""
    return query(task_hint) if task_hint else query("recent work preferences")

def on_session_end(learned: str = "", built: str = "", preferences: str = ""):
    """Store what was learned/built/preferred. No manual training required."""
    if learned: store(f"Learned: {learned}")
    if built: store(f"Built: {built}")
    if preferences: store(f"User prefers: {preferences}")

# ── Status ───────────────────────────────────────────────────────────

def is_available() -> bool:
    if not _initialized: init_mem0()
    return _mem0_available

def status() -> dict:
    return {"mem0_available": _mem0_available, "initialized": _initialized,
            "fallback": "BRAIN.md", "backend": "ollama" if _mem0_available else "brain_md"}

# ── Self test ────────────────────────────────────────────────────────

def self_test() -> bool:
    # #57 — Mem0 init + graceful fallback
    global _mem0_client, _mem0_available, _initialized
    # Test fallback mode (Mem0 likely not installed in dev)
    _initialized = False
    _mem0_available = False
    _mem0_client = None
    # Store via fallback
    ok = store("test memory: user prefers dark mode")
    assert ok is True, "Store should succeed via BRAIN.md fallback"
    # Query via fallback
    results = query("dark mode preferences")
    assert isinstance(results, list), "Query should return list"
    # Brain search fallback
    brain_results = _brain_search("test memory", limit=3)
    assert isinstance(brain_results, list)
    # Session lifecycle
    ctx = on_session_start("test task")
    assert isinstance(ctx, list)
    on_session_end(learned="test pattern", built="test module")
    # Status
    st = status()
    assert "mem0_available" in st and "fallback" in st
    assert st["fallback"] == "BRAIN.md"
    # Graceful: no crash when Mem0 unavailable
    _mem0_available = False
    _mem0_client = None
    r2 = query("anything")
    assert isinstance(r2, list), "Should not crash without Mem0"
    return True

if __name__ == "__main__":
    print("self_test:", self_test())
