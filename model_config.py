"""model_config.py — Hardware-aware model selection + Ollama management.
Detects RAM, recommends model, launches Ollama hidden, shuts down on close.
MedGemma recommended when medical software detected.
"""
from __future__ import annotations
import atexit, os, platform, subprocess
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
            raw = subprocess.check_output(["sysctl", "-n", "hw.memsize"],
                stderr=subprocess.DEVNULL, timeout=5).decode().strip()
            if raw: return int(raw) // (1024 ** 3)
        elif system == "Linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        return int(line.split()[1]) // (1024 * 1024)
        elif system == "Windows":
            raw = subprocess.check_output(["wmic", "ComputerSystem", "get",
                "TotalPhysicalMemory", "/value"], stderr=subprocess.DEVNULL, timeout=10).decode().strip()
            for part in raw.split("\n"):
                if "=" in part: return int(part.split("=")[1]) // (1024 ** 3)
    except Exception: pass
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
    ram, gpu = detect_ram_gb(), detect_gpu()
    return {"ram_gb": ram, "os": platform.system(), "arch": platform.machine(),
            "gpu_name": gpu["name"], "has_metal": gpu["has_metal"], "has_cuda": gpu["has_cuda"]}

# ── Model recommendation ────────────────────────────────────────────

_MODEL_TIERS = [
    (64, "qwen3:35b-q8_0", "Qwen3 35B Q8 — maximum quality", "Qwen3 35B Q8 — calidad maxima", "maximum"),
    (32, "qwen3:35b", "Qwen3 35B — research grade", "Qwen3 35B — grado investigacion", "research"),
    (16, "qwen3:8b", "Qwen3 8B TurboQuant — full agents", "Qwen3 8B TurboQuant — agente completo", "full"),
    (8, "qwen2.5:3b-instruct-q4_K_M", "Qwen2.5 3B Q4 — basic tasks", "Qwen2.5 3B Q4 — tareas basicas", "basic"),
    (0, "qwen2.5:1.5b", "Qwen2.5 1.5B — minimal tasks only", "Qwen2.5 1.5B — solo tareas minimas", "minimal"),
]

def recommend(ram_gb: int = 0) -> dict:
    if ram_gb <= 0: ram_gb = detect_ram_gb()
    for min_ram, model, desc_en, desc_es, tier in _MODEL_TIERS:
        if ram_gb >= min_ram:
            return {"model": model, "description_en": desc_en,
                    "description_es": desc_es, "tier": tier, "ram_gb": ram_gb}
    return _MODEL_TIERS[-1][1:] | {"ram_gb": ram_gb}

def user_message(lang: str = "en", ram_gb: int = 0) -> str:
    rec = recommend(ram_gb)
    if lang == "es":
        return (f"Tu computadora tiene {rec['ram_gb']}GB de RAM.\n"
                f"  {rec['model']}\n  {rec['description_es']}\nLo instalo automaticamente?")
    return (f"Your computer has {rec['ram_gb']}GB of RAM.\n"
            f"  {rec['model']}\n  {rec['description_en']}\nInstall it automatically?")

# ── Installation ─────────────────────────────────────────────────────

def install_model(model: str = "") -> dict:
    if not model: model = recommend()["model"]
    try:
        r = subprocess.run(["ollama", "pull", model], capture_output=True, text=True, timeout=600)
        out = r.stdout.strip() or r.stderr.strip()
        if r.returncode == 0: _store_in_brain(model); _log(f"Installed: {model}")
        else: _log(f"Failed: {model}: {out[:100]}")
        return {"success": r.returncode == 0, "output": out, "model": model}
    except FileNotFoundError:
        _log("Ollama not found"); return {"success": False, "output": "Ollama not installed. Visit ollama.ai", "model": model}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Download timed out.", "model": model}
    except Exception as e:
        return {"success": False, "output": str(e), "model": model}

def check_ollama_models() -> list[str]:
    try:
        raw = subprocess.check_output(["ollama", "list"], stderr=subprocess.DEVNULL, timeout=10).decode()
        return [line.split()[0] for line in raw.strip().splitlines()[1:] if line.split()]
    except Exception: return []

# ── BRAIN.md storage ─────────────────────────────────────────────────

def _read(p): return p.read_text("utf-8") if p.exists() else ""
def _write(p, t): p.write_text(t, "utf-8")

def _store_in_brain(model: str):
    brain, ts = _read(BRAIN_PATH), datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"- Recommended model: {model} (configured {ts})"
    if "Recommended model:" in brain:
        import re; brain = re.sub(r"- Recommended model:.*", entry, brain); _write(BRAIN_PATH, brain)
    elif "## Machine" in brain:
        _write(BRAIN_PATH, brain.replace("## Machine", f"## Machine\n{entry}", 1))
    else:
        with open(BRAIN_PATH, "a", encoding="utf-8") as f: f.write(f"\n{entry}\n")

def get_stored_model() -> str:
    for line in _read(BRAIN_PATH).splitlines():
        if "Recommended model:" in line:
            model = line.split("Recommended model:")[-1].strip().split("(")[0].strip()
            if model: return model
    return ""

def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        with open(HEALING_LOG, "a") as f: f.write(f"- `{ts}` **model_config** {msg}\n")
    except Exception: pass

# ── Ollama background management ────────────────────────────────────

_ollama_proc = None

def start_ollama_hidden() -> bool:
    """Launch Ollama serve as hidden background process. No window."""
    global _ollama_proc
    if is_ollama_running(): return True
    try:
        _ollama_proc = subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
            env={**os.environ, "OLLAMA_NOPRUNE": "1"})
        atexit.register(stop_ollama)
        import time; time.sleep(1)
        return is_ollama_running()
    except (FileNotFoundError, Exception): return False

def stop_ollama():
    global _ollama_proc
    if _ollama_proc and _ollama_proc.poll() is None:
        try: _ollama_proc.terminate(); _ollama_proc.wait(timeout=5)
        except Exception:
            try: _ollama_proc.kill()
            except Exception: pass
    _ollama_proc = None

def is_ollama_running() -> bool:
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2); return True
    except Exception: return False

def is_ollama_installed() -> bool:
    try: subprocess.run(["ollama", "--version"], capture_output=True, timeout=5); return True
    except (FileNotFoundError, subprocess.TimeoutExpired): return False

# ── MedGemma detection ──────────────────────────────────────────────

def detect_medical_software() -> bool:
    try:
        from integration_detector import scan_all
        medical = {"Epic", "Cerner", "eClinicalWorks", "Meditech", "Athenahealth"}
        return any(a["name"] in medical for a in scan_all())
    except Exception: return False

def recommend_medgemma() -> dict | None:
    if not detect_medical_software(): return None
    return {"model": "medgemma:4b", "description_en": "MedGemma 4B — trained on clinical data",
            "description_es": "MedGemma 4B — entrenado en datos medicos clinicos",
            "tier": "medical", "size": "3.2GB"}

# ── Research profiles ────────────────────────────────────────────────

_PROFILES = {
    "oncology": (["cancer", "oncology", "tumor", "hpv", "genomic", "carcinoma", "hematology", "pathology"],
                 "medgemma:4b"),
    "pharma": (["pharmacy", "pharmacology", "drug", "regulatory", "fda", "gmp", "validation", "qc", "qa", "laboratory"],
               None),
    "engineering": (["engineering", "mechanical", "electrical", "civil", "chemical", "materials", "structural"],
                    None),
    "veterinary": (["veterinary", "vet", "animal", "clinic", "equine", "bovine", "feline", "canine"],
                   None),
    "medical_billing": (["billing", "facturacion", "insurance", "claims", "coding", "medical billing"],
                        None),
}

def detect_research_profile() -> str:
    """Detect research profile from BRAIN.md ## Identity field."""
    brain = _read(BRAIN_PATH).lower()
    for profile, (keywords, _) in _PROFILES.items():
        if any(kw in brain for kw in keywords): return profile
    return ""

def set_research_profile(profile: str):
    """Store RESEARCH_PROFILE in BRAIN.md."""
    brain = _read(BRAIN_PATH)
    entry = f"- RESEARCH_PROFILE: {profile}"
    if "RESEARCH_PROFILE:" in brain:
        import re; brain = re.sub(r"- RESEARCH_PROFILE:.*", entry, brain); _write(BRAIN_PATH, brain)
    else: _append_brain(entry + "\n")

def _append_brain(text):
    with open(BRAIN_PATH, "a", encoding="utf-8") as f: f.write(text)

def auto_configure_profile():
    """Auto-detect and store profile, recommend model if needed."""
    profile = detect_research_profile()
    if profile:
        set_research_profile(profile)
        _, model_override = _PROFILES.get(profile, ([], None))
        if model_override: _store_in_brain(model_override)
    return profile

# ── First-run flow ───────────────────────────────────────────────────

def first_run_check() -> dict:
    stored, installed, rec = get_stored_model(), check_ollama_models(), recommend()
    return {"needs_setup": not stored or (stored not in " ".join(installed)),
            "recommendation": rec, "stored_model": stored, "installed_models": installed}

# ── Self test ────────────────────────────────────────────────────────

def self_test() -> bool:
    ram = detect_ram_gb()
    assert isinstance(ram, int) and ram >= 0, f"RAM: {ram}"
    gpu = detect_gpu()
    assert isinstance(gpu, dict) and "has_metal" in gpu and "has_cuda" in gpu
    hw = hardware_summary()
    assert "ram_gb" in hw and "os" in hw and "arch" in hw and hw["ram_gb"] >= 0
    for gb, exp in [(4, "minimal"), (8, "basic"), (16, "full"), (32, "research"), (64, "maximum"), (128, "maximum")]:
        rec = recommend(gb)
        assert rec["tier"] == exp, f"{gb}GB → {rec['tier']}, expected {exp}"
        assert rec["model"], f"no model for {gb}GB"
    msg_en = user_message("en", 16)
    assert "16GB" in msg_en and "qwen3:8b" in msg_en, f"en msg: {msg_en}"
    msg_es = user_message("es", 16)
    assert "16GB" in msg_es and "qwen3:8b" in msg_es, f"es msg: {msg_es}"
    assert isinstance(get_stored_model(), str)
    frc = first_run_check()
    assert "needs_setup" in frc and isinstance(frc["installed_models"], list)
    assert isinstance(is_ollama_installed(), bool)
    assert isinstance(is_ollama_running(), bool)
    assert isinstance(detect_medical_software(), bool)
    return True
