# *OpenClay*

I am a local-first AI agent that runs on your machine. I help you get through your day — organizing files, summarizing documents, drafting reports, managing expenses, and executing tasks you describe in plain language. Everything stays on your hardware.

## What I do every day

- **Organize your folders.** Point me at a directory and I sort, rename, and clean it up.
- **Summarize files and documents.** Drop PDFs, notes, or code — I extract what matters.
- **Draft reports and notes.** Describe what you need, I write the first version. You refine it.
- **Track expenses and accounting.** Feed me receipts or transaction notes, I produce summaries you can keep.
- **Research and synthesize.** Ask a question, I search your wiki and local files, then give you a straight answer.
- **Ingest knowledge into a wiki.** Drop articles, docs, transcripts — I file them into a local wiki that compounds over time.
- **Find duplicates and clean up.** I scan directories for redundant files and help you reclaim space.
- **Plan your day.** Tell me what you're working on, I break it into steps.

## What else I can do

- **Post to Twitter** — optional. If you connect your API keys, I can draft and post tweets. This is not required for anything else to work.
- **Accept tasks from your phone** — WebSocket bridge with QR code, voice input, file uploads over local WiFi.
- **Heal and improve myself** — retry failed calls, auto-fix recurring errors, and run a constrained self-build loop that only keeps changes that pass all 21 tests.
- **Guard every input and output** — prompt injection detection, permission tiers (GREEN/YELLOW/RED), output validation.

## Why not cloud agents?

Cloud-hosted AI agents are powerful. They run on someone else's servers, require their subscription, and your data passes through their infrastructure. When pricing changes, your workflow breaks. When a platform pivots, your agent disappears.

OpenClay runs on your machine. Your data never leaves. No subscription can cut you off. No platform can change the rules on you. Same capability. Full ownership.

If the cloud goes down, OpenClay keeps working. If a provider raises prices, OpenClay costs nothing. If a company pivots to healthcare or enterprise, OpenClay still answers to you.

## Industries

- **Healthcare and life sciences.** Keep patient notes, research summaries, and clinical references in a local wiki that never touches a cloud server.
- **Finance and accounting.** Ingest transaction records, draft expense reports, and maintain audit trails — all on hardware you control.
- **Operations and file management.** Organize folders, clean up downloads, find duplicates, and maintain structured archives without uploading anything.
- **Research and knowledge work.** Build a compounding knowledge base from papers, transcripts, and notes — query it in plain language, keep it forever.

## How to run me

```bash
pip install openclay-agent
```

Or from source:

```bash
git clone https://github.com/openclay1/OpenClay.git
cd OpenClay
pip3 install -r requirements.txt
python3 app.py
```

I detect your machine, pick the right model, install it, and open a browser panel at `http://127.0.0.1:7861`. The first thing you see is a prompt: *What are we working on?*

## Architecture

```
intention → ClayRuntime [guard → permission gate → execute → validate output]
                ↓
    model_router [LOCAL_FAST → LOCAL_SMART → CLOUD]
                ↓
    agent_backend → Ollama (gemma4:e4b / gemma4:26b)
                ↓
    vibe_brain [L0 SOUL.md → L1 BRAIN.md → L2 SESSION.md → L3 DECISIONS.md]
                ↓
    memory ← wiki ← logs ← self_build_loop
```

### Memory architecture (Vibe Brain)

| Level | What | Loaded when | Size |
|-------|------|-------------|------|
| L0 | Identity (SOUL.md core traits) | Always | ~100 tokens |
| L1 | Long-term knowledge (BRAIN.md) | Always | <500 words |
| L2 | Current task context (SESSION.md) | Always | <200 words |
| L3 | Past decisions (DECISIONS.md) | On demand only | Unlimited |

Plain markdown memory. No databases. No embeddings. No cloud. BRAIN.md stays under 500 words via a compression cycle that runs every 10 completed tasks. Default load (L0+L1+L2) stays under 2,000 tokens.

### Model routing tiers

| Tier | Model | Used for |
|------|-------|----------|
| LOCAL_FAST | `gemma4:e4b` | Formatting, scheduling, captions, file ops, simple Q&A |
| LOCAL_SMART | `gemma4:26b` | Wiki ingest/query/lint, summarization, code review, reasoning |
| CLOUD | Claude / GPT-4o | Only when local fails — architecture, multi-step debugging |

### Permission tiers

| Tier | Behaviour | Examples |
|------|-----------|----------|
| GREEN | Fully autonomous | Read files, wiki ops, local LLM, queue management |
| YELLOW | Auto-execute, logged | Install stack, pull models, read public URLs |
| RED | Blocked until approved | Post tweet, run shell command, delete data |

Every module stays under 300 lines. Every module has a `self_test()`. All 22 pass.

### Project structure

```
app.py              — entry point
panel.py            — browser UI (Gradio) — conversational first screen
agent.py            — core loop + ClayRuntime security wrapper
agent_backend.py    — switchable LLM backend (Ollama)
model_router.py     — LOCAL_FAST / LOCAL_SMART / CLOUD routing
input_guard.py      — prompt injection detection + sanitization
permissions.py      — GREEN/YELLOW/RED action tiers + domain allowlist
wiki_engine.py      — wiki: ingest, query, lint
vibe_brain.py       — plain markdown memory (BRAIN.md, SESSION.md, DECISIONS.md)
memory.py           — AGENTS.md persistent memory
twitter_post.py     — tweet posting (optional, Tweepy)
post_flows.py       — social post workflows
credential_store.py — .env credential writer
vision_caption.py   — image/video captioning
mobile_bridge.py    — phone interface (WebSocket + QR + voice)
self_build_loop.py  — constrained self-editing
retry_ext.py        — retry decorator (3x, exponential backoff)
watchdog.py         — 4-tier self-healing daemon
installer.py        — silent Ollama + tool installation
```

Built locally. Runs quietly. Gets better slowly. Answers to you.

## License

MIT — it's yours.

[github.com/openclay1/OpenClay](https://github.com/openclay1/OpenClay)
