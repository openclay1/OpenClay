"""model_config.py — Hardware-aware model selection for OpenClay.

Detects available RAM, recommends the right Ollama model, offers to
install it automatically, and stores the choice in BRAIN.md.

Model tiers:
    8GB  RAM → Qwen2.5 3B Q4        — basic tasks
   16GB  RAM → Qwen3 8B TurboQuant  — full agents
   32GB  RAM → Qwen3 35B            — research grade
   64GB+ RAM → Qwen3 35B Q8         — maximum quality
"""
from __future__ import annotations

import platform
import subprocess
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
BRAIN_PATH = BASE_DIR / "BRAIN.md"
HEALING_LOG = BASE_DIR / "healing_log.md"


# ── Hardware detection ───────────────────────────────────────────────

def detect_ram_gb() -> int:
    """Detect total system RAM in GB. Cross-platform."""
    system = platform.system()
    try:
        if system == "Darwin":
            raw = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode().strip()
            if raw:
                return int(raw) // (1024 ** 3)
        elif system == "Linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        kb = int(line.split()[1])
                        return kb // (1024 * 1024)
        elif system == "Windows":
            raw = subprocess.check_output(
                ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory", "/value"],
                stderr=subprocess.DEVNULL, timeout=10
            ).decode().strip()
            for part in raw.split("\n"):
                if "=" in part:
                    return int(part.split("=")[1]) // (1024 ** 3)
    except Exception:
        pass
    return 0


def detect_gpu() -> dict:
    """Detect GPU info. Returns {name, has_metal, has_cuda}."""
    system, info = platform.system(), {"name": "", "has_metal": False, "has_cuda": False}
    try:
        if system == "Darwin":
            raw = subprocess.check_output(["system_profiler", "SPDisplaysDataType",
                "-detailLevel", "mini"], stderr=subprocess.DEVNULL, timeout=10).decode()
            for ln in raw.splitlines():
                if "Chipset Model" in ln or "Chip" in ln:
                    info["name"] = ln.split(":")[-1].strip(); break
            info["has_metal"] = True
        elif system == "Linux":
            raw = subprocess.check_output(["lspci"], stderr=subprocess.DEVNULL, timeout=5).decode()
            for ln in raw.splitlines():
                if "VGA" in ln or "3D" in ln:
                    info["name"] = ln.split(":")[-1].strip()[:80]; break
            info["has_cuda"] = Path("/usr/local/cuda").exists()
    except Exception: pass
    return info


def hardware_summary() -> dict:
    """Full hardware summary for model selection."""
    ram, gpu = detect_ram_gb(), detect_gpu()
    return {"ram_gb": ram, "os": platform.system(), "arch": platform.machine(),
            "gpu_name": gpu["name"], "has_metal": gpu["has_metal"], "has_cuda": gpu["has_cuda"]}


# ── Model recommendation ────────────────────────────────────────────

# (min_ram_gb, model_tag, description_en, description_es, tier_label)
_MODEL_TIERS = [
    (64, "qwen3:35b-q8_0",
     "Qwen3 35B Q8 — maximum quality, research and complex reasoning",
     "Qwen3 35B Q8 — calidad maxima, investigacion y razonamiento complejo",
     "maximum"),
    (32, "qwen3:35b",
     "Qwen3 35B — research grade, literature review and deep analysis",
     "Qwen3 35B — grado investigacion, revision de literatura y analisis profundo",
     "research"),
    (16, "qwen3:8b",
     "Qwen3 8B TurboQuant — full agent capabilities, best speed/quality balance",
     "Qwen3 8B TurboQuant — agente completo, mejor balance velocidad/calidad",
     "full"),
    (8, "qwen2.5:3b-instruct-q4_K_M",
     "Qwen2.5 3B Q4 — basic tasks, summaries, and file organization",
     "Qwen2.5 3B Q4 — tareas basicas, resumenes y organizacion de archivos",
     "basic"),
    (0, "qwen2.5:1.5b",
     "Qwen2.5 1.5B — minimal tasks only, very limited hardware",
     "Qwen2.5 1.5B — solo tareas minimas, hardware muy limitado",
     "minimal"),
]


def recommend(ram_gb: int = 0) -> dict:
    """Recommend a model based on available RAM.

    Returns: {model, description_en, description_es, tier, ram_gb}
    """
    if ram_gb <= 0:
        ram_gb = detect_ram_gb()
    for min_ram, model, desc_en, desc_es, tier in _MODEL_TIERS:
        if ram_gb >= min_ram:
            return {
                "model": model,
                "description_en": desc_en,
                "description_es": desc_es,
                "tier": tier,
                "ram_gb": ram_gb,
            }
    # Absolute fallback
    return _MODEL_TIERS[-1][1:] | {"ram_gb": ram_gb}


def user_message(lang: str = "en", ram_gb: int = 0) -> str:
    """Build a plain-language recommendation message."""
    rec = recommend(ram_gb)
    if lang == "es":
        return (f"Tu computadora tiene {rec['ram_gb']}GB de RAM. "
                f"Te recomiendo este modelo para el mejor balance de "
                f"velocidad y calidad:\n\n"
                f"  {rec['model']}\n"
                f"  {rec['description_es']}\n\n"
                f"Lo instalo automaticamente?")
    return (f"Your computer has {rec['ram_gb']}GB of RAM. "
            f"I recommend this model for the best balance of "
            f"speed and quality:\n\n"
            f"  {rec['model']}\n"
            f"  {rec['description_en']}\n\n"
            f"Install it automatically?")


# ── Installation ─────────────────────────────────────────────────────

def install_model(model: str = "") -> dict:
    """Run `ollama pull [model]`. Returns {success, output, model}."""
    if not model: model = recommend()["model"]
    try:
        r = subprocess.run(["ollama", "pull", model], capture_output=True, text=True, timeout=600)
        out = r.stdout.strip() or r.stderr.strip()
        if r.returncode == 0:
            _store_in_brain(model); _log(f"Installed model: {model}")
        else:
            _log(f"Failed to install {model}: {out[:100]}")
        return {"success": r.returncode == 0, "output": out, "model": model}
    except FileNotFoundError:
        _log("Ollama not found"); return {"success": False, "output": "Ollama not installed. Visit ollama.ai", "model": model}
    except subprocess.TimeoutExpired:
        _log(f"Timeout installing {model}"); return {"success": False, "output": "Download timed out.", "model": model}
    except Exception as e:
        _log(f"Error: {e}"); return {"success": False, "output": str(e), "model": model}


def check_ollama_models() -> list[str]:
    """List currently installed Ollama models."""
    try:
        raw = subprocess.check_output(
            ["ollama", "list"], stderr=subprocess.DEVNULL, timeout=10
        ).decode()
        models = []
        for line in raw.strip().splitlines()[1:]:  # skip header
            parts = line.split()
            if parts:
                models.append(parts[0])
        return models
    except Exception:
        return []


# ── BRAIN.md storage ─────────────────────────────────────────────────

def _read(p): return p.read_text("utf-8") if p.exists() else ""
def _write(p, t): p.write_text(t, "utf-8")

def _store_in_brain(model: str):
    """Store model choice in BRAIN.md."""
    brain = _read(BRAIN_PATH)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"- Recommended model: {model} (configured {ts})"
    # Replace existing model line or append to Machine section
    if "Recommended model:" in brain:
        import re
        brain = re.sub(r"- Recommended model:.*", entry, brain)
        _write(BRAIN_PATH, brain)
    elif "## Machine" in brain:
        brain = brain.replace("## Machine", f"## Machine\n{entry}", 1)
        _write(BRAIN_PATH, brain)
    else:
        with open(BRAIN_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n{entry}\n")


def get_stored_model() -> str:
    """Read the stored model choice from BRAIN.md."""
    brain = _read(BRAIN_PATH)
    for line in brain.splitlines():
        if "Recommended model:" in line:
            # "- Recommended model: qwen3:8b (configured ...)"
            part = line.split("Recommended model:")[-1].strip()
            model = part.split("(")[0].strip()
            if model:
                return model
    return ""


def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        with open(HEALING_LOG, "a") as f:
            f.write(f"- `{ts}` **model_config** {msg}\n")
    except Exception:
        pass


# ── First-run flow ───────────────────────────────────────────────────

def first_run_check() -> dict:
    """Check if model configuration is needed.

    Returns: {needs_setup, recommendation, stored_model, installed_models}
    """
    stored = get_stored_model()
    installed = check_ollama_models()
    rec = recommend()
    needs_setup = not stored or (stored not in " ".join(installed))
    return {
        "needs_setup": needs_setup,
        "recommendation": rec,
        "stored_model": stored,
        "installed_models": installed,
    }


# ── Self test ────────────────────────────────────────────────────────

def self_test() -> bool:
    """Verify hardware detection and model recommendation."""
    # RAM detection returns a number
    ram = detect_ram_gb()
    assert isinstance(ram, int), "RAM must be int"
    assert ram >= 0, f"RAM negative: {ram}"

    # GPU detection returns dict
    gpu = detect_gpu()
    assert isinstance(gpu, dict), "GPU must be dict"
    assert "has_metal" in gpu and "has_cuda" in gpu, "GPU missing keys"

    # Hardware summary
    hw = hardware_summary()
    assert "ram_gb" in hw and "os" in hw and "arch" in hw, "hw missing keys"
    assert hw["ram_gb"] >= 0, "hw ram negative"

    # Recommendation works for all tiers
    for gb, expected_tier in [(4, "minimal"), (8, "basic"), (16, "full"),
                               (32, "research"), (64, "maximum"), (128, "maximum")]:
        rec = recommend(gb)
        assert rec["tier"] == expected_tier, f"{gb}GB → {rec['tier']}, expected {expected_tier}"
        assert rec["model"], f"no model for {gb}GB"

    # User message in both languages
    msg_en = user_message("en", 16)
    assert "16GB" in msg_en and "qwen3:8b" in msg_en, f"en msg: {msg_en}"
    msg_es = user_message("es", 16)
    assert "16GB" in msg_es and "qwen3:8b" in msg_es, f"es msg: {msg_es}"

    # Stored model read (may be empty)
    stored = get_stored_model()
    assert isinstance(stored, str), "stored must be string"

    # First run check
    frc = first_run_check()
    assert "needs_setup" in frc and "recommendation" in frc, "frc missing keys"
    assert isinstance(frc["installed_models"], list), "installed not list"

    return True
