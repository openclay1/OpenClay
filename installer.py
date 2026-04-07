"""installer.py — Silent Ollama + tool installation, OS-aware."""
from __future__ import annotations
import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"
QUEUE_DIR = BASE_DIR / "queue"
ENV_PATH = BASE_DIR / ".env"


def _log_decision(action: str, detail: str, confidence: float = 1.0):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO agent_log (module, action, detail, confidence) VALUES (?, ?, ?, ?)",
            ("installer", action, detail, confidence),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    decisions_path = BASE_DIR / "agent_decisions.md"
    line = f"- **installer**: {action} — {detail} (confidence: {confidence})\n"
    with open(decisions_path, "a") as f:
        f.write(line)


def _run_silent(cmd: str, timeout: int = 300) -> tuple[bool, str]:
    """Run a shell command silently with retry. Returns (success, output)."""
    from retry_ext import retry_call
    try:
        result = retry_call(
            subprocess.run, cmd, shell=True, capture_output=True,
            text=True, timeout=timeout, label=f"installer-cmd",
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


def install_ollama() -> bool:
    """Ensure Ollama is installed."""
    if shutil.which("ollama"):
        _log_decision("ollama already installed", "skipping installation")
        return True

    import platform
    system = platform.system()

    attempts = []
    if system == "Darwin":
        attempts = [
            "brew install ollama",
            "curl -fsSL https://ollama.com/install.sh | sh",
        ]
    elif system == "Linux":
        attempts = [
            "curl -fsSL https://ollama.com/install.sh | sh",
            "snap install ollama",
        ]
    elif system == "Windows":
        attempts = [
            "winget install Ollama.Ollama",
        ]

    for i, cmd in enumerate(attempts):
        _log_decision(f"installing ollama (attempt {i+1})", cmd)
        success, output = _run_silent(cmd, timeout=600)
        if success:
            _log_decision("ollama installed successfully", f"attempt {i+1}")
            return True
        _log_decision(f"ollama install attempt {i+1} failed", output[:200], 0.5)

    return False


def ensure_ollama_running() -> bool:
    """Make sure Ollama server is running."""
    # Check if already running
    success, _ = _run_silent("ollama list", timeout=10)
    if success:
        return True

    # Start it
    _log_decision("starting ollama server", "ollama serve &")
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for it to be ready
    for _ in range(10):
        time.sleep(1)
        success, _ = _run_silent("ollama list", timeout=5)
        if success:
            _log_decision("ollama server started", "ready")
            return True

    return False


def pull_model(model_name: str) -> bool:
    """Pull a model via Ollama. Tries alternatives on failure."""
    if model_name == "none":
        _log_decision("skipping model pull", "template tier — no local LLM")
        return True

    # Check if already pulled
    success, output = _run_silent("ollama list", timeout=10)
    if success and model_name.split(":")[0] in output:
        _log_decision(f"model {model_name} already available", "skipping pull")
        return True

    # Attempt pulls with fallbacks
    alternatives = [model_name]
    if "llama3" in model_name:
        alternatives.append("phi3:mini")
        alternatives.append("qwen2.5:1.5b")
    elif "phi3" in model_name:
        alternatives.append("qwen2.5:1.5b")
        alternatives.append("qwen2.5:0.5b")

    for model in alternatives:
        _log_decision(f"pulling model {model}", "this may take a few minutes")
        success, output = _run_silent(f"ollama pull {model}", timeout=1800)
        if success:
            _log_decision(f"model {model} pulled successfully", "")
            return True
        _log_decision(f"failed to pull {model}", output[:200], 0.5)

    return False


def pull_intake_model() -> bool:
    """Pull the small model used for intake conversations."""
    return pull_model("qwen2.5:0.5b")


def install_tool(tool: dict) -> dict:
    """Install a single tool. Returns result dict."""
    name = tool["name"]
    install_cmd = tool.get("install_cmd")

    if not install_cmd:
        return {"name": name, "status": "skipped", "reason": "no install command"}

    # Check if already installed
    if shutil.which(name):
        _log_decision(f"{name} already installed", "skipping")
        return {"name": name, "status": "already_installed"}

    # Attempt install
    _log_decision(f"installing {name}", install_cmd)
    success, output = _run_silent(install_cmd, timeout=300)
    if success:
        _log_decision(f"{name} installed successfully", "")
        return {"name": name, "status": "installed"}

    # Try pip fallback for Python tools
    if "pip" not in install_cmd:
        pip_cmd = f"pip3 install {name}"
        _log_decision(f"retrying {name} via pip", pip_cmd, 0.6)
        success, output = _run_silent(pip_cmd, timeout=120)
        if success:
            return {"name": name, "status": "installed", "method": "pip_fallback"}

    _log_decision(f"failed to install {name}", output[:200], 0.3)
    return {"name": name, "status": "failed", "error": output[:200]}


def install_python_deps() -> bool:
    """Install core Python dependencies for OpenClay."""
    deps = ["gradio", "requests"]
    cmd = f"pip3 install {' '.join(deps)}"
    _log_decision("installing python dependencies", cmd)
    success, output = _run_silent(cmd, timeout=300)
    if success:
        _log_decision("python dependencies installed", "")
    else:
        _log_decision("python deps install failed", output[:200], 0.5)
    return success


def collect_credentials(tools: list[dict]) -> dict:
    """
    Determine which credentials are needed.
    Does NOT prompt — returns a list for the panel to collect.
    """
    needed = []
    for tool in tools:
        name = tool.get("name", "")
        if name in ("n8n",):
            needed.append({
                "key": "N8N_ENCRYPTION_KEY",
                "label": "n8n encryption key (optional)",
                "required": False,
            })

    return {"credentials_needed": needed}


def run() -> dict:
    """Run the full installation pipeline."""
    stack_path = DATA_DIR / "stack.json"
    if not stack_path.exists():
        raise FileNotFoundError("No stack.json found — run selector first")

    with open(stack_path) as f:
        stack = json.load(f)

    results = {
        "ollama": {"status": "pending"},
        "model": {"status": "pending"},
        "intake_model": {"status": "pending"},
        "tools": [],
        "python_deps": {"status": "pending"},
        "credentials_needed": [],
    }

    # Step 1: Ensure Ollama
    if install_ollama():
        if ensure_ollama_running():
            results["ollama"] = {"status": "ready"}
        else:
            results["ollama"] = {"status": "installed_not_running"}
    else:
        results["ollama"] = {"status": "failed"}

    # Step 2: Pull intake model (small, fast)
    if pull_intake_model():
        results["intake_model"] = {"status": "ready"}
    else:
        results["intake_model"] = {"status": "failed"}

    # Step 3: Pull main model
    model_name = stack.get("model", {}).get("model", "phi3:mini")
    if pull_model(model_name):
        results["model"] = {"status": "ready", "model": model_name}
    else:
        results["model"] = {"status": "failed", "model": model_name}

    # Step 4: Install tools
    for tool in stack.get("tools", []):
        result = install_tool(tool)
        results["tools"].append(result)

    # Step 5: Python deps
    if install_python_deps():
        results["python_deps"] = {"status": "ready"}
    else:
        results["python_deps"] = {"status": "failed"}

    # Step 6: Credentials
    creds = collect_credentials(stack.get("tools", []))
    results["credentials_needed"] = creds.get("credentials_needed", [])

    # Save results
    with open(DATA_DIR / "install_results.json", "w") as f:
        json.dump(results, f, indent=2)

    # Queue for agent
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    queue_item = {
        "source": "installer",
        "task_type": "start_agent",
        "payload": results,
    }
    with open(QUEUE_DIR / "installer_complete.json", "w") as f:
        json.dump(queue_item, f, indent=2)

    installed_count = sum(1 for t in results["tools"]
                          if t["status"] in ("installed", "already_installed"))
    _log_decision("installation complete",
                  f"ollama={results['ollama']['status']}, model={model_name}, "
                  f"tools={installed_count}/{len(results['tools'])}")

    return results


def self_test() -> bool:
    """Verify installer helpers."""
    ok, out = _run_silent("echo hello", timeout=5)
    assert ok and "hello" in out, "run_silent failed"
    assert isinstance(collect_credentials([]), dict), "creds not dict"
    return True

if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
