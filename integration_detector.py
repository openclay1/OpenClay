"""integration_detector.py — Software detection + integration offers for OpenClay.
Scans for installed apps across hospital, pharma, vet, research, engineering,
accounting. Zotero + Obsidian native support. Never connects without consent.
"""
from __future__ import annotations
import os, platform, re, shutil
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DECISIONS_PATH = BASE_DIR / "DECISIONS.md"
BRAIN_PATH = BASE_DIR / "BRAIN.md"
_HOME = Path.home()

def _read(p): return p.read_text(encoding="utf-8") if p.exists() else ""
def _append(p, t):
    with open(p, "a", encoding="utf-8") as f: f.write(t)
def _is_mac(): return platform.system() == "Darwin"

# ── Detection targets ────────────────────────────────────────────────
# (name, category, mac_paths, win_paths, desc_es, desc_en)

_TARGETS = [
    # Hospital / Clinical
    ("Epic", "hospital", ["/Applications/Epic"], ["C:/Epic", "C:/Program Files/Epic"],
     "Leer notas de alta y generar resumenes.", "Read discharge notes and generate summaries."),
    ("Cerner", "hospital", ["/Applications/Cerner"], ["C:/Program Files/Cerner"],
     "Leer notas clinicas y extraer acciones.", "Read clinical notes and extract actions."),
    ("eClinicalWorks", "hospital", ["/Applications/eClinicalWorks"], ["C:/Program Files/eClinicalWorks"],
     "Resumir visitas y generar seguimientos.", "Summarize visits and generate follow-ups."),
    ("Meditech", "hospital", ["/Applications/Meditech"], ["C:/Meditech", "C:/Program Files/Meditech"],
     "Analizar reportes clinicos.", "Analyze clinical reports."),
    ("Athenahealth", "hospital", ["/Applications/athenahealth"], ["C:/Program Files/athenahealth"],
     "Resumir notas de visitas.", "Summarize visit notes."),
    ("ASSERTUS", "hospital", ["/Applications/ProClaim"], ["C:/Program Files/ProClaim", "C:/Program Files/ASSERTUS"],
     "Procesar reclamos y generar apelaciones.", "Process claims and generate appeals."),
    ("AdvancedMD", "hospital", ["/Applications/AdvancedMD"], ["C:/Program Files/AdvancedMD"],
     "Resumir facturacion medica.", "Summarize medical billing."),
    ("Medisoft", "hospital", [], ["C:/Medisoft", "C:/Program Files/Medisoft"],
     "Leer reportes de facturacion.", "Read billing reports."),
    ("Kareo", "hospital", ["/Applications/Kareo"], ["C:/Program Files/Kareo"],
     "Resumir reclamos y pagos.", "Summarize claims and payments."),
    # Pharma / Biotech
    ("LabWare LIMS", "pharma", ["/Applications/LabWare"], ["C:/LabWare", "C:/Program Files/LabWare"],
     "Analizar batch y detectar desviaciones.", "Analyze batches and detect deviations."),
    ("Veeva Vault", "pharma", ["/Applications/Veeva"], ["C:/Program Files/Veeva"],
     "Leer documentos regulatorios.", "Read regulatory documents."),
    ("MasterControl", "pharma", ["/Applications/MasterControl"], ["C:/Program Files/MasterControl"],
     "Resumir cambios de documentos.", "Summarize document changes."),
    ("SAP", "pharma", ["/Applications/SAP"], ["C:/SAP", "C:/Program Files/SAP"],
     "Leer reportes exportados.", "Read exported reports."),
    ("Benchling", "pharma", [], [], "Organizar datos de laboratorio.", "Organize lab data."),
    ("Dotmatics", "pharma", ["/Applications/Dotmatics"], ["C:/Program Files/Dotmatics"],
     "Analizar datos quimicos.", "Analyze chemical data."),
    # Veterinary
    ("ezyVet", "vet", ["/Applications/ezyVet"], ["C:/Program Files/ezyVet"],
     "Organizar notas SOAP veterinarias.", "Organize vet SOAP notes."),
    ("Cornerstone", "vet", ["/Applications/Cornerstone"], ["C:/Program Files/Cornerstone", "C:/Program Files/IDEXX"],
     "Organizar notas y recordatorios.", "Organize notes and reminders."),
    ("DaySmart Vet", "vet", ["/Applications/DaySmart Vet"], ["C:/Program Files/DaySmart Vet"],
     "Resumir visitas veterinarias.", "Summarize vet visits."),
    ("AVImark", "vet", ["/Applications/AVImark"], ["C:/Program Files/AVImark"],
     "Detectar interacciones de medicamentos.", "Detect drug interactions."),
    ("Impromed", "vet", ["/Applications/Impromed"], ["C:/Program Files/Impromed"],
     "Estructurar notas de visita.", "Structure visit notes."),
    # Research tools
    ("Zotero", "research", [str(_HOME / "Zotero"), "/Applications/Zotero.app"],
     [str(_HOME / "Zotero"), "C:/Program Files/Zotero"],
     "Analizar PDFs nuevos automaticamente.", "Auto-analyze new PDFs."),
    ("Obsidian", "research", [str(_HOME / "Library/Application Support/obsidian")],
     [str(Path(os.environ.get("APPDATA", "")) / "obsidian")] if not _is_mac() else [],
     "Guardar resumenes en tu vault.", "Save summaries to your vault."),
    ("Mendeley", "research", [str(_HOME / "Mendeley Desktop")], [str(_HOME / "Mendeley Desktop")],
     "Sincronizar biblioteca de papers.", "Sync paper library."),
    ("EndNote", "research", ["/Applications/EndNote*"], ["C:/Program Files/EndNote"],
     "Importar referencias.", "Import references."),
    ("RStudio", "research", [str(_HOME / "Library/Application Support/RStudio"), "/Applications/RStudio.app"],
     ["C:/Program Files/RStudio"],
     "Organizar scripts de analisis.", "Organize analysis scripts."),
    # Engineering / Science
    ("AutoCAD", "engineering", ["/Applications/Autodesk"], ["C:/Program Files/Autodesk"],
     "Resumir especificaciones.", "Summarize specifications."),
    ("SolidWorks", "engineering", [], ["C:/Program Files/SOLIDWORKS Corp"],
     "Analizar reportes de diseno.", "Analyze design reports."),
    ("GraphPad Prism", "engineering", ["/Applications/Prism*"], ["C:/Program Files/GraphPad"],
     "Organizar resultados estadisticos.", "Organize statistical results."),
    ("SPSS", "engineering", ["/Applications/IBM SPSS*"], ["C:/Program Files/IBM/SPSS"],
     "Resumir analisis estadistico.", "Summarize statistical analysis."),
    # Accounting
    ("QuickBooks", "accounting", ["/Applications/QuickBooks", str(_HOME / "Library/Application Support/Intuit")],
     ["C:/Program Files/Intuit/QuickBooks"],
     "Generar resumenes financieros.", "Generate financial summaries."),
    ("Sage", "accounting", ["/Applications/Sage"], ["C:/Program Files/Sage"],
     "Leer reportes contables.", "Read accounting reports."),
]

_UNIVERSAL = [
    ("Microsoft Word", ["/Applications/Microsoft Word.app"], ["C:/Program Files/Microsoft Office"],
     "Leer y resumir documentos.", "Read and summarize documents."),
    ("Microsoft Excel", ["/Applications/Microsoft Excel.app"], ["C:/Program Files/Microsoft Office"],
     "Detectar anomalias en hojas.", "Flag spreadsheet anomalies."),
    ("Google Drive", [str(_HOME / "Google Drive"), str(_HOME / "My Drive")],
     [str(_HOME / "Google Drive")], "Monitorear archivos nuevos.", "Watch for new files."),
    ("Apple Mail", ["/Applications/Mail.app"], [], "Resumir correos marcados.", "Summarize flagged emails."),
    ("Outlook", ["/Applications/Microsoft Outlook.app"], ["C:/Program Files/Microsoft Office"],
     "Resumir correos marcados.", "Summarize flagged emails."),
]

# Also check for tools in PATH
_PATH_TOOLS = [
    ("JupyterLab", "jupyter", "research", "Organizar notebooks.", "Organize notebooks."),
    ("MATLAB", "matlab", "engineering", "Resumir scripts.", "Summarize scripts."),
]

# ── Scanner ──────────────────────────────────────────────────────────

def _check_paths(mac_paths, win_paths) -> bool:
    paths = mac_paths if _is_mac() else win_paths
    return any(os.path.exists(p) for p in paths)

def scan_all() -> list[dict]:
    found = []
    for name, cat, mac, win, d_es, d_en in _TARGETS:
        if _check_paths(mac, win):
            found.append({"name": name, "category": cat, "desc_es": d_es, "desc_en": d_en})
    for name, mac, win, d_es, d_en in _UNIVERSAL:
        if _check_paths(mac, win):
            found.append({"name": name, "category": "universal", "desc_es": d_es, "desc_en": d_en})
    for name, cmd, cat, d_es, d_en in _PATH_TOOLS:
        if shutil.which(cmd):
            found.append({"name": name, "category": cat, "desc_es": d_es, "desc_en": d_en})
    return found

def was_declined(app_name: str) -> bool:
    return f"declined integration: {app_name.lower()}" in _read(DECISIONS_PATH).lower()

def log_decision(app_name: str, accepted: bool):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    action = "Accepted" if accepted else "Declined"
    _append(DECISIONS_PATH, f"\n### {ts} — Integration: {app_name}\n"
            f"**Decision:** {action} integration: {app_name}\n"
            f"**Outcome:** {'Connected' if accepted else 'Skipped'}\n")

def store_detected_in_brain(detected: list[dict]):
    brain = _read(BRAIN_PATH)
    if "## Integrations" not in brain:
        _append(BRAIN_PATH, "\n## Integrations\n")
    today = datetime.now().strftime("%Y-%m-%d")
    for app in detected:
        line = f"- {app['name']} detected {today}"
        if line not in brain:
            _append(BRAIN_PATH, f"{line}\n")

def get_pending_offers(lang: str = "en") -> list[dict]:
    detected = scan_all()
    store_detected_in_brain(detected)
    return [{"name": a["name"], "category": a["category"],
             "description": a["desc_es"] if lang == "es" else a["desc_en"]}
            for a in detected if not was_declined(a["name"])]

# ── Zotero integration ──────────────────────────────────────────────

def watch_zotero() -> list[str]:
    """Find new PDFs in Zotero storage."""
    zotero = _HOME / "Zotero" / "storage"
    if not zotero.exists(): return []
    import time; cutoff = time.time() - 86400
    return [str(f) for f in zotero.rglob("*.pdf") if f.stat().st_mtime > cutoff][:10]

# ── Obsidian integration ────────────────────────────────────────────

_obsidian_vault = ""

def set_obsidian_vault(path: str): global _obsidian_vault; _obsidian_vault = path

def save_to_obsidian(title: str, content: str, tags: list[str] = None) -> str:
    if not _obsidian_vault: return ""
    vault = Path(_obsidian_vault)
    if not vault.exists(): return ""
    tags = tags or []
    today = datetime.now().strftime("%Y-%m-%d")
    frontmatter = f"---\ntitle: {title}\ndate: {today}\ntags: [{', '.join(tags)}]\nsource: OpenClay\n---\n\n"
    p = vault / f"{title.replace(' ', '_')}.md"
    p.write_text(frontmatter + content, encoding="utf-8")
    return str(p)

# ── Self test ────────────────────────────────────────────────────────

def self_test() -> bool:
    found = scan_all()
    assert isinstance(found, list)
    if _is_mac():
        assert isinstance([a["name"] for a in found], list)
    assert isinstance(was_declined("FakeApp123"), bool)
    offers = get_pending_offers("en")
    assert isinstance(offers, list)
    for o in offers: assert "name" in o and "description" in o
    # #44 Zotero detection
    assert isinstance(watch_zotero(), list)
    # #45 Obsidian output
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        set_obsidian_vault(tmp)
        p = save_to_obsidian("Test Note", "Content here", ["test"])
        assert Path(p).exists(), "obsidian save failed"
        text = Path(p).read_text()
        assert "title: Test Note" in text and "tags:" in text, "YAML frontmatter invalid"
    set_obsidian_vault("")
    return True
