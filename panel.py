"""panel.py — OpenClay dashboard."""
import re, time
from pathlib import Path
try: import gradio as gr
except ImportError: gr = None
BASE_DIR = Path(__file__).parent
def _show(val=True): return gr.update(visible=val)
def _hide(): return gr.update(visible=False)
def _verb(t): return f'<span class="status-verb">{t}</span>'


# ─── Intent detection ───

_P = {
    "tweet": [r"\b(?:post|send|write)\s+(?:a\s+)?(?:\w+\s+)*tweet\b",
              r"\btweet\s+(that|about|saying|on|something)\b", r"^tweet\s+",
              r"\b(?:post|tweet)\s+(?:to|on)\s+(?:twitter|x)\b",
              r"^post\s+(?:about|something|this)\b",
              r"^post\s+(?:a\s+)?(?:\w+\s+)*(?:about|on)\b"],
    "direct": [r"\b(?:post|tweet)\s+this\s+directly\b",
               r"\b(?:post|tweet)\s+(?:now|immediately)\b"],
    "wiki_init": [r"\b(?:build|create|init(?:ialize)?|setup)\s+(?:my\s+)?wiki\b"],
    "wiki_ingest": [r"\bingest\s+(.+)", r"\badd\s+to\s+wiki\s*:?\s*(.+)",
                    r"\bimport\s+(?:into\s+wiki\s*:?\s*)?(.+)"],
    "wiki_query": [r"\bquery\s*:\s*(.+)", r"\bwiki\s*:\s*(.+)",
                   r"\bwhat\s+does\s+(?:my\s+)?wiki\s+(?:say|know)\s+about\s+(.+)",
                   r"\bsearch\s+(?:my\s+)?wiki\s+(?:for\s+)?(.+)"],
    "wiki_lint": [r"^lint(?:\s+wiki)?\s*$", r"^check\s+wiki\b", r"\bwiki\s+health\b"],
    "approve": [r"^approve\s+(\S+)"], "deny": [r"^deny\s+(\S+)"],
}

def _detect_intent(text: str) -> tuple:
    low = text.lower().strip()
    for pat in _P["approve"]:
        m = re.search(pat, low)
        if m: return "approve", m.group(1).strip()
    for pat in _P["deny"]:
        m = re.search(pat, low)
        if m: return "deny", m.group(1).strip()
    for pat in _P["wiki_init"]:
        if re.search(pat, low): return "wiki_init", ""
    for pat in _P["wiki_ingest"]:
        m = re.search(pat, low)
        if m: return "wiki_ingest", m.group(1).strip()
    for pat in _P["wiki_query"]:
        m = re.search(pat, low)
        if m: return "wiki_query", m.group(1).strip()
    for pat in _P["wiki_lint"]:
        if re.search(pat, low): return "wiki_lint", ""
    for pat in _P["direct"]:
        m = re.search(pat, low)
        if m:
            after = text[m.end():].strip().lstrip(":\"'")
            before = text[:m.start()].strip().rstrip(":\"'")
            return "direct_post", (after or before).strip() or text
    for pat in _P["tweet"]:
        m = re.search(pat, low)
        if m:
            after = text[m.end():].strip().lstrip(":\"'")
            return "tweet", after.strip() if after.strip() else text
    return "general", text


def _receive_files(files):
    import shutil
    if not files: return gr.update()
    paths = [Path(str(f)) for f in (files if isinstance(files, list) else [files])]
    raw_dir = BASE_DIR / "raw" / "articles"; raw_dir.mkdir(parents=True, exist_ok=True)
    names = []
    for src in paths:
        try: shutil.copy2(str(src), str(raw_dir / src.name)); names.append(src.name)
        except Exception: pass
    return gr.update(value=f"ingest {names[0]}") if names else gr.update()


def _clean_tweet(raw): return __import__("post_flows").clean_tweet(raw)


# ─── Main handler ───

def _run_and_fill(intention, files, prev_ctx):
    """5-tuple: (run_status, run_result_grp, agent_result, draft_post_btn, ctx)."""
    _e = ("", _hide(), "", _hide(), None)
    if not intention or not intention.strip(): yield _e; return
    intention = intention.strip()
    kind, content = _detect_intent(intention)
    if kind in ("approve", "deny"):
        fn = getattr(__import__("permissions"), kind)
        ok = fn(content); w = kind.capitalize() + "d"
        msg = f"**{w}** `{content}`." if ok else f"**Not found:** `{content}`"
        yield msg, _show(), msg, _hide(), None; return
    if kind == "wiki_init":
        yield _verb("Building wiki..."), _hide(), "", _hide(), None
        msg = __import__("wiki_engine").wiki_init(); yield msg, _show(), msg, _hide(), None; return
    if kind == "wiki_ingest":
        yield _verb("Looking for file..."), _hide(), "", _hide(), None
        from wiki_engine import find_raw_file, build_ingest_prompt, save_ingest_result
        fpath = find_raw_file(content)
        if not fpath: yield f"**Error:** No file matching '{content}'.", _hide(), "", _hide(), None; return
        yield _verb(f"Reading {fpath.name}..."), _hide(), "", _hide(), None
        try: result = __import__("agent_backend").generate(build_ingest_prompt(fpath))
        except Exception as e: yield f"**Error:** {e}", _hide(), "", _hide(), None; return
        yield _verb("Filing into wiki..."), _hide(), "", _hide(), None
        yield "**Ingested:** " + ", ".join(save_ingest_result(fpath, result)), _show(), result, _hide(), None; return
    if kind == "wiki_query":
        yield _verb("Searching wiki..."), _hide(), "", _hide(), None
        try: answer = __import__("agent_backend").generate(__import__("wiki_engine").build_query_prompt(content))
        except Exception as e: yield f"**Error:** {e}", _hide(), "", _hide(), None; return
        yield _verb("Done."), _show(), answer.strip(), _hide(), {"type": "query", "result": answer.strip()}; return
    if kind == "wiki_lint":
        yield _verb("Checking wiki health..."), _hide(), "", _hide(), None
        try: report = __import__("agent_backend").generate(__import__("wiki_engine").build_lint_prompt())
        except Exception as e: yield f"**Error:** {e}", _hide(), "", _hide(), None; return
        yield _verb("Report ready."), _show(), report.strip(), _hide(), None; return
    if kind == "direct_post":
        tweet = _clean_tweet(content)
        if not tweet: yield "**Error:** No tweet text.", _hide(), "", _hide(), None; return
        yield _verb("Posting directly..."), _show(), tweet, _hide(), None
        yield __import__("twitter_post").post_and_log(tweet), _show(), tweet, _hide(), None; return
    if kind == "tweet":
        yield _verb("Drafting tweet..."), _hide(), "", _hide(), None
        try: raw = __import__("agent_backend").generate(__import__("wiki_engine").build_tweet_prompt(content))
        except Exception as e: yield f"**Error:** {e}", _hide(), "", _hide(), None; return
        yield _verb("Sharpening..."), _hide(), "", _hide(), None; time.sleep(0.5)
        tweet = _clean_tweet(raw)
        if not tweet: yield "**Error:** Could not generate tweet.", _hide(), "", _hide(), None; return
        yield _verb("Draft ready — hit Post."), _show(), tweet, _show(), {"type": "tweet", "result": tweet}; return
    # ── General task (or follow-up) ──
    from agent_backend import generate
    if prev_ctx and prev_ctx.get("result"):
        prompt = f"PREVIOUS RESULT:\n{prev_ctx['result'][:1000]}\n\n---\n\nUSER FOLLOW-UP: {intention}\n\nRevise the previous result. Output only the revised result.\n"
        yield _verb("Refining..."), _hide(), "", _hide(), None
    else: prompt = intention; yield _verb("Thinking..."), _hide(), "", _hide(), None
    try: raw = generate(prompt)
    except Exception as e: yield f"**Error:** {e}", _hide(), "", _hide(), None; return
    result = raw.strip()
    show_post = _show() if prev_ctx and prev_ctx.get("type") == "tweet" else _hide()
    ctx = {"type": prev_ctx["type"] if prev_ctx else "general", "result": result}
    yield _verb("Done. Type to refine."), _show(), result, show_post, ctx


def _load_css() -> str:
    p = BASE_DIR / "theme.css"
    return p.read_text() if p.exists() else ""


# ─── Build the panel ───

def build_panel() -> "gr.Blocks":
    if gr is None: raise ImportError("gradio not installed")
    def _post_draft(dt, c):
        yield _verb("Posting..."), _show(), dt, _show(), c
        yield __import__("twitter_post").post_and_log(dt), _show(), dt, _hide(), None
    with gr.Blocks(title="OpenClay") as panel:
        # ══ GREETING ══
        gr.Markdown("## *What are we working on?*", elem_classes=["app-title"])
        main_input = gr.Textbox(label="", show_label=False, placeholder="What's the goal for today?",
            lines=3, elem_id="main_input", container=True, autofocus=True)
        drop_zone = gr.File(label="Drop files here", file_count="multiple", elem_classes=["drop-zone"])
        # ══ STARTER ACTIONS ══
        with gr.Row():
            s1 = gr.Button("Organize this folder", size="sm", elem_classes=["starter-btn"])
            s2 = gr.Button("Summarize these files", size="sm", elem_classes=["starter-btn"])
            s3 = gr.Button("Help me plan today", size="sm", elem_classes=["starter-btn"])
        run_btn = gr.Button("Go", variant="primary", elem_classes=["run-btn"])
        run_status = gr.Markdown("", elem_classes=["status-bar"])
        ctx_state = gr.State(None)
        # ══ RESULT AREA ══
        with gr.Group(visible=False, elem_classes=["result-card"]) as run_result_grp:
            gr.Markdown("### Result", elem_classes=["result-heading"])
            agent_result = gr.Textbox(label="", lines=6, interactive=True, elem_classes=["result-text"])
            draft_post_btn = gr.Button("Post", variant="primary", visible=False, elem_classes=["run-btn"])
        # ══ DAILY WORK ══
        with gr.Accordion("Daily Work", open=True, elem_classes=["result-card"]):
            with gr.Row():
                dw1 = gr.Button("Summarize folder", size="sm"); dw2 = gr.Button("Clean downloads", size="sm"); dw3 = gr.Button("Draft report", size="sm")
            with gr.Row():
                dw4 = gr.Button("Ingest docs", size="sm"); dw5 = gr.Button("Find duplicates", size="sm"); dw6 = gr.Button("Expense notes", size="sm")
        # ══ LOCAL SUCCESS ══
        with gr.Accordion("Local Success", open=True, elem_classes=["result-card"]):
            success_md = gr.Markdown("_Checking..._")
            def _success():
                w = len(list((BASE_DIR/"wiki").glob("*.md"))) if (BASE_DIR/"wiki").exists() else 0
                q = len(list((BASE_DIR/"queue").glob("*.json"))) if (BASE_DIR/"queue").exists() else 0
                sb = sum(1 for l in (BASE_DIR/"self_build_log.md").read_text().splitlines() if l.startswith("##")) if (BASE_DIR/"self_build_log.md").exists() else 0
                arts = [f.name for f in BASE_DIR.glob("*.md") if f.name not in ("README.md","CHANGELOG.md","AGENTS.md","SOUL.md")]
                items = [f"**{w}** wiki pages", f"**{q}** queued tasks", f"**{sb}** self-builds", f"**{len(arts)}** artifacts"]
                return " | ".join(items) if any([w, q, sb, arts]) else "No local work yet — try a starter action above."
            gr.Timer(60).tick(_success, inputs=[], outputs=[success_md])
        # ══ TWITTER (optional) ══ # Working app: 2040419672282087424anomalia939
        with gr.Accordion("Twitter (optional)", open=False, elem_classes=["result-card"]):
            tw_k = gr.Textbox(label="API Key", type="password"); tw_s = gr.Textbox(label="API Secret", type="password")
            tw_t = gr.Textbox(label="Access Token", type="password"); tw_ts = gr.Textbox(label="Access Token Secret", type="password")
            tw_save = gr.Button("Save & Test Twitter", variant="primary", elem_classes=["run-btn"])
            tw_status = gr.Markdown("", elem_classes=["status-bar"])
            def _save_tw(k, s, t, ts):
                if not all([k.strip(), s.strip(), t.strip(), ts.strip()]): return "❌ All four fields required"
                __import__("twitter_post").write_credentials(k.strip(), s.strip(), t.strip(), ts.strip())
                v = __import__("twitter_post").validate_twitter_credentials()
                return f"✅ Twitter ready — @{v['username']}" if v["status"] == "ready" else f"❌ {v['detail']}"
            tw_save.click(_save_tw, inputs=[tw_k, tw_s, tw_t, tw_ts], outputs=[tw_status])
        # ══ STORAGE ══
        with gr.Accordion("Storage", open=False, elem_classes=["result-card"]):
            st_md = gr.Markdown(""); clean_btn = gr.Button("Clean Now", variant="secondary", elem_classes=["run-btn"])
            def _disk():
                return "**Disk:** " + __import__("subprocess").run(["du", "-sh", str(BASE_DIR)], capture_output=True, text=True).stdout.split()[0]
            def _clean():
                import time as _t; now = _t.time(); out = []
                for f in list(BASE_DIR.glob("*_log*")) + list(BASE_DIR.glob("*decisions*")):
                    days = 30 if "security" in f.name else 7
                    if f.is_file() and (now - f.stat().st_mtime) > days * 86400: out.append(f.name); f.unlink()
                for f in (list((BASE_DIR/"backups").iterdir()) if (BASE_DIR/"backups").exists() else []):
                    if f.is_file() and (now - f.stat().st_mtime) > 7 * 86400: out.append(f"backups/{f.name}"); f.unlink()
                return f"**Cleaned:** {', '.join(out)}\n{_disk()}" if out else f"Nothing to clean. {_disk()}"
            clean_btn.click(_clean, inputs=[], outputs=[st_md])
        # ══ MOBILE ══
        with gr.Accordion("Mobile", open=False, elem_classes=["result-card"]):
            try: gr.HTML(__import__("mobile_bridge").add_mobile_section())
            except Exception: gr.Markdown("_Mobile bridge not available._")
        # ══ SELF-BUILD ══
        improve_status = gr.Markdown("", elem_classes=["status-bar"])
        def _run_improve():
            try:
                r = __import__("self_build_loop").run_once()
                return f"**Self-build:** {r.get('status')} — {r.get('explanation', r.get('failures', 'done'))}"
            except Exception as e: return f"**Error:** {e}"
        improve_btn = gr.Button("Improve OpenClay", variant="secondary", elem_classes=["run-btn"])
        improve_btn.click(_run_improve, inputs=[], outputs=[improve_status])
        # ══ APPROVALS + WATCHDOG ══
        approvals_md = gr.Markdown("", visible=False, elem_classes=["approvals-bar"])
        needs_attn = gr.Markdown("", visible=False, elem_classes=["watchdog-alert"])
        def _poll_approvals():
            p = __import__("permissions").list_pending()
            if not p: return gr.update(value="", visible=False)
            lines = [f"- `{x['action']}` — {x['detail'][:60]} — id: `{x['id']}`" for x in p[:5]]
            return gr.update(value="**Pending:**\n" + "\n".join(lines) + "\n_approve/deny <id>_", visible=True)
        def _poll_alert():
            p = BASE_DIR / "data" / "watchdog_alert.txt"
            t = p.read_text().strip() if p.exists() else ""
            return gr.update(value=f"**Needs from you:** {t}", visible=True) if t else gr.update(value="", visible=False)
        # ══ WIRING ══
        gr.Timer(15).tick(_poll_approvals, inputs=[], outputs=[approvals_md])
        gr.Timer(30).tick(_poll_alert, inputs=[], outputs=[needs_attn])
        drop_zone.change(_receive_files, inputs=[drop_zone], outputs=[main_input])
        _out = [run_status, run_result_grp, agent_result, draft_post_btn, ctx_state]
        run_btn.click(_run_and_fill, inputs=[main_input, drop_zone, ctx_state], outputs=_out)
        main_input.submit(_run_and_fill, inputs=[main_input, drop_zone, ctx_state], outputs=_out)
        draft_post_btn.click(_post_draft, inputs=[agent_result, ctx_state], outputs=_out)
        s1.click(lambda: "organize the current folder", outputs=[main_input])
        s2.click(lambda: "summarize the files I dropped", outputs=[main_input])
        s3.click(lambda: "help me plan my day", outputs=[main_input])
        for b, t in [(dw1,"summarize this folder"),(dw2,"clean up my downloads folder"),(dw3,"draft a report from recent files"),
                     (dw4,"ingest documents into wiki"),(dw5,"find duplicate files"),(dw6,"create expense notes from recent transactions")]:
            b.click(lambda x=t: x, outputs=[main_input])
    return panel


def launch(share=False):
    p = build_panel()
    p.launch(server_name="127.0.0.1", server_port=7861, share=share,
             inbrowser=True, show_error=True, css=_load_css(), quiet=True)

def self_test() -> bool:
    """Verify intent detection."""
    assert _detect_intent("build wiki")[0] == "wiki_init"
    assert _detect_intent("post a tweet about AI")[0] == "tweet"
    assert _detect_intent("ingest report.md")[0] == "wiki_ingest"
    assert _detect_intent("approve abc123")[0] == "approve"
    assert _detect_intent("deny xyz")[0] == "deny"
    assert _detect_intent("hello world")[0] == "general"
    return True

if __name__ == "__main__": launch()
