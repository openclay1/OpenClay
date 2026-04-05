# *OpenClay*

You describe what you want done. It executes.

OpenClay is a local AI agent bootstrapper. It detects your hardware, installs the right open-source models, and runs the workflow — on your machine, forever. No cloud. No subscription. No API costs.

Twitter posting was the first proof the pipeline works. But OpenClay is not a Twitter tool. It's not a content tool. It's a general-purpose local agent that takes an intention and acts on it.

You point it at a problem. It figures out what it needs, installs it, and goes.

---

## Quick Start

```bash
git clone https://github.com/openclay1/OpenClay.git
cd OpenClay
pip3 install -r requirements.txt
python3 app.py
```

The browser opens. You see a blinking cursor. Type what you want to build.

---

## Honest Status

This is an early build. It works — it posted its own launch tweet on April 4, 2026 using itself. But it's raw. Expect rough edges, missing features, and things that break. If you're the kind of person who builds anyway, this is for you.

What works today:
- Hardware detection → automatic model selection via Ollama
- Tweet drafting and posting via local LLM + Tweepy
- Image analysis and Instagram captions via local llava vision model
- Wiki memory layer that compounds knowledge across sessions
- Dual agent backend (Claw Code tool-use loop / Claude Code generation)

What's coming:
- Video workflows
- Research and monitoring pipelines
- Data ingestion and generation
- Whatever you point it at — it's a bootstrapper, not a product

---

## How It Works

```
You type an intention
       ↓
Hardware detection → picks the right model for your machine
       ↓
Silent installation → installs what it needs, no questions
       ↓
Execution → does the thing
       ↓
Wiki memory → logs what it did, compounds over time
```

Everything runs locally through Ollama. No data leaves your machine.

---

## Memory

OpenClay maintains a local wiki (`wiki/`) that it reads and writes itself. Every tweet posted, every source ingested, every operation logged. The wiki is the agent's memory — it compounds over time so the agent gets better the more you use it.

This follows the pattern Karpathy described on April 4, 2026: LLM-maintained persistent knowledge bases. The difference is that OpenClay's wiki isn't for you — it's for the agent, so it can act with consistency.

---

## Hardware Tiers

OpenClay reads your machine and picks the right model:

| Your hardware | What it runs |
|---|---|
| 32GB+ RAM, Apple Silicon / 6GB+ VRAM | `llama3:8b` |
| 16GB+ RAM, Apple Silicon / CUDA | `qwen2.5:7b` |
| 16GB+ RAM, Intel, no GPU | `qwen2.5:3b-instruct-q4_K_M` |
| 8GB+ RAM | `qwen2.5:1.5b` |
| Under 8GB | Template-only mode |

---

## Configuration

Copy `.env.example` to `.env` and fill in what you need:

```bash
AGENT_BACKEND=clawcode    # or claudecode
TWITTER_API_KEY=           # optional — only if you want to post
TWITTER_API_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_TOKEN_SECRET=
```

Most things work with zero configuration. The agent picks its own model and installs its own tools.

---

## Project Structure

```
app.py              — entry point, sequences everything
panel.py            — browser UI (Gradio)
agent_backend.py    — switchable LLM backend
wiki_engine.py      — persistent wiki memory
vision_caption.py   — local image analysis (llava)
twitter_post.py     — tweet posting (Tweepy)
introspect.py       — hardware detection
installer.py        — silent tool installation
theme.css           — design system
openclay.md         — wiki schema / brand brain
wiki/               — agent's compounding memory
```

Every module stays under 300 lines. Modules talk through `queue/` (JSON) and SQLite — no direct imports for business logic.

---

## Principles

1. **Act, don't ask** — if the agent can do it, it does it
2. **Local-first** — no cloud dependency for core function
3. **Install what's missing** — if a tool isn't there, get it silently
4. **No half-outputs** — every result must be complete and actionable

---

## License

MIT — it's yours, do what you want with it.

github.com/openclay1/OpenClay
