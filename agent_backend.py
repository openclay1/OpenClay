"""agent_backend.py — Switchable agent backend (clawcode / claudecode via Ollama)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import urllib.request

try:
    import requests
except ImportError:
    requests = None

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
ENV_PATH = BASE_DIR / ".env"
OLLAMA_URL = "http://localhost:11434"

# ── Tools available to the Claw Code agent loop ──
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "File content"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file and return its contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command and return stdout.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path"},
                },
                "required": ["path"],
            },
        },
    },
]


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
    """Return the configured backend: 'clawcode' or 'claudecode'."""
    val = _read_env_key("AGENT_BACKEND").lower().strip()
    if val in ("clawcode", "claw", "claw-code", "claw_code"):
        return "clawcode"
    return "claudecode"


def get_model() -> str:
    """Return the configured Ollama model name."""
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
        p.write_text(args["content"])
        return f"Written {len(args['content'])} chars to {p}"
    elif name == "read_file":
        p = Path(args["path"])
        if not p.exists():
            return f"Error: {p} not found"
        return p.read_text()[:4000]
    elif name == "run_command":
        try:
            r = subprocess.run(
                args["command"], shell=True, capture_output=True,
                text=True, timeout=30, cwd=str(BASE_DIR))
            return (r.stdout + r.stderr)[:4000]
        except subprocess.TimeoutExpired:
            return "Error: command timed out (30s)"
    elif name == "list_files":
        p = Path(args.get("path", str(BASE_DIR)))
        if p.is_dir():
            return "\n".join(f.name for f in sorted(p.iterdir())[:50])
        return f"Error: {p} is not a directory"
    return f"Error: unknown tool {name}"


# ── Shared: urllib fallback for when requests is unavailable ──

def _ollama_chat_urllib(prompt: str, model: str) -> str:
    """Simple /api/chat call using only urllib (no tool use)."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode()
    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat", data=payload,
            headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        return data.get("message", {}).get("content", "")
    except Exception:
        return ""


def _ollama_post(url: str, body: dict, timeout: int = 120) -> dict | None:
    """POST to Ollama using requests or urllib."""
    if requests:
        try:
            r = requests.post(url, json=body, timeout=timeout)
            return r.json() if r.status_code == 200 else None
        except Exception:
            return None
    # urllib fallback
    payload = json.dumps(body).encode()
    try:
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=timeout)
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
    ollama = _find_ollama()
    try:
        result = subprocess.run(
            [ollama, "run", model, prompt],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    # Fallback: use urllib if subprocess fails
    return _ollama_chat_urllib(prompt, model)


# ── Public API ──

def _inject_memory(prompt: str) -> str:
    """Prepend AGENTS.md context to the prompt if available."""
    try:
        from memory import load_memory_context
        ctx = load_memory_context()
        if ctx:
            return f"AGENT MEMORY:\n{ctx}\n\n---\n\n{prompt}"
    except Exception:
        pass
    return prompt


def generate(prompt: str, model: str | None = None) -> str:
    """Generate text using the configured backend.

    Reads AGENTS.md before every call. Logs outcome after.
    This is the single entry point all modules should use.
    """
    if model is None:
        model = get_model()
    backend = get_backend()
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


def generate_with_tools(prompt: str, model: str | None = None,
                        max_turns: int = 5) -> str:
    """Force the tool-use agent loop regardless of backend setting."""
    if model is None:
        model = get_model()
    return _clawcode_generate(prompt, model, max_turns=max_turns)
