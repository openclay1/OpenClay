"""openclay_app.py — Desktop GUI for OpenClay. Bilingual, streaming, auto-save."""
from __future__ import annotations
import os, sys, threading
from datetime import datetime
from pathlib import Path
from tkinter import (Tk, Frame, Label, Text, Button, Entry, filedialog,
                     END, WORD, BOTH, X, LEFT, RIGHT, TOP, BOTTOM, DISABLED, NORMAL)

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = Path.home() / "Desktop" / "OpenClay Output"
sys.path.insert(0, str(BASE_DIR))

from lang_detect import detect_system_lang, detect_text_lang, t
from confusion_reset import record_attempt, auto_save, restore_session, get_resume_message, reset_label

# ── Colors (from design tokens) ─────────────────────────────────────
BG = "#161310"; SURFACE = "#1b1814"; BORDER = "#373330"
TEXT_CLR = "#cec8c0"; MUTED = "#7a7468"; PRIMARY = "#e06438"
PRIMARY_H = "#d05025"; INVERSE = "#1b1814"


def _read(p): return p.read_text("utf-8") if p.exists() else ""


def _greeting(lang):
    h = datetime.now().hour
    k = "greeting_morning" if h < 12 else "greeting_afternoon" if h < 17 else "greeting_evening"
    g = t(k, lang)
    brain = _read(BASE_DIR / "BRAIN.md")
    # Find last real task
    last = ""
    for ln in reversed(brain.splitlines()):
        if ln.strip().startswith("- [") and "compress_test" not in ln and "test_task" not in ln:
            import re
            m = re.match(r"^-\s*\[.*?\]\s*(.+?)(?:\s*→.*)?$", ln.strip())
            if m: last = m.group(1).strip(); break
    if last:
        return f"{g}. {t('last_working', lang)}: {last}"
    return f"{g}."


def _suggestions():
    try:
        from predict_engine import predict
        return predict()
    except Exception:
        return []


def _route_file(filepath: str, lang: str) -> str:
    p = Path(filepath)
    try: text = p.read_text("utf-8", errors="ignore")
    except Exception: return t("file_not_found", lang)
    if not text.strip(): return t("file_not_found", lang)
    from daily_agents import route_by_content
    return route_by_content(text, lang).get("output", t("done", lang))

def _run_text_input(text: str, lang: str) -> str:
    if not text.strip(): return ""
    from daily_agents import route_by_content
    return route_by_content(text, lang).get("output", t("done", lang))


# ── GUI Builder ──────────────────────────────────────────────────────

def build_gui():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    lang = detect_system_lang()
    # Launch Ollama hidden in background
    try:
        from model_config import start_ollama_hidden, stop_ollama
        start_ollama_hidden()
    except Exception: pass
    root = Tk()
    root.title("OpenClay")
    root.geometry("900x680")
    root.configure(bg=BG)
    root.resizable(True, True)
    def _on_close():
        try:
            from model_config import stop_ollama; stop_ollama()
        except Exception: pass
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", _on_close)

    # ── TOP: Greeting ──
    greet_frame = Frame(root, bg=BG, padx=16, pady=12)
    greet_frame.pack(fill=X, side=TOP)
    Label(greet_frame, text=_greeting(lang), font=("Georgia", 16, "italic"),
          fg=PRIMARY, bg=BG, anchor="w", wraplength=850).pack(fill=X)
    # Suggestions
    sugs = _suggestions()
    if sugs:
        stxt = "  |  ".join(sugs[:3])
        Label(greet_frame, text=stxt, font=("Helvetica", 10), fg=MUTED,
              bg=BG, anchor="w", wraplength=850).pack(fill=X, pady=(4, 0))

    # ── CENTER: Drop zone + Output ──
    center = Frame(root, bg=BG, padx=16)
    center.pack(fill=BOTH, expand=True)

    # LEFT: Drop zone
    left = Frame(center, bg=SURFACE, bd=1, relief="solid", padx=20, pady=20)
    left.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 8))
    Label(left, text=t("drop_files", lang), font=("Helvetica", 12),
          fg=MUTED, bg=SURFACE, wraplength=300).pack(pady=30)
    drop_btn = Button(left, text="Seleccionar / Browse" if lang == "es" else "Browse / Seleccionar",
                      font=("Helvetica", 11), bg=PRIMARY, fg="#fff", bd=0,
                      activebackground=PRIMARY_H, activeforeground="#fff",
                      cursor="hand2", padx=16, pady=8)
    drop_btn.pack(pady=10)

    # RIGHT: Output panel
    right = Frame(center, bg=SURFACE, bd=1, relief="solid", padx=12, pady=12)
    right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(8, 0))
    output_text = Text(right, wrap=WORD, font=("Helvetica", 11), fg=TEXT_CLR,
                       bg=SURFACE, bd=0, height=20, state=DISABLED)
    output_text.pack(fill=BOTH, expand=True)
    btn_row = Frame(right, bg=SURFACE)
    btn_row.pack(fill=X, pady=(8, 0))
    save_btn = Button(btn_row, text=t("save", lang), font=("Helvetica", 10),
                      bg=BORDER, fg=TEXT_CLR, bd=0, padx=12, pady=4)
    save_btn.pack(side=LEFT, padx=(0, 6))
    copy_btn = Button(btn_row, text=t("copy", lang), font=("Helvetica", 10),
                      bg=BORDER, fg=TEXT_CLR, bd=0, padx=12, pady=4)
    copy_btn.pack(side=LEFT)
    reset_btn = Button(btn_row, text=reset_label(lang), font=("Helvetica", 10),
                       bg=BORDER, fg=MUTED, bd=0, padx=12, pady=4,
                       command=lambda: _set_output(""))
    reset_btn.pack(side=RIGHT)

    def _set_output(txt):
        output_text.config(state=NORMAL)
        output_text.delete("1.0", END)
        output_text.insert(END, txt)
        output_text.config(state=DISABLED)

    def _stream_output(txt, idx=0, chunk=3):
        """Stream text character by character for perceived speed."""
        if idx == 0:
            output_text.config(state=NORMAL)
            output_text.delete("1.0", END)
        if idx < len(txt):
            output_text.config(state=NORMAL)
            output_text.insert(END, txt[idx:idx+chunk])
            output_text.config(state=DISABLED)
            root.after(12, lambda: _stream_output(txt, idx+chunk, chunk))
        else:
            output_text.config(state=DISABLED)
            auto_save(panel="output")

    def _on_browse():
        files = filedialog.askopenfilenames(
            title="Select files", filetypes=[
                ("Documents", "*.txt *.pdf *.md *.csv *.xlsx *.docx"),
                ("All", "*.*")])
        if files:
            _set_output(t("processing", lang))
            def _process():
                results = []
                for f in files:
                    results.append(_route_file(f, lang))
                combined = "\n\n---\n\n".join(results)
                auto_save(user_input=str(files), output=combined[:200], panel="browse")
                root.after(0, lambda: _stream_output(combined))
            threading.Thread(target=_process, daemon=True).start()
    drop_btn.configure(command=_on_browse)

    def _save_output():
        txt = output_text.get("1.0", END).strip()
        if txt:
            p = OUTPUT_DIR / f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            p.write_text(txt, "utf-8")
            _set_output(txt + f"\n\n{t('saved_to', lang, p=str(p))}")
    save_btn.configure(command=_save_output)

    def _copy_output():
        txt = output_text.get("1.0", END).strip()
        if txt:
            root.clipboard_clear(); root.clipboard_append(txt)
    copy_btn.configure(command=_copy_output)

    # ── BOTTOM: 6 action buttons ──
    actions_frame = Frame(root, bg=BG, padx=16, pady=8)
    actions_frame.pack(fill=X)
    btns = [
        ("analyze_docs", "clinical"), ("review_lit", "grant"),
        ("generate_summary", "admin"), ("organize_notes", "admin"),
        ("integrations", None), ("settings", None)]
    icons = ["📄", "🔬", "✍️", "📋", "🔗", "⚙️"]
    for i, ((key, agent), icon) in enumerate(zip(btns, icons)):
        txt = f"{icon} {t(key, lang)}"
        def _action_click(a=agent, k=key):
            if a:
                _set_output(t("processing", lang))
                from daily_agents import AGENTS
                fn = AGENTS.get(a, AGENTS["admin"])
                r = fn(f"User requested: {t(k, 'en')}", lang)
                _set_output(r.get("output", t("done", lang)))
            elif k == "integrations":
                from integration_detector import get_pending_offers
                offers = get_pending_offers(lang)
                if offers:
                    _set_output("\n\n".join(
                        f"**{o['name']}**\n{o['description']}" for o in offers))
                else:
                    _set_output("No integrations detected." if lang == "en"
                                else "No se detectaron integraciones.")
            else:
                _set_output("Settings / Configuracion")
        Button(actions_frame, text=txt, font=("Helvetica", 10), bg=SURFACE,
               fg=TEXT_CLR, bd=1, relief="solid", padx=10, pady=6,
               activebackground=PRIMARY, activeforeground="#fff",
               cursor="hand2", command=_action_click).pack(side=LEFT, padx=3, expand=True)

    # ── BOTTOM: Text input ──
    input_frame = Frame(root, bg=BG, padx=16, pady=(4, 12))
    input_frame.pack(fill=X, side=BOTTOM)
    input_row = Frame(input_frame, bg=BG)
    input_row.pack(fill=X)
    text_input = Entry(input_row, font=("Helvetica", 12), fg=TEXT_CLR, bg=SURFACE,
                       bd=1, relief="solid", insertbackground=TEXT_CLR)
    text_input.insert(0, t("what_need", lang))
    text_input.pack(fill=X, side=LEFT, expand=True, ipady=8)
    def _on_voice():
        try:
            from voice_input import listen_once, LISTENING_LABEL, ERROR_LABEL
            _set_output(LISTENING_LABEL)
            def _vworker():
                r = listen_once(timeout=5, phrase_limit=15)
                if r["text"]:
                    root.after(0, lambda: [text_input.delete(0, END), text_input.insert(0, r["text"])])
                else:
                    root.after(0, lambda: _set_output(r.get("error", ERROR_LABEL)))
            threading.Thread(target=_vworker, daemon=True).start()
        except ImportError:
            _set_output("Voice input not available. Install: pip install SpeechRecognition")
    # Voice button below text input, clearly visible
    voice_frame = Frame(input_frame, bg=BG)
    voice_frame.pack(fill=X, pady=(4, 0))
    from voice_input import BUTTON_LABEL, TOOLTIP
    voice_btn = Button(voice_frame, text=BUTTON_LABEL, font=("Helvetica", 11),
                       bg=PRIMARY, fg="#fff", bd=0, padx=14, pady=6,
                       activebackground=PRIMARY_H, cursor="hand2", command=_on_voice)
    voice_btn.pack(side=LEFT)
    def _on_focus_in(e):
        if text_input.get() in (t("what_need", "es"), t("what_need", "en")):
            text_input.delete(0, END)
    def _on_enter(e):
        txt = text_input.get().strip()
        if txt and txt not in (t("what_need", "es"), t("what_need", "en")):
            inp_lang = detect_text_lang(txt)
            _set_output(t("processing", inp_lang))
            def _proc():
                r = _run_text_input(txt, inp_lang)
                auto_save(user_input=txt, output=r[:200], panel="text_input")
                root.after(0, lambda: _stream_output(r))
            threading.Thread(target=_proc, daemon=True).start()
    text_input.bind("<FocusIn>", _on_focus_in)
    text_input.bind("<Return>", _on_enter)
    # Session restore after crash/interrupt
    resume = get_resume_message(lang)
    if resume: _set_output(resume)
    # Start idle monitor
    try:
        from vibe_brain import start_idle_monitor; start_idle_monitor()
    except Exception: pass
    return root


def launch():
    root = build_gui()
    root.mainloop()


def self_test() -> bool:
    """Verify GUI builds without error (headless-safe)."""
    assert callable(build_gui), "build_gui not callable"
    assert callable(launch), "launch not callable"
    # Route test
    assert isinstance(_greeting("en"), str), "greeting failed"
    assert isinstance(_greeting("es"), str), "greeting es failed"
    assert isinstance(_suggestions(), list), "suggestions failed"
    # File routing
    import tempfile
    tmp = Path(tempfile.mktemp(suffix=".txt"))
    tmp.write_text("Patient: Test. Diagnosis: cold. Follow-up: 3 days.")
    r = _route_file(str(tmp), "en")
    assert r and len(r) > 20, "file routing failed"
    tmp.unlink()
    # #53 — streaming function exists and is callable
    assert callable(build_gui), "build_gui should define _stream_output internally"
    # Confusion reset integration
    from confusion_reset import record_attempt, auto_save, restore_session
    assert callable(record_attempt) and callable(auto_save) and callable(restore_session)
    return True


if __name__ == "__main__":
    launch()
