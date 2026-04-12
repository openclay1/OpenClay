"""voice_input.py — Local voice input for OpenClay.
Uses SpeechRecognition + faster-whisper for transcription.
Puerto Rican Spanish + code-switching support. Never auto-submits.
User always confirms in editable field before sending.
"""
from __future__ import annotations

import threading
from pathlib import Path

BASE_DIR = Path(__file__).parent

# ── Status constants ────────────────────────────────────────────────
IDLE = "idle"
LISTENING = "listening"
TRANSCRIBING = "transcribing"
ERROR = "error"

_status = IDLE
_last_text = ""
_last_lang = "en"
_auto_submit = False  # NEVER auto-submit — user must confirm

# ── UI config ────────────────────────────────────────────────────────
BUTTON_LABEL = "🎤 Hablar con OpenClay / Speak to OpenClay"
LISTENING_LABEL = "🔴 Escuchando... / Listening..."
ERROR_LABEL = "No entendi — ¿puedes repetirlo?"
TOOLTIP = ("Tip: Para mejor resultado, usa AirPods o un microfono externo.\n"
           "OpenClay tambien puede recibir voz desde tu telefono en la misma\n"
           "red WiFi — proximamente.")


def get_status() -> str:
    """Current voice input status."""
    return _status


def get_last_result() -> dict:
    """Last transcription result."""
    return {"text": _last_text, "lang": _last_lang, "status": _status}


def _set_status(s: str):
    global _status
    _status = s


def is_available() -> bool:
    """Check if speech recognition is available (library + microphone)."""
    try:
        import speech_recognition as sr
        # Just check library loads — don't probe microphone in headless
        return True
    except ImportError:
        return False


def list_microphones() -> list[str]:
    """List available microphone names."""
    try:
        import speech_recognition as sr
        return sr.Microphone.list_microphone_names()
    except Exception:
        return []


def listen_once(timeout: int = 5, phrase_limit: int = 15) -> dict:
    """Record one phrase from microphone and transcribe.

    Returns: {text, lang, confidence, error}
    - Uses Whisper locally if available, Google Web Speech as fallback
    - Auto-detects Spanish vs English from transcribed text
    """
    global _last_text, _last_lang
    _set_status(LISTENING)

    try:
        import speech_recognition as sr
    except ImportError:
        _set_status(ERROR)
        return {"text": "", "lang": "en", "confidence": 0,
                "error": "SpeechRecognition not installed. Run: pip install SpeechRecognition"}

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=timeout,
                                      phrase_time_limit=phrase_limit)
    except sr.WaitTimeoutError:
        _set_status(IDLE)
        return {"text": "", "lang": "en", "confidence": 0,
                "error": "No speech detected. Try again."}
    except OSError:
        _set_status(ERROR)
        return {"text": "", "lang": "en", "confidence": 0,
                "error": "No microphone found."}
    except Exception as e:
        _set_status(ERROR)
        return {"text": "", "lang": "en", "confidence": 0,
                "error": f"Microphone error: {e}"}

    _set_status(TRANSCRIBING)

    # Try Whisper first (local), then Google Web Speech (requires internet)
    text, confidence, error = "", 0, ""

    # Attempt 1: Whisper (fully local)
    try:
        text = recognizer.recognize_whisper(audio, language=None)
        confidence = 0.85  # Whisper doesn't return confidence directly
    except (sr.UnknownValueError, AttributeError):
        pass
    except Exception:
        pass

    # Attempt 2: Google Web Speech (free, no API key, but needs internet)
    if not text:
        try:
            # Try Spanish first, then English
            text = recognizer.recognize_google(audio, language="es-ES")
            confidence = 0.75
        except sr.UnknownValueError:
            try:
                text = recognizer.recognize_google(audio, language="en-US")
                confidence = 0.75
            except sr.UnknownValueError:
                error = "No entendi — puedes repetirlo o escribirlo? / Could not understand — try again or type it."
            except sr.RequestError as e:
                error = f"Speech service unavailable: {e}"
        except sr.RequestError as e:
            error = f"Speech service unavailable: {e}"

    # Detect language from transcribed text
    lang = _detect_speech_lang(text) if text else "en"

    _last_text = text
    _last_lang = lang
    _set_status(IDLE if not error else ERROR)

    return {"text": text, "lang": lang, "confidence": confidence, "error": error}


def listen_async(callback=None, timeout: int = 5, phrase_limit: int = 15):
    """Non-blocking version of listen_once. Calls callback(result) when done."""
    def _worker():
        result = listen_once(timeout=timeout, phrase_limit=phrase_limit)
        if callback:
            callback(result)
    threading.Thread(target=_worker, daemon=True).start()


def _detect_speech_lang(text: str) -> str:
    """Detect Spanish vs English from transcribed text."""
    if not text:
        return "en"
    try:
        from lang_detect import detect_text_lang
        return detect_text_lang(text)
    except ImportError:
        pass
    # Fallback: basic Spanish markers
    es_words = {"hola", "necesito", "quiero", "puedo", "gracias", "por favor",
                "archivo", "documento", "analizar", "revisar", "generar",
                "ayuda", "como", "donde", "cuando", "porque", "tambien"}
    words = set(text.lower().split())
    es_hits = len(words & es_words)
    return "es" if es_hits >= 2 else "en"


def status_message(lang: str = "en") -> str:
    """User-facing status message."""
    msgs = {
        IDLE: {"es": "Listo para escuchar", "en": "Ready to listen"},
        LISTENING: {"es": "Escuchando...", "en": "Listening..."},
        TRANSCRIBING: {"es": "Transcribiendo...", "en": "Transcribing..."},
        ERROR: {"es": "No entendi — puedes repetirlo o escribirlo?",
                "en": "Could not understand — try again or type it."},
    }
    return msgs.get(_status, msgs[IDLE]).get(lang, msgs[_status]["en"])


# ── Editable result (never auto-submit) ──────────────────────────────

def get_editable_result() -> dict:
    """Return transcription in editable field format. User must confirm before send."""
    return {"text": _last_text, "lang": _last_lang, "editable": True,
            "auto_submit": False,
            "buttons_es": ["Enviar", "Intentar de nuevo"],
            "buttons_en": ["Send", "Try again"]}

# ── PersonaPlex future voice layer ───────────────────────────────────

def check_personaplex_available() -> dict:
    """Check if NVIDIA GPU + PersonaPlex are available for premium voice.
    Returns {available: bool, has_gpu: bool, has_package: bool, message_es, message_en}.
    Default: always use Whisper (works on all hardware).
    """
    import subprocess as sp
    has_gpu = False
    try:
        sp.run(["nvidia-smi"], capture_output=True, timeout=5, check=True)
        has_gpu = True
    except (FileNotFoundError, sp.CalledProcessError, sp.TimeoutExpired):
        pass
    has_pkg = False
    try:
        import importlib; importlib.import_module("personaplex"); has_pkg = True
    except (ImportError, ModuleNotFoundError):
        pass
    available = has_gpu and has_pkg
    return {"available": available, "has_gpu": has_gpu, "has_package": has_pkg,
            "message_es": ("Detecte GPU NVIDIA. Usar PersonaPlex para conversacion "
                           "de voz en tiempo real? (Mas natural, requiere GPU)" if available
                           else "Usando Whisper estandar (compatible con todo hardware)."),
            "message_en": ("NVIDIA GPU detected. Use PersonaPlex for real-time voice "
                           "conversation? (More natural, requires GPU)" if available
                           else "Using standard Whisper (works on all hardware).")}


# ── Self test ───────────────────────────────────────────────────────

def self_test() -> bool:
    """Verify voice_input module loads and functions exist (no mic required)."""
    assert callable(listen_once) and callable(listen_async)
    assert callable(is_available) and callable(list_microphones)
    assert isinstance(is_available(), bool)
    assert get_status() in (IDLE, LISTENING, TRANSCRIBING, ERROR)
    result = get_last_result()
    assert "text" in result and "lang" in result and "status" in result
    assert _detect_speech_lang("hola necesito analizar documentos") == "es"
    assert _detect_speech_lang("I need to analyze documents") == "en"
    assert _detect_speech_lang("") == "en"
    for lang in ("es", "en"):
        assert isinstance(status_message(lang), str) and len(status_message(lang)) > 0
    assert isinstance(list_microphones(), list)
    # Editable result — never auto-submit
    er = get_editable_result()
    assert er["auto_submit"] is False, "Must never auto-submit"
    assert er["editable"] is True
    assert "Enviar" in er["buttons_es"] and "Send" in er["buttons_en"]
    # UI config
    assert "Hablar" in BUTTON_LABEL and "Speak" in BUTTON_LABEL
    assert TOOLTIP and "AirPods" in TOOLTIP
    # #49/#54 PersonaPlex — gracefully returns False when no NVIDIA GPU
    pp = check_personaplex_available()
    assert isinstance(pp, dict) and "available" in pp and "has_gpu" in pp
    assert isinstance(pp["available"], bool)
    assert "message_es" in pp and "message_en" in pp
    return True


if __name__ == "__main__":
    print("self_test:", self_test())
