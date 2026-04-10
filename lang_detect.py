"""lang_detect.py — Bilingual Spanish/English language support for OpenClay.

Detects language from system locale and input text. Returns 'es' or 'en'.
Provides translation dict for all UI strings.
"""
from __future__ import annotations

import locale
import re

# ── Detection ────────────────────────────────────────────────────────

_ES_MARKERS = (
    r"\b(?:hola|necesito|quiero|puedo|archivo|documento|resumen|analizar"
    r"|revisar|generar|ayuda|carpeta|nota|buscar|organizar|configurar"
    r"|guardar|copiar|pendiente|nuevos?|encontr[eé]|detecté|continuamos"
    r"|gracias|también|aquí|cómo|está|están|hacer)\b"
)

_EN_MARKERS = (
    r"\b(?:hello|need|want|file|document|summary|analyze|review|generate"
    r"|help|folder|note|search|organize|configure|save|copy|pending"
    r"|found|detect|continue|thanks|also|here|how|are|make|please)\b"
)


def detect_system_lang() -> str:
    """Detect language from OS locale. Returns 'es' or 'en'."""
    try:
        lang = locale.getdefaultlocale()[0] or ""
        if lang.lower().startswith("es"):
            return "es"
    except Exception:
        pass
    return "en"


def detect_text_lang(text: str) -> str:
    """Detect language from input text. Returns 'es' or 'en'."""
    if not text:
        return detect_system_lang()
    low = text.lower()
    es_hits = len(re.findall(_ES_MARKERS, low, re.IGNORECASE))
    en_hits = len(re.findall(_EN_MARKERS, low, re.IGNORECASE))
    if es_hits > en_hits:
        return "es"
    if en_hits > es_hits:
        return "en"
    return detect_system_lang()


def detect(text: str = "") -> str:
    """Smart detect: text first, fallback to system locale."""
    return detect_text_lang(text) if text else detect_system_lang()


# ── UI Strings ───────────────────────────────────────────────────────

_STRINGS = {
    "greeting_morning":     {"es": "Buenos dias",        "en": "Good morning"},
    "greeting_afternoon":   {"es": "Buenas tardes",      "en": "Good afternoon"},
    "greeting_evening":     {"es": "Buenas noches",      "en": "Good evening"},
    "what_need":            {"es": "Que necesitas hoy?",
                             "en": "What do you need today?"},
    "drop_files":           {"es": "Arrastra tus archivos aqui / Drop your files here",
                             "en": "Drop your files here / Arrastra tus archivos aqui"},
    "analyze_docs":         {"es": "Analizar documentos", "en": "Analyze documents"},
    "review_lit":           {"es": "Revisar literatura",  "en": "Review literature"},
    "generate_summary":     {"es": "Generar resumen",     "en": "Generate summary"},
    "organize_notes":       {"es": "Organizar notas",     "en": "Organize notes"},
    "integrations":         {"es": "Integraciones",       "en": "Integrations"},
    "settings":             {"es": "Configuracion",       "en": "Settings"},
    "save":                 {"es": "Guardar",             "en": "Save"},
    "copy":                 {"es": "Copiar",              "en": "Copy"},
    "last_working":         {"es": "La ultima vez trabajabas en",
                             "en": "Last time you were working on"},
    "unfinished":           {"es": "Ayer dejaste pendiente: {f}. Continuamos?",
                             "en": "You left unfinished: {f}. Continue?"},
    "new_files":            {"es": "Encontre {n} archivos nuevos. Los analizo ahora?",
                             "en": "Found {n} new files. Analyze them now?"},
    "file_not_found":       {"es": "No encontre ese archivo — puedes arrastrarlo aqui?",
                             "en": "I could not find that file — can you drop it here?"},
    "processing":           {"es": "Procesando...",       "en": "Processing..."},
    "done":                 {"es": "Listo.",              "en": "Done."},
    "error_generic":        {"es": "Algo salio mal. Intenta de nuevo.",
                             "en": "Something went wrong. Try again."},
    "saved_to":             {"es": "Guardado en: {p}",    "en": "Saved to: {p}"},
    "detect_app":           {"es": "Detecte {app} en tu computadora. Quieres conectarlo?\n{desc}\n",
                             "en": "I found {app} on your computer. Connect it?\n{desc}\n"},
    "yes_connect":          {"es": "Si, conectar",        "en": "Yes, connect"},
    "no_thanks":            {"es": "No, gracias",         "en": "No, thanks"},
    "clinical_summary":     {"es": "Resumen clinico",     "en": "Clinical summary"},
    "lab_report":           {"es": "Reporte de laboratorio", "en": "Lab report"},
    "vet_summary":          {"es": "Resumen veterinario", "en": "Vet summary"},
    "grant_draft":          {"es": "Borrador de subvencion", "en": "Grant draft"},
    "admin_summary":        {"es": "Resumen administrativo", "en": "Admin summary"},
}


def t(key: str, lang: str = "", **kwargs) -> str:
    """Get translated string. Falls back to English."""
    lang = lang or detect_system_lang()
    entry = _STRINGS.get(key, {})
    text = entry.get(lang, entry.get("en", key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


# ── Self test ────────────────────────────────────────────────────────

def self_test() -> bool:
    """Verify language detection and translation."""
    assert detect_system_lang() in ("es", "en"), "bad system lang"
    assert detect_text_lang("necesito analizar documentos") == "es"
    assert detect_text_lang("I need to analyze documents") == "en"
    assert detect_text_lang("hola quiero revisar") == "es"
    assert detect("") in ("es", "en"), "detect empty failed"
    # Translation
    assert t("save", "es") == "Guardar"
    assert t("save", "en") == "Save"
    assert t("saved_to", "en", p="/tmp/x") == "Saved to: /tmp/x"
    assert "pendiente" in t("unfinished", "es", f="test.md")
    return True
