# COANA Labs — OpenClay Project Profile

## Organization

**COANA Labs**
- Founded in Puerto Rico
- URL: coana.lab
- Team: Francis Davila Rios (founder), COANA Labs

## Mission

Resilient, private, local-first AI for communities with unreliable infrastructure. COANA Labs builds tools that work when the cloud doesn't — designed after Hurricane Maria-era infrastructure failures demonstrated the need for AI systems that function independently of internet connectivity, cloud providers, and subscription services.

## Project: OpenClay

OpenClay is a local AI research assistant that runs entirely on the user's hardware. No data egress. No cloud dependency. No subscription required.

### Key Technical Achievements

- **Zero-data-egress architecture**: All AI processing stays on the local machine. No data ever leaves the user's infrastructure.
- **Local LLM execution via Ollama**: Supports qwen2.5, llama3.2, phi3, gemma4, and other models running locally.
- **Autonomous task engine (v1.3)**: Multi-step agentic execution with planning, verification, retry logic, and structured output.
- **Biomedical compliance modules**: FDA 21 CFR 312, EU GMP Annex 1, ICH E6 GCP, EMA guidelines — built-in document review and gap analysis.
- **Mem0 persistent memory**: Long-term memory across sessions using local vector storage (Chroma).
- **Tamper-proof log chain**: Cryptographic hash chain for audit-ready session logs.
- **Multi-agent system**: 7 specialized agents (Clay General, Biotech Research, Grant Writer, Document Analyst, Data Science, Clinical Workflow, Regulatory Affairs).
- **Mesh network support**: Meshtastic integration for operation in environments with no internet connectivity.

### Use Cases

- Biotech and pharmaceutical research document review
- Clinical workflow support and protocol analysis
- Grant writing — alignment scoring and abstract drafting
- Regulatory document review (FDA, GMP, ICH, EMA)
- General research assistance and document summarization

### Impact

- Demonstrated consistent operation in infrastructure-constrained environments
- 60% efficiency improvement in research task completion (documented internal benchmarks)
- Designed for communities that cannot rely on continuous internet connectivity
- Operates offline: no API calls to external services, no usage tracking

## Why Unique

OpenClay was built specifically to address the reality that many research institutions, especially in regions like Puerto Rico and other areas with unreliable infrastructure, cannot depend on cloud-based AI tools. After Hurricane Maria demonstrated how fragile cloud-dependent systems are, COANA Labs designed OpenClay so that:

1. All AI runs locally — no subscription, no cloud, no data leaving the machine
2. The system works during power outages (on battery/generator) and network outages
3. Sensitive research data (clinical, pharmaceutical, financial) never touches external servers
4. The tool is affordable and accessible to under-resourced institutions

## Technical Stack

- Python HTTP server (no framework dependencies)
- p5.js canvas interface
- Ollama for local LLM inference
- Mem0 + Chroma for persistent vector memory
- Meshtastic for mesh networking
- All data stored locally in structured files (JSON, Markdown)
