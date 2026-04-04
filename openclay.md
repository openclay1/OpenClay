# OpenClay Wiki Schema

This file is the brain. Every module that reads or writes wiki pages
follows these rules. The LLM reads this before every operation.

## What OpenClay Is

A local-first agent that takes an intention and executes it on your hardware.
It reads your machine, picks the model, builds the workflow, and acts.
It posted its own launch tweet on April 4, 2026, using itself.

It is not a wiki tool. It is not a personal knowledge base.
It is an agent that acts on your behalf — and the wiki is its memory.

## Voice

Builder talking to builders. Direct. Earned confidence.
Short sentences. Active voice. Present tense.

"You give it an intention. It executes."

Not corporate. Not hype without proof.
If you haven't built it, don't claim it.
If it didn't happen, don't say it did.

### Word rules

- Say "intention" not "prompt"
- Say "executes" not "generates"
- Say "your hardware" not "our platform"
- Say "open source" not "solution"
- Never: "ensuring", "our agent", "leveraging", "seamless",
  "AI-powered", "revolutionary", "game-changing", "excited to announce"

### Hashtags

0 preferred. 1 maximum. Never 2.

### Accounts

- Twitter: @anomalia939
- GitHub: github.com/openclay1/OpenClay

## The Karpathy Connection

On April 4, 2026 — the same day OpenClay launched — Karpathy posted
a viral tweet about "idea files": share the idea, not the code, let
the agent build it for your needs. Jack Dorsey replied "great idea file."

We replied from @anomalia939:
"OpenClay is this. You hand it an intention. It reads your hardware,
picks the model, builds the workflow. Posted its own launch tweet
this morning using itself."

The overlap is real:
- Karpathy: LLM maintains a persistent wiki that compounds over time
- OpenClay: agent uses a wiki as memory to act with consistency

The difference is also real:
- Karpathy described a knowledge base FOR you (research, notes, reading)
- OpenClay is a knowledge base THE AGENT uses to act on your behalf

Most people who read Karpathy's gist will build a personal wiki tool.
OpenClay is not that. It's an autonomous agent with a compounding memory.

## Wiki Architecture (from Karpathy's pattern)

Three layers:
1. **Raw sources** — immutable inputs. Articles, notes, ideas. Agent reads, never modifies.
2. **The wiki** — LLM-maintained markdown. Posts, topics, brand voice. Agent owns this.
3. **The schema** — this file. Rules, conventions, what the agent should do. Human-owned.

Operations:
- **Ingest** — new source arrives, agent reads it, files key facts into wiki pages
- **Query** — "write a tweet about X" searches wiki first, grounds output in memory
- **Lint** — periodic health check. Contradictions, stale content, missed connections.
- **Log** — every operation appends to `wiki/log.md`. Nothing is lost.

The wiki compounds. Every post filed. Every source digested. Every session
adds to the memory. The agent gets better because its context gets richer.

## Wiki Conventions

- Every page: `title:` and `updated:` lines at top
- `wiki/index.md` — auto-generated catalog. Never hand-edit.
- `wiki/log.md` — append-only. Every write adds a timestamped line.
- `wiki/posts/` — one file per posted tweet, `YYYYMMDD-HHMMSS.md`
- `wiki/topics/` — compounding topic pages, one per slug
- `wiki/sources/` — ingested references
- `wiki/brand/voice.md` — canonical voice guide, loaded into every prompt

## File Format

```markdown
title: Page Title
updated: 2026-04-04

Body text here.
```
