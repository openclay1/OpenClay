"""workflow_simulator.py — Day-in-the-life simulations for 5 roles.
Outputs to ~/Desktop/OpenClay Output/. Generates RESISTANCE_GUIDE.md + EMPLOYEE_ONBOARDING_ES.md.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path.home() / "Desktop" / "OpenClay Output"
def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M")
def _save(name, content):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUTPUT_DIR / name; p.write_text(content, encoding="utf-8"); return str(p)

_ROLES = {
    "nurse": {
        "title": "Floor Nurse — Hospital (Centro Medico level)",
        "industry": "Hospital / Clinical",
        "schedule": [
            ("08:00", "08:15", "Shift handoff — read overnight notes", 10, "clinical_notes_agent summarizes overnight charts into 5 bullets with flags"),
            ("08:15", "09:00", "Medication reconciliation for 6 patients", 15, "Cross-checks med lists, flags interactions and missing allergies"),
            ("09:00", "09:30", "Chart documentation — morning rounds", 12, "Structures free-text notes into SOAP format automatically"),
            ("09:30", "10:30", "Direct patient care — vitals, assessments", 0, "CANNOT replace bedside care, clinical judgment, or patient interaction"),
            ("10:30", "11:00", "Update care plans in EHR", 10, "Drafts care plan updates from assessment notes"),
            ("11:00", "12:00", "Patient education + family questions", 0, "CANNOT replace empathy, cultural context, or trust-building"),
            ("12:00", "12:30", "Lunch", 0, ""),
            ("12:30", "13:00", "Incident report for fall on unit", 8, "Structures incident narrative, flags required fields"),
            ("13:00", "14:30", "Afternoon med pass + treatments", 0, "CANNOT administer medications or perform procedures"),
            ("14:30", "15:00", "Discharge paperwork for 2 patients", 15, "Generates discharge summary with med list, follow-ups, red flags"),
            ("15:00", "15:30", "Handoff report for evening shift", 10, "Compiles shift summary from all documented notes"),
            ("15:30", "16:00", "Chart completion + sign-off", 10, "Identifies incomplete documentation before shift ends"),
        ],
        "total_saved": 90,
        "freed_time": "An extra 90 minutes to spend at the bedside, mentor a new nurse, or leave on time for once.",
        "cannot": ["Replace clinical judgment or patient assessment", "Administer medications or perform procedures",
                    "Build the trust that comes from a nurse who remembers your name", "Override physician orders or make treatment decisions"],
        "value": "The nurse becomes the nurse who never misses a detail in handoff, whose patients always have complete discharge instructions, who mentors new staff because they have the time.",
    },
    "admin": {
        "title": "Admin Coordinator — Hospital / Pharma",
        "industry": "Hospital / Pharma",
        "schedule": [
            ("08:00", "08:30", "Process overnight emails (30+ messages)", 15, "admin_relief_agent summarizes each into bullets + action items"),
            ("08:30", "09:00", "Schedule coordination for 3 departments", 10, "Extracts scheduling conflicts and deadlines from threads"),
            ("09:00", "09:30", "Credentialing paperwork for new hire", 12, "Structures requirements checklist, flags missing documents"),
            ("09:30", "10:00", "Insurance pre-auth follow-up calls", 0, "CANNOT make phone calls or negotiate with insurers"),
            ("10:00", "10:30", "Meeting minutes from yesterday's staff mtg", 12, "Structures raw notes into minutes with action items"),
            ("10:30", "11:00", "Vendor invoice review", 8, "Flags discrepancies, summarizes line items"),
            ("11:00", "12:00", "Front desk coverage + patient check-in", 0, "CANNOT replace human presence at the front desk"),
            ("12:00", "12:30", "Lunch", 0, ""),
            ("12:30", "13:00", "Compliance training tracking", 10, "Cross-references completion records, flags overdue staff"),
            ("13:00", "14:00", "Budget report formatting", 15, "Formats raw data into presentation-ready summaries"),
            ("14:00", "15:00", "Interdepartmental communication", 8, "Drafts memos and updates from bullet points"),
            ("15:00", "15:30", "End-of-day report to supervisor", 10, "Compiles day's completed/pending items automatically"),
            ("15:30", "16:00", "Tomorrow's prep + pending items", 5, "Predicts tomorrow's priorities from patterns"),
        ],
        "total_saved": 105,
        "freed_time": "Nearly 2 hours back — enough to handle the crises that always come, train a temp, or actually take a full lunch.",
        "cannot": ["Make phone calls or attend meetings on your behalf", "Handle sensitive conversations with staff or patients",
                    "Replace the judgment calls that come from knowing your organization", "Access systems that require your credentials"],
        "value": "The coordinator becomes the person who never drops a ball, whose reports are always ready, who somehow handles three departments without burning out.",
    },
    "qc_tech": {
        "title": "QC Technician — Pharma Manufacturing",
        "industry": "Pharma / Biotech",
        "schedule": [
            ("08:00", "08:15", "Review overnight batch results", 8, "lab_deviation_agent flags OOS results and severity levels"),
            ("08:15", "09:00", "Morning instrument calibration", 0, "CANNOT calibrate instruments or run physical tests"),
            ("09:00", "10:00", "Environmental monitoring data entry", 15, "Structures EM data, flags excursions, drafts deviation narrative"),
            ("10:00", "10:30", "Deviation investigation write-up", 12, "Generates investigation template with root cause prompts from past patterns"),
            ("10:30", "11:30", "In-process testing — active batch", 0, "CANNOT perform assays or make pass/fail decisions"),
            ("11:30", "12:00", "CAPA documentation", 10, "Structures corrective actions from investigation notes"),
            ("12:00", "12:30", "Lunch", 0, ""),
            ("12:30", "13:30", "Stability sample pull + testing", 0, "CANNOT handle samples or operate analytical equipment"),
            ("13:30", "14:00", "SOP review — annual revision", 12, "Compares current vs. previous version, flags changed sections"),
            ("14:00", "14:30", "Training record updates", 8, "Tracks completion status, generates training matrix"),
            ("14:30", "15:30", "Certificate of Analysis prep", 15, "Compiles test results into CoA format with release criteria"),
            ("15:30", "16:00", "Logbook entries + equipment log", 8, "Structures entries from raw notes"),
        ],
        "total_saved": 88,
        "freed_time": "88 minutes freed — enough to actually investigate that recurring deviation instead of just documenting it.",
        "cannot": ["Perform any laboratory testing or sample handling", "Make batch release decisions",
                    "Sign off on regulated documents (21 CFR Part 11)", "Replace the trained eye that spots a contaminated plate"],
        "value": "The tech becomes the one whose investigations actually find root cause, whose CAPAs are effective, who has time to mentor the new hires on good documentation practices.",
    },
    "reg_affairs": {
        "title": "Regulatory Affairs Assistant — Pharma",
        "industry": "Pharma / Biotech",
        "schedule": [
            ("08:00", "08:30", "Review FDA guidance updates", 10, "Summarizes new guidances, flags relevant changes"),
            ("08:30", "09:30", "Compile submission package sections", 15, "Structures Module 3 content from raw data sources"),
            ("09:30", "10:00", "Cross-reference product labeling", 10, "Compares label claims against approved language"),
            ("10:00", "11:00", "Meeting with CMC team — prep materials", 12, "Generates meeting agenda and discussion points from prior minutes"),
            ("11:00", "11:30", "Regulatory correspondence drafts", 10, "Drafts response letters from bullet points"),
            ("11:30", "12:00", "Annual report data compilation", 12, "Pulls and formats data from multiple source docs"),
            ("12:00", "12:30", "Lunch", 0, ""),
            ("12:30", "13:30", "Literature review for safety update", 15, "biotech_review_agent indexes papers, runs gap analysis"),
            ("13:30", "14:00", "Variation tracking spreadsheet", 8, "Structures variation data, flags pending deadlines"),
            ("14:00", "15:00", "Review promotional materials for compliance", 0, "CANNOT make compliance determinations or approve claims"),
            ("15:00", "15:30", "Draft timeline for upcoming submission", 8, "Generates milestone timeline from regulatory requirements"),
            ("15:30", "16:00", "End-of-day status update to RA manager", 5, "Compiles day's progress into structured update"),
        ],
        "total_saved": 105,
        "freed_time": "Nearly 2 hours — enough to actually read the guidance instead of just filing it, and think strategically about the submission.",
        "cannot": ["Make regulatory strategy decisions", "Interpret FDA feedback or determine regulatory pathway",
                    "Sign regulatory submissions", "Replace the judgment that comes from years of agency interaction"],
        "value": "The assistant becomes the one who catches the labeling discrepancy before it reaches the FDA, whose submissions are organized and complete, who makes the RA director look good.",
    },
    "vet_tech": {
        "title": "Veterinary Technician — Small Animal Practice",
        "industry": "Veterinary",
        "schedule": [
            ("08:00", "08:15", "Review today's appointment schedule", 5, "Summarizes cases, flags recurring patients and pending labs"),
            ("08:15", "09:00", "Morning treatments + hospitalized patients", 0, "CANNOT administer treatments or handle animals"),
            ("09:00", "09:30", "Client call-backs — lab results", 0, "CANNOT make phone calls or discuss results with clients"),
            ("09:30", "10:30", "Assist in surgery — dental cleaning", 0, "CANNOT assist in procedures or monitor anesthesia"),
            ("10:30", "11:00", "Post-op notes + discharge instructions", 12, "vet_soap_agent structures notes, generates take-home instructions"),
            ("11:00", "11:30", "Inventory check + order list", 8, "Compares stock against par levels, generates order draft"),
            ("11:30", "12:00", "Rabies certificate + county paperwork", 8, "Fills certificate template from patient record data"),
            ("12:00", "12:30", "Lunch", 0, ""),
            ("12:30", "13:30", "Afternoon appointments — assist DVM", 0, "CANNOT restrain patients or perform diagnostics"),
            ("13:30", "14:00", "Prescription refill processing", 8, "Checks for drug interactions, structures refill records"),
            ("14:00", "14:30", "Client education handouts", 8, "Generates condition-specific handouts from templates"),
            ("14:30", "15:30", "End-of-day records completion", 12, "Structures visit notes into SOAP format with reminders"),
            ("15:30", "16:00", "Treatment board update + tomorrow's prep", 5, "Compiles hospitalized patient status board"),
        ],
        "total_saved": 66,
        "freed_time": "Over an hour freed — enough to actually comfort the anxious pet owner, prep surgery more carefully, or leave before 7pm.",
        "cannot": ["Handle, restrain, or treat animals", "Administer medications or monitor anesthesia",
                    "Replace the calm voice that reassures a scared pet owner", "Make diagnostic or treatment recommendations"],
        "value": "The tech becomes the one whose records are always complete, whose clients get clear take-home instructions, who catches the drug interaction before it happens.",
    },
}


def simulate_role(role_key: str) -> str:
    """Generate a full 8-hour workday simulation for one role."""
    role = _ROLES[role_key]
    lines = [f"# {role['title']}", f"**Industry:** {role['industry']}",
             f"**Simulated by OpenClay — {_now()}**\n",
             "## Full 8-Hour Workday\n",
             "| Time | Task | Min Saved | How OpenClay Helps |",
             "|------|------|-----------|-------------------|"]
    for start, end, task, saved, how in role["schedule"]:
        saved_str = f"{saved} min" if saved > 0 else "—"
        how_str = how if how else "—"
        lines.append(f"| {start}–{end} | {task} | {saved_str} | {how_str} |")
    lines.append(f"\n**Total time saved: {role['total_saved']} minutes per day**")
    lines.append(f"\n**What they do with freed time:** {role['freed_time']}\n")
    lines.append("## What OpenClay CANNOT Do for This Role\n")
    for c in role["cannot"]:
        lines.append(f"- {c}")
    lines.append(f"\n## Why This Job Becomes More Valuable\n{role['value']}\n")
    return "\n".join(lines)


def simulate_all() -> str:
    """Generate all 5 role simulations in one document."""
    parts = ["# OpenClay — Day-in-the-Life Workflow Simulations\n",
             f"_Generated: {_now()}_\n",
             "_All simulations based on real-world role analysis. "
             "Time savings are conservative estimates._\n",
             "---\n"]
    for key in _ROLES:
        parts.append(simulate_role(key))
        parts.append("\n---\n")
    # Summary table
    parts.append("## Summary: Time Saved Across All Roles\n")
    parts.append("| Role | Industry | Daily Savings | Weekly (5-day) |")
    parts.append("|------|----------|--------------|----------------|")
    for key, role in _ROLES.items():
        weekly = role["total_saved"] * 5
        parts.append(f"| {role['title'].split(' — ')[0]} | {role['industry']} | "
                     f"{role['total_saved']} min | {weekly} min ({weekly//60}h {weekly%60}m) |")
    parts.append("\n_OpenClay does not replace people. It gives them back the time "
                 "that paperwork stole._\n")
    return "\n".join(parts)


# ── Resistance guide ────────────────────────────────────────────────

_RESISTANCE_GUIDE = """# Introducing OpenClay Without Triggering Fear
## A Leadership Guide for Honest AI Adoption
_Generated by OpenClay. For managers, directors, and team leads._
---
## 5 Real Reasons Employees Resist AI Tools
1. **"They're replacing me."** The most common fear. Even if untrue, it feels true.
2. **"I'll have to learn something new when I'm already overwhelmed."** Change fatigue is real.
3. **"My expertise won't matter anymore."** People who are good at their jobs fear being made generic.
4. **"They'll see how long things actually took me."** Transparency can feel like surveillance.
5. **"If it works, they'll cut headcount."** Because historically, that's exactly what happened.
## What NOT to Say
- ~~"This will make everyone more efficient."~~ (They hear: "We'll need fewer of you.")
- ~~"It's just a tool, like email."~~ (Email didn't threaten anyone's job.)
- ~~"Everyone else is already using AI."~~ (Pressure disguised as encouragement.)
- ~~"Trust the process."~~ (Trust is earned, not commanded.)
- ~~"This is mandatory."~~ (Nothing kills adoption faster.)
## What TO Say
- "This handles the paperwork you hate so you can do the work you're good at."
- "You decide what it touches. You can turn it off anytime."
- "It doesn't see anything you don't show it. Nothing leaves your machine."
- "I want to know what's not working. Your feedback changes what we keep."
- "Your job isn't going away. The boring part of your job is."
## Identifying Informal Leaders
Every team has 1-2 people others watch before deciding. They are NOT always the loudest or most senior. Look for:
- The person everyone asks "did you try it?" before they try anything
- The person whose skepticism carries weight (win them, win everyone)
- The person who quietly adopted the last tool change (they'll adopt this one first)

Start with them. One-on-one. Let them break it. Let them complain. Then let them discover it saves them 20 minutes on a task they hate.
## Handling Avoidance
If someone avoids the tool entirely:
- Don't force it. Ask: "What's the part of your day you wish took less time?"
- Show them ONE task, solved in under 2 minutes
- Let them keep their current workflow alongside it — no ultimatums
- Check back in a week. If they're still not using it, ask why and actually listen
## Framing Freed Time
The most dangerous moment is when time is saved. If leadership immediately fills that time with more work, trust dies instantly.

Instead:
- Let the employee decide what to do with saved time for the first 2 weeks
- Celebrate when someone uses freed time for mentoring, learning, or quality improvement
- Never, ever say "since you have extra time now..."
- Track outcomes (quality improvement, error reduction, satisfaction) — not just speed
---
_OpenClay is not a productivity tool. It's a dignity tool. It gives people back the time that paperwork stole, so they can do the work that actually matters._
"""

_ONBOARDING_ES = """# Bienvenido/a a OpenClay
## Lo que necesitas saber antes de empezar
---
### Que es OpenClay?
OpenClay es un asistente que corre en tu computadora — no en la nube, no en un servidor de la empresa. Es tuyo.

Lo que hace:
- Organiza notas y documentos que le muestres
- Resume correos largos en 5 puntos
- Estructura reportes de laboratorio, notas clinicas, o papeles administrativos
- Detecta errores o informacion que falta en tus documentos
- Sugiere los proximos pasos basado en tus patrones de trabajo
### Lo que NO hace
- **No lee tu pantalla.** Solo ve los archivos que tu le das.
- **No envia nada a internet.** Todo se procesa aqui, en tu maquina.
- **No toma decisiones por ti.** Sugiere, organiza, resume — tu decides.
- **No reemplaza tu trabajo.** Reemplaza el papeleo que te roba tiempo de tu trabajo real.
- **No te vigila.** No hay metricas de productividad, no hay reportes a tu supervisor.
### Quien ve lo que produces?
Solo tu. Los archivos se guardan en tu escritorio, en una carpeta llamada "OpenClay Output". Nadie mas tiene acceso a menos que tu lo compartas.
### Como apagarlo
- Cierra la ventana. Eso es todo.
- Si no quieres usarlo un dia, no lo abras. No pasa nada.
- Si quieres desinstalarlo, borra la carpeta. No deja rastro.
### Tu primera tarea
1. Abre OpenClay
2. Arrastra cualquier documento a la ventana (una nota, un correo, un reporte)
3. Lee lo que produce
4. Decide si te es util

Si no te es util, dilo. Tu opinion cambia lo que se queda y lo que se va.
---
**Esto es tuyo. Tu decides como usarlo.**
"""


def generate_all() -> dict:
    """Generate all outputs: simulations, resistance guide, onboarding."""
    sim = simulate_all()
    sim_path = _save("WORKFLOW_SIMULATIONS.md", sim)
    res_path = _save("RESISTANCE_GUIDE.md", _RESISTANCE_GUIDE.strip() + "\n")
    onb_path = _save("EMPLOYEE_ONBOARDING_ES.md", _ONBOARDING_ES.strip() + "\n")
    return {"simulation_path": sim_path, "resistance_path": res_path,
            "onboarding_path": onb_path, "roles": list(_ROLES.keys())}


# ── Self test ───────────────────────────────────────────────────────

def self_test() -> bool:
    """Verify all 5 role simulations and document generation."""
    for key in ["nurse", "admin", "qc_tech", "reg_affairs", "vet_tech"]:
        sim = simulate_role(key)
        assert f"# {_ROLES[key]['title']}" in sim, f"{key} title missing"
        assert "CANNOT" in sim, f"{key} missing CANNOT section"
        assert "More Valuable" in sim, f"{key} missing value section"
        assert "08:00" in sim, f"{key} missing schedule"
    full = simulate_all()
    assert full.count("---") >= 5, "not enough role separators"
    assert "Summary" in full, "missing summary table"
    result = generate_all()
    assert Path(result["simulation_path"]).exists(), "sim file not created"
    assert Path(result["resistance_path"]).exists(), "resistance file not created"
    assert Path(result["onboarding_path"]).exists(), "onboarding file not created"
    assert len(result["roles"]) == 5, f"expected 5 roles, got {len(result['roles'])}"
    res = Path(result["resistance_path"]).read_text()
    assert "What NOT to Say" in res, "resistance guide incomplete"
    onb = Path(result["onboarding_path"]).read_text()
    assert "Tu decides como usarlo" in onb, "onboarding incomplete"
    return True


if __name__ == "__main__":
    print("self_test:", self_test())
