---
title: Overview
type: overview
created: 2026-04-05
updated: 2026-04-05
confidence: high
---

# Overview

This wiki is maintained by OpenClay's LLM agent. It compounds over time.

Every source ingested, every post filed, every query answered adds to the
memory. The agent reads this wiki before acting. Better wiki, better actions.

## Structure

- **concepts/** — idea pages, one per concept
- **entities/** — people, orgs, tools
- **sources/** — one summary per ingested source
- **comparisons/** — cross-source analysis
- **posts/** — filed tweets and social posts
- **brand/** — voice guide, identity
- **log.md** — append-only activity record
- **index.md** — master catalog, auto-generated

## Rules

- `raw/` is immutable. LLM reads, never writes.
- `wiki/` is LLM-owned. User reads, LLM writes.
- Every page has YAML frontmatter: title, type, sources, related, created, updated, confidence.
- Every write appends to log.md.
- Index rebuilds after every operation.
