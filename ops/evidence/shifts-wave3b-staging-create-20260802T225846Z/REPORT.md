# Shifts Wave 3B — staging create-path closure

**Stamp:** `20260802T225846Z`  
**Evidence:** `ops/evidence/shifts-wave3b-staging-create-20260802T225846Z/`  

## Gate result: **GO**

Mandatory create-path closure passed before any production synthetic deploy.

### Fixes shipped
- Canonical `POST /dashboard/posthire/shifts` create endpoint (Wave 3 gates + scope + synthetic)
- Workspace composer uses `createShift` — **not** unsupported `POST /dashboard/posthire/actions`
- Plural `/actions` still returns **405** (proven)
- Browser composer proved same-day, split (2 authority rows), overnight (`ends_next_day`) with UI↔API↔DB reconcile
- Residual zero for SHW3B staging markers
- Module `shifts_wave3_controlled.py` **v3.1.0** (+ SHW3B / 965531* synthetic markers)

### Suites
| Suite | Result |
|---|---|
| UX smoke | **43 / 0** |
| Browser create-path | **10 / 0** |
| Freezes | E360 57, Onboarding 54, Attendance 26, Leave 35 |

Screenshots under `screenshots/`.
