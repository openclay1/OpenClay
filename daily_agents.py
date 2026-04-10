"""daily_agents.py — 5 industry-specific daily use agents for OpenClay.

Each agent takes plain text input (from dragged files or typed),
produces structured markdown output, and saves to ~/Desktop/OpenClay Output/.
All processing is local. No data leaves the machine.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = Path.home() / "Desktop" / "OpenClay Output"
BRAIN_PATH = BASE_DIR / "BRAIN.md"

def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M")
def _today(): return datetime.now().strftime("%Y-%m-%d")
def _read(p): return p.read_text(encoding="utf-8") if p.exists() else ""
def _save(name, content):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUTPUT_DIR / f"{name}_{_today()}.md"
    p.write_text(content, encoding="utf-8")
    return str(p)
def _lines(text): return [ln.strip() for ln in text.splitlines() if ln.strip()]
def _bullets(items): return "\n".join(f"- {i}" for i in items) if items else "- None identified"


# ── 1. CLINICAL NOTES AGENT ─────────────────────────────────────────

def clinical_notes_agent(text: str, lang: str = "en") -> dict:
    """Parse discharge/SOAP notes into structured handoff summary."""
    lines = _lines(text)
    # Extract action items (follow-up, meds, referrals)
    action_kw = r"\b(?:follow.up|refer|prescrib|schedul|order|monitor|return|recheck|medication|dosage|mg)\b"
    actions = [ln for ln in lines if re.search(action_kw, ln, re.I)]
    # Flag missing info
    flags = []
    if not any(re.search(r"\b(?:allerg|reaction)\b", ln, re.I) for ln in lines):
        flags.append("No allergy information documented")
    if not any(re.search(r"\b(?:medication|rx|prescri|dosage|mg)\b", ln, re.I) for ln in lines):
        flags.append("No medication list found")
    if not any(re.search(r"\b(?:diagnos|dx|assessment|impression)\b", ln, re.I) for ln in lines):
        flags.append("No diagnosis/assessment section found")
    hdr = "Resumen Clinico" if lang == "es" else "Clinical Summary"
    content = (f"# {hdr}\n_Generated: {_now()}_\n\n"
               f"## Patient Summary\n{text[:800]}\n\n"
               f"## Action Items\n{_bullets(actions[:10])}\n\n"
               f"## Flags\n{_bullets(flags)}\n")
    path = _save("CLINICAL_SUMMARY", content)
    return {"output": content, "path": path, "actions": actions, "flags": flags}


# ── 2. LAB DEVIATION AGENT ──────────────────────────────────────────

def lab_deviation_agent(text: str, lang: str = "en") -> dict:
    """Analyze batch records/QC logs for deviations."""
    lines = _lines(text)
    deviations = []
    for ln in lines:
        sev = "high" if re.search(r"\b(?:critical|fail|oos|out.of.spec|reject)\b", ln, re.I) \
            else "medium" if re.search(r"\b(?:warn|deviat|alert|limit|excee)\b", ln, re.I) \
            else "low" if re.search(r"\b(?:note|minor|info|observation)\b", ln, re.I) else None
        if sev:
            deviations.append({"line": ln[:120], "severity": sev})
    # Compare to BRAIN.md for past patterns
    brain = _read(BRAIN_PATH).lower()
    past_notes = []
    for d in deviations:
        words = [w for w in d["line"].lower().split() if len(w) > 4]
        if any(w in brain for w in words):
            past_notes.append(f"Pattern match in BRAIN.md for: {d['line'][:60]}")
    hdr = "Reporte de Laboratorio" if lang == "es" else "Lab Deviation Report"
    dev_text = "\n".join(f"- [{d['severity'].upper()}] {d['line']}" for d in deviations) or "- No deviations detected"
    content = (f"# {hdr}\n_Generated: {_now()}_\n\n"
               f"## Deviations Found\n{dev_text}\n\n"
               f"## Past Pattern Matches\n{_bullets(past_notes)}\n\n"
               f"## Suggested Corrective Actions\n"
               f"- Review all HIGH severity items immediately\n"
               f"- Document root cause for each deviation\n"
               f"- Update SOP if recurring pattern detected\n")
    path = _save("LAB_REPORT", content)
    return {"output": content, "path": path, "deviations": deviations}


# ── 3. VET SOAP AGENT ───────────────────────────────────────────────

def vet_soap_agent(text: str, lang: str = "en") -> dict:
    """Structure vet notes into SOAP format + follow-up reminders."""
    lines = _lines(text)
    soap = {"S": [], "O": [], "A": [], "P": []}
    current = "S"
    for ln in lines:
        low = ln.lower()
        if re.match(r"^(?:subjective|history|complaint|s:)", low): current = "S"; continue
        elif re.match(r"^(?:objective|exam|vitals|findings|o:)", low): current = "O"; continue
        elif re.match(r"^(?:assessment|diagnosis|impression|a:)", low): current = "A"; continue
        elif re.match(r"^(?:plan|treatment|rx|follow|p:)", low): current = "P"; continue
        soap[current].append(ln)
    # Drug interaction check
    drug_pat = r"\b\w*(?:cillin|mycin|azole|olol|pam|ine|ide|ase|mab|nib)\b"
    drugs = list(set(re.findall(drug_pat, text, re.I)))
    drug_flag = f"Medications found: {', '.join(drugs[:5])}. Verify interactions." if drugs else ""
    # Follow-up
    followups = [ln for ln in lines if re.search(r"\b(?:recheck|follow.up|return|days?|weeks?)\b", ln, re.I)]
    hdr = "Resumen Veterinario" if lang == "es" else "Vet Visit Summary"
    content = (f"# {hdr}\n_Generated: {_now()}_\n\n"
               f"## Subjective\n{chr(10).join(soap['S']) or 'Not documented'}\n\n"
               f"## Objective\n{chr(10).join(soap['O']) or 'Not documented'}\n\n"
               f"## Assessment\n{chr(10).join(soap['A']) or 'Not documented'}\n\n"
               f"## Plan\n{chr(10).join(soap['P']) or 'Not documented'}\n\n"
               f"## Follow-Up Reminders\n{_bullets(followups[:5])}\n\n"
               + (f"## Drug Alert\n{drug_flag}\n" if drug_flag else ""))
    path = _save("VET_SUMMARY", content)
    return {"output": content, "path": path, "drugs": drugs}


# ── 4. RESEARCH GRANT AGENT ─────────────────────────────────────────

def research_grant_agent(text: str, lang: str = "en") -> dict:
    """Convert research summary into grant-ready one-pager."""
    brain = _read(BRAIN_PATH)
    pr_context = "Puerto Rico" if "puerto" in brain.lower() or "creator" in brain.lower() else ""
    # Extract key phrases for budget categories
    budget_kw = {"personnel": r"\b(?:staff|hire|salary|PI|co-PI|postdoc|student)\b",
                 "equipment": r"\b(?:equipment|instrument|device|hardware|server)\b",
                 "supplies": r"\b(?:reagent|consumable|kit|material|suppli)\b",
                 "travel": r"\b(?:travel|conference|present|meeting)\b",
                 "other": r"\b(?:publication|license|software|subscription)\b"}
    categories = [k for k, v in budget_kw.items() if re.search(v, text, re.I)]
    if not categories:
        categories = ["personnel", "supplies", "other"]
    hdr = "Borrador de Subvencion" if lang == "es" else "Grant Draft"
    impact = (f"\n## Local Impact — Puerto Rico\nThis project directly benefits "
              f"Puerto Rico's research community by addressing gaps in local data "
              f"representation, building local research capacity, and ensuring "
              f"findings reflect the health needs of the island's population.\n"
              if pr_context else "")
    content = (f"# {hdr}\n_Generated: {_now()}_\n\n"
               f"## Project Summary\n{text[:1000]}\n"
               f"{impact}\n"
               f"## Suggested Budget Categories\n{_bullets(categories)}\n\n"
               f"## Next Steps\n- Finalize specific aims\n- Identify co-investigators\n"
               f"- Draft timeline and milestones\n")
    path = _save("GRANT_DRAFT", content)
    return {"output": content, "path": path, "budget": categories}


# ── 5. ADMIN RELIEF AGENT ───────────────────────────────────────────

def admin_relief_agent(text: str, lang: str = "en") -> dict:
    """Summarize any document into 5 bullets + action items + reply draft."""
    lines = _lines(text)
    # Build 5-bullet summary from key sentences
    scored = []
    for ln in lines:
        score = 0
        if re.search(r"\b(?:important|urgent|deadline|action|required|please|must|asap)\b", ln, re.I): score += 3
        if re.search(r"\b(?:by|before|due|date|tomorrow|monday|friday)\b", ln, re.I): score += 2
        if len(ln.split()) > 5: score += 1
        scored.append((score, ln))
    scored.sort(key=lambda x: x[0], reverse=True)
    summary = [s[1][:120] for s in scored[:5]]
    # Action items with deadlines
    action_lines = [ln for ln in lines if re.search(
        r"\b(?:action|todo|task|follow.up|please|need to|required|must|should|deadline|by \w+ \d)\b", ln, re.I)]
    # Reply draft (if looks like an email)
    is_email = any(re.search(r"\b(?:dear|hi |hello|from:|to:|subject:|regards|sincerely)\b", ln, re.I) for ln in lines[:5])
    reply = ""
    if is_email:
        reply = (f"\n## Reply Draft\nThank you for your message. "
                 f"I have reviewed the items below and will follow up on the action items "
                 f"by the requested deadlines.\n")
    hdr = "Resumen Administrativo" if lang == "es" else "Admin Summary"
    content = (f"# {hdr}\n_Generated: {_now()}_\n\n"
               f"## 5-Point Summary\n{_bullets(summary)}\n\n"
               f"## Action Items\n{_bullets(action_lines[:8])}\n"
               f"{reply}\n")
    path = _save("SUMMARY", content)
    return {"output": content, "path": path, "is_email": is_email}


# ── Router ───────────────────────────────────────────────────────────

AGENTS = {
    "clinical": clinical_notes_agent,
    "lab": lab_deviation_agent,
    "vet": vet_soap_agent,
    "grant": research_grant_agent,
    "admin": admin_relief_agent,
}


def route_by_content(text: str, lang: str = "en") -> dict:
    """Auto-detect which agent to use based on content."""
    low = text.lower()
    if re.search(r"\b(?:patient|discharge|soap|diagnosis|clinical|vitals|bp|hr)\b", low):
        if re.search(r"\b(?:canine|feline|kg body|veterinar|spay|neuter|rabies)\b", low):
            return vet_soap_agent(text, lang)
        return clinical_notes_agent(text, lang)
    if re.search(r"\b(?:batch|deviation|qc|oos|specification|lims|assay)\b", low):
        return lab_deviation_agent(text, lang)
    if re.search(r"\b(?:grant|funding|proposal|specific aims|NIH|NSF)\b", low):
        return research_grant_agent(text, lang)
    return admin_relief_agent(text, lang)


# ── Self test ────────────────────────────────────────────────────────

def self_test() -> bool:
    """Verify all 5 daily agents produce non-empty output."""
    clinical_txt = ("Patient: John Doe. Diagnosis: Type 2 Diabetes. "
                    "Medication: Metformin 500mg twice daily. "
                    "Follow-up: Return in 2 weeks for HbA1c recheck. "
                    "Allergies: Penicillin.")
    r = clinical_notes_agent(clinical_txt)
    assert r["output"] and r["path"], "clinical agent empty"
    assert any("return" in a.lower() or "recheck" in a.lower() for a in r["actions"]), "clinical actions"

    lab_txt = ("Batch 2024-0415. QC Result: pH 7.2 — within spec. "
               "Endotoxin: 0.8 EU/mL — CRITICAL: out of spec (limit 0.5). "
               "Visual: minor particulate noted.")
    r = lab_deviation_agent(lab_txt)
    assert r["output"] and r["deviations"], "lab agent empty"
    assert any(d["severity"] == "high" for d in r["deviations"]), "lab no high severity"

    vet_txt = ("S: Owner reports dog not eating for 2 days, lethargy. "
               "O: Temp 103.5F, HR 120, dehydrated. "
               "A: Suspected gastroenteritis. "
               "P: Metronidazole 250mg BID x 7 days. Recheck in 5 days.")
    r = vet_soap_agent(vet_txt)
    assert r["output"], "vet agent empty"
    assert r["drugs"], "vet no drugs detected"

    grant_txt = ("This project aims to study GLP-1 receptor agonist efficacy "
                 "in Hispanic populations. We will hire 2 research staff and "
                 "purchase lab equipment for biomarker analysis.")
    r = research_grant_agent(grant_txt)
    assert r["output"] and r["budget"], "grant agent empty"

    admin_txt = ("Subject: Q2 Budget Review\nDear team,\n"
                 "Please review the attached budget by Friday. "
                 "Action required: submit updated projections by March 15. "
                 "Important: travel expenses must be pre-approved.")
    r = admin_relief_agent(admin_txt)
    assert r["output"] and r["is_email"], "admin agent empty or not email"
    return True
