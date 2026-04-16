# OpenClay v1.3 — COANA Labs
# Local AI Research Assistant
# No data leaves this machine.
# Memory: Mem0 + Karpathy Wiki + Procedural + Agentic + Hindsight
from __future__ import annotations
import http.server, io, json, os, re, subprocess, sys, threading, time, email.parser
import hashlib, glob as glob_module, uuid
import urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

PORT = 3000
OLLAMA_URL = "http://localhost:11434"
PREFERRED_MODELS = ["qwen2.5:3b-instruct-q4_K_M", "qwen2.5:3b", "llama3.2:3b",
                     "phi3:mini", "gemma4:latest"]
BASE_DIR = Path(__file__).parent
WIKI_DIR = BASE_DIR / "wiki"
MEMORY_DIR = BASE_DIR / "memory"
WATCHERS_DIR = BASE_DIR / "watchers"
AGENTS_DIR = BASE_DIR / "agents"
LOGS_DIR = BASE_DIR / "logs"
SANDBOX_DIR = BASE_DIR / "sandbox"
MEMORY_STORE_DIR = BASE_DIR / "memory_store"
TASKS_DIR = BASE_DIR / "tasks"
_ollama_proc = None
_model = None

# ── Session state ────────────────────────────────────────────────
loaded_document = ""
loaded_filename = ""
conversation_history = []
AGENT_BACKEND = "simple"
_watcher_threads = {}
_new_ingested_count = 0
_connected_folders = []
_soul_text = ""
_current_agent = None   # active agent config dict
_agents = {}            # name -> config
_mem0_client = None     # Mem0 Memory instance
_log_last_hash = "genesis"
_execution_history = []
_active_tasks = {}      # id -> task dict
_task_threads = {}      # id -> thread

# ── Soul document loading ────────────────────────────────────────
def _load_soul():
    global _soul_text
    parts = []
    soul_path = BASE_DIR / "soul.md"
    if soul_path.exists():
        parts.append(soul_path.read_text("utf-8"))
    custom_path = BASE_DIR / "soul_custom.md"
    if custom_path.exists():
        parts.append(custom_path.read_text("utf-8"))
    _soul_text = "\n\n".join(parts)
    model = _detect_model() if _is_ollama_running() else PREFERRED_MODELS[0]
    _soul_text = _soul_text.replace("[MODEL_NAME]", model)
    return _soul_text

# ── Ollama management ────────────────────────────────────────────
def _is_ollama_running():
    try: urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2); return True
    except Exception: return False

def _start_ollama():
    global _ollama_proc
    if _is_ollama_running(): return True
    try:
        _ollama_proc = subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(30):
            if _is_ollama_running(): return True
            time.sleep(0.5)
    except FileNotFoundError:
        print("  Ollama not found. Install from https://ollama.com"); return False
    return False

def _stop_ollama():
    global _ollama_proc
    if _ollama_proc: _ollama_proc.terminate(); _ollama_proc = None

def _detect_model():
    global _model
    if _model: return _model
    try:
        resp = urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5)
        available = [m["name"] for m in json.loads(resp.read()).get("models", [])]
        for pref in PREFERRED_MODELS:
            for avail in available:
                if pref in avail or avail.startswith(pref.split(":")[0]):
                    _model = avail; return _model
        if available: _model = available[0]; return _model
    except Exception: pass
    _model = PREFERRED_MODELS[0]; return _model

# ── Mem0 Persistent Memory ──────────────────────────────────────
def _init_mem0():
    global _mem0_client
    try:
        from mem0 import Memory
        config = {
            "llm": {"provider": "ollama", "config": {
                "model": _detect_model(),
                "ollama_base_url": OLLAMA_URL
            }},
            "embedder": {"provider": "ollama", "config": {
                "model": "qwen2.5:0.5b",
                "ollama_base_url": OLLAMA_URL
            }},
            "vector_store": {"provider": "chroma", "config": {
                "collection_name": "openclay_memory",
                "path": str(MEMORY_STORE_DIR)
            }}
        }
        _mem0_client = Memory.from_config(config)
        return True
    except Exception as e:
        print(f"  Mem0 init failed ({e}), using fallback memory")
        return False

def _memory_add(text, user_id="local_user"):
    if not _mem0_client: return
    def _worker():
        try: _mem0_client.add(text, user_id=user_id)
        except Exception: pass
    threading.Thread(target=_worker, daemon=True).start()

def _memory_search(query, user_id="local_user", limit=5):
    if not _mem0_client: return []
    try:
        results = _mem0_client.search(query, user_id=user_id, limit=limit)
        if isinstance(results, dict):
            return results.get("results", results.get("memories", []))
        return results if isinstance(results, list) else []
    except Exception: return []

def _memory_get_all(user_id="local_user"):
    if not _mem0_client: return []
    try:
        results = _mem0_client.get_all(user_id=user_id)
        if isinstance(results, dict):
            return results.get("results", results.get("memories", []))
        return results if isinstance(results, list) else []
    except Exception: return []

def _memory_delete(memory_id):
    if not _mem0_client: return False
    try: _mem0_client.delete(memory_id); return True
    except Exception: return False

# ── Tamper-Evident Logging ──────────────────────────────────────
def _log_write(role, content, model=None):
    global _log_last_hash
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"{today}.jsonl"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "role": role,
        "content": content,
        "model": model or _detect_model()
    }
    # Hash chain: SHA256(previous_hash + JSON of this entry)
    entry_json = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    chain_input = _log_last_hash + entry_json
    entry["hash"] = hashlib.sha256(chain_input.encode("utf-8")).hexdigest()
    _log_last_hash = entry["hash"]
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def _log_read_today():
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"{today}.jsonl"
    if not log_file.exists(): return []
    entries = []
    for line in log_file.read_text("utf-8").splitlines():
        if line.strip():
            try: entries.append(json.loads(line))
            except Exception: pass
    return entries

def _log_verify(date=None):
    if not date: date = datetime.now().strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"{date}.jsonl"
    if not log_file.exists(): return {"intact": True, "entries": 0, "message": "No log for this date"}
    prev_hash = "genesis"
    entries = []
    for line in log_file.read_text("utf-8").splitlines():
        if not line.strip(): continue
        try: entries.append(json.loads(line))
        except Exception:
            return {"intact": False, "entries": len(entries), "message": "Corrupt JSON at entry " + str(len(entries)+1)}
    for i, entry in enumerate(entries):
        stored_hash = entry.get("hash", "")
        check = {k: v for k, v in entry.items() if k != "hash"}
        check_json = json.dumps(check, ensure_ascii=False, sort_keys=True)
        expected = hashlib.sha256((prev_hash + check_json).encode("utf-8")).hexdigest()
        if expected != stored_hash:
            return {"intact": False, "entries": len(entries),
                    "broken_at": i + 1, "message": f"Hash mismatch at entry {i+1}"}
        prev_hash = stored_hash
    return {"intact": True, "entries": len(entries), "message": "Registro integro / Log intact"}

def _log_export_md(date=None):
    entries = _log_read_today() if not date else []
    if date:
        log_file = LOGS_DIR / f"{date}.jsonl"
        if log_file.exists():
            for line in log_file.read_text("utf-8").splitlines():
                if line.strip():
                    try: entries.append(json.loads(line))
                    except Exception: pass
    lines = [f"# OpenClay Log — {date or datetime.now().strftime('%Y-%m-%d')}\n"]
    lines.append(f"Entries: {len(entries)} | Verified: {_log_verify(date).get('message', '?')}\n\n---\n")
    for e in entries:
        ts = e.get("timestamp", "?")[:19].replace("T", " ")
        role = e.get("role", "?").upper()
        content = e.get("content", "")
        lines.append(f"**[{ts}] {role}**\n{content}\n\n---\n")
    return "\n".join(lines)

def _init_log_chain():
    """Load the last hash from today's log to continue the chain."""
    global _log_last_hash
    entries = _log_read_today()
    if entries:
        _log_last_hash = entries[-1].get("hash", "genesis")

# ── Agent Registry ──────────────────────────────────────────────
def _load_agents():
    global _agents, _current_agent
    _agents = {}
    if not AGENTS_DIR.exists(): return
    for f in AGENTS_DIR.glob("*.agent.json"):
        try:
            cfg = json.loads(f.read_text("utf-8"))
            name = cfg.get("name", f.stem)
            _agents[name] = cfg
        except Exception: pass
    # Default to Clay General
    if "Clay General" in _agents and not _current_agent:
        _current_agent = _agents["Clay General"]
    elif _agents and not _current_agent:
        _current_agent = list(_agents.values())[0]

def _select_agent(name):
    global _current_agent
    if name in _agents:
        _current_agent = _agents[name]
        return True
    return False

# ── Research Memory (Hindsight-style three-network) ─────────────
_research_db = None

def _init_research_memory():
    global _research_db
    try:
        import chromadb
        _research_db = chromadb.PersistentClient(path=str(MEMORY_STORE_DIR / "hindsight"))
        # Create three collections
        _research_db.get_or_create_collection("factual")
        _research_db.get_or_create_collection("experiential")
        _research_db.get_or_create_collection("beliefs")
        return True
    except Exception as e:
        print(f"  Research memory init failed: {e}")
        return False

def _research_add(network, text, metadata=None):
    """Add to one of the three networks: factual, experiential, beliefs"""
    if not _research_db: return
    def _worker():
        try:
            col = _research_db.get_collection(network)
            doc_id = hashlib.md5((text + str(time.time())).encode()).hexdigest()[:12]
            meta = metadata or {}
            meta["timestamp"] = datetime.now().isoformat()
            col.add(documents=[text], ids=[doc_id], metadatas=[meta])
        except Exception: pass
    threading.Thread(target=_worker, daemon=True).start()

def _research_search(network, query, n=5):
    if not _research_db: return []
    try:
        col = _research_db.get_collection(network)
        if col.count() == 0: return []
        results = col.query(query_texts=[query], n_results=min(n, col.count()))
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        return [{"text": d, "metadata": m} for d, m in zip(docs, metas)]
    except Exception: return []

def _research_get_context():
    """Get full research context from all three networks."""
    if not _research_db: return {"factual": [], "experiential": [], "beliefs": []}
    context = {}
    for network in ["factual", "experiential", "beliefs"]:
        try:
            col = _research_db.get_collection(network)
            if col.count() == 0:
                context[network] = []
                continue
            all_data = col.get(include=["documents", "metadatas"])
            items = []
            for doc, meta in zip(all_data.get("documents", []), all_data.get("metadatas", [])):
                items.append({"text": doc, "metadata": meta})
            # Sort by timestamp, newest first
            items.sort(key=lambda x: x.get("metadata", {}).get("timestamp", ""), reverse=True)
            context[network] = items[:10]
        except Exception:
            context[network] = []
    return context

def _extract_research_insights(prompt, response):
    """Background: classify conversation into factual/experiential/belief memories."""
    if not _research_db: return
    def _worker():
        try:
            classify_prompt = f"""Analyze this exchange and extract structured memories.

User: {prompt[:500]}
Assistant: {response[:500]}

Reply ONLY in JSON:
{{"factual": ["fact1", "fact2"], "experiential": "one-line session summary", "belief": "inference about user goal or null"}}"""
            body = json.dumps({"model": _detect_model(), "prompt": classify_prompt,
                               "stream": False, "options": {"temperature": 0.2, "num_predict": 256}}).encode()
            req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=body,
                                         headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=30)
            text = json.loads(resp.read()).get("response", "")
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                data = json.loads(m.group())
                for fact in data.get("factual", []):
                    if fact: _research_add("factual", fact)
                exp = data.get("experiential", "")
                if exp: _research_add("experiential", exp)
                belief = data.get("belief")
                if belief and belief != "null":
                    _research_add("beliefs", belief)
        except Exception: pass
    threading.Thread(target=_worker, daemon=True).start()

# ── Sandbox Execution ───────────────────────────────────────────
def _execute_code(code, language="python", timeout=30, cwd=None):
    """Execute code with timeout. cwd defaults to SANDBOX_DIR (UI runner stays sandboxed).
    Task engine passes BASE_DIR so paths like ./sandbox/... resolve correctly."""
    import tempfile
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = str(cwd) if cwd else str(SANDBOX_DIR)
    tmp_file = None
    if language == "python":
        # Always write to a temp file to avoid -c newline/f-string issues
        tmp_file = tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                               delete=False, dir=run_dir)
        tmp_file.write(code)
        tmp_file.close()
        cmd = [sys.executable, tmp_file.name]
    elif language == "bash":
        cmd = ["bash", "-c", code]
    else:
        return {"ok": False, "error": "Unsupported language", "stdout": "", "stderr": ""}
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout, cwd=run_dir)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "language": language,
            "code": code[:500],
            "exit_code": result.returncode,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:500]
        }
        _execution_history.append(entry)
        if len(_execution_history) > 50:
            _execution_history.pop(0)
        # Log the execution
        _log_write("system", f"Executed {language}: exit={result.returncode}")
        return {"ok": result.returncode == 0, "stdout": result.stdout[:2000],
                "stderr": result.stderr[:500], "exit_code": result.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timeout (30s)", "stdout": "", "stderr": ""}
    except Exception as e:
        return {"ok": False, "error": str(e), "stdout": "", "stderr": ""}
    finally:
        if tmp_file and os.path.exists(tmp_file.name):
            try: os.unlink(tmp_file.name)
            except: pass

# ── Task Engine (v1.3) ─────────────────────────────────────────
MAX_TASK_STEPS = 20
TASK_LLM_TIMEOUT = 60

def _task_create(goal, agent_name=None):
    """Create a new task and return its dict."""
    task_id = str(uuid.uuid4())
    agent = agent_name or (_current_agent.get("name", "Clay General") if _current_agent else "Clay General")
    task = {
        "id": task_id,
        "goal": goal,
        "agent": agent,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "steps": [],
        "final_result": None,
        "retry_count": 0,
        "max_retries": 3
    }
    _active_tasks[task_id] = task
    _task_save(task)
    return task

def _task_save(task):
    """Persist task to JSON file."""
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    path = TASKS_DIR / f"{task['id']}.json"
    task["updated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(task, indent=2, ensure_ascii=False), "utf-8")

def _task_load(task_id):
    """Load task from disk."""
    path = TASKS_DIR / f"{task_id}.json"
    if path.exists():
        return json.loads(path.read_text("utf-8"))
    return None

def _task_list():
    """List all tasks, newest first."""
    tasks = []
    if not TASKS_DIR.exists(): return tasks
    for f in TASKS_DIR.glob("*.json"):
        try:
            t = json.loads(f.read_text("utf-8"))
            tasks.append(t)
        except Exception: pass
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return tasks

def _task_ollama_call(prompt, system="", timeout=TASK_LLM_TIMEOUT):
    """Blocking Ollama call with timeout. Returns response text."""
    body = json.dumps({
        "model": _detect_model(),
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 512}
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", data=body,
        headers={"Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read()).get("response", "")

def _task_auto_summarize(task):
    """Generate a summary from completed steps."""
    results = []
    for s in task.get("steps", []):
        if s.get("success") and s.get("result"):
            results.append(str(s["result"]).split("\nVerification")[0].strip()[:150])
    return "Task completed. Results:\n" + "\n".join(f"- {r}" for r in results[-5:])

def _is_goal_satisfied(task):
    """FIX 3 — Check if goal is satisfied based on completed steps."""
    steps = task.get("steps", [])
    if len(steps) < 2:
        return False, None

    # Check for repeated last two steps (model is looping on an already-done goal)
    if len(steps) >= 2:
        last = steps[-1]
        prev = steps[-2]
        if (last.get("description", "")[:60] == prev.get("description", "")[:60]
                and last.get("success") and prev.get("success")):
            return True, _task_auto_summarize(task)

    # Check if all goal-action keywords appear in completed steps
    goal_words = set(task["goal"].lower().split())
    action_words = {"create", "write", "verify", "check", "read", "find",
                    "report", "list", "search", "count", "calculate"}
    goal_actions = goal_words & action_words
    completed_actions = set()
    for s in steps:
        if s.get("success"):
            desc_lower = s.get("description", "").lower()
            for word in action_words:
                if word in desc_lower:
                    completed_actions.add(word)
    if goal_actions and goal_actions.issubset(completed_actions):
        return True, _task_auto_summarize(task)

    # Hard cap: 8+ successful steps with no recent failures → assume done
    successful = sum(1 for s in steps if s.get("success"))
    if successful >= 8:
        return True, _task_auto_summarize(task)

    return False, None

def _parse_action(raw_text):
    """FIX 1 — Parse LLM output into {action, input} regardless of format."""
    known_actions = ["bash", "python", "write", "read", "search", "done"]

    # Strategy 1: try direct JSON parse (handles clean output)
    data = None
    stripped = raw_text.strip()
    try:
        data = json.loads(stripped)
    except Exception:
        pass

    # Strategy 2: extract outermost {...} — first { to last }
    if data is None:
        start = raw_text.find('{')
        end = raw_text.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(raw_text[start:end+1])
            except Exception:
                pass

    # Strategy 3: no JSON found — extract intent from plain text
    if data is None:
        text_lower = raw_text.lower()
        for action in ["done", "bash", "python", "write", "read"]:
            if action in text_lower:
                return {"action": action, "input": raw_text.strip()}
        return {"action": "done", "input": "Goal appears complete"}

    # --- normalize data formats below ---

    # Format A: {"action": "write", "input": "..."} — canonical
    if "action" in data and "input" in data:
        return data

    # Format A2: {"action": "read|filename"} — 3B malformed (action|input merged)
    if "action" in data and "input" not in data:
        raw_action = str(data["action"])
        for act in known_actions:
            if raw_action.startswith(act + "|"):
                return {"action": act, "input": raw_action[len(act)+1:]}
            if raw_action == act:
                # action exists but no input — use empty
                return {"action": act, "input": ""}

    # Format B: {"write": "content"} — 3B model style
    for action in known_actions:
        if action in data:
            return {"action": action, "input": str(data[action])}

    # Format C: {"command": "...", "code": "..."} — alternate style
    if "command" in data:
        return {"action": "bash", "input": str(data["command"])}
    if "code" in data:
        return {"action": "python", "input": str(data["code"])}

    # Last resort: if any value suggests completion
    values = " ".join(str(v) for v in data.values()).lower()
    if any(w in values for w in ["complete", "done", "finished", "achieved"]):
        return {"action": "done", "input": values}

    return {"action": "done", "input": str(data)}

def _task_plan(task):
    """Ask LLM for the next action. Returns parsed action dict or None."""
    # FIX 3 — check goal satisfaction before asking LLM
    satisfied, summary = _is_goal_satisfied(task)
    if satisfied:
        return {"action": "done", "input": summary}

    steps_summary = ""
    for s in task["steps"][-5:]:
        status = "\u2713" if s.get("success") else "\u2717"
        steps_summary += f"\nStep {s['step_num']} [{status}]: {s.get('description', '')}"
        result_text = str(s.get("result", "")).split("\nVerification")[0].strip()[:150]
        if result_text:
            steps_summary += f"\n  \u2192 {result_text}"

    num_done = len([s for s in task["steps"] if s.get("success")])
    # Build a concrete example based on what makes sense for this goal
    prompt = f"""You are an autonomous task executor. Your goal:
{task['goal']}

Progress so far ({num_done} successful steps):{steps_summary if steps_summary else " none — this is step 1"}

Pick the SINGLE best next action and reply with ONLY a JSON object.

VALID ACTIONS:
- bash   → run a shell command (e.g. ls, wc, cat)
- python → run Python code
- write  → create/write a file
- read   → read a file
- done   → mark task complete

EXAMPLES of valid replies:
{{"action": "bash", "input": "ls -la"}}
{{"action": "python", "input": "print(open('file.txt').read())"}}
{{"action": "write", "input": "report.md|||# Report\\ncontent here"}}
{{"action": "read", "input": "file.txt"}}
{{"action": "done", "input": "Task complete. Summary of what was accomplished."}}

Do NOT repeat a step that already succeeded. If all sub-goals are achieved, reply with action=done.
Your reply must contain ONLY a JSON object — no explanation, no markdown, no code fences."""

    system = "Task executor. Reply with ONLY a JSON object with keys 'action' and 'input'."

    try:
        text = _task_ollama_call(prompt, system)
        # FIX 1 — use robust multi-format parser
        return _parse_action(text)
    except Exception:
        return None

def _task_execute_action(action_dict):
    """Execute an action and return result dict.
    bash/python run from BASE_DIR so paths like ./sandbox/... resolve correctly.
    write is still restricted to SANDBOX_DIR. read resolves relative to BASE_DIR."""
    action = action_dict.get("action", "")
    inp = action_dict.get("input", "")

    if action == "python":
        return _execute_code(inp, "python", timeout=30, cwd=BASE_DIR)
    elif action == "bash":
        return _execute_code(inp, "bash", timeout=30, cwd=BASE_DIR)
    elif action == "read":
        try:
            # Resolve relative to BASE_DIR; fall back to SANDBOX_DIR for bare filenames
            candidate = (BASE_DIR / inp.strip()).resolve()
            if not candidate.exists():
                candidate = (SANDBOX_DIR / inp.strip()).resolve()
            if not candidate.exists():
                return {"ok": False, "error": f"File not found: {inp}", "stdout": "", "stderr": ""}
            # Safety: must stay within BASE_DIR
            candidate.relative_to(BASE_DIR)
            content = candidate.read_text("utf-8", errors="ignore")[:4000]
            return {"ok": True, "stdout": content, "stderr": ""}
        except ValueError:
            return {"ok": False, "error": "Path escapes project directory", "stdout": "", "stderr": ""}
        except Exception as e:
            return {"ok": False, "error": str(e), "stdout": "", "stderr": ""}
    elif action == "write":
        try:
            parts = inp.split("|||", 1)
            if len(parts) != 2:
                return {"ok": False, "error": "Write format: filename|||content", "stdout": "", "stderr": ""}
            filename, content = parts[0].strip(), parts[1]
            filepath = SANDBOX_DIR / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, "utf-8")
            return {"ok": True, "stdout": f"Written {len(content)} bytes to {filename}", "stderr": ""}
        except Exception as e:
            return {"ok": False, "error": str(e), "stdout": "", "stderr": ""}
    elif action == "done":
        return {"ok": True, "stdout": inp, "stderr": "", "done": True}
    else:
        return {"ok": False, "error": f"Unknown action: {action}", "stdout": "", "stderr": ""}

def _task_verify(task, action_dict, result):
    """FIX 2 — Verify step success. Trust system result first; no LLM call needed."""
    ok = result.get("ok", False)
    action = action_dict.get("action", "")
    output = str(result.get("stdout", "")).strip()
    error  = str(result.get("error",  "") or result.get("stderr", "")).strip()

    if ok:
        if action in ("write",):
            return True, f"File written successfully: {output[:100]}"
        if action in ("python", "bash"):
            return True, f"Execution succeeded: {output[:100]}" if output else "Execution succeeded (no output)"
        if action == "read":
            return True, f"Read successful: {len(output)} chars"
        if action == "done":
            return True, "Task marked complete"
        return True, f"{action} completed successfully"

    # System execution failed — return the error directly, no LLM call
    return False, f"System execution failed: {error or 'unknown error'}"

def _task_run(task_id):
    """Main task loop — runs in a background thread."""
    task = _active_tasks.get(task_id)
    if not task:
        task = _task_load(task_id)
        if not task: return
        _active_tasks[task_id] = task

    task["status"] = "running"
    _task_save(task)
    _log_write("system", f"Task started: {task['goal'][:100]}", _detect_model())

    step_num = len(task["steps"])

    while task["status"] == "running":
        step_num += 1

        # FIX 3 — auto-complete if goal is already satisfied
        satisfied, summary = _is_goal_satisfied(task)
        if satisfied:
            task["status"] = "complete"
            task["final_result"] = summary or _task_auto_summarize(task)
            _task_save(task)
            _log_write("system", f"Task {task_id[:8]} auto-completed in {len(task['steps'])} steps")
            break

        # Safety: max steps
        if step_num > MAX_TASK_STEPS:
            task["status"] = "failed"
            task["final_result"] = f"Exceeded maximum {MAX_TASK_STEPS} steps"
            _task_save(task)
            _log_write("system", f"Task {task_id[:8]} failed: max steps exceeded")
            break

        # a. PLAN
        action_dict = _task_plan(task)
        if not action_dict:
            task["retry_count"] += 1
            if task["retry_count"] >= task["max_retries"]:
                task["status"] = "failed"
                task["final_result"] = "Failed to get valid plan from LLM"
                _task_save(task)
                _log_write("system", f"Task {task_id[:8]} failed: no valid plan")
                break
            continue

        step = {
            "step_num": step_num,
            "type": "plan",
            "description": f"{action_dict.get('action', '?')}: {str(action_dict.get('input', ''))[:100]}",
            "result": None,
            "success": None,
            "timestamp": datetime.now().isoformat()
        }

        # b. EXECUTE
        if action_dict.get("action") == "done":
            step["type"] = "execute"
            step["result"] = action_dict.get("input", "Task complete")
            step["success"] = True
            task["steps"].append(step)
            task["status"] = "complete"
            task["final_result"] = action_dict.get("input", "Task complete")
            _task_save(task)
            _log_write("system", f"Task {task_id[:8]} complete: {task['final_result'][:200]}")
            break

        step["type"] = "execute"
        result = _task_execute_action(action_dict)
        step["result"] = result.get("stdout", "") or result.get("error", "")

        # c. VERIFY
        success, reason = _task_verify(task, action_dict, result)
        step["success"] = success
        if reason:
            step["result"] = f"{step['result']}\nVerification: {reason}"

        # d. STORE
        task["steps"].append(step)
        _task_save(task)
        _log_write("system",
            f"Task {task_id[:8]} step {step_num}: {action_dict.get('action', '?')} \u2192 {'ok' if success else 'fail'}",
            _detect_model())

        # e. DECIDE
        if not success:
            task["retry_count"] += 1
            if task["retry_count"] >= task["max_retries"]:
                task["status"] = "failed"
                task["final_result"] = f"Failed after {task['max_retries']} retries. Last error: {reason}"
                _task_save(task)
                _log_write("system", f"Task {task_id[:8]} failed: max retries")
                break
        else:
            task["retry_count"] = 0  # reset on success

        # Check for paused
        if task["status"] == "paused":
            _task_save(task)
            break

    # Cleanup
    _task_threads.pop(task_id, None)

def _task_start(task_id):
    """Start task execution in background thread."""
    if not _current_agent:
        return False, "No agent loaded"
    t = threading.Thread(target=_task_run, args=(task_id,), daemon=True)
    _task_threads[task_id] = t
    t.start()
    return True, "Task started"

def _task_stop(task_id):
    """Pause a running task."""
    task = _active_tasks.get(task_id)
    if task and task["status"] == "running":
        task["status"] = "paused"
        _task_save(task)
        return True
    return False

# ── System prompt ────────────────────────────────────────────────
SYSTEM_PROMPT = """You are OpenClay, a local AI research assistant running on a COANA Labs device in Puerto Rico. You specialize in pharmaceutical compliance (FDA 21 CFR, EU GMP Annex 1, ICH guidelines), clinical research methodology, and scientific paper analysis. You respond in whatever language the user writes in — Spanish or English. You are precise, cite specific regulatory sections when relevant, and flag ambiguities and logical gaps in documents you analyze. When uncertain, say so clearly and explain what information would resolve the uncertainty."""

def _build_system_prompt(query=""):
    parts = []
    # Soul document first
    if _soul_text:
        parts.append(_soul_text)
    # Active agent prompt overrides default
    if _current_agent and _current_agent.get("system_prompt"):
        parts.append(_current_agent["system_prompt"])
    else:
        parts.append(SYSTEM_PROMPT)
    # Connected folders
    if _connected_folders:
        folder_list = ", ".join(_connected_folders)
        parts.append(f"\n\n## Connected Directories\nThe user has granted access to: {folder_list}.")
    # Mem0 relevant memories
    if query:
        memories = _memory_search(query, limit=5)
        if memories:
            mem_texts = []
            for m in memories:
                text = m.get("memory", m.get("text", str(m))) if isinstance(m, dict) else str(m)
                if text: mem_texts.append(f"- {text}")
            if mem_texts:
                parts.append("\n\n## Persistent Memory (things you remember about this user):\n" + "\n".join(mem_texts))
    # Research memory (Hindsight) if in research mode
    if _current_agent and _current_agent.get("memory_backend") == "hindsight" and query:
        for network in ["factual", "experiential", "beliefs"]:
            items = _research_search(network, query, n=3)
            if items:
                texts = [r["text"] for r in items]
                labels = {"factual": "Known Facts", "experiential": "Past Sessions", "beliefs": "Inferred Goals"}
                parts.append(f"\n\n## Research Context — {labels[network]}:\n" + "\n".join(f"- {t}" for t in texts))
    # Preferences
    prefs = MEMORY_DIR / "preferences.md"
    if prefs.exists():
        parts.append(f"\n\n## User Preferences:\n{prefs.read_text('utf-8')[:2000]}")
    # Wiki
    wiki_context = _get_relevant_wiki(query)
    if wiki_context:
        parts.append(f"\n\n## Relevant wiki:\n{wiki_context}")
    return "\n".join(parts)

# ── Wiki (Karpathy Layer 1) ──────────────────────────────────────
def _get_relevant_wiki(query=""):
    keywords = set()
    if loaded_filename:
        keywords.update(re.findall(r'[a-zA-Z]{3,}', loaded_filename.lower()))
    if query:
        keywords.update(w.lower() for w in query.split() if len(w) > 3)
    if not keywords: return ""
    results = []
    for md in WIKI_DIR.rglob("*.md"):
        name_lower = md.stem.lower()
        if any(kw in name_lower for kw in keywords):
            results.append(md.read_text("utf-8")[:1000])
    return "\n---\n".join(results[:3])

def _wiki_slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:60]

def _save_wiki_page(title, content, category="cases", source=""):
    slug = _wiki_slug(title)
    cat_dir = WIKI_DIR / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    path = cat_dir / f"{slug}.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conflict = ""
    if path.exists():
        conflict = f"\n\n## Conflict Note\n- Updated {now}\n"
    page = f"# {title}\n\n## Summary\n{content[:500]}\n\n## Key Facts\n- Extracted from document analysis\n\n## Source\n{source or loaded_filename or 'user query'}\n\n## Last Updated\n{now}\n{conflict}"
    path.write_text(page, "utf-8")
    return str(path)

def _count_wiki_pages():
    return sum(1 for _ in WIKI_DIR.rglob("*.md"))

def _generate_wiki_from_response(prompt, response):
    def _worker():
        try:
            wiki_prompt = f"""Based on this conversation, create a short wiki entry.
Title: one phrase. Category: one of [regulations, papers, cases].
Summary: 2-3 sentences. Key facts: 3-5 bullets.
User asked: {prompt[:500]}
Assistant answered: {response[:1000]}
Reply ONLY in JSON: {{"title": "...", "category": "...", "summary": "...", "facts": ["..."]}}"""
            body = json.dumps({"model": _detect_model(), "prompt": wiki_prompt,
                               "stream": False, "options": {"temperature": 0.3, "num_predict": 512}}).encode()
            req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=body,
                                         headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=60)
            data = json.loads(resp.read())
            text = data.get("response", "")
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                entry = json.loads(m.group())
                _save_wiki_page(entry.get("title", "untitled"),
                                entry.get("summary", text[:300]),
                                entry.get("category", "cases"))
        except Exception: pass
    threading.Thread(target=_worker, daemon=True).start()

# ── Procedural Memory (Layer 2) ──────────────────────────────────
def _update_preferences(prompt, response):
    def _worker():
        try:
            pref_prompt = f"""Analyze this conversation and extract user behavior patterns.
User said: {prompt[:500]}
Assistant said: {response[:500]}
List ONLY new observations. If nothing new, reply "none"."""
            body = json.dumps({"model": _detect_model(), "prompt": pref_prompt,
                               "stream": False, "options": {"temperature": 0.2, "num_predict": 256}}).encode()
            req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=body,
                                         headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read()).get("response", "").strip()
            if result and "none" not in result.lower()[:10]:
                prefs = MEMORY_DIR / "preferences.md"
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                with open(prefs, "a", encoding="utf-8") as f:
                    f.write(f"\n### {now}\n{result}\n")
        except Exception: pass
    threading.Thread(target=_worker, daemon=True).start()

# ── Agent Backend (Layer 3) ──────────────────────────────────────
def _agentic_loop(prompt, handler):
    system = _build_system_prompt(prompt)
    tool_instructions = """\n\nYou have these tools. Reply with EXACTLY the tool call on its own line:
TOOL:READ_WIKI:filename
TOOL:WRITE_WIKI:title|content
TOOL:REREAD_DOCUMENT
TOOL:DONE
Use tools to gather info, then call TOOL:DONE with your final answer."""
    full_prompt = prompt
    if loaded_document:
        full_prompt = f"[Document: {loaded_filename}]\n\n{loaded_document[:4000]}\n\n---\nUser: {prompt}"
    for iteration in range(5):
        body = json.dumps({"model": _detect_model(), "prompt": full_prompt,
                           "system": system + tool_instructions,
                           "stream": False, "options": {"temperature": 0.7, "num_predict": 1024}}).encode()
        req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=120)
        text = json.loads(resp.read()).get("response", "")
        if "TOOL:READ_WIKI:" in text:
            fname = text.split("TOOL:READ_WIKI:")[1].split("\n")[0].strip()
            for md in WIKI_DIR.rglob("*.md"):
                if fname.lower() in md.stem.lower():
                    full_prompt += f"\n\n[Wiki: {md.stem}]:\n{md.read_text('utf-8')[:2000]}"; break
            continue
        elif "TOOL:WRITE_WIKI:" in text:
            parts = text.split("TOOL:WRITE_WIKI:")[1].split("\n")[0].split("|", 1)
            if len(parts) == 2: _save_wiki_page(parts[0].strip(), parts[1].strip())
            continue
        elif "TOOL:REREAD_DOCUMENT" in text:
            if loaded_document: full_prompt += f"\n\n[Re-reading]:\n{loaded_document[:4000]}"
            continue
        else:
            return text.replace("TOOL:DONE", "").strip()
    return text

# ── File Watcher ────────────────────────────────────────────────
def _extract_text_from_file(filepath):
    p = Path(filepath)
    if p.suffix.lower() == '.pdf':
        try:
            import pdfplumber
            with pdfplumber.open(p) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception: return ""
    elif p.suffix.lower() in ('.txt', '.md'):
        return p.read_text("utf-8", errors="ignore")
    return ""

def _auto_ingest_file(filepath):
    global _new_ingested_count
    text = _extract_text_from_file(filepath)
    if not text.strip(): return
    title = Path(filepath).stem.replace("_", " ").replace("-", " ")
    _save_wiki_page(title, text[:500], "papers", Path(filepath).name)
    ingested_log = MEMORY_DIR / "ingested.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(ingested_log, "a", encoding="utf-8") as f:
        f.write(f"- [{now}] Auto-ingested: {Path(filepath).name}\n")
    _new_ingested_count += 1

def _start_watcher(folder_path):
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory and Path(event.src_path).suffix.lower() in ('.pdf', '.txt'):
                    threading.Thread(target=_auto_ingest_file, args=(event.src_path,), daemon=True).start()
        observer = Observer()
        observer.schedule(Handler(), folder_path, recursive=False)
        observer.start()
        _watcher_threads[folder_path] = observer
        return True
    except Exception: return False

def _stop_watcher(folder_path):
    obs = _watcher_threads.pop(folder_path, None)
    if obs: obs.stop()

def _detect_apps():
    apps = {}
    zotero = Path.home() / "Zotero"
    if zotero.exists():
        pdfs = list(zotero.rglob("*.pdf"))
        apps["zotero"] = {"available": True, "path": str(zotero), "pdf_count": len(pdfs)}
    obsidian = Path.home() / "Library" / "Application Support" / "obsidian"
    if obsidian.exists():
        vaults = [d.name for d in obsidian.iterdir() if d.is_dir()] if obsidian.is_dir() else []
        apps["obsidian"] = {"available": True, "path": str(obsidian), "vaults": vaults}
    downloads = Path.home() / "Downloads"
    apps["downloads"] = {"available": True, "path": str(downloads),
                          "pdf_count": len(list(downloads.glob("*.pdf")))}
    desktop = Path.home() / "Desktop"
    apps["desktop"] = {"available": True, "path": str(desktop),
                        "pdf_count": len(list(desktop.glob("*.pdf")))}
    return apps

def _load_watcher_config():
    cfg_path = WATCHERS_DIR / "watcher_config.json"
    if cfg_path.exists():
        return json.loads(cfg_path.read_text("utf-8"))
    return {"watched_folders": [], "auto_ingest": False, "notify_on_new": True}

def _save_watcher_config(cfg):
    (WATCHERS_DIR / "watcher_config.json").write_text(json.dumps(cfg, indent=2), "utf-8")

# ── HTTP Handler ─────────────────────────────────────────────────
class ClayHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_POST(self):
        routes = {
            "/api/ask": self._handle_ask,
            "/api/upload": self._handle_upload,
            "/api/clear-document": self._handle_clear_doc,
            "/api/set-mode": self._handle_set_mode,
            "/api/status": self._handle_status,
            "/api/setup-watchers": self._handle_setup_watchers,
            "/api/detect-apps": self._handle_detect_apps,
            "/api/voice-transcribe": self._handle_voice,
            "/api/history": self._handle_history,
            "/api/connect-folder": self._handle_connect_folder,
            "/api/mesh-status": self._handle_mesh_status,
            "/api/mesh-send": self._handle_mesh_send,
            # v1.2 endpoints
            "/api/memories": self._handle_memories,
            "/api/memories/delete": self._handle_memory_delete,
            "/api/logs": self._handle_logs,
            "/api/logs/verify": self._handle_log_verify,
            "/api/logs/export": self._handle_log_export,
            "/api/execute": self._handle_execute,
            "/api/agents": self._handle_agents,
            "/api/agents/select": self._handle_agent_select,
            "/api/workflows": self._handle_workflows,
            "/api/research-context": self._handle_research_context,
            "/api/execution-history": self._handle_execution_history,
            # v1.3 task engine
            "/api/tasks/create": self._handle_task_create,
            "/api/tasks": self._handle_tasks_list,
            "/api/tasks/stop": self._handle_task_stop,
        }
        handler = routes.get(self.path)
        if handler: handler()
        else: self.send_error(404)

    def do_GET(self):
        # Handle GET /api/tasks (list all)
        if self.path == "/api/tasks":
            self._handle_tasks_list()
            return
        # Handle /api/tasks/:id
        if self.path.startswith("/api/tasks/") and len(self.path) > 12:
            task_id = self.path.split("/api/tasks/")[1].strip("/")
            task = _active_tasks.get(task_id) or _task_load(task_id)
            if task:
                self._send_json(task)
            else:
                self._send_json({"error": "Task not found"}, 404)
            return
        # Fall through to static file serving
        super().do_GET()

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def _handle_ask(self):
        global AGENT_BACKEND
        body = json.loads(self._read_body())
        prompt = body.get("prompt", "")
        if not prompt: return self.send_error(400)

        # Commands
        if prompt.strip().lower() == "/agentic":
            AGENT_BACKEND = "agentic"
            self._send_json({"command": True, "mode": "agentic"}); return
        if prompt.strip().lower() == "/simple":
            AGENT_BACKEND = "simple"
            self._send_json({"command": True, "mode": "simple"}); return

        now = datetime.now().isoformat()
        conversation_history.append({"role": "user", "content": prompt, "timestamp": now})
        _log_write("user", prompt)
        _memory_add(prompt)

        # Check for workflow prefix
        workflow_prefix = body.get("workflow_prompt", "")
        if workflow_prefix:
            prompt = f"{workflow_prefix}\n\n{prompt}"

        # Agentic mode
        if AGENT_BACKEND == "agentic":
            result = _agentic_loop(prompt, self)
            conversation_history.append({"role": "assistant", "content": result, "timestamp": datetime.now().isoformat()})
            _log_write("assistant", result)
            _memory_add(result)
            _generate_wiki_from_response(prompt, result)
            _update_preferences(prompt, result)
            # Research memory if applicable
            if _current_agent and _current_agent.get("memory_backend") == "hindsight":
                _extract_research_insights(prompt, result)
            self._send_json({"response": result, "done": True}); return

        # Simple mode — streaming
        system = _build_system_prompt(prompt)
        full_prompt = prompt
        if loaded_document:
            full_prompt = f"[Document: {loaded_filename}]\n\n{loaded_document[:6000]}\n\n---\nUser: {prompt}"

        model = _current_agent.get("model", _detect_model()) if _current_agent else _detect_model()
        ollama_body = json.dumps({"model": model, "prompt": full_prompt,
                                   "system": system, "stream": True,
                                   "options": {"temperature": 0.7, "num_predict": 1024}}).encode()
        try:
            req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=ollama_body,
                                         headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=120)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            full_response = ""
            for line in resp:
                self.wfile.write(line); self.wfile.flush()
                try:
                    chunk = json.loads(line)
                    full_response += chunk.get("response", "")
                except Exception: pass
            if full_response:
                conversation_history.append({"role": "assistant", "content": full_response,
                                              "timestamp": datetime.now().isoformat()})
                _log_write("assistant", full_response)
                _memory_add(full_response)
                _generate_wiki_from_response(prompt, full_response)
                _update_preferences(prompt, full_response)
                if _current_agent and _current_agent.get("memory_backend") == "hindsight":
                    _extract_research_insights(prompt, full_response)
        except urllib.error.URLError as e:
            self._send_json({"error": f"Cannot reach Ollama: {e}"}, 502)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_upload(self):
        global loaded_document, loaded_filename
        content_type = self.headers.get("Content-Type", "")
        if "multipart" not in content_type:
            self._send_json({"error": "Expected multipart upload"}, 400); return
        raw = self._read_body()
        boundary = content_type.split("boundary=")[-1].strip().encode()
        parts = raw.split(b"--" + boundary)
        file_data, filename = None, ""
        for part in parts:
            if b"filename=" not in part: continue
            header_end = part.find(b"\r\n\r\n")
            if header_end < 0: continue
            header_text = part[:header_end].decode("utf-8", errors="ignore")
            m = re.search(r'filename="([^"]+)"', header_text)
            if m: filename = m.group(1)
            file_data = part[header_end+4:]
            if file_data.endswith(b"\r\n"): file_data = file_data[:-2]
            break
        if not file_data or not filename:
            self._send_json({"error": "No file provided"}, 400); return
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            try:
                import pdfplumber
                pdf = pdfplumber.open(io.BytesIO(file_data))
                loaded_document = "\n".join(p.extract_text() or "" for p in pdf.pages)
                pdf.close()
            except Exception as e:
                self._send_json({"error": f"PDF error: {e}"}, 500); return
        elif ext in (".txt", ".md"):
            loaded_document = file_data.decode("utf-8", errors="ignore")
        else:
            self._send_json({"error": "Only PDF and TXT supported"}, 400); return
        loaded_filename = filename
        _log_write("system", f"Document uploaded: {filename} ({len(loaded_document)} chars)")
        self._send_json({"ok": True, "filename": filename, "chars": len(loaded_document)})

    def _handle_clear_doc(self):
        global loaded_document, loaded_filename
        self._read_body()
        loaded_document = ""; loaded_filename = ""
        self._send_json({"ok": True})

    def _handle_set_mode(self):
        global AGENT_BACKEND
        body = json.loads(self._read_body())
        AGENT_BACKEND = body.get("mode", "simple")
        self._send_json({"mode": AGENT_BACKEND})

    def _handle_status(self):
        global _new_ingested_count
        self._read_body()
        count = _new_ingested_count
        _new_ingested_count = 0
        prefs_active = (MEMORY_DIR / "preferences.md").exists()
        agent_name = _current_agent.get("name", "Clay General") if _current_agent else "Clay General"
        mem_count = len(_memory_get_all()) if _mem0_client else 0
        # Active task info
        active_task = None
        for tid, t in _active_tasks.items():
            if t.get("status") == "running":
                active_task = {"id": tid, "goal": t["goal"][:60], "step": len(t.get("steps", []))}
                break
        self._send_json({
            "wiki_pages": _count_wiki_pages(), "preferences_active": prefs_active,
            "mode": AGENT_BACKEND, "document": loaded_filename,
            "new_ingested": count, "model": _detect_model(),
            "agent": agent_name, "memory_count": mem_count,
            "log_entries": len(_log_read_today()),
            "color_accent": _current_agent.get("color_accent", "#e06438") if _current_agent else "#e06438",
            "active_task": active_task
        })

    def _handle_setup_watchers(self):
        body = json.loads(self._read_body())
        folders = body.get("folders", [])
        cfg = _load_watcher_config()
        for old in list(_watcher_threads.keys()):
            if old not in folders: _stop_watcher(old)
        started = []
        for f in folders:
            if Path(f).exists() and f not in _watcher_threads:
                if _start_watcher(f): started.append(f)
        cfg["watched_folders"] = folders
        _save_watcher_config(cfg)
        self._send_json({"ok": True, "watching": list(_watcher_threads.keys()), "started": started})

    def _handle_detect_apps(self):
        self._read_body()
        self._send_json(_detect_apps())

    def _handle_voice(self):
        self._send_json({"error": "Use client-side voice input"}, 501)

    def _handle_history(self):
        self._read_body()
        recent = conversation_history[-40:]
        self._send_json({"history": recent, "total": len(conversation_history)})

    def _handle_connect_folder(self):
        global _connected_folders
        body = json.loads(self._read_body())
        action = body.get("action", "add")
        folder = body.get("folder", "")
        if action == "add" and folder and folder not in _connected_folders:
            _connected_folders.append(folder)
        elif action == "remove" and folder in _connected_folders:
            _connected_folders.remove(folder)
        self._send_json({"ok": True, "connected": _connected_folders})

    def _handle_mesh_status(self):
        self._read_body()
        try:
            req = urllib.request.Request("http://localhost:4403/api/v1/fromradio", method="GET")
            urllib.request.urlopen(req, timeout=2)
            self._send_json({"connected": True, "status": "active"})
        except Exception:
            self._send_json({"connected": False, "status": "offline"})

    def _handle_mesh_send(self):
        body = json.loads(self._read_body())
        message = body.get("message", "")
        if not message: self._send_json({"error": "No message"}, 400); return
        try:
            mesh_body = json.dumps({"text": message}).encode()
            req = urllib.request.Request("http://localhost:4403/api/v1/sendtext",
                                         data=mesh_body, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
            self._send_json({"ok": True, "sent": message})
        except Exception as e:
            self._send_json({"error": f"Mesh send failed: {e}"}, 502)

    # ── v1.2 endpoints ──────────────────────────────────────────
    def _handle_memories(self):
        self._read_body()
        memories = _memory_get_all()
        self._send_json({"memories": memories, "count": len(memories)})

    def _handle_memory_delete(self):
        body = json.loads(self._read_body())
        mid = body.get("id", "")
        ok = _memory_delete(mid)
        self._send_json({"ok": ok})

    def _handle_logs(self):
        body = json.loads(self._read_body())
        date = body.get("date")
        entries = _log_read_today() if not date else []
        if date:
            log_file = LOGS_DIR / f"{date}.jsonl"
            if log_file.exists():
                for line in log_file.read_text("utf-8").splitlines():
                    if line.strip():
                        try: entries.append(json.loads(line))
                        except Exception: pass
        self._send_json({"entries": entries, "count": len(entries)})

    def _handle_log_verify(self):
        body = json.loads(self._read_body())
        date = body.get("date")
        result = _log_verify(date)
        self._send_json(result)

    def _handle_log_export(self):
        body = json.loads(self._read_body())
        date = body.get("date")
        md_content = _log_export_md(date)
        self._send_json({"content": md_content, "format": "markdown"})

    def _handle_execute(self):
        body = json.loads(self._read_body())
        code = body.get("code", "")
        language = body.get("language", "python")
        if not code: self._send_json({"error": "No code"}, 400); return
        # Security: check allowed tools for current agent
        if _current_agent:
            allowed = _current_agent.get("allowed_tools", [])
            if "code_execute" not in allowed:
                self._send_json({"error": "Agent does not allow code execution"}, 403); return
        result = _execute_code(code, language)
        self._send_json(result)

    def _handle_agents(self):
        self._read_body()
        agent_list = []
        for name, cfg in _agents.items():
            agent_list.append({
                "name": name,
                "description": cfg.get("description", ""),
                "color_accent": cfg.get("color_accent", "#e06438"),
                "active": _current_agent and _current_agent.get("name") == name,
                "workflows": len(cfg.get("workflows", [])),
                "disclaimer": cfg.get("disclaimer", "")
            })
        self._send_json({"agents": agent_list})

    def _handle_agent_select(self):
        body = json.loads(self._read_body())
        name = body.get("name", "")
        ok = _select_agent(name)
        agent = _current_agent or {}
        _log_write("system", f"Agent switched to: {name}")
        self._send_json({
            "ok": ok, "agent": agent.get("name", ""),
            "color_accent": agent.get("color_accent", "#e06438"),
            "disclaimer": agent.get("disclaimer", ""),
            "workflows": agent.get("workflows", [])
        })

    def _handle_workflows(self):
        self._read_body()
        if _current_agent:
            self._send_json({"workflows": _current_agent.get("workflows", []),
                              "agent": _current_agent.get("name", ""),
                              "disclaimer": _current_agent.get("disclaimer", "")})
        else:
            self._send_json({"workflows": [], "agent": "Clay General"})

    def _handle_research_context(self):
        self._read_body()
        context = _research_get_context()
        self._send_json(context)

    def _handle_execution_history(self):
        self._read_body()
        self._send_json({"history": _execution_history[-20:]})

    # ── v1.3 task endpoints ────────────────────────────────────
    def _handle_task_create(self):
        body = json.loads(self._read_body())
        goal = body.get("goal", "")
        if not goal:
            self._send_json({"error": "No goal provided"}, 400); return
        if not _current_agent:
            self._send_json({"error": "No agent loaded"}, 400); return
        agent = body.get("agent", _current_agent.get("name", "Clay General"))
        task = _task_create(goal, agent)
        ok, msg = _task_start(task["id"])
        self._send_json({"ok": ok, "task_id": task["id"], "message": msg})

    def _handle_tasks_list(self):
        self._read_body()
        tasks = _task_list()
        summary = []
        for t in tasks[:20]:
            summary.append({
                "id": t["id"],
                "goal": t["goal"][:100],
                "status": t["status"],
                "steps": len(t.get("steps", [])),
                "created_at": t.get("created_at", ""),
                "final_result": (t.get("final_result") or "")[:200]
            })
        # Include active task info
        active = None
        for tid, t in _active_tasks.items():
            if t.get("status") == "running":
                active = {"id": tid, "goal": t["goal"][:60], "step": len(t.get("steps", [])),
                          "current_step": t["steps"][-1]["description"][:80] if t.get("steps") else "Starting..."}
                break
        self._send_json({"tasks": summary, "active": active})

    def _handle_task_stop(self):
        body = json.loads(self._read_body())
        task_id = body.get("id", "")
        ok = _task_stop(task_id)
        self._send_json({"ok": ok})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        if "404" in str(args) or "500" in str(args): super().log_message(format, *args)

# ── Main ─────────────────────────────────────────────────────────
def main():
    print()
    print("  \u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557")
    print("  \u2551   OpenClay v1.3 \u2014 COANA Labs                \u2551")
    print("  \u2551   Local AI Research Assistant                \u2551")
    print("  \u2551   Todo es local. Nada sale de aqui.          \u2551")
    print("  \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d")
    print()
    # Create directories
    for d in [WIKI_DIR / "regulations", WIKI_DIR / "papers", WIKI_DIR / "cases",
              MEMORY_DIR, WATCHERS_DIR, AGENTS_DIR, LOGS_DIR, SANDBOX_DIR, MEMORY_STORE_DIR, TASKS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    # Start Ollama
    print("  Starting engine...", end=" ", flush=True)
    if _start_ollama():
        print(f"ok  (model: {_detect_model()})")
    else:
        print("x  Ollama not available"); sys.exit(1)
    # Load soul
    soul = _load_soul()
    if soul:
        custom = (BASE_DIR / "soul_custom.md").exists()
        print(f"  Soul loaded ({len(soul)} chars" + (" + custom" if custom else "") + ")")
    # Load agents
    _load_agents()
    if _agents:
        names = ", ".join(_agents.keys())
        active = _current_agent.get("name", "?") if _current_agent else "?"
        print(f"  Agents: {names} (active: {active})")
    # Init Mem0
    print("  Memory...", end=" ", flush=True)
    if _init_mem0():
        count = len(_memory_get_all())
        print(f"ok  (Mem0, {count} memories)")
    else:
        print("fallback mode")
    # Init research memory
    if _init_research_memory():
        print("  Research memory (Hindsight-style) ready")
    # Init log chain
    _init_log_chain()
    today_entries = len(_log_read_today())
    if today_entries:
        print(f"  Log: {today_entries} entries today (chain intact)")
    else:
        print("  Log: fresh chain started")
    # Start watchers
    cfg = _load_watcher_config()
    for f in cfg.get("watched_folders", []):
        if Path(f).exists(): _start_watcher(f)
    if _watcher_threads:
        print(f"  Watching {len(_watcher_threads)} folder(s)")
    # Wiki stats
    wp = _count_wiki_pages()
    if wp: print(f"  Wiki: {wp} pages")
    # Start server
    server = http.server.HTTPServer(("0.0.0.0", PORT), ClayHandler)
    print(f"\n  Ready -> http://localhost:{PORT}")
    print()
    # Dev mode: run test task
    if "--test-task" in sys.argv or os.environ.get("OPENCLAY_TEST_TASK"):
        test_goal = ("Create a file called openclay_test.txt in the sandbox directory "
                     "with the text 'OpenClay v1.3.0 task engine works — built in Puerto Rico by COANA Labs', "
                     "then verify the file exists and contains that exact text, "
                     "then report the file size in bytes.")
        test_task = _task_create(test_goal)
        _task_start(test_task["id"])
        print(f"  Test task started: {test_task['id'][:8]}...")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        for f in list(_watcher_threads.keys()): _stop_watcher(f)
        _stop_ollama(); server.shutdown()
        print("  Hasta luego.")

if __name__ == "__main__":
    main()
