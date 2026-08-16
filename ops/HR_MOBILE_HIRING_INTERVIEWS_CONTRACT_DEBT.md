# HR mobile Hiring + Interviews — contract debt

Stamp locked: `20260810T174850Z`  
Evidence: `ops/evidence/hr-hiring-interviews-cream-20260810T174850Z/`  
Freeze: `.cursor/rules/hr-mobile-hiring-interviews-freeze.mdc`

## Accepted for now (not blockers)

| Item | Notes |
| --- | --- |
| Interview notes = direct POST (not SOD) | Intentional vs Leave/Candidate; concurrency tokens required |
| `schedule_interview` → interviews list only | No mobile schedule composer; copy says Open interviews |
| Write still listed on cancelled/completed interviews | Capability vs presentation debt; do not invent stage gating in this freeze |
| Assessments | Hidden on mobile; web-only until a real mobile surface exists |
| Priority titles for some kinds | Mobile owns localized title/body keys; server summary kept as fallback |
| Demo Hiring destinations | Demo cards route to Jobs/Interviews lists, not fake detail ids |

## Explicitly out of scope until a new owner wave

- Assessments mobile workflow / queue
- Interview schedule / reschedule / cancel on mobile
- Company-wide unscoped candidate list bypassing job-scoped ranking
- Offer mutations from Hiring home
- Folding Delivery Alerts / Tasks into Hiring
