"""watchdog.py — 4-tier self-healing daemon.
T1 (60s): restart stopped modules. T2 (120s): verify Gradio/queue/Ollama.
T3: on 2× T2 fail, pattern-match known_errors.json + auto-fix.
T4: if T3 fails, surface one line to panel.
"""
from __future__ import annotations
import json, re, sqlite3, subprocess, threading, time, urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"
HEALING_LOG = BASE_DIR / "healing_log.md"
KNOWN_ERRORS_PATH = BASE_DIR / "known_errors.json"
PANEL_MSG_PATH = DATA_DIR / "watchdog_alert.txt"
LOG_DIRS = [BASE_DIR / "logs", DATA_DIR]
GRADIO_URL = "http://127.0.0.1:7861/"
OLLAMA_URL = "http://localhost:11434/api/tags"
_t2_fail_count = 0
_running = True

def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str) -> None:
    """Append to healing_log.md."""
    line = f"- `{_now()}` **watchdog** {msg}\n"
    try:
        with open(HEALING_LOG, "a") as f:
            if f.tell() == 0:
                f.write("# Healing Log\n\nRetried external calls.\n\n")
            f.write(line)
    except FileNotFoundError:
        with open(HEALING_LOG, "w") as f:
            f.write("# Healing Log\n\nRetried external calls.\n\n")
            f.write(line)


def _log_db(action: str, detail: str, confidence: float = 1.0) -> None:
    """Log to SQLite agent_log."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO agent_log (module, action, detail, confidence) "
            "VALUES (?, ?, ?, ?)",
            ("watchdog", action, detail[:200], confidence),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── Helpers ──

def _http_ok(url: str, timeout: int = 5) -> bool:
    try:
        r = urllib.request.urlopen(url, timeout=timeout)
        return r.status == 200
    except Exception:
        return False


def _run_cmd(cmd: str, timeout: int = 30) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout, cwd=str(BASE_DIR))
        return r.returncode == 0, (r.stdout + r.stderr)[:500]
    except Exception as e:
        return False, str(e)[:500]


def _load_known_errors() -> list[dict]:
    try:
        return json.loads(KNOWN_ERRORS_PATH.read_text())
    except Exception:
        return []


def _tail_logs(n: int = 50) -> str:
    """Read last n lines from every .md and .log in log directories."""
    lines: list[str] = []
    for d in LOG_DIRS + [BASE_DIR]:
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.suffix in (".md", ".log") and f.is_file():
                try:
                    all_lines = f.read_text().splitlines()
                    lines.extend(all_lines[-n:])
                except Exception:
                    pass
    return "\n".join(lines[-200:])  # cap total


def _stuck_queue_items() -> list[Path]:
    """Return queue .json files older than 2 min."""
    q = BASE_DIR / "queue"
    if not q.is_dir(): return []
    cutoff = time.time() - 120
    items = []
    for f in q.iterdir():
        if f.suffix == ".json" and not f.name.startswith("."):
            try:
                if f.stat().st_mtime < cutoff: items.append(f)
            except Exception: pass
    return items

def _clear_stuck_queue() -> int:
    items = _stuck_queue_items()
    if not items: return 0
    dest = BASE_DIR / "queue" / "processed"; dest.mkdir(exist_ok=True)
    for f in items:
        try: f.rename(dest / f.name)
        except Exception: pass
    return len(items)

def _write_panel_alert(msg: str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PANEL_MSG_PATH.write_text(f"`{_now()}` — {msg}\n")

def _clear_panel_alert():
    try: PANEL_MSG_PATH.unlink(missing_ok=True)
    except Exception: pass

# ── Core module check ──
_CORE_MODULES = {"agent": ("agent", "run_loop")}
_module_threads: dict[str, threading.Thread] = {}

def _ensure_module_running(name: str, mod_name: str, func_name: str) -> bool:
    t = _module_threads.get(name)
    if t and t.is_alive(): return True
    try:
        import importlib
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, func_name)
        t = threading.Thread(target=fn, daemon=True, name=f"oc-{name}")
        t.start(); _module_threads[name] = t
        _log(f"restarted module **{name}**"); _log_db("module_restarted", name)
        return True
    except Exception as e:
        _log(f"failed to restart **{name}**: `{str(e)[:80]}`"); return False


# ── TIER 1 — every 60 s: restart stopped modules ──

def tier1() -> bool:
    return all(_ensure_module_running(n, m, f) for n, (m, f) in _CORE_MODULES.items())

# ── TIER 2 — every 120 s: health checks ──

def tier2() -> list[str]:
    fails: list[str] = []
    if not _http_ok(GRADIO_URL): fails.append("Gradio panel not responding")
    stuck = _stuck_queue_items()
    if stuck:
        c = _clear_stuck_queue()
        _log(f"cleared {c} stuck queue item(s)"); _log_db("stuck_queue_cleared", f"{c} items")
        fails.append(f"Queue stuck — cleared {c} items")
    if not _http_ok(OLLAMA_URL):
        _run_cmd("ollama serve &"); time.sleep(2)
        if not _http_ok(OLLAMA_URL): fails.append("Ollama unreachable after restart attempt")
    try:
        c = sqlite3.connect(str(DB_PATH), timeout=5); c.execute("SELECT 1"); c.close()
    except Exception as e:
        fails.append(f"SQLite error: {str(e)[:60]}")
    return fails

# ── TIER 3 — on 2 consecutive T2 failures: auto-fix ──

def tier3(failures: list[str]) -> bool:
    combined = "\n".join(failures) + "\n" + _tail_logs()
    known = _load_known_errors()
    any_fixed = False
    for entry in known:
        pat = entry.get("pattern", "")
        if not pat: continue
        try:
            if not re.search(pat, combined, re.IGNORECASE): continue
        except re.error: continue
        eid, fix_cmd = entry.get("id", "?"), entry.get("fix_command", "")
        check_cmd = entry.get("success_check", "")
        _log(f"Tier 3: matched **{eid}** — applying fix: `{fix_cmd[:60]}`")
        ok, out = _run_cmd(fix_cmd, timeout=60)
        if check_cmd and check_cmd != "false": ok, _ = _run_cmd(check_cmd, timeout=15)
        if ok:
            _log(f"Tier 3: **{eid}** fix succeeded"); _log_db("tier3_fix_applied", eid, 0.9)
            any_fixed = True
        else:
            _log(f"Tier 3: **{eid}** fix failed — `{out[:60]}`"); _log_db("tier3_fix_failed", eid, 0.3)
    return any_fixed

# ── TIER 4 — escalate to panel ──

def tier4(failures: list[str]) -> None:
    short = (failures[0] if failures else "Unknown issue")[:80].rstrip(".")
    _write_panel_alert(f"Something needs attention. {short}. Check healing_log.md.")
    _log(f"Tier 4: escalated to panel — `{short}`"); _log_db("tier4_escalated", short, 0.1)


# ── Main loop ──

def run() -> None:
    global _t2_fail_count, _running
    _log("started"); _log_db("watchdog_started", "4-tier self-healing active")
    tick = 0
    while _running:
        time.sleep(10); tick += 10
        if tick % 60 == 0: tier1()
        if tick % 120 == 0:
            failures = tier2()
            if failures:
                _t2_fail_count += 1
                for f in failures: _log(f"Tier 2 failure: {f}")
                if _t2_fail_count >= 2:
                    if tier3(failures): _t2_fail_count = 0; _clear_panel_alert()
                    else: tier4(failures); _t2_fail_count = 0
            else:
                _t2_fail_count = 0; _clear_panel_alert()
        if tick >= 86400: tick = 0

def stop():
    global _running; _running = False

def self_test() -> bool:
    """Verify watchdog helpers."""
    assert _http_ok("http://localhost:99999") is False, "bad port should fail"
    assert _load_known_errors(), "known_errors.json empty"
    items = _stuck_queue_items(); assert isinstance(items, list)
    return True

if __name__ == "__main__":
    try: run()
    except KeyboardInterrupt: print("\nWatchdog stopped.")
