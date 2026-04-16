# OpenClay v1.0 — COANA Labs
# Local AI Research Assistant
# No data leaves this machine.
# Memory: Karpathy Wiki + Procedural + Agentic
from __future__ import annotations
import http.server, io, json, os, re, subprocess, sys, threading, time, email.parser
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
_ollama_proc = None
_model = None

# ── Session state ────────────────────────────────────────────────
loaded_document = ""
loaded_filename = ""
conversation_history = []  # [{role, content, timestamp}, ...]
AGENT_BACKEND = "simple"
_watcher_threads = {}
_new_ingested_count = 0
_connected_folders = []  # user-connected folder paths
_soul_text = ""  # loaded from soul.md + soul_custom.md

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
    # Replace [MODEL_NAME] with actual model
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

# ── System prompt ────────────────────────────────────────────────
SYSTEM_PROMPT = """You are OpenClay, a local AI research assistant running on a COANA Labs device in Puerto Rico. You specialize in pharmaceutical compliance (FDA 21 CFR, EU GMP Annex 1, ICH guidelines), clinical research methodology, and scientific paper analysis. You respond in whatever language the user writes in — Spanish or English. You are precise, cite specific regulatory sections when relevant, and flag ambiguities and logical gaps in documents you analyze. When uncertain, say so clearly and explain what information would resolve the uncertainty."""

def _build_system_prompt():
    parts = []
    # Soul document first (identity layer)
    if _soul_text:
        parts.append(_soul_text)
    parts.append(SYSTEM_PROMPT)
    # Connected folders context
    if _connected_folders:
        folder_list = ", ".join(_connected_folders)
        parts.append(f"\n\n## Connected Directories\nThe user has granted access to the following directories: {folder_list}. When they reference a file or ask you to read something, ask which file they mean.")
    prefs = MEMORY_DIR / "preferences.md"
    if prefs.exists():
        parts.append(f"\n\n## User Preferences (learned over time):\n{prefs.read_text('utf-8')[:2000]}")
    wiki_context = _get_relevant_wiki()
    if wiki_context:
        parts.append(f"\n\n## Relevant knowledge from wiki:\n{wiki_context}")
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
        conflict = f"\n\n## Conflict Note\n- Updated {now} — new analysis may differ from previous version.\n"
    page = f"# {title}\n\n## Summary\n{content[:500]}\n\n## Key Facts\n- Extracted from document analysis\n\n## Source\n{source or loaded_filename or 'user query'}\n\n## Last Updated\n{now}\n{conflict}"
    path.write_text(page, "utf-8")
    return str(path)

def _count_wiki_pages():
    return sum(1 for _ in WIKI_DIR.rglob("*.md"))

def _generate_wiki_from_response(prompt, response):
    """Background: ask Ollama to create a wiki entry from the conversation."""
    def _worker():
        try:
            wiki_prompt = f"""Based on this conversation, create a short wiki entry.
Title: one phrase summarizing the main topic.
Category: one of [regulations, papers, cases].
Summary: 2-3 sentences.
Key facts: bullet list of 3-5 facts.

User asked: {prompt[:500]}
Assistant answered: {response[:1000]}

Reply ONLY in this JSON format:
{{"title": "...", "category": "...", "summary": "...", "facts": ["...", "..."]}}"""
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

List ONLY new observations about:
- Language preference (Spanish/English/mixed)
- Output format preferences
- Domain focus
- Any corrections made

Reply as a short bullet list. If nothing new, reply "none"."""
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
    """Multi-turn loop: Ollama can read wiki, write wiki, re-read doc, refine."""
    system = _build_system_prompt()
    tool_instructions = """\n\nYou have these tools available. To use one, reply with EXACTLY the tool call on its own line:
TOOL:READ_WIKI:filename
TOOL:WRITE_WIKI:title|content
TOOL:REREAD_DOCUMENT
TOOL:DONE

Use tools to gather info, then call TOOL:DONE with your final answer below it.
If you don't need tools, just respond normally."""
    full_prompt = prompt
    if loaded_document:
        full_prompt = f"[Document loaded: {loaded_filename}]\n\n{loaded_document[:4000]}\n\n---\nUser question: {prompt}"

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
                    full_prompt += f"\n\n[Wiki page {md.stem}]:\n{md.read_text('utf-8')[:2000]}"
                    break
            continue
        elif "TOOL:WRITE_WIKI:" in text:
            parts = text.split("TOOL:WRITE_WIKI:")[1].split("\n")[0].split("|", 1)
            if len(parts) == 2:
                _save_wiki_page(parts[0].strip(), parts[1].strip())
            continue
        elif "TOOL:REREAD_DOCUMENT" in text:
            if loaded_document:
                full_prompt += f"\n\n[Re-reading document]:\n{loaded_document[:4000]}"
            continue
        else:
            # No tool call or TOOL:DONE — this is the final answer
            final = text.replace("TOOL:DONE", "").strip()
            return final
    return text

# ── File Watcher (Step 7) ────────────────────────────────────────
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
        routes = {"/api/ask": self._handle_ask, "/api/upload": self._handle_upload,
                  "/api/clear-document": self._handle_clear_doc, "/api/set-mode": self._handle_set_mode,
                  "/api/status": self._handle_status, "/api/setup-watchers": self._handle_setup_watchers,
                  "/api/detect-apps": self._handle_detect_apps, "/api/voice-transcribe": self._handle_voice,
                  "/api/history": self._handle_history,
                  "/api/connect-folder": self._handle_connect_folder,
                  "/api/mesh-status": self._handle_mesh_status,
                  "/api/mesh-send": self._handle_mesh_send}
        handler = routes.get(self.path)
        if handler: handler()
        else: self.send_error(404)

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def _handle_ask(self):
        global AGENT_BACKEND
        body = json.loads(self._read_body())
        prompt = body.get("prompt", "")
        if not prompt: return self.send_error(400)

        # Handle /agentic and /simple commands
        if prompt.strip().lower() == "/agentic":
            AGENT_BACKEND = "agentic"
            self._send_json({"command": True, "mode": "agentic"}); return
        if prompt.strip().lower() == "/simple":
            AGENT_BACKEND = "simple"
            self._send_json({"command": True, "mode": "simple"}); return

        # Track user message
        now = datetime.now().isoformat()
        conversation_history.append({"role": "user", "content": prompt, "timestamp": now})

        # Agentic mode — non-streaming
        if AGENT_BACKEND == "agentic":
            result = _agentic_loop(prompt, self)
            conversation_history.append({"role": "assistant", "content": result, "timestamp": datetime.now().isoformat()})
            _generate_wiki_from_response(prompt, result)
            _update_preferences(prompt, result)
            self._send_json({"response": result, "done": True}); return

        # Simple mode — streaming
        system = _build_system_prompt()
        full_prompt = prompt
        if loaded_document:
            full_prompt = f"[Document: {loaded_filename}]\n\n{loaded_document[:6000]}\n\n---\nUser: {prompt}"

        ollama_body = json.dumps({"model": _detect_model(), "prompt": full_prompt,
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
            # Track assistant response
            if full_response:
                conversation_history.append({"role": "assistant", "content": full_response,
                                              "timestamp": datetime.now().isoformat()})
                _generate_wiki_from_response(prompt, full_response)
                _update_preferences(prompt, full_response)
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
        # Parse multipart boundary
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
        self._send_json({"wiki_pages": _count_wiki_pages(), "preferences_active": prefs_active,
                          "mode": AGENT_BACKEND, "document": loaded_filename,
                          "new_ingested": count, "model": _detect_model()})

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
        self._read_body()  # consume body
        self._send_json(_detect_apps())

    def _handle_voice(self):
        # Placeholder — voice processing happens client-side with Web Speech API
        self._send_json({"error": "Use client-side voice input"}, 501)

    def _handle_history(self):
        self._read_body()
        # Return last 40 messages (20 exchanges)
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
        elif action == "list":
            pass
        self._send_json({"ok": True, "connected": _connected_folders})

    def _handle_mesh_status(self):
        self._read_body()
        try:
            req = urllib.request.Request("http://localhost:4403/api/v1/fromradio",
                                         method="GET")
            resp = urllib.request.urlopen(req, timeout=2)
            # Try to get node info
            try:
                node_req = urllib.request.Request("http://localhost:4403/hotspot-detect/generate_204",
                                                   method="GET")
                urllib.request.urlopen(node_req, timeout=2)
            except Exception:
                pass
            self._send_json({"connected": True, "status": "active"})
        except Exception:
            self._send_json({"connected": False, "status": "offline"})

    def _handle_mesh_send(self):
        body = json.loads(self._read_body())
        message = body.get("message", "")
        if not message:
            self._send_json({"error": "No message"}, 400); return
        try:
            # Forward to Meshtastic HTTP API
            mesh_body = json.dumps({"text": message}).encode()
            req = urllib.request.Request("http://localhost:4403/api/v1/sendtext",
                                         data=mesh_body,
                                         headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=5)
            self._send_json({"ok": True, "sent": message})
        except Exception as e:
            self._send_json({"error": f"Mesh send failed: {e}"}, 502)

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
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║   OpenClay v1.0 — COANA Labs                ║")
    print("  ║   Local AI Research Assistant                ║")
    print("  ║   Todo es local. Nada sale de aqui.          ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    # Create directories
    for d in [WIKI_DIR / "regulations", WIKI_DIR / "papers", WIKI_DIR / "cases", MEMORY_DIR, WATCHERS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    # Start Ollama
    print("  Starting engine...", end=" ", flush=True)
    if _start_ollama():
        print(f"ok  (model: {_detect_model()})")
    else:
        print("x  Ollama not available"); sys.exit(1)
    # Load soul document
    soul = _load_soul()
    if soul:
        custom = (BASE_DIR / "soul_custom.md").exists()
        print(f"  Soul loaded ({len(soul)} chars" + (" + custom" if custom else "") + ")")
    # Start any saved watchers
    cfg = _load_watcher_config()
    for f in cfg.get("watched_folders", []):
        if Path(f).exists(): _start_watcher(f)
    if _watcher_threads:
        print(f"  Watching {len(_watcher_threads)} folder(s)")
    # Check for new ingested files
    ingested = MEMORY_DIR / "ingested.md"
    if ingested.exists():
        lines = [l for l in ingested.read_text("utf-8").splitlines() if l.strip()]
        if lines:
            print(f"  Wiki: {_count_wiki_pages()} pages | Ingested log: {len(lines)} entries")
    # Start server
    server = http.server.HTTPServer(("0.0.0.0", PORT), ClayHandler)
    print(f"  Ready -> http://localhost:{PORT}")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        for f in list(_watcher_threads.keys()): _stop_watcher(f)
        _stop_ollama(); server.shutdown()
        print("  Hasta luego.")

if __name__ == "__main__":
    main()
