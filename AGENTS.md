<!-- OpenClay persistent memory. Never delete this file. -->
<!-- Last updated: 2026-04-05 09:41:02 -->

## Machine Profile

- OS: Darwin 24.6.0
- Machine: x86_64
- RAM: 16384MB
- GPU: {'name': 'Intel Iris Plus Graphics 645', 'vram_mb': 1536, 'has_metal': True, 'has_cuda': False}
- Tier: medium-low
- Model: ?
- Detected: 2026-04-05 09:37:34

## What Works

- [2026-04-04 21:26:10] generate(clawcode) (tools: qwen2.5:3b-instruct-q4_K_M) — VOICE: # Voice  Builder talking to builders. You built something that works. Say
- [2026-04-04 21:39:53] generate(clawcode) (tools: qwen2.5:3b-instruct-q4_K_M) — VOICE: # Voice  Builder talking to builders. You built something that works. Say
- [2026-04-04 22:24:04] generate(clawcode) (tools: qwen2.5:3b-instruct-q4_K_M) — VOICE: # Voice  Builder talking to builders. You built something that works. Say
- [2026-04-05 09:41:02] generate(clawcode) (tools: qwen2.5:3b-instruct-q4_K_M) — Post a mysterious tweet on x about working on something new.

## What Failed

_Empty — no failures recorded yet._

## User Preferences

_Empty — no patterns observed yet._

## Banned Patterns

_Empty — nothing banned yet._

## Wiki

OpenClay maintains a Karpathy-style LLM wiki — a local, file-based knowledge
base that compounds over time. The LLM reads it before acting. Better wiki,
better actions.

### Structure

```
wiki/
  index.md          ← auto-generated catalog, rebuilt after every op
  log.md            ← append-only activity record
  overview.md       ← high-level synthesis
  brand/voice.md    ← canonical voice guide
  concepts/         ← one page per concept
  entities/         ← people, orgs, tools
  sources/          ← one summary per ingested source
  comparisons/      ← cross-source analysis
  posts/            ← filed tweets and social posts
raw/
  articles/         ← source documents (immutable, LLM never writes here)
  assets/           ← images, PDFs, binary files
```

### Page Frontmatter

Every wiki page uses YAML frontmatter:
```yaml
---
title: Page Title
type: concept | entity | source | comparison | post | overview
sources: [filename1.md, filename2.md]
related: [page1, page2]
created: 2026-04-05
updated: 2026-04-05
confidence: high | medium | low
---
```

### Operations

- **init** — "build my wiki" creates the full directory structure
- **ingest** — "ingest [filename]" reads from raw/, creates wiki pages, updates index
- **query** — "query: [question]" searches wiki pages, synthesizes answer with citations
- **lint** — "lint" health-checks for orphans, contradictions, missing pages

### Rules

- `raw/` is immutable. LLM reads, never writes.
- `wiki/` is LLM-owned. User reads, LLM writes.
- Every write appends to `wiki/log.md`.
- `wiki/index.md` rebuilds after every operation.
- Existing concept/entity pages are appended to, not overwritten.
