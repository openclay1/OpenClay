# 🏺 OpenClay — turn intention into infrastructure.

You describe what you want. OpenClay reads your machine, builds a local AI stack, and starts working. No config files. No copy-paste. Everything it learns about you stays on your computer, in files you own.

<!-- TODO: replace with actual GIF -->
![OpenClay demo](https://via.placeholder.com/800x400?text=demo+GIF+goes+here)

```bash
git clone https://github.com/openclay1/OpenClay.git && cd OpenClay && pip3 install -r requirements.txt && python3 app.py
```

| Your hardware | What OpenClay runs |
|---|---|
| 32 GB+ RAM, Apple Silicon / 6 GB+ VRAM | `llama3:8b` — full reasoning |
| 16 GB+ RAM, Apple Silicon / CUDA | `qwen2.5:7b` — fast + capable |
| 16 GB+ RAM, Intel, no discrete GPU | `qwen2.5:3b-instruct-q4_K_M` — lean workhorse |
| 8 GB+ RAM | `qwen2.5:1.5b` — lightweight |
| Under 8 GB | Template-only mode — no model needed |
| Any machine + API key | Claude, GPT-4, etc. via config |

---

## What it does today

- **Single input, single button.** Type an intention, hit Go.
- **Hardware detection → model selection → silent install.** You don't pick a model. It does.
- **LLM Wiki.** Karpathy-pattern knowledge base. Ingest files, query your wiki, lint for health. Local markdown, yours forever.
- **Tweet drafting and posting.** Draft from intention, review, post — or post directly.
- **Persistent memory.** AGENTS.md tracks what works, what fails, your preferences. The agent reads it before every action.

## How it works

```
intention → hardware scan → model install → execution → wiki memory
```

Everything runs locally through Ollama. No data leaves your machine.

## Wiki

OpenClay maintains a local wiki that compounds over time. Drop a file in `raw/`, type `ingest filename`, and the LLM breaks it into concept pages, entity pages, and source summaries. Query it later. Lint it for contradictions.

```
raw/              ← your files, immutable, LLM never writes here
wiki/
  concepts/       ← idea pages
  entities/       ← people, orgs, tools
  sources/        ← one summary per ingested file
  comparisons/    ← cross-source analysis
  index.md        ← auto-generated catalog
  log.md          ← append-only activity record
```

The wiki is not for you. It's for the agent — so it can act with consistency.

## Configuration

```bash
cp .env.example .env
```

Most things work with zero config. Add Twitter keys only if you want to post.

## Project structure

```
app.py              — entry point
panel.py            — browser UI (Gradio)
agent_backend.py    — switchable LLM backend
wiki_engine.py      — wiki operations: ingest, query, lint
memory.py           — AGENTS.md persistent memory
twitter_post.py     — tweet posting (Tweepy)
introspect.py       — hardware detection
theme.css           — design system
openclay.md         — wiki schema
wiki/               — agent's compounding memory
raw/                — immutable source documents
```

Every module stays under 300 lines.

## Principles

1. **Act, don't ask.** If the agent can do it, it does it.
2. **Local-first.** No cloud dependency for core function.
3. **Files over apps.** Markdown you own, not data locked in a platform.
4. **Install what's missing.** Silent. No questions.

## License

MIT — it's yours.

[github.com/openclay1/OpenClay](https://github.com/openclay1/OpenClay)
