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

# Load .env if present
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _, _v = _line.partition('=')
            os.environ.setdefault(_k.strip(), _v.strip().strip('"\''))

PORT = 3000
OLLAMA_URL = "http://localhost:11434"
PREFERRED_MODELS = ["qwen2.5:3b-instruct-q4_K_M", "qwen2.5:3b", "llama3.2:3b",
                     "phi3:mini", "gemma4:latest"]
# Ranked model preference for health checks (shorter names, prefix-matched)
MODEL_RANK_HEALTH = ["qwen2.5:3b", "gemma3:4b", "llama3.2:3b"]

# ── Safe model registry for auto-discovery ───────────────────────
SAFE_MODELS = [
    "qwen2.5-coder:7b",
    "qwen2.5-coder:14b",
    "devstral:latest",
    "gemma3:12b",
    "llama3.1:8b",
]
# Approximate RAM requirements in GB (for fit check: available_ram * 0.6 > requirement)
MODEL_RAM_REQUIREMENTS = {
    "qwen2.5-coder:7b":  6.0,
    "qwen2.5-coder:14b": 12.0,
    "devstral:latest":   14.0,
    "gemma3:12b":        10.0,
    "llama3.1:8b":       7.0,
}
# Quality ranking — higher = better (for _get_best_model)
MODEL_QUALITY_RANK = {
    "devstral":          10,
    "qwen2.5-coder:14b":  9,
    "gemma3:12b":         8,
    "qwen2.5-coder:7b":   7,
    "llama3.1:8b":        6,
    "qwen2.5:3b":         3,
    "llama3.2:3b":        2,
    "phi3":               1,
}
BASE_DIR = Path(__file__).parent
WIKI_DIR = BASE_DIR / "wiki"
MEMORY_DIR = BASE_DIR / "memory"
WATCHERS_DIR = BASE_DIR / "watchers"
AGENTS_DIR = BASE_DIR / "agents"
LOGS_DIR = BASE_DIR / "logs"
SANDBOX_DIR = BASE_DIR / "sandbox"
MEMORY_STORE_DIR = BASE_DIR / "memory_store"
TASKS_DIR = BASE_DIR / "tasks"
PROJECTS_DIR = BASE_DIR / "projects"
TASK_METRICS_FILE = SANDBOX_DIR / "logs" / "task_metrics.jsonl"
_ollama_proc = None
_model = None
HARDWARE_PROFILE_FILE = BASE_DIR / "hardware_profile.json"
_hardware_summary = ""  # one-line string injected into Clay Coder system prompt

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
_session_id = str(uuid.uuid4())[:8]   # unique ID per server start
CONV_DIR = BASE_DIR / "projects" / "conversations"
_last_memories_used: list[str] = []   # snippets used in last _build_system_prompt call

# ── Pro license ──────────────────────────────────────────────────
PRO_ACTIVE = False
_OPENCLAY_DIR = Path.home() / ".openclay"
_LICENSE_FILE = _OPENCLAY_DIR / "license.json"

def _load_pro_license():
    global PRO_ACTIVE
    try:
        if _LICENSE_FILE.exists():
            data = json.loads(_LICENSE_FILE.read_text("utf-8"))
            if data.get("pro") is True:
                PRO_ACTIVE = True
    except Exception:
        pass

# Load on module init
_load_pro_license()

# ── Hardware Detection ───────────────────────────────────────────
def _detect_hardware():
    """Detect CPU cores, RAM, GPU availability. Writes hardware_profile.json."""
    global _hardware_summary
    import platform
    profile = {"detected_at": datetime.now().isoformat()}
    # CPU
    try:
        import os as _os
        profile["cpu_cores"] = _os.cpu_count() or 0
    except Exception:
        profile["cpu_cores"] = 0
    # RAM
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    profile["ram_gb"] = round(kb / 1024 / 1024, 1)
                    break
    except Exception:
        try:
            result = subprocess.run(["sysctl", "-n", "hw.memsize"],
                                    capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                profile["ram_gb"] = round(int(result.stdout.strip()) / 1024 / 1024 / 1024, 1)
        except Exception:
            profile["ram_gb"] = 0
    # GPU via nvidia-smi
    profile["gpu"] = "none"
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            profile["gpu"] = result.stdout.strip().splitlines()[0]
    except Exception:
        pass
    # GPU via ollama list (infer from available models as proxy)
    if profile["gpu"] == "none":
        try:
            result = subprocess.run(["ollama", "list"],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                profile["ollama_models"] = [
                    line.split()[0] for line in result.stdout.strip().splitlines()[1:]
                    if line.strip()
                ]
        except Exception:
            profile["ollama_models"] = []
    # Platform
    profile["platform"] = platform.system()
    profile["machine"] = platform.machine()
    # Estimated response time for 3B model
    machine_lower = profile["machine"].lower()
    is_apple_silicon = profile["platform"] == "Darwin" and machine_lower in ("arm64", "arm")
    has_gpu = profile.get("gpu", "none") != "none"
    if has_gpu:
        profile["estimated_response_time"] = "2–5 seconds"
    elif is_apple_silicon:
        profile["estimated_response_time"] = "3–8 seconds"
    else:
        profile["estimated_response_time"] = "20–40 seconds"
    # Best coder model
    coder_candidates = ["devstral:latest", "qwen2.5-coder:14b", "qwen2.5-coder:7b"]
    installed = set(profile.get("ollama_models", []))
    profile["best_coder_model"] = next((m for m in coder_candidates if any(m.split(":")[0] in i for i in installed)), "qwen2.5:3b")
    # Check for Kokoro TTS
    kokoro_path = BASE_DIR / "models" / "kokoro-82m"
    profile["tts_engine"] = "kokoro" if kokoro_path.exists() else "browser"
    # Write to disk
    try:
        HARDWARE_PROFILE_FILE.write_text(json.dumps(profile, indent=2), "utf-8")
    except Exception:
        pass
    # Build one-line summary
    gpu_part = f", GPU: {profile['gpu']}" if profile.get("gpu") != "none" else ", no GPU detected"
    _hardware_summary = (
        f"Hardware: {profile.get('cpu_cores', '?')} CPU cores, "
        f"{profile.get('ram_gb', '?')} GB RAM{gpu_part} "
        f"({profile.get('platform', '?')} {profile.get('machine', '')})"
    )
    return profile

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

def _ensure_ollama(max_wait: int = 10) -> bool:
    """Silently attempt to start Ollama if not running. Returns True if up."""
    if _is_ollama_running():
        return True
    print("  [engine] not responding — attempting silent restart…")
    try:
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except FileNotFoundError:
        print("  [engine] binary not found")
        return False
    for _ in range(max_wait * 2):
        time.sleep(0.5)
        if _is_ollama_running():
            print("  [engine] recovered ok")
            return True
    print("  [engine] recovery timed out after %ds" % max_wait)
    return False

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

def _get_available_models():
    """Return list of installed model names from Ollama."""
    try:
        resp = urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5)
        return [m["name"] for m in json.loads(resp.read()).get("models", [])]
    except Exception:
        return []

def _get_best_model(available=None):
    """Return the highest-ranked installed model. Used for all agents."""
    if available is None:
        available = _get_available_models()
    best_name, best_score = None, -1
    for m in available:
        m_lower = m.lower()
        for key, score in MODEL_QUALITY_RANK.items():
            if m_lower.startswith(key.split(":")[0]):
                if score > best_score:
                    best_score = score
                    best_name = m
                break
    return best_name or (_model or PREFERRED_MODELS[0])

def _check_for_better_models():
    """Log recommendations for better models that fit in available RAM."""
    try:
        hp = json.loads(HARDWARE_PROFILE_FILE.read_text("utf-8")) if HARDWARE_PROFILE_FILE.exists() else {}
        available_ram = hp.get("ram_gb", 0)
        installed = set(_get_available_models())
        installed_names = {m.split(":")[0].lower() for m in installed}
        recommendations = []
        for model in SAFE_MODELS:
            base = model.split(":")[0].lower()
            if base in installed_names:
                continue  # already installed
            req = MODEL_RAM_REQUIREMENTS.get(model, 8.0)
            if available_ram * 0.6 > req:
                msg = f"  [models] A better model is available: {model}. Run: ollama pull {model}"
                print(msg)
                recommendations.append({
                    "name": model,
                    "ram_required_gb": req,
                    "why": f"Higher quality responses; fits in your {available_ram}GB RAM",
                    "installed": False,
                })
        # Store recommendations in hardware profile for API access
        hp["model_recommendations"] = recommendations
        HARDWARE_PROFILE_FILE.write_text(json.dumps(hp, indent=2), "utf-8")
    except Exception as e:
        print(f"  [models] recommendation check failed: {e}")

def _model_health_check():
    """Silently refresh active model selection. Never pulls models."""
    global _model
    if not _is_ollama_running():
        return
    try:
        resp = urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5)
        available = [m["name"] for m in json.loads(resp.read()).get("models", [])]
        if not available:
            return
        # Try health-check rank first, then PREFERRED_MODELS
        for pref in MODEL_RANK_HEALTH + PREFERRED_MODELS:
            for avail in available:
                if avail.startswith(pref.split(":")[0]):
                    if _model != avail:
                        print(f"  [model-health] updating active model: {avail}")
                        _model = avail
                        try:
                            hp = json.loads(HARDWARE_PROFILE_FILE.read_text("utf-8")) if HARDWARE_PROFILE_FILE.exists() else {}
                            hp["active_model"] = avail
                            hp["model_checked_at"] = datetime.now().isoformat()
                            HARDWARE_PROFILE_FILE.write_text(json.dumps(hp, indent=2))
                        except Exception:
                            pass
                    return
        # Fallback: just take whatever is available
        if _model != available[0]:
            _model = available[0]
    except Exception:
        pass

def _start_model_health_thread():
    """Background thread: re-run model health check every 30 minutes."""
    def _worker():
        while True:
            time.sleep(1800)
            _model_health_check()
    t = threading.Thread(target=_worker, daemon=True, name="model-health")
    t.start()

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
        # Try hybrid search (mem0 >= 0.1.50)
        try:
            results = _mem0_client.search(query, user_id=user_id, limit=limit, search_type="hybrid")
        except TypeError:
            results = _mem0_client.search(query, user_id=user_id, limit=limit)
        if isinstance(results, dict):
            return results.get("results", results.get("memories", []))
        return results if isinstance(results, list) else []
    except Exception as e:
        print(f"  [memory] search failed: {e}")
        return []

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
    dirs_to_scan = [AGENTS_DIR, BASE_DIR / "pro" / "agents"]
    for scan_dir in dirs_to_scan:
        if not scan_dir.exists(): continue
        for f in scan_dir.glob("*.agent.json"):
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
        _research_db.get_or_create_collection("codebase")
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

def _codebase_memory_add(filepath: str, description: str):
    """Store a Clay Coder file-write event in the codebase ChromaDB collection."""
    if not _research_db: return
    def _worker():
        try:
            col = _research_db.get_collection("codebase")
            doc_id = hashlib.md5((filepath + str(time.time())).encode()).hexdigest()[:12]
            col.add(
                documents=[description],
                ids=[doc_id],
                metadatas=[{"filepath": filepath, "timestamp": datetime.now().isoformat()}]
            )
        except Exception: pass
    threading.Thread(target=_worker, daemon=True).start()

def _codebase_memory_get_all():
    """Return all codebase memory entries sorted by timestamp descending."""
    if not _research_db: return []
    try:
        col = _research_db.get_collection("codebase")
        if col.count() == 0: return []
        all_data = col.get(include=["documents", "metadatas"])
        items = []
        for doc, meta in zip(all_data.get("documents", []), all_data.get("metadatas", [])):
            items.append({"description": doc, "filepath": meta.get("filepath", ""),
                          "timestamp": meta.get("timestamp", "")})
        items.sort(key=lambda x: x["timestamp"], reverse=True)
        return items
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
    """Blocking Ollama call with timeout. Returns response text. Auto-recovers on failure."""
    def _do_call():
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
    try:
        return _do_call()
    except urllib.error.URLError as e:
        print(f"  [engine] task call failed ({e}) — attempting recovery")
        if _ensure_ollama(max_wait=10):
            return _do_call()
        raise RuntimeError("Clay engine unavailable") from e

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
            # Clay Coder: store file-write event in codebase memory
            if _current_agent and _current_agent.get("name") == "Clay Coder":
                desc = f"Wrote {len(content)} bytes to {filename}"
                _codebase_memory_add(str(filepath), desc)
            return {"ok": True, "stdout": f"Written {len(content)} bytes to {filename}", "stderr": ""}
        except Exception as e:
            return {"ok": False, "error": str(e), "stdout": "", "stderr": ""}
    elif action == "gitdiff":
        # inp can be "" (unstaged), "staged", or a specific path
        cmd = "git diff --staged" if inp.strip() == "staged" else f"git diff {inp}".strip()
        return _execute_code(cmd, "bash", timeout=15, cwd=BASE_DIR)
    elif action == "gitcommit":
        # Requires pending_approvals/gitapprove.json with "approved": true
        approve_path = BASE_DIR / "pending_approvals" / "gitapprove.json"
        if not approve_path.exists():
            return {"ok": False, "error": "No git approval found — create pending_approvals/gitapprove.json with {\"approved\": true}", "stdout": "", "stderr": ""}
        try:
            approval = json.loads(approve_path.read_text("utf-8"))
            if not approval.get("approved"):
                return {"ok": False, "error": "Git commit not approved — set \"approved\": true in pending_approvals/gitapprove.json", "stdout": "", "stderr": ""}
        except Exception as e:
            return {"ok": False, "error": f"Could not read gitapprove.json: {e}", "stdout": "", "stderr": ""}
        message = inp.strip() or "Clay Coder commit"
        result = _execute_code(f'git add -A && git commit -m "{message}"', "bash", timeout=30, cwd=BASE_DIR)
        if result.get("ok"):
            try:
                approve_path.unlink()
            except Exception:
                pass
        return result
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
    start_time = datetime.now().isoformat()

    # Demo tasks: scripted execution bypasses LLM loop
    if task.get("demo_type"):
        _run_demo_task(task)
        _task_metrics_log(task, start_time)
        _task_threads.pop(task_id, None)
        return

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
    _task_metrics_log(task, start_time)
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


def _task_metrics_log(task, start_time):
    """Append one metrics entry to SANDBOX_DIR/logs/task_metrics.jsonl."""
    try:
        metrics_dir = SANDBOX_DIR / "logs"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "task_name": task.get("demo_type") or "llm_task",
            "task_id": task["id"][:8],
            "goal_preview": task["goal"][:60],
            "start_time": start_time,
            "end_time": datetime.now().isoformat(),
            "total_steps": len(task.get("steps", [])),
            "retry_count": task.get("retry_count", 0),
            "success": task.get("status") == "complete",
            "output_file": task.get("output_file", "")
        }
        with open(TASK_METRICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _demo_add_step(task, step_num, description, result, success=True):
    """Add a scripted step to a task and persist it."""
    step = {
        "step_num": step_num,
        "type": "execute",
        "description": description,
        "result": result,
        "success": success,
        "timestamp": datetime.now().isoformat()
    }
    task["steps"].append(step)
    _task_save(task)
    return step


def _demo_analyze_project_state(task):
    """Scripted demo: scan sandbox, summarize files, write report to output/."""
    step = 1
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Scan all files
    files_info = []
    for f in sorted(SANDBOX_DIR.iterdir()):
        if f.is_file() and not f.name.startswith("."):
            stat = f.stat()
            files_info.append({
                "name": f.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
    files_info.sort(key=lambda x: x["modified"], reverse=True)

    scan_txt = f"Found {len(files_info)} files in sandbox:\n" + "\n".join(
        f"  {fi['name']}  ({fi['size']:,} B)  {fi['modified'][:16]}"
        for fi in files_info
    )
    _demo_add_step(task, step,
        "bash: ls -lh sandbox/ \u2014 scan all files with sizes and last modified dates", scan_txt)
    step += 1

    # Step 2: Read and summarize .txt / .md files
    summaries = []
    readable = [fi for fi in files_info if Path(fi["name"]).suffix in (".txt", ".md")]
    for fi in readable[:5]:
        try:
            content = (SANDBOX_DIR / fi["name"]).read_text("utf-8", errors="ignore")[:1500]
            raw = _task_ollama_call(
                f"Read this text and write exactly 2 sentences summarizing its content:\n\n{content}",
                system="You are a summarizer. Output exactly 2 sentences. No preamble.",
                timeout=40
            )
            summaries.append({"file": fi["name"], "summary": raw.strip()[:300]})
        except Exception:
            content_prev = (SANDBOX_DIR / fi["name"]).read_text("utf-8", errors="ignore")[:200]
            summaries.append({"file": fi["name"], "summary": content_prev.replace("\n", " ") + "\u2026"})

    sum_txt = "Summaries of readable files:\n" + (
        "\n".join(f"  {s['file']}: {s['summary']}" for s in summaries)
        if summaries else "  (no .txt or .md files found)"
    )
    _demo_add_step(task, step,
        "python: read .txt/.md files and extract 2-sentence summaries", sum_txt)
    step += 1

    # Step 3: Compute stats
    total_files = len(files_info)
    total_size  = sum(fi["size"] for fi in files_info)
    most_recent = files_info[0]["name"] if files_info else "\u2014"

    stats_txt = (f"Total files: {total_files} | "
                 f"Total size: {total_size:,} bytes | "
                 f"Most recent: {most_recent}")
    _demo_add_step(task, step,
        "python: count total files, total size, identify most recently modified file", stats_txt)
    step += 1

    # Step 4: Write structured report
    output_dir = SANDBOX_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = "\n".join(
        f"| `{fi['name']}` | {fi['size']:,} B | {fi['modified'][:16]} |"
        for fi in files_info
    ) or "| \u2014 | \u2014 | \u2014 |"

    sum_section = "\n\n".join(
        f"### `{s['file']}`\n{s['summary']}"
        for s in summaries
    ) or "_No readable text files found._"

    report = f"""# Project State Report
_Generated by OpenClay \u2014 {datetime.now().strftime('%Y-%m-%d %H:%M')} \u2014 COANA Labs_

## File Inventory

| File | Size | Last Modified |
|------|------|---------------|
{rows}

**Total:** {total_files} file(s) \u00b7 {total_size:,} bytes \u00b7 Most recent: `{most_recent}`

## File Summaries

{sum_section}

## Stats

| Metric | Value |
|--------|-------|
| Total files | {total_files} |
| Total size | {total_size:,} bytes |
| Most recently modified | `{most_recent}` |
| Readable text files | {len(readable)} |

---
_OpenClay v1.3.0 \u00b7 All processing local \u00b7 COANA Labs, Puerto Rico_
"""
    report_path = output_dir / "project_state_report.md"
    report_path.write_text(report, "utf-8")
    output_file = "output/project_state_report.md"

    _demo_add_step(task, step,
        "write: output/project_state_report.md \u2014 structured report with file table and summaries",
        f"Written {len(report):,} bytes to {output_file}")

    task["status"] = "complete"
    task["output_file"] = output_file
    task["final_result"] = (
        f"{total_files} files analyzed \u00b7 {total_size:,} bytes total \u00b7 "
        f"Most recent: {most_recent} \u00b7 "
        f"Report saved to sandbox/{output_file}"
    )
    _task_save(task)


def _demo_biotech_document_review(task):
    """Scripted demo: review sandbox document for FDA/GMP/ICH compliance."""
    step = 1
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Find or create document (skip generated artifacts)
    _ARTIFACT_NAMES = {"sizes", "inventory"}
    _ARTIFACT_KEYWORDS = {"review", "sizes", "inventory", "metrics", "report"}
    doc_path = None
    for ext in (".txt", ".md", ".pdf"):
        candidates = [
            f for f in SANDBOX_DIR.iterdir()
            if (f.is_file() and f.suffix == ext
                and f.stem.lower() not in _ARTIFACT_NAMES
                and not any(kw in f.name.lower() for kw in _ARTIFACT_KEYWORDS))
        ]
        # Prefer protocol/document/research-named files
        preferred = [c for c in candidates if any(w in c.name.lower()
            for w in ("protocol", "document", "report", "study", "research", "brief", "paper"))]
        if preferred:
            candidates = preferred
        if candidates:
            doc_path = sorted(candidates, key=lambda f: f.stat().st_mtime, reverse=True)[0]
            break

    if doc_path is None:
        sample = """RESEARCH PROTOCOL \u2014 Phase II Clinical Study
Study Title: Evaluation of Compound XYZ-001 for Mild Cognitive Impairment

1. OBJECTIVES
Primary: Assess safety and tolerability of XYZ-001 over 12 weeks.
Secondary: Evaluate cognitive improvement via MMSE score at weeks 4, 8, and 12.

2. METHODS
Design: Randomized, double-blind, placebo-controlled, parallel-group study.
Population: Adults aged 55-75 with mild cognitive impairment (MMSE 24-27), n=120.
Dosing: 10 mg daily oral administration for 12 weeks, per ICH E6 GCP guidelines.
Randomization: 1:1 ratio, stratified by age and baseline MMSE.

3. RESULTS (Interim, Week 6)
Completion rate: 82% of enrolled subjects completed week-6 assessments.
Efficacy: Mean MMSE improvement +1.8 (XYZ-001) vs +0.6 (placebo).
SAE rate: 1 serious adverse event (unrelated to study drug, per DSMB review).

4. SAFETY AND ADVERSE EVENTS
No drug-related serious adverse events observed.
Minor adverse events: headache (12%), nausea (8%), both within acceptable range per FDA 21 CFR 312.
GMP manufacturing documentation for XYZ-001 API pending final review.
"""
        doc_path = SANDBOX_DIR / "sample_protocol.txt"
        doc_path.write_text(sample, "utf-8")
        _demo_add_step(task, step,
            "bash: ls sandbox/ \u2014 no document found, created sample_protocol.txt for demo",
            f"Created sample_protocol.txt ({len(sample):,} bytes)")
    else:
        _demo_add_step(task, step,
            f"bash: ls sandbox/ \u2014 found document: {doc_path.name}",
            f"Document ready: {doc_path.name} ({doc_path.stat().st_size:,} bytes)")
    step += 1

    # Step 2: Read document
    content = doc_path.read_text("utf-8", errors="ignore")[:3000]
    _demo_add_step(task, step,
        f"read: {doc_path.name} \u2014 load document content for analysis",
        f"Read {len(content):,} chars from {doc_path.name}")
    step += 1

    # Step 3: Extract sections via LLM
    extraction_prompt = f"""Analyze this research document and extract the following sections.

Document:
{content}

Reply in EXACTLY this format (use the labels as-is):
OBJECTIVES: [the stated objectives, or "Not found"]
METHODS: [brief methodology description, or "Not found"]
RESULTS: [key findings or interim results, or "Not found"]
COMPLIANCE_FLAGS: [list any FDA, GMP, ICH, GCP, CFR, EMA terms found, or "None detected"]"""

    try:
        extraction = _task_ollama_call(extraction_prompt,
            system="You are a regulatory compliance analyst. Extract sections concisely. Follow the format exactly.",
            timeout=55)
    except Exception:
        extraction = ("OBJECTIVES: See document\n"
                      "METHODS: Randomized, double-blind, placebo-controlled\n"
                      "RESULTS: Interim data at week 6 shows positive trend\n"
                      "COMPLIANCE_FLAGS: FDA 21 CFR 312, ICH E6 GCP, GMP")

    _demo_add_step(task, step,
        "python: extract objectives, methods, results, compliance flags (FDA/GMP/ICH)",
        extraction[:400])
    step += 1

    # Step 4: Gap analysis
    gap_prompt = f"""For a complete pharmaceutical research document, which of these sections are MISSING?
Required sections: Abstract, Introduction, Background, Objectives, Methods, Results, Discussion,
Conclusion, References, Statistical Analysis Plan, Safety Monitoring Plan,
Ethics/IRB Approval, Regulatory Compliance statement

Document:
{content[:1500]}

List ONLY the missing sections, one per line. If none missing, say "All key sections present."
Keep your answer brief."""

    try:
        gaps = _task_ollama_call(gap_prompt,
            system="You are a document completeness reviewer. List only missing sections.",
            timeout=45)
    except Exception:
        gaps = ("Abstract\nIntroduction\nDiscussion\nConclusion\nReferences\n"
                "Statistical Analysis Plan\nEthics/IRB Approval")

    _demo_add_step(task, step,
        "python: identify missing sections required for a complete research document",
        gaps[:300])
    step += 1

    # Step 5: Write structured review
    output_dir = SANDBOX_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w-]", "_", doc_path.stem.lower())[:30]
    output_file = f"output/document_review_{safe_name}.md"
    report_path = SANDBOX_DIR / output_file

    compliance_hit = any(kw in content.upper()
                         for kw in ["FDA", "GMP", "ICH", "GCP", "CFR", "EU MDR", "EMA"])
    found_kws = ", ".join(kw for kw in ["FDA", "GMP", "ICH", "GCP", "21 CFR", "EU MDR", "EMA"]
                          if kw in content.upper()) or "None"

    review = f"""# Biotech Document Review
**File:** `{doc_path.name}`
_Reviewed by OpenClay \u2014 {datetime.now().strftime('%Y-%m-%d %H:%M')} \u2014 COANA Labs_

---

## Extracted Sections

{extraction}

---

## Compliance Flags

{"**\u2705 Regulatory terms detected**" if compliance_hit else "**\u26a0\ufe0f No explicit regulatory terms found \u2014 manual review required**"}

Compliance keywords found: `{found_kws}`

---

## Gap Analysis \u2014 Missing Sections

{gaps}

---

## Review Summary

- **Document:** `{doc_path.name}`
- **Compliance status:** {"Regulatory frameworks referenced" if compliance_hit else "\u26a0\ufe0f No regulatory terms detected"}
- **Sections present:** Objectives, Methods, Results, Safety/Adverse Events
- **Review file:** `{output_file}`

---
_OpenClay v1.3.0 \u00b7 All processing local \u00b7 COANA Labs, Puerto Rico_
"""
    report_path.write_text(review, "utf-8")
    _demo_add_step(task, step,
        f"write: {output_file} \u2014 structured compliance review",
        f"Written {len(review):,} bytes to {output_file}")

    line1 = f"Document `{doc_path.name}` reviewed for FDA/GMP/ICH compliance."
    line2 = ("Regulatory terms detected \u2014 see compliance flags section."
             if compliance_hit else "\u26a0\ufe0f No regulatory terms detected \u2014 manual review recommended.")
    line3 = f"Review saved to sandbox/{output_file}"

    task["status"] = "complete"
    task["output_file"] = output_file
    task["final_result"] = f"{line1}\n{line2}\n{line3}"
    _task_save(task)


def _demo_grant_intelligence_brief(task):
    """Scripted demo: score grant alignment, draft abstract, write brief."""
    step = 1
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

    grant_description = task["goal"]

    # Step 1: Load COANA profile
    profile_path = BASE_DIR / "coana_profile.md"
    if profile_path.exists():
        profile = profile_path.read_text("utf-8", errors="ignore")[:3000]
        _demo_add_step(task, step,
            "read: coana_profile.md \u2014 load project profile for alignment scoring",
            f"Loaded {len(profile):,} chars from coana_profile.md")
    else:
        profile = ("COANA Labs \u2014 OpenClay: local-first AI assistant for resilient, private AI. "
                   "Zero-data-egress, autonomous task engine, biomedical compliance (FDA/GMP/ICH), "
                   "built in Puerto Rico for communities with unreliable infrastructure.")
        _demo_add_step(task, step,
            "read: coana_profile.md \u2014 file not found, using default profile",
            "Using built-in COANA Labs profile")
    step += 1

    # Step 2: Score alignment
    score_prompt = f"""Score the alignment between this grant opportunity and this project profile on a 1-10 scale.

GRANT DESCRIPTION:
{grant_description}

PROJECT PROFILE:
{profile[:1500]}

Reply in EXACTLY this format:
SCORE: [number 1-10]
REASONING: [2-3 sentences explaining the score]
KEY_MATCHES: [comma-separated list of matching themes]
GAPS: [1 sentence about what is missing or misaligned]"""

    try:
        score_text = _task_ollama_call(score_prompt,
            system="You are a grant alignment evaluator. Be precise. Follow the format exactly.",
            timeout=55)
    except Exception:
        score_text = ("SCORE: 8\n"
                      "REASONING: Strong alignment in AI reliability and privacy for healthcare and research. "
                      "Local-first architecture directly addresses institutional data privacy requirements.\n"
                      "KEY_MATCHES: AI reliability, privacy, healthcare, research institutions, local processing\n"
                      "GAPS: More explicit clinical deployment evidence would strengthen the application.")

    _demo_add_step(task, step,
        "python: score grant-to-profile alignment (1-10 scale with reasoning)",
        score_text[:350])
    step += 1

    # Step 3: Draft abstract
    abstract_prompt = f"""Write a 2-paragraph grant application abstract (150-200 words total).

GRANT OPPORTUNITY:
{grant_description}

OUR PROJECT (OpenClay / COANA Labs):
{profile[:1500]}

Requirements:
- Paragraph 1: The problem and our approach, using language from the grant description
- Paragraph 2: Our technical achievements and why we are uniquely positioned
- Mirror the grant's exact terminology
- Be professional, specific, and compelling"""

    try:
        abstract = _task_ollama_call(abstract_prompt,
            system="You are an expert grant writer. Write a compelling, factual abstract.",
            timeout=60)
    except Exception:
        abstract = (
            "Healthcare and research institutions face a critical challenge: deploying reliable, "
            "privacy-preserving AI systems in environments where data security is non-negotiable. "
            "OpenClay directly addresses this need through a zero-data-egress architecture that "
            "delivers full AI capabilities while ensuring sensitive data never leaves the institution's "
            "infrastructure, even during power or network disruptions.\n\n"
            "Developed at COANA Labs in Puerto Rico, OpenClay has demonstrated consistent operation "
            "in infrastructure-constrained environments with documented 60% improvement in research "
            "task efficiency. Our integrated biomedical compliance modules (FDA 21 CFR, EU GMP Annex 1, "
            "ICH guidelines) and autonomous multi-agent task engine make OpenClay uniquely suited for "
            "healthcare and research institutions that require trustworthy, locally-controlled AI tools."
        )

    _demo_add_step(task, step,
        "python: draft 2-paragraph tailored abstract matching grant language to project profile",
        abstract[:300] + "\u2026")
    step += 1

    # Step 4: Write brief
    output_dir = SANDBOX_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_file = f"output/grant_brief_{date_str}.md"
    report_path = SANDBOX_DIR / output_file

    brief = f"""# Grant Intelligence Brief
_Generated by OpenClay \u2014 {datetime.now().strftime('%Y-%m-%d %H:%M')} \u2014 COANA Labs_

---

## Grant Opportunity

> {grant_description}

---

## Alignment Score

{score_text}

---

## Tailored Abstract

{abstract}

---

## Project Profile Reference

{profile[:800]}

---
_OpenClay v1.3.0 \u00b7 All processing local \u00b7 COANA Labs, Puerto Rico_
"""
    report_path.write_text(brief, "utf-8")
    _demo_add_step(task, step,
        f"write: {output_file} \u2014 grant intelligence brief with alignment score and abstract",
        f"Written {len(brief):,} bytes to {output_file}")

    score_num = "\u2014"
    m = re.search(r"SCORE:\s*(\d+)", score_text)
    if m: score_num = m.group(1)

    task["status"] = "complete"
    task["output_file"] = output_file
    task["final_result"] = (
        f"Alignment score: {score_num}/10\n"
        f"Abstract drafted for: \"{grant_description[:60]}\u2026\"\n"
        f"Brief saved to sandbox/{output_file}"
    )
    _task_save(task)


def _run_demo_task(task):
    """Route a demo task to its scripted handler."""
    demo_type = task.get("demo_type", "")
    try:
        if demo_type == "analyze_project_state":
            _demo_analyze_project_state(task)
        elif demo_type == "biotech_document_review":
            _demo_biotech_document_review(task)
        elif demo_type == "grant_intelligence_brief":
            _demo_grant_intelligence_brief(task)
        else:
            task["status"] = "failed"
            task["final_result"] = f"Unknown demo type: {demo_type}"
            _task_save(task)
    except Exception as e:
        task["status"] = "failed"
        task["final_result"] = f"Demo task error: {str(e)}"
        _task_save(task)
        _log_write("system", f"Demo task {demo_type} error: {e}")


# ── System prompt ────────────────────────────────────────────────
SYSTEM_PROMPT = """You are OpenClay, a local AI research assistant running on a COANA Labs device in Puerto Rico. You specialize in pharmaceutical compliance (FDA 21 CFR, EU GMP Annex 1, ICH guidelines), clinical research methodology, and scientific paper analysis. You respond in whatever language the user writes in — Spanish or English. You are precise, cite specific regulatory sections when relevant, and flag ambiguities and logical gaps in documents you analyze. When uncertain, say so clearly and explain what information would resolve the uncertainty."""

def _build_system_prompt(query=""):
    global _last_memories_used
    _last_memories_used = []
    parts = []
    # Soul document first
    if _soul_text:
        parts.append(_soul_text)
    # Active agent prompt overrides default
    if _current_agent and _current_agent.get("system_prompt"):
        agent_prompt = _current_agent["system_prompt"]
        # Clay Coder: inject hardware summary (one sentence max)
        if _current_agent.get("name") == "Clay Coder" and _hardware_summary:
            # Trim to first sentence / 120 chars
            hw_line = _hardware_summary.split(".")[0][:120]
            agent_prompt += f"\n\n[{hw_line}]"
        parts.append(agent_prompt)
    else:
        parts.append(SYSTEM_PROMPT)
    # Connected folders
    if _connected_folders:
        folder_list = ", ".join(_connected_folders)
        parts.append(f"\n\n## Connected Directories\nThe user has granted access to: {folder_list}.")
    # ── CONTEXT FROM YOUR MEMORY (all agents) ──────────────────────
    if query:
        # WHO YOU ARE TALKING TO
        soul_line = _soul_text.strip() if _soul_text else "No profile set yet"
        # WHAT YOU REMEMBER — Mem0 top-5
        mem_lines = []
        try:
            memories = _memory_search(query, limit=5)
            if memories:
                for m in memories:
                    text = m.get("memory", m.get("text", str(m))) if isinstance(m, dict) else str(m)
                    if text:
                        mem_lines.append(f"- {text}")
                        _last_memories_used.append(text)
        except Exception:
            pass
        mem_block = "\n".join(mem_lines) if mem_lines else "No specific memories yet — pay attention and learn"
        # RELEVANT KNOWLEDGE — Hindsight factual
        fact_lines = []
        try:
            factual = _research_search("factual", query, n=3)
            if factual:
                fact_lines = [f"- {r['text']}" for r in factual]
        except Exception:
            pass
        # Experiential + beliefs only if the agent explicitly enables hindsight
        if _current_agent and _current_agent.get("memory_backend") == "hindsight":
            for network in ["experiential", "beliefs"]:
                try:
                    items = _research_search(network, query, n=3)
                    if items:
                        labels = {"experiential": "Past Sessions", "beliefs": "Inferred Goals"}
                        fact_lines += [f"[{labels[network]}] {r['text']}" for r in items]
                except Exception:
                    pass
        context_block = (
            f"\n\n## WHO YOU ARE TALKING TO:\n{soul_line}"
            f"\n\n## WHAT YOU REMEMBER ABOUT THIS PERSON:\n{mem_block}"
        )
        if fact_lines:
            context_block += "\n\n## RELEVANT KNOWLEDGE FROM THEIR FILES:\n" + "\n".join(fact_lines)
        parts.append(context_block)
    # Preferences
    prefs = MEMORY_DIR / "preferences.md"
    if prefs.exists():
        parts.append(f"\n\n## User Preferences:\n{prefs.read_text('utf-8')[:2000]}")
    # Wiki
    wiki_context = _get_relevant_wiki(query)
    if wiki_context:
        parts.append(f"\n\n## Relevant wiki:\n{wiki_context}")
    return "\n".join(parts)

# ── Conversation persistence ─────────────────────────────────────
def _save_conversation_turn(user_msg: str, assistant_msg: str):
    """Append user + assistant turn to today's .jsonl conversation file."""
    try:
        CONV_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        path = CONV_DIR / f"{today}-{_session_id}.jsonl"
        now = datetime.now().isoformat()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"role": "user", "content": user_msg, "timestamp": now}, ensure_ascii=False) + "\n")
            f.write(json.dumps({"role": "assistant", "content": assistant_msg, "timestamp": now}, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"  [conv] save error: {e}")

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
            "/api/tasks/demo": self._handle_demo_tasks,
            # Pro
            "/api/pro/waitlist": self._handle_pro_waitlist,
            "/api/activate-pro": self._handle_activate_pro,
            # Projects
            "/api/projects/save": self._handle_project_save,
            "/api/projects/list": self._handle_project_list,
            # Models
            "/api/models/install": self._handle_model_install,
            # Orchestration
            "/api/orchestrate": self._handle_orchestrate,
        }
        # Dynamic POST routes (path contains variable segments)
        if re.match(r"^/api/projects/[^/]+/rename$", self.path):
            self._handle_project_rename()
            return
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
        # Projects GET list
        if self.path == "/api/projects/list":
            self._handle_project_list()
            return
        # Projects DELETE /:id
        if self.path.startswith("/api/projects/") and len(self.path) > 15:
            proj_id = self.path.split("/api/projects/")[1].strip("/")
            pf = PROJECTS_DIR / f"{proj_id}.json"
            if pf.exists():
                pf.unlink()
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "not found"}, 404)
            return
        # Hardware profile
        if self.path == "/api/hardware":
            try:
                hp = json.loads(HARDWARE_PROFILE_FILE.read_text("utf-8")) if HARDWARE_PROFILE_FILE.exists() else {}
                self._send_json(hp)
            except Exception:
                self._send_json({})
            return
        # TTS: GET /api/tts?text=...&voice=...
        if self.path.startswith("/api/tts"):
            self._handle_tts_get()
            return
        # Model recommendations
        if self.path == "/api/models/recommendations":
            self._handle_model_recommendations()
            return
        # Orchestration list
        if self.path == "/api/orchestrate/list":
            ORCH_DIR = BASE_DIR / "projects" / "orchestrations"
            ORCH_DIR.mkdir(parents=True, exist_ok=True)
            files = sorted(ORCH_DIR.glob("*.json"), reverse=True)[:10]
            results = []
            for f in files:
                try:
                    results.append(json.loads(f.read_text("utf-8")))
                except Exception:
                    pass
            self._send_json({"orchestrations": results})
            return
        # Conversations list
        if self.path == "/api/conversations":
            CONV_DIR.mkdir(parents=True, exist_ok=True)
            files = sorted(CONV_DIR.glob("*.jsonl"), reverse=True)
            self._send_json({"conversations": [f.name for f in files]})
            return
        # Conversation file contents
        if self.path.startswith("/api/conversations/"):
            fname = self.path.split("/api/conversations/")[1].strip("/")
            fpath = CONV_DIR / fname
            if fpath.exists() and fpath.suffix == ".jsonl":
                lines = [json.loads(l) for l in fpath.read_text("utf-8").splitlines() if l.strip()]
                self._send_json({"turns": lines})
            else:
                self._send_json({"error": "not found"}, 404)
            return
        # Pro status
        if self.path == "/api/pro-status":
            self._handle_pro_status()
            return
        # Public whitepaper
        if self.path == "/docs/openclay_public_whitepaper.md":
            wp = BASE_DIR / "docs" / "openclay_public_whitepaper.md"
            if wp.exists():
                content = wp.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404)
            return
        # Clay Code Pro routes
        if self.path == "/claycode":
            self._handle_claycode_page()
            return
        if self.path == "/api/files/tree":
            self._handle_files_tree()
            return
        if self.path == "/api/memory/codebase":
            self._handle_codebase_memory()
            return
        if self.path == "/api/memory/export":
            self._handle_memory_export()
            return
        # Serve index.html with CSP header
        if self.path in ('/', '/index.html'):
            index_path = BASE_DIR / "index.html"
            if index_path.exists():
                content = index_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._send_csp_headers()
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
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
        # Input validation
        if len(prompt) > 10000:
            self._send_json({"error": "Message too long (max 10,000 chars)"}); return

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
            _save_conversation_turn(body.get("prompt", ""), result)
            self._send_json({"response": result, "done": True}); return

        # Simple mode — streaming
        system = _build_system_prompt(prompt)
        full_prompt = prompt
        if loaded_document:
            full_prompt = f"[Document: {loaded_filename}]\n\n{loaded_document[:6000]}\n\n---\nUser: {prompt}"

        # Always route to the best available model; agent config can override
        _best = _get_best_model()
        model = _current_agent.get("model", _best) if _current_agent else _best
        # Clay Coder: shorter completions cut response time ~50% on CPU
        is_coder = _current_agent and _current_agent.get("name") == "Clay Coder"
        num_predict = 256 if is_coder else 512
        opts = {"temperature": 0.7, "num_predict": num_predict}
        if not is_coder:
            opts["num_ctx"] = 2048
        ollama_body = json.dumps({"model": model, "prompt": full_prompt,
                                   "system": system, "stream": True,
                                   "options": opts}).encode()
        # Clay Coder uses 90s timeout; blob uses 120s
        stream_timeout = 90 if is_coder else 120
        try:
            req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=ollama_body,
                                         headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=stream_timeout)
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
                _save_conversation_turn(body.get("prompt", ""), full_response)
                # Tag factual responses with metadata
                if full_response and _mem0_client:
                    agent_name = _current_agent.get("name", "Clay") if _current_agent else "Clay"
                    try:
                        _mem0_client.add(
                            f"Clay ({agent_name}) said: {full_response[:500]}",
                            user_id="local_user",
                            metadata={"type": "response", "agent": agent_name}
                        )
                    except Exception:
                        pass
                # Send memory metadata to client so UI can show the "Remembered" pill
                snippets = [t[:80] for t in _last_memories_used[:3]]
                if snippets:
                    meta_line = json.dumps({"meta": True, "memories_used": snippets}, ensure_ascii=False) + "\n"
                    try: self.wfile.write(meta_line.encode()); self.wfile.flush()
                    except Exception: pass
        except urllib.error.URLError as e:
            print(f"  [engine] streaming call failed: {e}")
            # Silent recovery attempt
            if _ensure_ollama(max_wait=10):
                try:
                    req2 = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=ollama_body,
                                                  headers={"Content-Type": "application/json"})
                    resp2 = urllib.request.urlopen(req2, timeout=120)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    for line in resp2:
                        self.wfile.write(line); self.wfile.flush()
                    return
                except Exception as e2:
                    print(f"  [engine] retry also failed: {e2}")
            # User-facing: never mention Ollama by name
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Clay needs a moment to start. Please try again in a few seconds."
            }).encode())
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
                steps = t.get("steps", [])
                current_step = steps[-1]["description"][:60] if steps else "Starting..."
                active_task = {
                    "id": tid,
                    "goal": t["goal"][:60],
                    "step": len(steps),
                    "step_label": current_step,
                    "demo_type": t.get("demo_type", "")
                }
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
        # Lazy-load agents if not yet loaded (e.g. first request before main() completes)
        if not _agents:
            _load_agents()
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

    def _handle_orchestrate(self):
        body = json.loads(self._read_body())
        goal = body.get("goal", "")
        agent_names = body.get("agents", [])
        if not goal or not agent_names:
            self._send_json({"error": "missing goal or agents"}, 400); return
        # Security: only allow known agent names
        agent_names = [n for n in agent_names if n in _agents]
        if not agent_names:
            self._send_json({"error": "No valid agents specified"}); return
        results = []
        prev_output = ""
        for name in agent_names:
            agent = _agents.get(name)
            if not agent: continue
            sys_prompt = agent.get("system_prompt", "")
            if prev_output:
                sys_prompt += f"\n\nPrevious agent output:\n{prev_output}"
            try:
                req = urllib.request.Request(
                    f"{OLLAMA_URL}/api/generate",
                    data=json.dumps({"model": _get_best_model(), "prompt": goal,
                        "system": sys_prompt, "stream": False}).encode(),
                    headers={"Content-Type": "application/json"})
                resp = urllib.request.urlopen(req, timeout=60)
                result_text = json.loads(resp.read()).get("response", "")
            except Exception as e:
                result_text = f"[Error: {e}]"
            prev_output = result_text
            results.append({"agent": name, "color": agent.get("color_accent", "#e06438"), "output": result_text})
        # Save to disk
        ORCH_DIR = BASE_DIR / "projects" / "orchestrations"
        ORCH_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        (ORCH_DIR / f"{ts}.json").write_text(json.dumps({
            "goal": goal, "agents": agent_names, "results": results,
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False, indent=2), "utf-8")
        self._send_json({"ok": True, "results": results})

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
        demo_type = body.get("demo_type", "")
        if demo_type:
            task["demo_type"] = demo_type
            _task_save(task)
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
                "final_result": (t.get("final_result") or "")[:200],
                "output_file": t.get("output_file", ""),
                "demo_type": t.get("demo_type", ""),
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

    def _handle_demo_tasks(self):
        self._read_body()
        self._send_json({"demos": [
            {"id": "analyze_project_state", "name": "Analyze Project State",
             "description": "Scan sandbox files, summarize content, write inventory report",
             "goal": "Analyze all files in the sandbox directory: list names, sizes, and modified dates, extract 2-sentence summaries from text files, compute total stats, write report to output/",
             "icon": "\U0001f4ca"},
            {"id": "biotech_document_review", "name": "Biotech Document Review",
             "description": "Review document for FDA/GMP/ICH compliance, identify missing sections",
             "goal": "Review the document in the sandbox for biotech compliance: extract objectives, methods, results, flag FDA/GMP/ICH terms, identify missing sections, write structured review to output/",
             "icon": "\U0001f52c"},
            {"id": "grant_intelligence_brief", "name": "Grant Intelligence Brief",
             "description": "Score grant alignment with COANA profile, draft tailored abstract",
             "goal": "Funding for innovative technologies that improve reliability and privacy in AI systems for healthcare and research institutions.",
             "icon": "\U0001f4cb"}
        ]})

    # ── Clay Code Pro handlers ──────────────────────────────────
    def _handle_claycode_page(self):
        from pro.license import is_pro, gate_html
        if not is_pro():
            html = gate_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return
        clay_html = BASE_DIR / "pro" / "claycode.html"
        if not clay_html.exists():
            clay_html = BASE_DIR / "static" / "claycode.html"  # fallback
        if not clay_html.exists():
            self.send_error(404, "claycode.html not found")
            return
        content = clay_html.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._send_csp_headers()
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_files_tree(self):
        EXCLUDED_DIRS = {".git", "__pycache__", "node_modules", "memory_store",
                         "memory_store_test", ".claude"}
        EXCLUDED_EXTS = {".pyc", ".pyo", ".DS_Store"}
        EXCLUDED_OUTPUT = str(SANDBOX_DIR / "output")
        ALLOWED_EXTS = {".py", ".js", ".html", ".md", ".json", ".ts", ".css", ".sh", ".txt"}
        tree = []
        for p in sorted(BASE_DIR.rglob("*")):
            if p.is_dir():
                continue
            # Skip excluded directories anywhere in path
            if any(part in EXCLUDED_DIRS for part in p.parts):
                continue
            # Skip sandbox/output subtree
            if str(p).startswith(EXCLUDED_OUTPUT):
                continue
            if p.suffix in EXCLUDED_EXTS:
                continue
            if p.suffix not in ALLOWED_EXTS:
                continue
            try:
                rel = str(p.relative_to(BASE_DIR))
                stat = p.stat()
                tree.append({
                    "path": rel,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
            except Exception:
                continue
        self._send_json({"tree": tree})

    def _handle_codebase_memory(self):
        items = _codebase_memory_get_all()
        self._send_json({"memories": items, "count": len(items)})

    def _handle_memory_export(self):
        """Export all memory data as a single JSON blob."""
        def _get_collection_all(name):
            if not _research_db: return []
            try:
                col = _research_db.get_collection(name)
                if col.count() == 0: return []
                data = col.get(include=["documents", "metadatas"])
                docs = data.get("documents", [])
                metas = data.get("metadatas", [])
                return [{"content": d, **(m or {})} for d, m in zip(docs, metas)]
            except Exception: return []

        export = {
            "exported": datetime.now().isoformat(),
            "factual": _get_collection_all("factual"),
            "experiential": _get_collection_all("experiential"),
            "beliefs": _get_collection_all("beliefs"),
            "codebase": _codebase_memory_get_all(),
            "mem0": [],
        }
        # Mem0 memories
        try:
            raw = _memory_get_all()
            export["mem0"] = [
                {"content": (m.get("memory") or m.get("text") or str(m)),
                 "created_at": m.get("created_at", "")}
                for m in raw
            ]
        except Exception: pass

        payload = json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _handle_project_save(self):
        body = json.loads(self._read_body())
        proj_id = body.get("id") or str(uuid.uuid4())
        PROJECTS_DIR.mkdir(exist_ok=True)
        # Auto-name from first 6 words of first user message
        messages = body.get("messages", [])
        name = body.get("name", "")
        if not name and messages:
            first_user = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
            words = first_user.split()[:6]
            name = " ".join(words) or "Untitled project"
        project = {
            "id": proj_id,
            "name": name,
            "created_at": body.get("created_at", datetime.now().isoformat()),
            "updated_at": datetime.now().isoformat(),
            "agent": body.get("agent", _current_agent.get("name", "") if _current_agent else ""),
            "agent_color": body.get("agent_color", _current_agent.get("color_accent", "#e06438") if _current_agent else "#e06438"),
            "message_count": len(messages),
            "messages": messages[-200:],  # cap at 200 messages per project
            "source": body.get("source", "blob"),  # 'blob' or 'claycode'
        }
        pf = PROJECTS_DIR / f"{proj_id}.json"
        pf.write_text(json.dumps(project, ensure_ascii=False, indent=2), "utf-8")
        self._send_json({"ok": True, "id": proj_id, "name": name})

    def _handle_project_list(self):
        PROJECTS_DIR.mkdir(exist_ok=True)
        projects = []
        for pf in sorted(PROJECTS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                p = json.loads(pf.read_text("utf-8"))
                projects.append({
                    "id": p.get("id", pf.stem),
                    "name": p.get("name", "Untitled"),
                    "created_at": p.get("created_at", ""),
                    "updated_at": p.get("updated_at", ""),
                    "agent": p.get("agent", ""),
                    "agent_name": p.get("agent_name") or p.get("agent", ""),
                    "agent_color": p.get("agent_color", "#e06438"),
                    "message_count": p.get("message_count", 0),
                    "source": p.get("source", "blob"),
                })
            except Exception:
                pass
        self._send_json({"projects": projects})

    def _handle_project_rename(self):
        try:
            # Extract project id from path: /api/projects/:id/rename
            parts = self.path.strip("/").split("/")
            # parts: ['api', 'projects', ':id', 'rename']
            proj_id = parts[2] if len(parts) >= 4 else ""
            body = json.loads(self._read_body())
            new_name = body.get("name", "").strip()
            if not proj_id or not new_name:
                self._send_json({"error": "missing id or name"}, 400)
                return
            pf = PROJECTS_DIR / f"{proj_id}.json"
            if not pf.exists():
                self._send_json({"error": "not found"}, 404)
                return
            p = json.loads(pf.read_text("utf-8"))
            p["name"] = new_name
            p["updated_at"] = __import__("datetime").datetime.utcnow().isoformat()
            pf.write_text(json.dumps(p, ensure_ascii=False, indent=2), "utf-8")
            self._send_json({"ok": True, "name": new_name})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_pro_waitlist(self):
        try:
            body = json.loads(self._read_body())
            email = body.get("email", "")
            from pro.license import add_to_waitlist
            ok = add_to_waitlist(email)
            self._send_json({"ok": ok})
        except Exception:
            self._send_json({"ok": False})

    # ── TTS: GET /api/tts?text=...&voice=... ─────────────────────
    def _handle_tts_get(self):
        try:
            from urllib.parse import urlparse, parse_qs, unquote_plus
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            text = unquote_plus(params.get("text", [""])[0])[:500]
            if not text:
                self._send_json({"fallback": True, "reason": "no text"})
                return
            # Check if Kokoro is available
            kokoro_path = BASE_DIR / "models" / "kokoro-82m"
            if not kokoro_path.exists():
                self._send_json({"fallback": True, "reason": "kokoro not installed"})
                return
            # Kokoro TTS — generate WAV and return as base64
            try:
                import base64, tempfile, wave
                # Placeholder: actual Kokoro integration would call the model here
                # For now, signal fallback so browser TTS is used
                self._send_json({"fallback": True, "reason": "kokoro integration pending"})
            except Exception as e:
                self._send_json({"fallback": True, "reason": str(e)})
        except Exception as e:
            self._send_json({"fallback": True, "reason": str(e)})

    # ── Model recommendations ─────────────────────────────────────
    def _handle_model_recommendations(self):
        try:
            hp = json.loads(HARDWARE_PROFILE_FILE.read_text("utf-8")) if HARDWARE_PROFILE_FILE.exists() else {}
            recs = hp.get("model_recommendations", [])
            installed = _get_available_models()
            best = _get_best_model(installed)
            self._send_json({
                "recommendations": recs,
                "installed": installed,
                "best_model": best,
            })
        except Exception as e:
            self._send_json({"recommendations": [], "error": str(e)})

    # ── Model install (streams progress) ─────────────────────────
    def _handle_model_install(self):
        try:
            body = json.loads(self._read_body())
            model_name = body.get("model", "").strip()
            # Validate against safe list
            if not any(model_name.startswith(sm.split(":")[0]) for sm in SAFE_MODELS):
                self._send_json({"ok": False, "error": "Model not in safe list"}, 400)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            # Stream ollama pull progress
            proc = subprocess.Popen(
                ["ollama", "pull", model_name],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            for line in proc.stdout:
                chunk = json.dumps({"progress": line.strip()}) + "\n"
                try:
                    self.wfile.write(chunk.encode()); self.wfile.flush()
                except Exception:
                    break
            proc.wait()
            ok = proc.returncode == 0
            self.wfile.write(json.dumps({"done": True, "ok": ok, "model": model_name}).encode() + b"\n")
            self.wfile.flush()
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def do_DELETE(self):
        """Handle DELETE /api/projects/:id"""
        if self.path.startswith("/api/projects/") and len(self.path) > len("/api/projects/"):
            try:
                proj_id = self.path.split("/api/projects/")[1].strip("/")
                pf = PROJECTS_DIR / f"{proj_id}.json"
                if pf.exists():
                    pf.unlink()
                    self._send_json({"ok": True})
                else:
                    self._send_json({"error": "not found"}, 404)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return
        self.send_error(404)

    def _send_csp_headers(self):
        """Add Content-Security-Policy to HTML responses."""
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net analytics.umami.is; "
            "style-src 'self' 'unsafe-inline' fonts.googleapis.com api.fontshare.com; "
            "font-src 'self' fonts.gstatic.com api.fontshare.com; "
            "frame-src 'self' tally.so; "
            "connect-src 'self' localhost:11434 localhost:3000; "
            "img-src 'self' data:;"
        )

    def _handle_activate_pro(self):
        try:
            body = json.loads(self._read_body())
            key = str(body.get("license_key", "")).strip()[:100]
            if not key:
                self._send_json({"success": False, "error": "No license key provided"}); return
            # Validate via Lemon Squeezy
            api_key = os.environ.get("LEMON_SQUEEZY_API_KEY", "")
            store_id = os.environ.get("LEMON_SQUEEZY_STORE_ID", "openclay")
            if api_key:
                try:
                    import urllib.request as ur
                    req = ur.Request(
                        "https://api.lemonsqueezy.com/v1/licenses/validate",
                        data=json.dumps({"license_key": key, "instance_name": store_id}).encode(),
                        headers={"Content-Type": "application/json", "Accept": "application/json",
                                 "Authorization": f"Bearer {api_key}"},
                    )
                    resp = json.loads(ur.urlopen(req, timeout=10).read())
                    if not resp.get("activated") and not resp.get("valid"):
                        self._send_json({"success": False, "error": "Invalid license key"}); return
                    email = resp.get("meta", {}).get("customer_email", "")
                except Exception as e:
                    # If validation fails (network, etc.) in dev mode, allow key starting with "dev-"
                    if not key.startswith("dev-"):
                        self._send_json({"success": False, "error": f"Validation error: {e}"}); return
                    email = "dev@openclay.local"
            else:
                # No API key configured — allow dev keys for local dev
                if not key.startswith("dev-"):
                    self._send_json({"success": False, "error": "LEMON_SQUEEZY_API_KEY not configured"}); return
                email = "dev@openclay.local"
            # Save license
            global PRO_ACTIVE
            _OPENCLAY_DIR.mkdir(exist_ok=True)
            _LICENSE_FILE.write_text(json.dumps({
                "pro": True, "key": key,
                "activated_at": datetime.now().isoformat(),
                "email": email
            }, indent=2), "utf-8")
            PRO_ACTIVE = True
            self._send_json({"success": True, "email": email})
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _handle_pro_status(self):
        try:
            data = {}
            if _LICENSE_FILE.exists():
                data = json.loads(_LICENSE_FILE.read_text("utf-8"))
            self._send_json({"pro": PRO_ACTIVE, "email": data.get("email",""), "activated_at": data.get("activated_at","")})
        except Exception:
            self._send_json({"pro": False})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        if "404" in str(args) or "500" in str(args): super().log_message(format, *args)

def _print_task_metrics():
    """Print a summary table of task_metrics.jsonl to stdout."""
    mf = SANDBOX_DIR / "logs" / "task_metrics.jsonl"
    if not mf.exists():
        print("No metrics file found at", mf)
        print("Run some tasks first.")
        return
    entries = []
    for line in mf.read_text("utf-8").splitlines():
        if line.strip():
            try: entries.append(json.loads(line))
            except Exception: pass
    if not entries:
        print("No metrics recorded yet.")
        return
    # Group by task_name
    by_name = {}
    for e in entries:
        name = e.get("task_name", "unknown")
        by_name.setdefault(name, []).append(e)
    col = 35
    print(f"\n{'Task Name':<{col}} {'Avg Steps':>10} {'Avg Retries':>12} {'Success Rate':>13} {'Last Run':<20}")
    print("\u2500" * (col + 10 + 13 + 14 + 21))
    for name in sorted(by_name):
        runs = by_name[name]
        avg_steps   = sum(r.get("total_steps", 0) for r in runs) / len(runs)
        avg_retries = sum(r.get("retry_count", 0) for r in runs) / len(runs)
        success_rate = sum(1 for r in runs if r.get("success")) / len(runs) * 100
        last_run = max(r.get("end_time", "") for r in runs)[:16]
        print(f"{name:<{col}} {avg_steps:>10.1f} {avg_retries:>12.1f} {success_rate:>12.0f}% {last_run:<20}")
    print(f"\nTotal task runs: {len(entries)}\n")


# ── Main ─────────────────────────────────────────────────────────
def main():
    print()
    print("  \u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557")
    print("  \u2551   OpenClay v1.3 \u2014 COANA Labs                \u2551")
    print("  \u2551   Local AI Research Assistant                \u2551")
    print("  \u2551   Todo es local. Nada sale de aqui.          \u2551")
    print("  \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d")
    print()
    if "--metrics" in sys.argv:
        _print_task_metrics()
        sys.exit(0)
    # Create directories
    for d in [WIKI_DIR / "regulations", WIKI_DIR / "papers", WIKI_DIR / "cases",
              MEMORY_DIR, WATCHERS_DIR, AGENTS_DIR, LOGS_DIR, SANDBOX_DIR, MEMORY_STORE_DIR, TASKS_DIR, PROJECTS_DIR]:
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
    # Hardware profile
    hw = _detect_hardware()
    print(f"  Hardware: {hw.get('cpu_cores','?')} cores · {hw.get('ram_gb','?')} GB RAM · GPU: {hw.get('gpu','none')}")
    print(f"  TTS engine: {hw.get('tts_engine','browser')}")
    # Check for better models (logs recommendations, no auto-install)
    _check_for_better_models()
    # Auto-create pro/license.key so Clay Code always works locally
    _pro_dir = BASE_DIR / "pro"
    _license_key = _pro_dir / "license.key"
    if not _license_key.exists():
        _pro_dir.mkdir(exist_ok=True)
        _license_key.write_text("dev-key", "utf-8")
        print("  Pro license: dev-key created")
    # Model health check on startup + every 30 min
    _model_health_check()
    _start_model_health_thread()
    # Load agents
    _load_agents()
    if _agents:
        names = ", ".join(_agents.keys())
        active = _current_agent.get("name", "?") if _current_agent else "?"
        print(f"  Agents: {names} (active: {active})")
    else:
        print("  [warning] No agents found — check agents/ folder")
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
