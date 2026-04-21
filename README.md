![version](https://img.shields.io/badge/version-v1.0.0-e06438?style=flat-square)
![license](https://img.shields.io/badge/license-MIT-cec8c0?style=flat-square)
![made in](https://img.shields.io/badge/made%20in-Puerto%20Rico%20%F0%9F%87%B5%F0%9F%87%B7-161310?style=flat-square)

# OpenClay

**A local AI that understands your context and acts on your machine.**  
You don't depend on anyone else's servers.

---

*by Francis Dávila · San Juan, Puerto Rico*

For years I ran my research on other people's computers.

Every query I typed into a cloud AI tool was a small act of trust — trust that the company would protect it, that the servers would stay up, that the subscription would remain affordable, that my work wouldn't become someone else's training data. That trust kept accumulating interest I didn't know I was paying.

Then the blackout happened.

It wasn't dramatic. Puerto Rico has blackouts the way some places have weather — you plan around them, you adapt, you keep a battery bank on the shelf next to the coffee. But that afternoon I needed to finish an analysis for a clinical team, the grid went down, and every tool I depended on was suddenly on the other side of a wall I couldn't get through. Not because I lacked the knowledge. Not because the hardware in front of me couldn't do the work. Because I'd let the work live somewhere else.

I sat in the dark for a while. Then I started building.

The idea was simple: an AI assistant that runs entirely on your own machine. No internet required. No API key. No monthly check to a company in California. Something that would work during a hurricane, in a hospital ward with strict data rules, in any place where the cloud was either unavailable or unacceptable.

But as I built it, I realized the deeper problem wasn't connectivity — it was memory. Every cloud tool I'd used reset with every session. It never knew me. It never learned what I cared about, how I preferred to think, what projects I was in the middle of. It was brilliant and amnesiac, every single time.

OpenClay is my answer to that. It knows your name. It remembers your projects. It learns your preferences and keeps them on your drive, not in someone else's database. The longer you use it, the more it becomes yours — irreplaceable not because of what it is, but because of what it knows about you.

I built it for Puerto Rico first, because Puerto Rico needed it first. Pharmaceutical researchers who can't send patient-adjacent data to the cloud. Clinicians who work in hospitals that lose power. Students who can't afford $200 a month for the tools their peers in richer markets take for granted.

But the truth is I built it for anyone who ever felt like the tools were working for someone else.

OpenClay isn't just software. It's a message from the version of us that figured it out.

---

## What it does

- **Remembers you across every session** — your name, your work, your preferences, your ongoing projects. Memory lives on your drive.
- **5 specialized agents** — General, Investigador, Clínico, Coder, Explorer. Each has a distinct voice and a distinct purpose.
- **Clay Code** — read, edit, and run code on your machine with full context. Diff view, plan mode, no cloud execution.
- **Agent orchestration** — chain agents together for complex multi-step tasks. Each agent in the chain gets memory context injected.
- **100% local** — no cloud, no API keys, no telemetry, no data leaving your machine.

## Install

**Requirements:** macOS or Linux · Python 3.10+ · [Ollama](https://ollama.ai)

```bash
# 1. Install Ollama, then pull a model
ollama pull llama3

# 2. Clone the repo
git clone https://github.com/openclay1/OpenClay
cd OpenClay

# 3. Run the installer (sets up virtualenv + dependencies)
bash install.sh

# 4. Launch
python3 clay_server.py
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

Ollama starts automatically when the server launches. A banner at the top shows "Starting local model…" and dismisses when it's ready.

## Run as a Mac app

Generate a double-clickable app once — then just click it to launch:

```bash
bash create_app.sh
```

This creates `OpenClay.app` in the project folder. Double-click it. Your browser opens to localhost:3000 automatically. The `.app` is gitignored — each user generates it locally.

## Tell Clay about yourself

Create `SOUL.md` in the project root with a few sentences about who you are and what you work on. Clay reads it on every session start and uses it as the foundation for all responses.

```markdown
# My context
I'm a pharmaceutical researcher in San Juan. I work on FDA compliance documents and clinical trial data. I prefer concise answers and I work in both English and Spanish.
```

The longer you use OpenClay, the more it builds on top of this foundation — using Mem0 to store memories from each conversation.

## Memory & Dreaming

After each session, OpenClay runs a background memory consolidation process called Dreaming. It has three phases:

**Light** — reads today's conversation logs and extracts candidate sentences from Clay's responses. Computes how often each sentence appeared (frequency), how late in the session it occurred (recency), and how many different questions it came up in (query diversity).

**REM** — asks the local model to classify each candidate (factual, experiential, belief, preference, or skill) and estimate how personally meaningful and conceptually rich it is. Combines those scores with the signals from the Light phase into a single composite score using six weighted signals:

| Signal | Weight |
|---|---|
| Relevance (LLM-rated) | 0.30 |
| Frequency | 0.24 |
| Query diversity | 0.15 |
| Recency | 0.15 |
| Not already in memory (consolidation) | 0.10 |
| Conceptual richness (LLM-rated) | 0.06 |

**Deep** — promotes the top-scoring candidates (threshold: 0.55) to `MEMORY.md` and syncs to ChromaDB. At most 8 memories are promoted per cycle.

**`MEMORY.md`** lives in the project root. It's the source of truth for everything the Dreaming system has learned about you — grouped by memory type, with a score annotation on each entry. You can edit it directly. The system respects your edits and won't overwrite them.

**`DREAMS.md`** also lives in the project root. It's a human-readable diary of what Clay learned about you each session — one entry per cycle, newest first. Each entry lists the promoted memories and includes a short narrative paragraph Clay writes about the session.

The whole system is fully local. No network calls. Runs on the same Ollama model as the rest of OpenClay. The diary paragraph is generated in a fire-and-forget background thread so it never delays inference or the memory writes.

## All features are free

Every feature is available to everyone. Clay Code, agent orchestration, scheduled tasks, multi-agent chains — all of it. No license key. No credit card. No upsell.

If OpenClay helps you, consider [supporting the project](YOUR_GUMROAD_LINK). Pay what you want. It keeps development going.

## Support

OpenClay is free forever. If it helps you: [support the project →](YOUR_GUMROAD_LINK)

Built by COANA Labs · San Juan, Puerto Rico
