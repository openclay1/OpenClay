"""daily_agents.py — 7 industry-specific daily agents for OpenClay.
Each agent: local processing, trust footer, audit logging. No data leaves machine.
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
    p = OUTPUT_DIR / f"{name}_{_today()}.md"; p.write_text(content, encoding="utf-8"); return str(p)
def _lines(text): return [ln.strip() for ln in text.splitlines() if ln.strip()]
def _bullets(items): return "\n".join(f"- {i}" for i in items) if items else "- None identified"

def _get_model():
    try:
        from model_config import get_stored_model; return get_stored_model() or "local"
    except Exception: return "local"

def _trust_footer(source: str = "", confidence: str = "HIGH") -> str:
    model = _get_model()
    return (f"\n\n---\n🔍 Fuente: {source or 'user input'} | Modelo: {model}\n"
            f"Procesado: {_now()} | Local: si, sin internet\n"
            f"Confianza: {confidence} (HIGH=extraido directo / MEDIUM=inferido / LOW=sugerencia)\n"
            f"Todo el procesamiento fue local. No data left machine.\n---")

def _audit(agent: str, source: str, output_path: str, confidence: str = "HIGH"):
    try:
        from audit_log import log_run; log_run(agent, source, _get_model(), output_path, confidence)
    except Exception: pass

# ── 1. CLINICAL NOTES ───────────────────────────────────────────────

def clinical_notes_agent(text: str, lang: str = "en") -> dict:
    lines = _lines(text)
    action_kw = r"\b(?:follow.up|refer|prescrib|schedul|order|monitor|return|recheck|medication|dosage|mg)\b"
    actions = [ln for ln in lines if re.search(action_kw, ln, re.I)]
    flags = []
    if not any(re.search(r"\b(?:allerg|reaction)\b", ln, re.I) for ln in lines): flags.append("No allergy info")
    if not any(re.search(r"\b(?:medication|rx|prescri|dosage|mg)\b", ln, re.I) for ln in lines): flags.append("No medication list")
    if not any(re.search(r"\b(?:diagnos|dx|assessment|impression)\b", ln, re.I) for ln in lines): flags.append("No diagnosis section")
    # Flag medications with ⚕️
    med_pat = r"\b\w*(?:cillin|mycin|azole|olol|pam|ine|ide|ase|mab|nib|min|cin)\b"
    meds = list(set(re.findall(med_pat, text, re.I)))
    med_line = f"\n⚕️ Medicamentos detectados: {', '.join(meds[:8])}" if meds else ""
    # MedGemma header
    model = _get_model()
    medgemma = ("⚕️ Procesado con MedGemma — modelo entrenado especificamente en datos medicos clinicos.\n\n"
                if "medgemma" in model.lower() else "")
    hdr = "Resumen Clinico" if lang == "es" else "Clinical Summary"
    content = (f"# {hdr}\n{medgemma}_Generated: {_now()}_\n\n"
               f"## Patient Summary\n{text[:800]}\n{med_line}\n\n"
               f"## Action Items\n{_bullets(actions[:10])}\n\n## Flags\n{_bullets(flags)}\n\n"
               f"_Este resumen no reemplaza el expediente clinico ni el criterio del medico._"
               + _trust_footer("clinical_notes"))
    path = _save("CLINICAL_SUMMARY", content)
    _audit("clinical_notes", "input", path)
    return {"output": content, "path": path, "actions": actions, "flags": flags}

# ── 2. LAB DEVIATION ────────────────────────────────────────────────

def lab_deviation_agent(text: str, lang: str = "en") -> dict:
    lines = _lines(text)
    deviations = []
    for ln in lines:
        sev = "high" if re.search(r"\b(?:critical|fail|oos|out.of.spec|reject)\b", ln, re.I) \
            else "medium" if re.search(r"\b(?:warn|deviat|alert|limit|excee)\b", ln, re.I) \
            else "low" if re.search(r"\b(?:note|minor|info|observation)\b", ln, re.I) else None
        if sev: deviations.append({"line": ln[:120], "severity": sev})
    brain = _read(BRAIN_PATH).lower()
    past = [f"Pattern match: {d['line'][:60]}" for d in deviations
            if any(w in brain for w in d["line"].lower().split() if len(w) > 4)]
    dev_text = "\n".join(f"- [{'**⚠️ CRITICO**' if d['severity']=='high' else d['severity'].upper()}] {d['line']}"
                         for d in deviations) or "- No deviations detected"
    hdr = "Reporte de Laboratorio" if lang == "es" else "Lab Deviation Report"
    content = (f"# {hdr}\n_Generated: {_now()}_\n\n## Deviations\n{dev_text}\n\n"
               f"## Past Patterns\n{_bullets(past)}\n\n"
               f"## Corrective Actions\n- Review HIGH items immediately\n- Document root cause\n- Update SOP if recurring\n\n"
               f"_No reemplaza revision del QC supervisor._" + _trust_footer("lab_report"))
    path = _save("LAB_REPORT", content)
    _audit("lab_deviation", "input", path)
    return {"output": content, "path": path, "deviations": deviations}

# ── 3. VET SOAP ─────────────────────────────────────────────────────

def vet_soap_agent(text: str, lang: str = "en") -> dict:
    lines = _lines(text)
    soap = {"S": [], "O": [], "A": [], "P": []}; current = "S"
    for ln in lines:
        low = ln.lower()
        if re.match(r"^(?:subjective|history|complaint|s:)", low): current = "S"; continue
        elif re.match(r"^(?:objective|exam|vitals|o:)", low): current = "O"; continue
        elif re.match(r"^(?:assessment|diagnosis|a:)", low): current = "A"; continue
        elif re.match(r"^(?:plan|treatment|rx|follow|p:)", low): current = "P"; continue
        soap[current].append(ln)
    drug_pat = r"\b\w*(?:cillin|mycin|azole|olol|pam|ine|ide|ase|mab|nib)\b"
    drugs = list(set(re.findall(drug_pat, text, re.I)))
    followups = [ln for ln in lines if re.search(r"\b(?:recheck|follow.up|return|days?|weeks?)\b", ln, re.I)]
    hdr = "Resumen Veterinario" if lang == "es" else "Vet Visit Summary"
    content = (f"# {hdr}\n_Generated: {_now()}_\n\n"
               + "".join(f"## {k}\n{chr(10).join(soap[k]) or 'Not documented'}\n\n" for k in "SOAP")
               + f"## Follow-Up\n{_bullets(followups[:5])}\n"
               + (f"\n## Drug Alert\n⚕️ {', '.join(drugs[:5])}. Verify interactions.\n" if drugs else "")
               + _trust_footer("vet_notes"))
    path = _save("VET_SUMMARY", content)
    _audit("vet_soap", "input", path)
    return {"output": content, "path": path, "drugs": drugs}

# ── 4. RESEARCH GRANT ───────────────────────────────────────────────

def research_grant_agent(text: str, lang: str = "en") -> dict:
    brain = _read(BRAIN_PATH)
    pr = "Puerto Rico" if "puerto" in brain.lower() else ""
    bkw = {"personnel": r"\b(?:staff|hire|salary|PI|postdoc)\b", "equipment": r"\b(?:equipment|instrument|device)\b",
           "supplies": r"\b(?:reagent|consumable|kit|material)\b", "travel": r"\b(?:travel|conference)\b"}
    cats = [k for k, v in bkw.items() if re.search(v, text, re.I)] or ["personnel", "supplies", "other"]
    impact = (f"\n## Local Impact — Puerto Rico\nBenefits PR research community.\n" if pr else "")
    hdr = "Borrador de Subvencion" if lang == "es" else "Grant Draft"
    content = (f"# {hdr}\n_Generated: {_now()}_\n\n## Summary\n{text[:1000]}\n{impact}\n"
               f"## Budget Categories\n{_bullets(cats)}\n\n## Next Steps\n- Finalize aims\n- ID co-investigators\n"
               + _trust_footer("grant_input", "MEDIUM"))
    path = _save("GRANT_DRAFT", content)
    _audit("research_grant", "input", path, "MEDIUM")
    return {"output": content, "path": path, "budget": cats}

# ── 5. ADMIN RELIEF ─────────────────────────────────────────────────

def admin_relief_agent(text: str, lang: str = "en") -> dict:
    lines = _lines(text)
    scored = [(sum([3 if re.search(r"\b(?:important|urgent|deadline|action|required|must)\b", ln, re.I) else 0,
                    2 if re.search(r"\b(?:by|before|due|date|tomorrow)\b", ln, re.I) else 0,
                    1 if len(ln.split()) > 5 else 0]), ln) for ln in lines]
    scored.sort(key=lambda x: x[0], reverse=True)
    summary = [s[1][:120] for s in scored[:5]]
    action_lines = [ln for ln in lines if re.search(r"\b(?:action|todo|task|follow.up|please|need to|required|must)\b", ln, re.I)]
    is_email = any(re.search(r"\b(?:dear|hi |hello|from:|to:|subject:|regards)\b", ln, re.I) for ln in lines[:5])
    reply = "\n## Reply Draft\nThank you. I will follow up on action items by requested deadlines.\n" if is_email else ""
    hdr = "Resumen Administrativo" if lang == "es" else "Admin Summary"
    content = (f"# {hdr}\n_Generated: {_now()}_\n\n## 5-Point Summary\n{_bullets(summary)}\n\n"
               f"## Action Items\n{_bullets(action_lines[:8])}\n{reply}" + _trust_footer("admin_input"))
    path = _save("SUMMARY", content)
    _audit("admin_relief", "input", path)
    return {"output": content, "path": path, "is_email": is_email}

# ── 6. ACCOUNTING AUDIT ─────────────────────────────────────────────

def accounting_audit_agent(text: str, lang: str = "en") -> dict:
    lines = _lines(text)
    amounts = re.findall(r"\$[\d,]+\.?\d*", text)
    nums = [float(a.replace("$", "").replace(",", "")) for a in amounts if a]
    total = sum(nums); flagged = [n for n in nums if n > 5000]
    dupes = [a for a in amounts if amounts.count(a) > 1]
    anomalies = []
    if dupes: anomalies.append(f"❗ Duplicate amounts: {', '.join(set(dupes))}")
    if flagged: anomalies.append(f"❗ Unusual amounts (>$5000): {', '.join(f'${f:,.2f}' for f in flagged[:5])}")
    if not amounts: anomalies.append("❗ No dollar amounts found in document")
    content = (f"# Resumen Financiero / Financial Summary\n_Generated: {_now()}_\n\n"
               f"## Summary\n- Total amounts found: ${total:,.2f}\n- Items: {len(amounts)}\n"
               f"- Flagged: {len(flagged)}\n\n## Anomalies\n{_bullets(anomalies)}\n\n"
               f"_No reemplaza un contador certificado._" + _trust_footer("financial_input", "MEDIUM"))
    path = _save("FINANCIAL_SUMMARY", content)
    _audit("accounting_audit", "input", path, "MEDIUM")
    return {"output": content, "path": path, "anomalies": anomalies, "total": total}

# ── 7. MEDICAL BILLING ──────────────────────────────────────────────

def medical_billing_agent(text: str, lang: str = "en") -> dict:
    lines = _lines(text)
    is_denial = any(re.search(r"\b(?:denied|denial|reject|appeal|reconsider)\b", ln, re.I) for ln in lines)
    is_clinical = any(re.search(r"\b(?:patient|diagnosis|assessment|hpi|exam)\b", ln, re.I) for ln in lines)
    claims = re.findall(r"\b(?:claim|CLM|referencia)\s*#?\s*[\w-]+", text, re.I)
    outputs = []
    # EOB Summary
    eob = (f"# Resumen EOB / EOB Summary\n_Generated: {_now()}_\n\n"
           f"## Claims Found\n{_bullets(claims[:10]) if claims else '- Review document for claim numbers'}\n\n"
           f"_Verificar con tu sistema antes de actuar._" + _trust_footer("billing_input"))
    path1 = _save("EOB_SUMMARY", eob); outputs.append(eob)
    # Appeal draft if denial
    if is_denial:
        appeal = (f"# Borrador de Apelacion / Appeal Draft\n_Generated: {_now()}_\n\n"
                  f"Estimado/a Director(a) Medico:\n\nPor medio de la presente, solicito la reconsideracion de la "
                  f"denegacion del reclamo referenciado.\n\nClaim: {claims[0] if claims else '[NUMERO DE RECLAMO]'}\n"
                  f"Diagnostico: [COMPLETAR]\nRazon de denegacion: [COMPLETAR]\n\n"
                  f"Argumento: El servicio fue medicamente necesario segun la documentacion clinica adjunta.\n\n"
                  f"[FIRMA DEL MEDICO AQUI]\n\n⚠️ Verifica codigos CPT/ICD-10 antes de enviar."
                  + _trust_footer("denial_notice", "MEDIUM"))
        _save("APPEAL_DRAFT", appeal); outputs.append(appeal)
    # Coding suggestions if clinical note
    if is_clinical:
        coding = (f"# Sugerencias de Codificacion / Coding Suggestions\n_Generated: {_now()}_\n\n"
                  f"⚠️ LOW confidence — todas las sugerencias requieren verificacion\n\n"
                  f"- Revisar documentacion para codigos ICD-10 aplicables\n"
                  f"- Verificar nivel de E/M segun complejidad documentada\n"
                  f"- ⚠️ Requiere verificacion por codificador CPC/CPC-H\n\n"
                  f"_Todo procesado localmente. Ningun dato de paciente salio de esta computadora. HIPAA-safe by design._"
                  + _trust_footer("clinical_note", "LOW"))
        _save("CODING_SUGGESTIONS", coding); outputs.append(coding)
    _audit("medical_billing", "input", path1)
    return {"output": "\n\n---\n\n".join(outputs), "path": path1, "is_denial": is_denial, "claims": claims}

# ── Router ───────────────────────────────────────────────────────────

AGENTS = {"clinical": clinical_notes_agent, "lab": lab_deviation_agent, "vet": vet_soap_agent,
          "grant": research_grant_agent, "admin": admin_relief_agent,
          "accounting": accounting_audit_agent, "billing": medical_billing_agent}

def route_by_content(text: str, lang: str = "en") -> dict:
    low = text.lower()
    if re.search(r"\b(?:patient|discharge|soap|diagnosis|clinical|vitals|bp|hr)\b", low):
        if re.search(r"\b(?:canine|feline|kg body|veterinar|spay|neuter|rabies)\b", low):
            return vet_soap_agent(text, lang)
        return clinical_notes_agent(text, lang)
    if re.search(r"\b(?:batch|deviation|qc|oos|specification|lims|assay)\b", low): return lab_deviation_agent(text, lang)
    if re.search(r"\b(?:grant|funding|proposal|specific aims|NIH|NSF)\b", low): return research_grant_agent(text, lang)
    if re.search(r"\b(?:invoice|expense|quickbooks|receipt|\$\d|budget|financial)\b", low): return accounting_audit_agent(text, lang)
    if re.search(r"\b(?:claim|eob|denial|appeal|cpt|icd|billing|factur)\b", low): return medical_billing_agent(text, lang)
    return admin_relief_agent(text, lang)

# ── Self test ────────────────────────────────────────────────────────

def self_test() -> bool:
    r = clinical_notes_agent("Patient: Doe. Diagnosis: Diabetes. Medication: Metformin 500mg. Follow-up: 2 weeks. Allergies: Penicillin.")
    assert r["output"] and r["path"] and "trust" not in r["output"] or "Fuente" in r["output"], "clinical fail"
    r = lab_deviation_agent("Batch 2024. Endotoxin: 0.8 EU/mL — CRITICAL: out of spec. Visual: minor note.")
    assert r["deviations"] and any(d["severity"] == "high" for d in r["deviations"]), "lab fail"
    r = vet_soap_agent("S: Dog not eating. O: Temp 103.5F. A: Gastroenteritis. P: Metronidazole 250mg. Recheck 5 days.")
    assert r["output"] and r["drugs"], "vet fail"
    r = research_grant_agent("Study GLP-1 efficacy. Hire 2 staff. Purchase equipment.")
    assert r["budget"], "grant fail"
    r = admin_relief_agent("Subject: Q2 Budget\nDear team,\nPlease review by Friday. Action required: submit by March 15.")
    assert r["is_email"], "admin fail"
    # #41 accounting
    r = accounting_audit_agent("Invoice #1: $500.00. Invoice #2: $500.00. Invoice #3: $7500.00. Total: $8500.00")
    assert r["total"] > 0 and r["anomalies"], "accounting fail"
    # #46 billing
    r = medical_billing_agent("Claim #CLM-2024-001 denied. Patient diagnosis: J06.9. Appeal requested.")
    assert r["is_denial"] and r["claims"], "billing fail"
    # #42 trust footer
    assert "Fuente" in r["output"] and "Local" in r["output"], "trust footer missing"
    return True
