"""retry_ext.py — Retry decorator for external calls.

3 attempts, exponential backoff starting at 1 s.
Every retry logged to healing_log.md.
Final failure marked in SQLite agent_log + re-raised.
"""
from __future__ import annotations

import functools, sqlite3, time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
HEALING_LOG = BASE_DIR / "healing_log.md"
DB_PATH = BASE_DIR / "data" / "openclay.db"

_MAX = 3
_BASE_DELAY = 1  # seconds


def _log_heal(module: str, attempt: int, exc: Exception) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"- `{ts}` **{module}** attempt {attempt}/{_MAX} failed: `{str(exc)[:120]}`\n"
    try:
        with open(HEALING_LOG, "a") as f:
            if f.tell() == 0:
                f.write("# Healing Log\n\nRetried external calls.\n\n")
            f.write(line)
    except FileNotFoundError:
        with open(HEALING_LOG, "w") as f:
            f.write("# Healing Log\n\nRetried external calls.\n\n")
            f.write(line)


def _log_final_failure(module: str, error: str) -> None:
    """Mark failure in SQLite agent_log if DB exists."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO agent_log (module, action, detail, confidence) "
            "VALUES (?, ?, ?, ?)",
            (module, "external_call_failed", error[:200], 0.0),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def retry(fn=None, *, label: str | None = None):
    """Decorator: retry *fn* up to 3 times with exponential backoff.

    Usage:
        @retry
        def fetch(): ...

        @retry(label="ollama-chat")
        def fetch(): ...
    """
    def _wrap(func):
        tag = label or func.__qualname__

        @functools.wraps(func)
        def wrapper(*a, **kw):
            last_exc: Exception | None = None
            for attempt in range(1, _MAX + 1):
                try:
                    return func(*a, **kw)
                except Exception as exc:
                    last_exc = exc
                    _log_heal(tag, attempt, exc)
                    if attempt < _MAX:
                        time.sleep(_BASE_DELAY * (2 ** (attempt - 1)))
            _log_final_failure(tag, str(last_exc))
            raise last_exc  # type: ignore[misc]

        return wrapper

    if fn is not None:          # bare @retry
        return _wrap(fn)
    return _wrap                # @retry(label="...")


def retry_call(fn, *args, label: str = "external", **kwargs):
    """Functional form: retry_call(requests.post, url, json=body, label="ollama").

    Same semantics as the decorator but usable inline.
    """
    last_exc: Exception | None = None
    for attempt in range(1, _MAX + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            _log_heal(label, attempt, exc)
            if attempt < _MAX:
                time.sleep(_BASE_DELAY * (2 ** (attempt - 1)))
    _log_final_failure(label, str(last_exc))
    raise last_exc  # type: ignore[misc]


def self_test() -> bool:
    """Verify retry logic."""
    c = {"n": 0}
    @retry(label="selftest")
    def flaky():
        c["n"] += 1
        if c["n"] < 3: raise ValueError("not yet")
        return "ok"
    assert flaky() == "ok" and c["n"] == 3, "retry decorator failed"
    c["n"] = 0
    def always_fail(): c["n"] += 1; raise RuntimeError("perm")
    try: retry_call(always_fail, label="selftest2")
    except RuntimeError: pass
    assert c["n"] == _MAX, "retry_call count wrong"
    return True
