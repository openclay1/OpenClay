# Boot Load Policy

_This file defines which context files load at boot vs on demand._
_Only 3 files load on cold boot: SOUL.md, BRAIN.md, boot_load_policy.md_

## Boot Files (always loaded)
- SOUL.md — identity and principles
- BRAIN.md — compressed long-term memory (<500 words)
- boot_load_policy.md — this file

## On-Demand Context (loaded when task requires it)

| Task Type | Context Files |
|-----------|--------------|
| clinical | context/clinical_context.md, DECISIONS.md |
| research | context/research_context.md, DECISIONS.md |
| grant | context/grant_context.md, DECISIONS.md |
| billing | context/billing_context.md, DECISIONS.md |
| veterinary | context/vet_context.md, DECISIONS.md |
| admin | SESSION.md |
| review | SESSION.md, DECISIONS.md |
| general | SESSION.md |

## Rules
- SESSION.md loads only when session history is needed
- DECISIONS.md loads only when past decisions are relevant
- All other .md files stay in /context/ and load per task type
- Never load all files at once — this degrades AI performance
