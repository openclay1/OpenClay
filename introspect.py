"""
introspect.py — Hardware detection and decision matrix.
Runs silently before intake. Never surfaces to user.
Outputs hardware profile to data/hardware.json.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"


def _run(cmd: list[str], fallback: str = "") -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=10).decode().strip()
    except Exception:
        return fallback


def detect_os() -> dict:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "platform": platform.platform(),
    }


def detect_ram_mb() -> int:
    system = platform.system()
    if system == "Darwin":
        raw = _run(["sysctl", "-n", "hw.memsize"])
        if raw:
            return int(raw) // (1024 * 1024)
    elif system == "Linux":
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return int(line.split()[1]) // 1024
    elif system == "Windows":
        raw = _run(["wmic", "ComputerSystem", "get", "TotalPhysicalMemory", "/value"])
        for part in raw.split("\n"):
            if "=" in part:
                return int(part.split("=")[1]) // (1024 * 1024)
    return 0


def detect_cpu() -> dict:
    cores = os.cpu_count() or 1
    system = platform.system()
    brand = ""
    if system == "Darwin":
        brand = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    elif system == "Linux":
        raw = _run(["grep", "-m1", "model name", "/proc/cpuinfo"])
        if ":" in raw:
            brand = raw.split(":", 1)[1].strip()
    return {"cores": cores, "brand": brand, "arch": platform.machine()}


def detect_gpu() -> dict:
    system = platform.system()
    gpu = {"name": "", "vram_mb": 0, "has_metal": False, "has_cuda": False}

    if system == "Darwin":
        raw = _run(["system_profiler", "SPDisplaysDataType"])
        for line in raw.splitlines():
            stripped = line.strip()
            if "Chipset Model" in stripped:
                gpu["name"] = stripped.split(":", 1)[1].strip()
            if "VRAM" in stripped:
                parts = stripped.split(":", 1)[1].strip()
                nums = [int(s) for s in parts.split() if s.isdigit()]
                if nums:
                    gpu["vram_mb"] = max(nums)
            if "Metal" in stripped and "Supported" not in stripped:
                gpu["has_metal"] = True
    elif system == "Linux":
        nvidia = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
        if nvidia:
            parts = nvidia.split(",")
            gpu["name"] = parts[0].strip()
            gpu["has_cuda"] = True
            if len(parts) > 1:
                mem = parts[1].strip().split()[0]
                gpu["vram_mb"] = int(mem)

    return gpu


def detect_disk_free_gb() -> float:
    usage = shutil.disk_usage(str(BASE_DIR))
    return round(usage.free / (1024 ** 3), 1)


def detect_package_manager() -> str:
    system = platform.system()
    if system == "Darwin":
        if shutil.which("brew"):
            return "brew"
    elif system == "Linux":
        for pm in ["apt", "dnf", "pacman", "snap"]:
            if shutil.which(pm):
                return pm
    elif system == "Windows":
        if shutil.which("winget"):
            return "winget"
        if shutil.which("choco"):
            return "choco"
    return "unknown"


def detect_ollama() -> dict:
    path = shutil.which("ollama")
    if not path:
        return {"installed": False, "path": "", "models": []}
    models_raw = _run(["ollama", "list"])
    models = []
    for line in models_raw.splitlines()[1:]:  # skip header
        parts = line.split()
        if parts:
            models.append(parts[0])
    return {"installed": True, "path": path, "models": models}


def compute_tier(ram_mb: int, gpu: dict, cpu: dict | None = None) -> dict:
    """Decision matrix: map hardware to capability tier."""
    vram = gpu.get("vram_mb", 0)
    has_accel = gpu.get("has_metal", False) or gpu.get("has_cuda", False)
    arch = (cpu or {}).get("arch", platform.machine())
    is_apple_silicon = arch == "arm64" and platform.system() == "Darwin"

    # Model size selection
    if ram_mb >= 32000 and (vram >= 6000 or is_apple_silicon):
        # High-end Apple Silicon or dedicated GPU with lots of RAM
        model_tier = "large"
        recommended_model = "llama3:8b"
        max_context = 8192
    elif ram_mb >= 16000 and (is_apple_silicon or gpu.get("has_cuda") or vram >= 4000):
        # Apple Silicon 16GB (unified memory) or dedicated GPU — 7B viable
        model_tier = "medium"
        recommended_model = "qwen2.5:7b"
        max_context = 4096
    elif ram_mb >= 16000 and not is_apple_silicon and vram < 4000:
        # Intel/AMD 16GB WITHOUT dedicated GPU — 7B too slow on CPU
        # qwen2.5:3b-instruct-q4_K_M fits ~2.5GB, runs 35-45 tok/s on Intel
        model_tier = "medium-low"
        recommended_model = "qwen2.5:3b-instruct-q4_K_M"
        max_context = 4096
    elif ram_mb >= 8000:
        model_tier = "small"
        recommended_model = "qwen2.5:1.5b"
        max_context = 2048
    else:
        model_tier = "template"
        recommended_model = "none"
        max_context = 0

    return {
        "tier": model_tier,
        "recommended_model": recommended_model,
        "max_context": max_context,
        "can_run_local_llm": model_tier != "template",
        "use_gpu": is_apple_silicon or (has_accel and vram >= 2000),
    }


def init_db():
    """Initialize the shared SQLite database."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS hardware (
            key TEXT PRIMARY KEY,
            value TEXT,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS agent_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT,
            action TEXT,
            detail TEXT,
            confidence REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS queue_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            task_type TEXT,
            payload TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def log_decision(module: str, action: str, detail: str, confidence: float = 1.0):
    """Log an autonomous decision to both SQLite and agent_decisions.md."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO agent_log (module, action, detail, confidence) VALUES (?, ?, ?, ?)",
        (module, action, detail, confidence),
    )
    conn.commit()
    conn.close()

    decisions_path = BASE_DIR / "agent_decisions.md"
    line = f"- **{module}**: {action} — {detail} (confidence: {confidence})\n"
    with open(decisions_path, "a") as f:
        f.write(line)


def run() -> dict:
    """Run full hardware introspection. Returns the complete profile."""
    init_db()

    os_info = detect_os()
    ram_mb = detect_ram_mb()
    cpu = detect_cpu()
    gpu = detect_gpu()
    disk_free = detect_disk_free_gb()
    pkg_manager = detect_package_manager()
    ollama = detect_ollama()
    tier = compute_tier(ram_mb, gpu, cpu)

    profile = {
        "os": os_info,
        "ram_mb": ram_mb,
        "cpu": cpu,
        "gpu": gpu,
        "disk_free_gb": disk_free,
        "package_manager": pkg_manager,
        "ollama": ollama,
        "tier": tier,
    }

    # Write to JSON
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / "hardware.json", "w") as f:
        json.dump(profile, f, indent=2)

    # Store in SQLite
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT OR REPLACE INTO hardware (key, value) VALUES (?, ?)",
        ("profile", json.dumps(profile)),
    )
    conn.commit()
    conn.close()

    log_decision(
        "introspect",
        f"classified as {tier['tier']} tier",
        f"{ram_mb}MB RAM, {cpu['cores']} cores, GPU: {gpu['name'] or 'none'}, "
        f"recommended model: {tier['recommended_model']}",
    )

    return profile


if __name__ == "__main__":
    profile = run()
    print(json.dumps(profile, indent=2))
