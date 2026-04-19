# OpenClay Clínico — Demo Script for CHAIC 2026
# Caribbean Health AI Congress · PR Convention Center · Sept 25–26

**Presenter:** Francis
**Audience:** Clinical informaticists, hospital administrators, pharma QA, physicians
**Demo device:** MacBook with OpenClay running locally (no internet needed)
**Time:** 5 minutes

---

## SETUP (before you go on stage)

- OpenClay running at localhost:3000
- Clay Clínico selected as active agent
- A sample de-identified clinical note loaded (see: `demo_clinical_note.txt`)
- Internet OFF — show this visibly by putting laptop in airplane mode on stage

---

## THE HOOK (0:00–0:30)

Say: *"Tengo una pregunta para la audiencia. ¿Cuántos de ustedes han tecleado información de un paciente en ChatGPT?"*

[Pause for reaction]

*"Esa información fue a los servidores de OpenAI. En San Francisco. Procesada por empleados que pueden revisarla para 'mejoras de calidad'. Eso es una violación de HIPAA. OpenClay hace todo esto..."*

[Point to screen where Clay is running]

*"...sin salir de esta laptop. Cero transmisiones. Cero servidores. Funciona sin internet."*

---

## DEMO SEQUENCE

### Minute 1 — Show "offline" concretely
- Open Network settings on Mac, show WiFi off / airplane mode on
- Reload OpenClay in browser — it loads instantly (it's local)
- Type: "What is my work about?" — Clay answers using local memory
- Say: *"Clay remembers what we talked about last time, locally."*

### Minute 2 — Clinical document analysis
- Upload the sample clinical note (or paste it)
- Click workflow: "🏥 Analizar documento clínico"
- Clay produces: summary, key findings, atypical values, recommendations
- Say: *"No API call. No data leaving the room. This is the note never leaving the hospital."*

### Minute 3 — Patient communication (bilingual)
- Click workflow: "💬 Explicar en términos simples"
- Show the medical jargon converted to 6th-grade Spanish for a patient
- Say: *"Spanish-English bilingual. Puerto Rico's reality, built in."*

### Minute 4 — Regulatory compliance query
- Type: "What are the FDA 21 CFR Part 11 requirements for electronic records in a clinical setting?"
- Clay answers correctly from its training
- Say: *"Pharma manufacturing, FDA compliance, clinical SOPs — all accessible from one tool, offline."*

### Minute 5 — The closer
- Show Clay running on a laptop with battery power, WiFi off
- Say: *"Hurricane Maria lasted 11 months without power in some areas. This tool works during a power outage on a laptop battery. That's not a feature — it's a design philosophy."*
- Show QR code to waitlist / Pro signup

---

## QUESTIONS TO ASK THE AUDIENCE

1. *"Does your hospital currently use any AI tools for clinical documentation?"*
2. *"Has your IT or legal team approved any cloud AI for patient-facing workflows?"*
3. *"What would it mean for your workflow if this ran on every nurse's tablet, offline?"*

---

## HANDLING TOUGH QUESTIONS

**Q: Is this FDA-approved?**
A: OpenClay is a decision-support tool, not a medical device. Same category as a medical calculator or reference app. HIPAA compliance is built-in because data never leaves the device.

**Q: What about liability?**
A: Every Clay Clínico response includes a disclaimer: "Las decisiones clínicas siempre requieren criterio profesional." We position this as augmentation, not replacement.

**Q: Can it connect to our EHR?**
A: Not yet — but it can read any document you paste or upload. EHR integration via FHIR is on the roadmap.

**Q: How do you make money?**
A: Pro license $12/month. Institutions get custom pricing. The community version is always free.

---

## COLLATERAL TO BRING

- [ ] Business cards with QR to waitlist (tally.so/r/wbeKQk)
- [ ] Printed one-pager (use `docs/openclay_public_whitepaper.md` as base)
- [ ] USB stick with install script (install.sh)
- [ ] Demo laptop fully charged, tested, airplane mode ready

---

*Built in Puerto Rico · OpenClay v1.3 · COANA Labs*
