# OpenClay — Technical White Paper (Draft)
**COANA Labs · v1.3.2 · 2026-04-17**

---

## 1. System Overview

OpenClay is a locally-executed AI assistant and autonomous task engine. It runs entirely on the host machine via Ollama — a local model runtime — and exposes a single HTTP server on port 3000 that serves both a browser-based interface and a JSON API.

The system does three things that are worth distinguishing:

1. **Conversational inference.** Users send messages through a p5.js interface; the server streams responses from a local language model and maintains per-session conversation history.

2. **Autonomous task execution.** Users submit goals. The system plans a multi-step sequence, executes each step via actual subprocess calls (`bash`, `python3`), verifies success by exit code, and retries on failure — up to a configurable maximum.

3. **Agent routing.** Four named agent configurations (Clay General, Clay Investigador, Clay Clínico, Clay Explorer) each carry a system prompt, an allowed-tools list, a color accent, and a model preference. The active agent is selected by the user and its system prompt is injected into every inference call.

No data leaves the machine. No API keys are required for baseline operation. The LLM is queried via `http://localhost:11434` (Ollama's local endpoint).

---

## 2. Architecture

### 2.1 clay_server.py — The central process

`clay_server.py` is a single-file Python HTTP server built on `http.server.BaseHTTPRequestHandler`. It handles all routes: static file serving, chat inference, task lifecycle management, memory operations, and log access. There is no framework dependency — all routing is done via string matching on `self.path`.

On startup, the server:
1. Starts Ollama if it is not already running (`subprocess.Popen(["ollama", "serve"])`)
2. Detects the available model by querying `/api/tags`, preferring `qwen2.5:3b-instruct-q4_K_M` from a ranked list
3. Loads the soul document (`soul.md` + optional `soul_custom.md`) and substitutes the detected model name
4. Loads agent configurations from `agents/*.agent.json`
5. Initializes Mem0 memory with a ChromaDB vector store at `memory_store/`
6. Initializes a three-network research memory (factual, experiential, beliefs) via ChromaDB at `memory_store/hindsight/`
7. Continues the tamper-evident log chain from the last recorded hash in today's log file

### 2.2 Task execution model

Tasks are created with a UUID, assigned the active agent, persisted to `tasks/<uuid>.json`, and executed in a background daemon thread. The task dict holds `status`, `steps[]`, `retry_count`, `max_retries` (3), and `final_result`.

The execution loop in `_task_run()` cycles through four phases per step:

- **Plan** — `_task_plan()` sends the goal and the last five steps to the LLM, asking for the next single action as a JSON object with keys `action` and `input`. Valid actions are `bash`, `python`, `write`, `read`, `done`.
- **Execute** — `_task_execute_action()` dispatches to `_execute_code()` for `bash`/`python`, a path-safe file read for `read`, or a direct write for `write`.
- **Verify** — `_task_verify()` trusts the OS exit code: exit 0 = success, non-zero = failure. No secondary LLM call is made for verification.
- **Decide** — On success the retry counter resets to 0. On failure it increments; at `max_retries` the task status is set to `"failed"`.

Goal-satisfaction checking (`_is_goal_satisfied()`) short-circuits the LLM loop if: two consecutive steps repeat the same description and both succeeded; all action-keywords from the goal appear in completed steps; or 8+ successful steps have accumulated. The hard upper limit is 20 steps (`MAX_TASK_STEPS`).

### 2.3 Sandbox vs. BASE_DIR

Two working directories are in use:

| Context | Path | Used for |
|---------|------|----------|
| `SANDBOX_DIR` | `<BASE_DIR>/sandbox/` | Default cwd for the `/api/execute` endpoint (ad-hoc code from the UI); all `write` actions in task steps; output files |
| `BASE_DIR` | Parent of `clay_server.py` | cwd for `bash` and `python` actions in the task engine, so that paths like `./sandbox/...` resolve correctly |

File `read` in tasks resolves first against `BASE_DIR`, then against `SANDBOX_DIR`. A path-escape check (`candidate.relative_to(BASE_DIR)`) prevents traversal outside the project.

### 2.4 Agent system

Agents are JSON files in `agents/`. The four shipped configurations are:

| Agent | Description | Language |
|-------|-------------|----------|
| Clay General | Versatile research/writing assistant | auto (es/en) |
| Clay Investigador | Research-focused | Spanish |
| Clay Clínico | Clinical/biomedical focus | Spanish |
| Clay Explorer | Exploration and discovery | auto |

Each agent specifies `allowed_tools` (a declarative list — `file_read`, `file_write`, `code_execute`, `log_export`), a `system_prompt`, and a model preference. The active agent's system prompt is prepended to every inference call in conversation mode.

Model routing (`model_router.py`) operates on three tiers: **LOCAL\_FAST** (`gemma4:e4b`) for formatting, scheduling, and simple Q&A; **LOCAL\_SMART** (`gemma4:26b`) for wiki ingest, code review, and multi-step reasoning; and **CLOUD** (Anthropic or OpenAI, via keys in `.env`) for tasks matching complexity signals like `architect`, `refactor`, or requests for 50+ lines of generated code. Cloud escalation only occurs if an API key is present; otherwise LOCAL\_SMART is the ceiling. Every routing decision is appended to `routing_log.md`.

### 2.5 Mem0 persistent memory

Mem0 is initialized with the local Ollama model for the LLM component and `qwen2.5:0.5b` as the embedding model. The vector store is ChromaDB at `memory_store/openclay_memory`. Memory operations are performed on a background daemon thread to avoid blocking inference.

Three operations are exposed: `_memory_add(text)` — stores a new memory; `_memory_search(query, limit=5)` — returns the top-k most similar memories; `_memory_get_all()` — returns all stored memories for display.

If Mem0 initialization fails (missing `mem0ai` package or embedder unavailable), the system falls back gracefully and logs the failure, continuing to operate without persistent memory.

### 2.6 Research memory (three-network)

In addition to Mem0, a second ChromaDB client at `memory_store/hindsight/` maintains three separate collections: **factual** (discrete facts extracted from conversations), **experiential** (one-line session summaries), and **beliefs** (inferences about user goals). After each conversation turn, `_extract_research_insights()` runs on a background thread, asking the LLM to classify the exchange into JSON with `factual[]`, `experiential`, and `belief` fields, and distributes the results across the three collections.

### 2.7 Tamper-evident logging

Every conversation turn, task step, and system event is written to a daily JSONL log at `logs/YYYY-MM-DD.jsonl`. Each entry contains `timestamp`, `role`, `content`, `model`, and `hash`. The hash is `SHA256(previous_hash + JSON_of_this_entry_sorted_keys)`, forming a hash chain anchored to the string `"genesis"` at the start of each day.

`_log_verify()` replays the chain and returns `{intact: bool, broken_at: int}`. If any entry has been modified or deleted after writing, the hash mismatch is detected at the first altered entry. The chain is resumed on server restart by reading the last stored hash from today's log.

---

## 3. Task System

### 3.1 LLM-driven task loop

For non-demo tasks, the planning prompt instructs the model to output a single JSON object per step. The parser (`_parse_action()`) handles multiple output formats the 3B model produces in practice:

- **Format A** — `{"action": "bash", "input": "ls -la"}` (canonical)
- **Format A2** — `{"action": "bash|ls -la"}` (action and input merged with pipe, a 3B malformation)
- **Format B** — `{"bash": "ls -la"}` (action as key, input as value)
- **Format C** — `{"command": "ls -la"}` or `{"code": "..."}` (alternate keys)
- **Fallback** — plain text: if any known action keyword appears in the text, that action is inferred; otherwise `done` is assumed

Python code is never run via `python3 -c` — it is always written to a temporary `.py` file and executed as `python3 tmpfile.py`. This avoids shell escaping failures with f-strings and multi-line code. The temp file is deleted in a `finally` block.

### 3.2 Demo task: analyze_project_state

A scripted four-step sequence that bypasses the LLM planning loop entirely.

| Step | Description | Implementation |
|------|-------------|----------------|
| 1 | Scan all files in `sandbox/` | `SANDBOX_DIR.iterdir()` — collects name, size, mtime for each file |
| 2 | Summarize readable files | Reads up to 5 `.txt`/`.md` files (≤1,500 chars each); calls Ollama once per file asking for exactly 2 sentences |
| 3 | Compute stats | Total file count, total bytes, most-recently-modified filename — no LLM |
| 4 | Write structured report | Builds a Markdown report with a file table, summaries, and stats table; writes to `sandbox/output/project_state_report.md` |

Observed metrics (from `task_metrics.jsonl`): 4 steps, 0 retries, 100% success.

### 3.3 Demo task: biotech_document_review

A scripted five-step sequence.

| Step | Description | Implementation |
|------|-------------|----------------|
| 1 | Find document | Iterates `sandbox/` for `.txt`, `.md`, `.pdf` files; excludes files whose stem matches `{"sizes", "inventory"}` or whose name contains `{"review", "sizes", "inventory", "metrics", "report"}`; prefers files with `protocol/document/study/research/brief/paper` in the name; creates a sample protocol if none found |
| 2 | Read document | Reads up to 3,000 chars |
| 3 | Extract sections | Calls Ollama with a structured prompt asking for `OBJECTIVES`, `METHODS`, `RESULTS`, `COMPLIANCE_FLAGS` in exact labeled format |
| 4 | Gap analysis | Calls Ollama asking which of 13 required pharmaceutical document sections are missing |
| 5 | Write review | Builds a Markdown review with extracted sections, detected regulatory keywords (FDA, GMP, ICH, GCP, CFR, EU MDR, EMA), and gap list; writes to `sandbox/output/document_review_<name>.md` |

Observed metrics: 5 steps, 0 retries, 100% success.

### 3.4 Demo task: grant_intelligence_brief

A scripted four-step sequence.

| Step | Description | Implementation |
|------|-------------|----------------|
| 1 | Load COANA profile | Reads `coana_profile.md` if it exists; uses a built-in profile string otherwise |
| 2 | Score alignment | Calls Ollama with the grant description and profile, asking for `SCORE: N`, `REASONING`, `KEY_MATCHES`, `GAPS` in exact format |
| 3 | Draft abstract | Calls Ollama for a 2-paragraph application abstract (150–200 words) mirroring the grant's terminology |
| 4 | Write brief | Combines score, reasoning, key matches, gaps, and abstract into a Markdown brief; writes to `sandbox/output/grant_brief_<date>.md` |

The `--hunt-grants` CLI command (`openclay.py`) reads `grants_targets.json`, creates one task per entry via `POST /api/tasks/create`, polls `GET /api/tasks/<id>` until `status` is `"complete"` or `"failed"` (180s timeout), extracts the `SCORE: N` value from the output file via regex, and prints a ranked table sorted by score descending.

Observed metrics: 4 steps, 0 retries, 100% success.

---

## 4. Performance Metrics

Metrics are collected in `_task_metrics_log()` and appended as JSONL to `sandbox/logs/task_metrics.jsonl` after every task run. Each entry records:

| Field | Type | Meaning |
|-------|------|---------|
| `task_name` | string | `demo_type` value, or `"llm_task"` for non-demo runs |
| `task_id` | string | First 8 chars of UUID |
| `goal_preview` | string | First 60 chars of the goal |
| `start_time` | ISO 8601 | Timestamp when `_task_run()` was entered |
| `end_time` | ISO 8601 | Timestamp when `_task_metrics_log()` was called |
| `total_steps` | int | Count of entries in `task["steps"]` |
| `retry_count` | int | Value of `task["retry_count"]` at completion |
| `success` | bool | `True` iff final status is `"complete"` |
| `output_file` | string | Relative path to the output file, if any |

The `--metrics` CLI flag (`openclay.py`) reads this file, groups entries by `task_name`, and computes averages. Numbers observed from actual runs:

| Task | Avg Steps | Avg Retries | Success Rate |
|------|-----------|-------------|--------------|
| analyze_project_state | 4.0 | 0.0 | 100% |
| biotech_document_review | 5.0 | 0.0 | 100% |
| grant_intelligence_brief | 4.0 | 0.0 | 100% |

These numbers reflect scripted demo tasks only. Demo tasks bypass the LLM planning loop and have deterministic step counts. Metrics for LLM-driven tasks (tagged `"llm_task"`) will differ based on goal complexity, model response quality, and available sandbox content.

---

## 5. Security Model

### 5.1 Input sanitization (input_guard.py)

Every user input and every LLM output passes through `guard()` before use. The function applies 14 compiled regex patterns targeting:

- Direct override commands ("ignore all previous instructions", "disregard your system prompt")
- Identity reassignment ("you are now a…")
- Unrestricted mode requests ("enter mode with no restrictions", "jailbreak")
- System prompt extraction attempts ("reveal your system prompt", "what are your original instructions")
- Delimiter injection (`<|system|>`, `[SYSTEM]`, `[INST]`)
- Instruction smuggling ("new system instructions:", "admin override:")

Matched fragments are replaced with the literal string `[BLOCKED]` in the text passed to the LLM. All hits are logged to `security_log.md`.

### 5.2 Permission tiers (permissions.py)

Every action executed by `agent.py`'s `ClayRuntime` is checked against a static action-to-tier map before execution:

- **GREEN** — executes without logging. Includes: `scan_queue`, `read_file`, `list_files`, `write_queue`, `write_file_local`, `generate_local`, `wiki_init/query/ingest`, `browser_navigate`, `browser_screenshot`.
- **YELLOW** — executes but writes an entry to `security_log.md`. Includes: `run_local_script`, `install_stack`, `pull_model`, `web_search`, `generate_text` (when writing to a file), `credential_read`, `model_route_cloud`.
- **RED** — blocked by default; requires an explicit approval file in `pending_approvals/`. Includes: `post_tweet`, `post_instagram`, `direct_post`, `form_submission`, `run_command`, `send_email`, `purchase`, `delete_data`, `profile_action` (arbitrary plugin code), `external_api_call`.

Any action not in the map defaults to RED.

Approvals are written as JSON files to `pending_approvals/<action>-<sha256[:10]>.json` with `status: "pending"`. The `approve()` function sets `status: "approved"`; `deny()` deletes the file. The approval ID is deterministic (`SHA256(action + ":" + detail)[:10]`) so the same action with the same detail reuses an existing approval.

### 5.3 Outbound domain allowlist

`permissions.check_domain(url)` extracts the hostname from the URL and compares it against `allowed_domains` in `config.json`. Subdomain matching is supported (e.g., `api.twitter.com` matches `twitter.com`). Blocked attempts are logged to `security_log.md`. All cloud API calls in `model_router.py` check the domain before making the request.

### 5.4 Path isolation in task execution

The `write` action in `_task_execute_action()` constructs the output path as `SANDBOX_DIR / filename` — the sandbox directory is the root. There is no way to supply an absolute path or a `../` escape through this interface. The `read` action resolves paths against `BASE_DIR` and calls `candidate.relative_to(BASE_DIR)` — a `ValueError` is raised and returned as an error if the resolved path is outside the project.

---

## 6. Local-First Design

### 6.1 Ollama integration

OpenClay communicates with Ollama exclusively over `http://localhost:11434`. If Ollama is not running, `clay_server.py` starts it via `subprocess.Popen(["ollama", "serve"])` and polls the `/api/tags` endpoint for up to 15 seconds before continuing. The model preference list (`PREFERRED_MODELS`) is ordered by size, with the 3B quantized model (`qwen2.5:3b-instruct-q4_K_M`) first, followed by fallbacks (`qwen2.5:3b`, `llama3.2:3b`, `phi3:mini`, `gemma4:latest`). Model detection runs once per server session and is cached in `_model`.

All inference calls use Ollama's `/api/generate` endpoint with `stream: false` for task steps and `stream: true` for the chat interface. Streaming is implemented with chunked HTTP reads, parsing each `data.done` sentinel.

### 6.2 No required cloud dependency

Cloud escalation is strictly conditional on the presence of `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in `.env`. If neither key is present, `model_router.route()` downgrades CLOUD-classified tasks to LOCAL\_SMART and logs the reason. A user who installs only Ollama and the 3B model gets full functionality — the cloud path is never invoked.

The Mem0 embedding model (`qwen2.5:0.5b`) is also served by Ollama. If it is not available, `_init_mem0()` fails silently and the system runs without vector memory. ChromaDB stores are on-disk at `memory_store/`.

### 6.3 Offline capability

Because all inference is local and all data is on-disk, OpenClay can operate with no network access once the model is pulled. The only network-dependent operations are: cloud escalation (disabled without keys), outbound HTTP calls gated by the domain allowlist, and the initial `ollama pull` during setup. The `--hunt-grants` CLI requires the server to be running but makes no external requests itself — it only talks to `localhost:3000`.

### 6.4 Why local-first matters in this context

OpenClay was built in Puerto Rico, an environment where infrastructure disruptions (power, internet) are not edge cases. The soul document encodes this constraint explicitly: "You exist to make people more capable, more informed, and more resilient — regardless of what is happening outside." This is not an aesthetic choice. A cloud-dependent research assistant is unavailable during a power outage. A local one is not. The design prioritizes operational continuity over capability ceiling.

For biomedical and clinical use cases, local-first also provides a direct answer to data governance requirements: patient data, clinical protocols, and grant materials never transit a network, are never logged to a third party, and remain subject only to the local file system's access controls.

---

## 7. Current Limitations

### 7.1 Model speed

The 3B quantized model (`qwen2.5:3b-instruct-q4_K_M`) runs on CPU without GPU acceleration. Inference latency for a single planning step is typically 10–40 seconds depending on hardware. Multi-step tasks that require 4–8 LLM calls take 2–5 minutes. The model's context window (4,096 tokens at the configured `num_predict` of 512) limits the depth of reasoning available per step. Complex or long-horizon tasks may require the user to decompose goals manually before submission.

### 7.2 Memory latency

Mem0 search calls go through the embedding model (`qwen2.5:0.5b` via Ollama) and ChromaDB query. The embedding model must be separately pulled. If it is not available, memory search silently returns empty results. When it is available, search latency adds 2–8 seconds per query on CPU hardware. Memory add operations run on a daemon thread and do not block inference.

### 7.3 LLM planning reliability

The 3B model does not consistently produce canonical JSON. The `_parse_action()` parser handles five documented malformation patterns, but novel malformations revert to the text-keyword fallback, which maps to `done` if no action keyword is found. This causes tasks to terminate prematurely without completing their goal. The retry limit (3) mitigates but does not eliminate this — a planning failure increments the retry counter regardless of whether any work was done.

### 7.4 Task goal scope

The goal-satisfaction heuristics (`_is_goal_satisfied()`) use keyword matching and step-count thresholds. Goals that are ambiguous, that contain action words unrelated to concrete steps (e.g., "understand", "explore"), or that require more than 8 successful steps can either terminate too early or consume the full 20-step budget. Users should state goals as concrete, verifiable outcomes.

### 7.5 UI constraints

The p5.js interface is a single-page canvas application. It has no text selection in the response display (the canvas draws text character-by-character). File uploads are handled via a separate form element and route (`/api/upload`), not drag-and-drop on the canvas. The voice input uses Web Speech API and requires Chrome or Safari; Firefox is not supported. The interface has no keyboard navigation.

### 7.6 Concurrent task limit

Tasks run in daemon threads with no thread pool or queue depth limit. The `_active_tasks` dict holds all tasks in memory. A large number of concurrent long-running tasks will consume proportional CPU and RAM. There is no backpressure mechanism; the server will accept task creation requests regardless of current load.

---

## 8. Deployment Context — Puerto Rico

Puerto Rico's power grid is not a reliable substrate for cloud-dependent software. Hurricane María (September 2017) caused the longest blackout in United States history: approximately 11 months for the last customers restored, with the bulk of the island without power for 4–6 months. The grid was already in structural decline before María — PREPA (Puerto Rico Electric Power Authority) had been operating under a federal oversight board since 2017 due to insolvency — and it has not stabilized since. In 2022, a series of generation failures and transmission line collapses caused rolling blackouts affecting hundreds of thousands of customers for weeks at a time. As of 2026, PREPA's installed generation capacity remains below pre-María levels and the private operator that assumed management under a federal concession has not resolved the underlying infrastructure deficit. For a research institution or clinical facility on the island, internet connectivity is not a guarantee; it is a variable that drops when the grid drops, when fiber lines flood, or when the local telco's backup power is exhausted.

This context makes local-first a functional constraint, not a design preference. A system that requires `https://api.openai.com` to return a response cannot assist a researcher during a grid event. OpenClay makes no network calls during inference: the model runs on the local CPU via Ollama, conversation history is in-process memory, task steps execute via local subprocess, and output files land on the local disk. The only network dependency at runtime is `http://localhost:11434` — a loopback address. A laptop on battery power with Ollama and the 3B model already pulled can run a complete task session with no external connectivity. This is not a theoretical property; it follows directly from the architecture described in Sections 2 and 6.

The institutions on the island that would benefit from this property immediately are identifiable. The University of Puerto Rico system operates research laboratories across eleven campuses — Río Piedras, Mayagüez, Medical Sciences — each with ongoing grant-funded research that generates documents requiring analysis, reporting, and literature work. Puerto Rico hosts more than 60 pharmaceutical and medical device manufacturers, representing the largest concentration of FDA-regulated biotech production per square mile in the United States. These facilities operate under GMP and ICH compliance requirements; they generate internal documents (batch records, protocols, deviation reports) that cannot be uploaded to external services under their data governance policies. Hospital systems — including Hospital del Maestro, Centro Médico, and the VA Caribbean Healthcare System — face the same constraint: patient-adjacent documents cannot transit a public API. For each of these institutions, a locally-running document review tool that operates without network egress addresses a real access control requirement, not just a preference.

The same infrastructure profile that describes Puerto Rico describes a larger class of environments. FEMA-designated disaster recovery zones in the continental United States — coastal Louisiana, Appalachian rural counties, parts of the Florida Gulf Coast — experience extended grid disruptions after major weather events. Rural and remote clinics under IHS (Indian Health Service) and in the Global South operate with intermittent or metered connectivity as a normal condition, not an exception. Research institutions in sub-Saharan Africa, Southeast Asia, and island-nation Pacific contexts have published on the operational costs of cloud-dependent research tools during connectivity gaps. OpenClay does not need modification to operate in any of these contexts — the local-first constraint is already the default. The Puerto Rico deployment is, in this sense, a proof-of-concept for the broader case: that a functional AI research assistant can be built to operate at the edge, under infrastructure constraints, without degrading to a no-op when the network goes away.

---

*OpenClay v1.3.2 · COANA Labs · Todo es local. Nada sale de aquí.*
