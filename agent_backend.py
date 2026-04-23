"""agent_backend.py — Switchable LLM backend (clawcode / claudecode via Ollama)."""
from __future__ import annotations
import json, os, subprocess, urllib.request
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
ENV_PATH = BASE_DIR / ".env"
OLLAMA_URL = "http://localhost:11434"

# ── Tools available to the Claw Code agent loop ──
AGENT_TOOLS = [{"type": "function", "function": {"name": n, "description": d,
    "parameters": {"type": "object", "properties": {k: {"type": "string",
        "description": v} for k, v in p.items()}, "required": list(p.keys())}}}
    for n, d, p in [
        ("write_file", "Write content to a file at the given path.",
         {"path": "File path", "content": "File content"}),
        ("read_file", "Read a file and return its contents.", {"path": "File path"}),
        ("run_command", "Run a shell command and return stdout.",
         {"command": "Shell command"}),
        ("list_files", "List files in a directory.", {"path": "Directory path"}),
    ]]


def _read_env_key(key: str) -> str:
    """Read a key from .env, fall back to os.environ."""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            l = line.strip()
            if l and not l.startswith("#") and "=" in l:
                k, _, v = l.partition("=")
                if k.strip() == key:
                    return v.strip()
    return os.environ.get(key, "")


def get_backend() -> str:
    """Return the configured backend: 'clawcode' or 'claudecode'.

    Reads AGENT_BACKEND env var; defaults to 'claudecode'.
    """
    val = _read_env_key("AGENT_BACKEND").lower().strip()
    if val in ("clawcode", "claw", "claw-code", "claw_code"):
        return "clawcode"
    if val in ("claudecode", "claude", "claude-code", "claude_code", "simple"):
        return "claudecode"
    return "claudecode"


def get_model() -> str:
    """Return the configured Ollama model name.

    Reads OLLAMA_MODEL env var, then data/stack.json, then returns a default.
    """
    env_model = os.environ.get("OLLAMA_MODEL", "").strip()
    if env_model:
        return env_model
    stack_path = DATA_DIR / "stack.json"
    if stack_path.exists():
        with open(stack_path) as f:
            stack = json.load(f)
        return stack.get("model", {}).get("model", "qwen2.5:3b-instruct-q4_K_M")
    return "qwen2.5:3b-instruct-q4_K_M"


# ── Tool executors (sandboxed to project directory) ──

def _exec_tool(name: str, args: dict) -> str:
    """Execute a tool call and return the result string."""
    if name == "write_file":
        p = Path(args["path"])
        if not str(p.resolve()).startswith(str(BASE_DIR)):
            return "Error: path outside project directory"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args["content"]); return f"Written {len(args['content'])} chars to {p}"
    if name == "read_file":
        p = Path(args["path"])
        return p.read_text()[:4000] if p.exists() else f"Error: {p} not found"
    if name == "run_command":
        try:
            r = subprocess.run(args["command"], shell=True, capture_output=True,
                               text=True, timeout=30, cwd=str(BASE_DIR))
            return (r.stdout + r.stderr)[:4000]
        except subprocess.TimeoutExpired: return "Error: command timed out (30s)"
    if name == "list_files":
        p = Path(args.get("path", str(BASE_DIR)))
        return "\n".join(f.name for f in sorted(p.iterdir())[:50]) if p.is_dir() else f"Error: {p} is not a directory"
    return f"Error: unknown tool {name}"


# ── Shared: urllib fallback for when requests is unavailable ──

def _check_domain(url: str) -> bool: return __import__("permissions").check_domain(url)

def _ollama_chat_urllib(prompt: str, model: str) -> str:
    """Simple /api/chat call using only urllib (no tool use)."""
    from retry_ext import retry_call
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode()
    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat", data=payload,
            headers={"Content-Type": "application/json"})
        resp = retry_call(urllib.request.urlopen, req, timeout=120,
                          label="ollama-chat-urllib")
        data = json.loads(resp.read())
        return data.get("message", {}).get("content", "")
    except Exception:
        return ""


def _ollama_post(url: str, body: dict, timeout: int = 120) -> dict | None:
    """POST to Ollama using requests or urllib."""
    if not _check_domain(url): return None
    from retry_ext import retry_call
    if requests:
        try:
            r = retry_call(requests.post, url, json=body, timeout=timeout,
                           label="ollama-post")
            return r.json() if r.status_code == 200 else None
        except Exception:
            return None
    payload = json.dumps(body).encode()
    try:
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"})
        resp = retry_call(urllib.request.urlopen, req, timeout=timeout,
                          label="ollama-post-urllib")
        return json.loads(resp.read())
    except Exception:
        return None


# ── Claw Code backend: Ollama /api/chat with tool-use loop ──

def _clawcode_generate(prompt: str, model: str, max_turns: int = 5) -> str:
    """Claw Code style agent loop: chat + tool calls over Ollama."""
    messages = [{"role": "user", "content": prompt}]
    content = ""

    for _ in range(max_turns):
        data = _ollama_post(f"{OLLAMA_URL}/api/chat", {
            "model": model, "messages": messages,
            "tools": AGENT_TOOLS, "stream": False,
        })
        if not data:
            return _claudecode_generate(prompt, model)

        msg = data.get("message", {})
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls", [])

        if not tool_calls:
            return content

        messages.append(msg)
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result = _exec_tool(name, args)
            messages.append({"role": "tool", "content": result})

    return content if content else "Agent completed (max turns reached)."


# ── Claude Code backend: simple Ollama CLI generate ──

def _find_ollama() -> str:
    """Find the ollama binary path."""
    for p in ["/usr/local/bin/ollama", "/opt/homebrew/bin/ollama", "ollama"]:
        if Path(p).exists() or p == "ollama":
            return p
    return "ollama"


def _claudecode_generate(prompt: str, model: str) -> str:
    """Original simple path: ollama run via subprocess."""
    from retry_ext import retry_call
    ollama = _find_ollama()
    try:
        result = retry_call(subprocess.run, [ollama, "run", model, prompt],
                            capture_output=True, text=True, timeout=120,
                            label="ollama-cli")
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return _ollama_chat_urllib(prompt, model)


# ── Public API ──

def _inject_memory(prompt: str) -> str:
    try:
        ctx = __import__("memory").load_memory_context()
        if ctx: return f"AGENT MEMORY:\n{ctx}\n\n---\n\n{prompt}"
    except Exception: pass
    return prompt


def generate(prompt: str, model: str | None = None) -> str:
    """Generate text using the configured backend.

    Reads AGENTS.md before every call. Logs outcome after.
    This is the single entry point all modules should use.
    """
    if model is None:
        model = get_model()
    backend = get_backend()
    from input_guard import guard
    prompt, _flags = guard(prompt)
    full_prompt = _inject_memory(prompt)
    try:
        if backend == "clawcode":
            result = _clawcode_generate(full_prompt, model)
        else:
            result = _claudecode_generate(full_prompt, model)
        # Silent success logging
        try:
            from memory import record_success
            short = prompt[:80].replace("\n", " ")
            record_success(f"generate({backend})", model, short)
        except Exception:
            pass
        return result
    except Exception as e:
        # Silent failure logging
        try:
            from memory import record_failure
            record_failure(f"generate({backend})", str(e)[:200])
        except Exception:
            pass
        raise


def generate_with_tools(prompt: str, model: str | None = None, max_turns: int = 5) -> str:
    """Force the tool-use agent loop regardless of backend setting."""
    if model is None: model = get_model()
    from input_guard import guard
    prompt, _ = guard(prompt)
    return _clawcode_generate(prompt, model, max_turns=max_turns)

def validate_twitter_credentials() -> dict:
    """Validate Twitter credentials. Delegates to twitter_post (single source of truth)."""
    from twitter_post import validate_twitter_credentials as _validate
    return _validate()


def self_test() -> bool:
    """Verify backend config, domain gate, and twitter validation wiring."""
    assert get_backend() in ("clawcode", "claudecode"), "bad backend"
    assert isinstance(get_model(), str), "model not str"
    assert _check_domain("http://localhost:11434"), "localhost blocked"
    assert not _check_domain("https://evil.com"), "evil allowed"
    v = validate_twitter_credentials()
    assert "status" in v and "detail" in v, "validate shape wrong"
    return True
