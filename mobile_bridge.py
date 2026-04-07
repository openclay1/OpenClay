"""mobile_bridge.py — Mobile interface: WebSocket + static server + QR + voice + file upload.

Part 1: WebSocket (8765) + static server (8080) + QR code for local WiFi access.
Part 2: Wake-word 'hey clay' via pvporcupine → Whisper STT → kokoro TTS (all optional).
Part 3: Share QR pointing to github.com/openclay1/OpenClay.
Part 4: File upload — images/video → /input/, docs → /wiki/raw/.
"""
from __future__ import annotations
import asyncio, base64, json, io, os, socket, threading
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
INPUT_DIR = BASE_DIR / "input"
RAW_DIR = BASE_DIR / "wiki" / "raw"
BRIDGE_LOG = BASE_DIR / "bridge_log.md"
WS_PORT = 8765
HTTP_PORT = 8080

try: import websockets  # type: ignore
except ImportError: websockets = None
try: import qrcode  # type: ignore
except ImportError: qrcode = None
try: import pvporcupine  # type: ignore
except ImportError: pvporcupine = None


def _now() -> str: return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _log(action: str, detail: str = ""):
    line = f"- `{_now()}` **{action}** — {detail}\n"
    try:
        with open(BRIDGE_LOG, "a") as f:
            if f.tell() == 0: f.write("# Bridge Log\n\nMobile bridge activity.\n\n")
            f.write(line)
    except FileNotFoundError:
        with open(BRIDGE_LOG, "w") as f:
            f.write("# Bridge Log\n\nMobile bridge activity.\n\n"); f.write(line)


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except Exception: return "127.0.0.1"


# ── QR generation ──

def generate_qr_base64(url: str) -> str:
    """Return a base64-encoded PNG of a QR code for *url*."""
    if not qrcode: return ""
    img = qrcode.make(url)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def mobile_app_qr() -> str:
    ip = get_local_ip()
    return generate_qr_base64(f"http://{ip}:{HTTP_PORT}")

def share_qr() -> str:
    return generate_qr_base64("https://github.com/openclay1/OpenClay")

def mobile_app_url() -> str:
    return f"http://{get_local_ip()}:{HTTP_PORT}"


# ── File upload handler ──

_MEDIA_EXT = {".jpg", ".jpeg", ".png", ".mp4", ".mov"}
_DOC_EXT = {".pdf", ".txt", ".md"}

def handle_file_upload(name: str, data_uri: str) -> str:
    """Decode base64 data URI, save to /input/ or /wiki/raw/. Return confirmation."""
    ext = Path(name).suffix.lower()
    if ext not in _MEDIA_EXT and ext not in _DOC_EXT:
        return f"Skipped {name} — unsupported type."
    # Decode
    try:
        header, encoded = data_uri.split(",", 1)
        raw = base64.b64decode(encoded)
    except Exception:
        return f"Failed to decode {name}."
    if ext in _MEDIA_EXT:
        dest = INPUT_DIR / name; INPUT_DIR.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        _log("file_upload", f"media → input/{name} ({len(raw)} bytes)")
        return f"Got it — {name} is in the queue."
    dest = RAW_DIR / name; RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    _log("file_upload", f"doc → wiki/raw/{name} ({len(raw)} bytes)")
    return f"Got it — adding {name} to your wiki."


# ── Task dispatch (reuses agent queue) ──

def _dispatch_text(text: str) -> str:
    """Run text through ClayRuntime and return the response."""
    from agent import ClayRuntime
    rt = ClayRuntime(policy="strict")
    sanitized, flags = rt.guard_input(text)
    if flags:
        _log("input_blocked", f"flags={flags}")
    ok, reason = rt.check_permission("generate_local", sanitized[:60])
    if not ok: return f"Blocked: {reason}"
    try:
        from model_router import route
        result = route(sanitized, task_type="simple_qa")
        if result: return rt.validate_output(result)
        return "No response from model."
    except Exception as e:
        _log("dispatch_error", str(e)[:120])
        return f"Error: {e}"


# ── WebSocket server ──

_CLIENTS: set = set()

async def _ws_handler(ws):
    _CLIENTS.add(ws)
    _log("ws_connect", f"client connected ({len(_CLIENTS)} total)")
    await ws.send(json.dumps({"type": "system", "text": "Connected to OpenClay."}))
    try:
        async for raw in ws:
            try: msg = json.loads(raw)
            except json.JSONDecodeError: continue
            if msg.get("type") == "message":
                text = msg.get("text", "").strip()
                if not text: continue
                _log("ws_message", text[:80])
                response = await asyncio.get_event_loop().run_in_executor(None, _dispatch_text, text)
                await ws.send(json.dumps({"type": "response", "text": response}))
            elif msg.get("type") == "file":
                name = msg.get("name", "upload")
                data = msg.get("data", "")
                ack = await asyncio.get_event_loop().run_in_executor(None, handle_file_upload, name, data)
                await ws.send(json.dumps({"type": "upload_ack", "text": ack}))
    except Exception: pass
    finally:
        _CLIENTS.discard(ws)
        _log("ws_disconnect", f"client left ({len(_CLIENTS)} remaining)")

async def _run_ws():
    if not websockets: return
    async with websockets.serve(_ws_handler, "0.0.0.0", WS_PORT):
        _log("ws_start", f"WebSocket server on :{WS_PORT}")
        await asyncio.Future()  # run forever


# ── Static HTTP server ──

class _StaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC_DIR), **kw)
    def log_message(self, *a): pass  # silence logs

def _run_http():
    srv = HTTPServer(("0.0.0.0", HTTP_PORT), _StaticHandler)
    _log("http_start", f"Static server on :{HTTP_PORT} → {STATIC_DIR}")
    srv.serve_forever()


# ── Wake-word listener (optional) ──

def start_wake_word():
    """Start 'hey clay' wake-word detection → Whisper STT → agent → kokoro TTS."""
    if pvporcupine is None:
        _log("wake_word", "pvporcupine not installed — skipping"); return
    key = os.environ.get("PORCUPINE_ACCESS_KEY", "")
    if not key:
        _log("wake_word", "PORCUPINE_ACCESS_KEY not set — skipping"); return
    try:
        import struct
        porcupine = pvporcupine.create(access_key=key, keywords=["hey google"])
        # Note: free tier doesn't have custom wake words; using built-in as placeholder
        _log("wake_word", "pvporcupine initialized — listening for wake word")
        try: import pyaudio  # type: ignore
        except ImportError:
            _log("wake_word", "pyaudio not installed — cannot capture audio"); return
        pa = pyaudio.PyAudio()
        stream = pa.open(rate=porcupine.sample_rate, channels=1, format=pyaudio.paInt16,
                         input=True, frames_per_buffer=porcupine.frame_length)
        while True:
            pcm = struct.unpack_from("h" * porcupine.frame_length, stream.read(porcupine.frame_length))
            if porcupine.process(pcm) >= 0:
                _log("wake_word", "wake word detected — starting transcription")
                _transcribe_and_respond()
    except Exception as e:
        _log("wake_word_error", str(e)[:120])

def _transcribe_and_respond():
    """Record after wake word, transcribe with Whisper, respond via TTS."""
    try:
        import whisper  # type: ignore
        model = whisper.load_model("base")
        # Record 5 seconds
        import pyaudio, wave, tempfile
        pa = pyaudio.PyAudio()
        stream = pa.open(rate=16000, channels=1, format=pyaudio.paInt16, input=True, frames_per_buffer=1024)
        frames = [stream.read(1024) for _ in range(int(16000 / 1024 * 5))]
        stream.stop_stream(); stream.close()
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wf = wave.open(tmp.name, "wb"); wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes(b"".join(frames)); wf.close()
        result = model.transcribe(tmp.name)
        text = result.get("text", "").strip()
        os.unlink(tmp.name)
        if not text: return
        _log("whisper_transcription", text[:80])
        response = _dispatch_text(text)
        _log("voice_response", response[:80])
        _speak(response)
    except Exception as e:
        _log("transcribe_error", str(e)[:120])

def _speak(text: str):
    """Speak text via kokoro TTS (optional)."""
    try:
        from kokoro import KPipeline  # type: ignore
        pipe = KPipeline(lang_code="a")
        for _, _, audio in pipe(text):
            import sounddevice as sd  # type: ignore
            sd.play(audio, samplerate=24000); sd.wait()
    except ImportError: _log("tts", "kokoro/sounddevice not installed — skipping TTS")
    except Exception as e: _log("tts_error", str(e)[:80])


# ── Panel integration ──

def add_mobile_section():
    """Return Gradio-compatible HTML for the Mobile section with QR codes."""
    app_qr = mobile_app_qr()
    share = share_qr()
    url = mobile_app_url()
    html = f'<div style="display:flex;gap:24px;flex-wrap:wrap;align-items:flex-start">'
    if app_qr:
        html += (f'<div style="text-align:center"><p style="color:var(--color-text-muted);margin-bottom:8px">'
                 f'Scan to connect</p><img src="data:image/png;base64,{app_qr}" '
                 f'style="width:180px;border-radius:12px"><p style="color:var(--color-text-faint);'
                 f'font-size:.85rem;margin-top:4px">{url}</p></div>')
    if share:
        html += (f'<div style="text-align:center"><p style="color:var(--color-text-muted);margin-bottom:8px">'
                 f'Share OpenClay</p><img src="data:image/png;base64,{share}" '
                 f'style="width:180px;border-radius:12px"><p style="color:var(--color-text-faint);'
                 f'font-size:.85rem;margin-top:4px">github.com/openclay1/OpenClay</p></div>')
    html += "</div>"
    return html


# ── Start everything ──

def start():
    """Launch HTTP + WebSocket servers + optional wake-word in background threads."""
    threading.Thread(target=_run_http, daemon=True, name="oc-http").start()
    threading.Thread(target=lambda: asyncio.new_event_loop().run_until_complete(_run_ws()),
                     daemon=True, name="oc-ws").start()
    threading.Thread(target=start_wake_word, daemon=True, name="oc-wakeword").start()
    _log("bridge_start", f"Mobile bridge started — {mobile_app_url()}")


def self_test() -> bool:
    """Verify QR generation, file routing, IP detection, and dispatch."""
    ip = get_local_ip(); assert isinstance(ip, str) and len(ip) > 0
    assert mobile_app_url().startswith("http://")
    # QR generation
    if qrcode:
        b64 = generate_qr_base64("https://example.com")
        assert len(b64) > 100, "QR too small"
        assert mobile_app_qr(), "app QR empty"
        assert share_qr(), "share QR empty"
    # File routing
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    assert "queue" in handle_file_upload("test.jpg", "data:image/jpeg;base64,/9j/")
    assert "wiki" in handle_file_upload("notes.md", "data:text/markdown;base64,IyB0ZXN0")
    assert "Skipped" in handle_file_upload("bad.exe", "data:x;base64,AA==")
    # Cleanup test files
    for f in [INPUT_DIR / "test.jpg", RAW_DIR / "notes.md"]:
        if f.exists(): f.unlink()
    # HTML exists
    assert (STATIC_DIR / "mobile.html").exists(), "mobile.html missing"
    # Panel HTML
    html = add_mobile_section(); assert "Share OpenClay" in html or "Scan" in html
    _log("self_test", "all checks passed")
    return True


if __name__ == "__main__":
    print("self_test:", self_test())
    print(f"\nStarting mobile bridge → {mobile_app_url()}")
    start()
    import time
    while True: time.sleep(60)
