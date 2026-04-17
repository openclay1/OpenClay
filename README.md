![version](https://img.shields.io/badge/version-v1.3.1-e06438?style=flat-square)
![license](https://img.shields.io/badge/license-MIT-cec8c0?style=flat-square)
![made in](https://img.shields.io/badge/made%20in-Puerto%20Rico%20%F0%9F%87%B5%F0%9F%87%B7-161310?style=flat-square)

# OpenClay

> Local AI that executes — not simulates. Built by COANA Labs in Puerto Rico.

## What it does

- **Runs real tasks autonomously** — scans files, writes reports, reviews documents, scores grant applications. No simulation, no hallucinated file systems. Steps resolve against the actual disk.
- **100% local, zero data egress** — everything runs on your machine via Ollama. No API keys, no subscriptions, no cloud.
- **Bilingual by default** — responds in Spanish or English depending on how you speak to it. Built for Puerto Rico, works anywhere.

## Demo tasks

| Task | What it does | Output |
|------|-------------|--------|
| **Analyze Project State** | Scans `sandbox/`, extracts 2-sentence summaries from text files, computes stats | `sandbox/output/project_state_report.md` |
| **Biotech Document Review** | Extracts objectives/methods/results, flags FDA/GMP/ICH terms, identifies missing sections | `sandbox/output/document_review_[name].md` |
| **Grant Intelligence Brief** | Scores grant alignment vs. COANA profile (1–10), drafts 2-paragraph tailored abstract | `sandbox/output/grant_brief_[date].md` |

Click any demo tile in the **Tareas** tab, or run from the CLI:

```bash
python openclay.py --hunt-grants   # runs all entries in grants_targets.json
python openclay.py --metrics       # shows execution stats
```

## Performance

Measured across demo task runs (scripted execution, no LLM loop):

| Task Name | Avg Steps | Avg Retries | Success Rate |
|-----------|-----------|-------------|--------------|
| analyze_project_state | 4.0 | 0.0 | 100% |
| biotech_document_review | 5.0 | 0.0 | 100% |
| grant_intelligence_brief | 4.0 | 0.0 | 100% |

## The principle

> "OpenClay operates in environments that reflect reality. It does not simulate file systems or execution contexts. Actions must resolve truthfully."
>
> — COANA Labs Design Principles

All task steps run via actual subprocess execution (`bash`, `python3`). The LLM plans; the system executes; the result is verified by exit code. No mocking.

## Run it

```bash
git clone https://github.com/openclay1/OpenClay.git
cd OpenClay

# Install dependencies
pip install mem0ai

# Pull the model (3B, runs on CPU)
ollama pull qwen2.5:3b-instruct-q4_K_M

# Start
python clay_server.py

# Open in browser
open http://localhost:3000
```

**CLI tools:**

```bash
python openclay.py --metrics       # task execution stats
python openclay.py --hunt-grants   # automated grant alignment for all targets
python openclay.py --help          # all commands
```

## Hardware

OpenClay runs on any machine with Ollama installed — no GPU required for the 3B model.

**Claydeck** is coming — a purpose-built device with local compute, LoRa mesh networking, and a custom enclosure. Designed for research teams, clinics, and communities that need AI without infrastructure dependency. Details at [coana.lab](https://coana.lab).

## Built with

Ollama · qwen2.5:3b-instruct-q4_K_M · p5.js · Python · Puerto Rico

---

*COANA Labs · Todo es local. Nada sale de aquí.*
