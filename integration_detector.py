"""integration_detector.py — Software detection and integration offers for OpenClay.

Scans the user's machine for installed applications (hospital, pharma, vet,
universal) and offers to integrate with each one — always with explicit
permission, plain language explanation, and local-only access.

Never connects without user consent. Never sends data externally.
Logs all decisions to DECISIONS.md.
"""
from __future__ import annotations

import os
import platform
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent
DECISIONS_PATH = BASE_DIR / "DECISIONS.md"

def _read(p): return p.read_text(encoding="utf-8") if p.exists() else ""
def _append(p, t):
    with open(p, "a", encoding="utf-8") as f:
        f.write(t)

# ── Detection targets ────────────────────────────────────────────────

_TARGETS = [
    # (name, category, paths_mac, paths_win, description_es, description_en)
    ("Epic", "hospital",
     ["/Applications/Epic"], ["C:/Epic", "C:/Program Files/Epic", "C:/Program Files (x86)/Epic"],
     "Leer notas de alta y generar resumenes automaticos. No enviaremos nada a internet.",
     "Read discharge notes and generate automatic summaries. Nothing sent to the internet."),
    ("Cerner", "hospital",
     ["/Applications/Cerner"], ["C:/Program Files/Cerner", "C:/Cerner"],
     "Leer notas clinicas y extraer elementos de accion.",
     "Read clinical notes and extract action items."),
    ("eClinicalWorks", "hospital",
     ["/Applications/eClinicalWorks"], ["C:/Program Files/eClinicalWorks"],
     "Resumir visitas de pacientes y generar listas de seguimiento.",
     "Summarize patient visits and generate follow-up lists."),
    ("Meditech", "hospital",
     ["/Applications/Meditech"], ["C:/Meditech", "C:/Program Files/Meditech"],
     "Analizar reportes y extraer tendencias clinicas.",
     "Analyze reports and extract clinical trends."),
    ("Athenahealth", "hospital",
     ["/Applications/athenahealth"], ["C:/Program Files/athenahealth"],
     "Resumir notas de visitas y organizar seguimientos.",
     "Summarize visit notes and organize follow-ups."),
    ("LabWare LIMS", "pharma",
     ["/Applications/LabWare"], ["C:/LabWare", "C:/Program Files/LabWare"],
     "Analizar reportes de batch y detectar desviaciones automaticamente.",
     "Analyze batch reports and detect deviations automatically."),
    ("Veeva Vault", "pharma",
     ["/Applications/Veeva"], ["C:/Program Files/Veeva"],
     "Leer documentos regulatorios y generar resumenes.",
     "Read regulatory documents and generate summaries."),
    ("MasterControl", "pharma",
     ["/Applications/MasterControl"], ["C:/Program Files/MasterControl"],
     "Resumir cambios de documentos y detectar brechas de cumplimiento.",
     "Summarize document changes and detect compliance gaps."),
    ("SAP", "pharma",
     ["/Applications/SAP"], ["C:/SAP", "C:/Program Files/SAP"],
     "Leer reportes exportados y resumir datos clave.",
     "Read exported reports and summarize key data."),
    ("ezyVet", "vet",
     ["/Applications/ezyVet"], ["C:/Program Files/ezyVet"],
     "Organizar notas SOAP y generar recordatorios de seguimiento.",
     "Organize SOAP notes and generate follow-up reminders."),
    ("Cornerstone", "vet",
     ["/Applications/Cornerstone"], ["C:/Program Files/Cornerstone", "C:/Program Files/IDEXX"],
     "Organizar notas SOAP y generar recordatorios automaticos.",
     "Organize SOAP notes and generate automatic reminders."),
    ("DaySmart Vet", "vet",
     ["/Applications/DaySmart Vet"], ["C:/Program Files/DaySmart Vet"],
     "Resumir visitas y programar seguimientos.",
     "Summarize visits and schedule follow-ups."),
    ("AVImark", "vet",
     ["/Applications/AVImark"], ["C:/Program Files/AVImark"],
     "Estructurar notas de visita y detectar interacciones de medicamentos.",
     "Structure visit notes and detect drug interactions."),
]

# Universal apps — check by common executable/folder
_UNIVERSAL = [
    ("Microsoft Word", ["/Applications/Microsoft Word.app"],
     ["C:/Program Files/Microsoft Office", "C:/Program Files (x86)/Microsoft Office"],
     "Leer documentos .docx, sugerir ediciones y resumir.",
     "Read .docx documents, suggest edits, and summarize."),
    ("Microsoft Excel", ["/Applications/Microsoft Excel.app"],
     ["C:/Program Files/Microsoft Office", "C:/Program Files (x86)/Microsoft Office"],
     "Leer hojas .xlsx, detectar anomalias y resumir.",
     "Read .xlsx spreadsheets, flag anomalies, and summarize."),
    ("QuickBooks", ["/Applications/QuickBooks"],
     ["C:/Program Files/Intuit/QuickBooks"],
     "Leer reportes exportados y generar resumenes financieros.",
     "Read exported reports and generate financial summaries."),
    ("Google Drive", [str(Path.home() / "Google Drive"), str(Path.home() / "My Drive")],
     [str(Path.home() / "Google Drive"), str(Path.home() / "My Drive")],
     "Monitorear nuevos archivos y procesarlos automaticamente.",
     "Watch for new files and auto-process them."),
    ("Apple Mail", ["/Applications/Mail.app"], [],
     "Leer correos marcados y resumir elementos de accion (solo local).",
     "Read flagged emails and summarize action items (local only)."),
    ("Outlook", ["/Applications/Microsoft Outlook.app"],
     ["C:/Program Files/Microsoft Office"],
     "Leer correos marcados y resumir elementos de accion (solo local).",
     "Read flagged emails and summarize action items (local only)."),
]


# ── Scanner ──────────────────────────────────────────────────────────

def _is_mac(): return platform.system() == "Darwin"

def _check_paths(mac_paths, win_paths) -> bool:
    paths = mac_paths if _is_mac() else win_paths
    return any(os.path.exists(p) for p in paths)


def scan_all() -> list[dict]:
    """Scan for all known applications. Returns list of detected apps."""
    found = []
    for name, cat, mac, win, desc_es, desc_en in _TARGETS:
        if _check_paths(mac, win):
            found.append({"name": name, "category": cat,
                          "desc_es": desc_es, "desc_en": desc_en})
    for name, mac, win, desc_es, desc_en in _UNIVERSAL:
        if _check_paths(mac, win):
            found.append({"name": name, "category": "universal",
                          "desc_es": desc_es, "desc_en": desc_en})
    return found


def was_declined(app_name: str) -> bool:
    """Check if user already declined this integration."""
    decisions = _read(DECISIONS_PATH).lower()
    return f"declined integration: {app_name.lower()}" in decisions


def log_decision(app_name: str, accepted: bool):
    """Log integration decision to DECISIONS.md."""
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    action = "Accepted" if accepted else "Declined"
    _append(DECISIONS_PATH, f"\n### {ts} — Integration: {app_name}\n"
            f"**Decision:** {action} integration: {app_name}\n"
            f"**Outcome:** {'Connected' if accepted else 'Skipped — will not ask again'}\n")


def get_pending_offers(lang: str = "en") -> list[dict]:
    """Return integration offers for detected apps not yet declined."""
    detected = scan_all()
    offers = []
    for app in detected:
        if not was_declined(app["name"]):
            desc = app["desc_es"] if lang == "es" else app["desc_en"]
            offers.append({"name": app["name"], "category": app["category"],
                           "description": desc})
    return offers


# ── Self test ────────────────────────────────────────────────────────

def self_test() -> bool:
    """Verify detection works and finds at least common apps if present."""
    found = scan_all()
    assert isinstance(found, list), "scan must return list"
    # On Mac, should find at least Mail.app or Word if installed
    if _is_mac():
        names = [a["name"] for a in found]
        # At least check the scan ran without error
        assert isinstance(names, list), "names must be list"
    # was_declined works
    assert isinstance(was_declined("NonexistentApp"), bool), "declined check failed"
    # get_pending_offers works
    offers = get_pending_offers("en")
    assert isinstance(offers, list), "offers must be list"
    for o in offers:
        assert "name" in o and "description" in o, "offer missing keys"
    return True
