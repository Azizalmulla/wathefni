# Onboarding Wave 2B — Production synthetic canary

**Stamp:** `20260802T011738Z`  
**Evidence:** `ops/evidence/onboarding-wave2b-prod-canary-20260802T011738Z/`  
**Scope:** WATHEFNI production — Wave 2 code + synthetic-only mutations. Four real checklists untouched.

---

## Verdict

| Gate | Result |
|---|---|
| Pre-deploy backup + rollback script | **PASS** |
| Rollback executed + Wave 1B SHA restored | **PASS** |
| Wave 2B redeploy after rollback | **PASS** |
| Production SEED | **off** |
| Production HR_MUTATE | **off** |
| Production SYNTHETIC_CANARY | **on** (strict keys only) |
| Four real checklist rows (19) unchanged | **PASS** |
| Synthetic canary proofs | **59/59** (×2, incl. post-rollback) |
| Wave 1 read authority | **38/38** |
| Employees 360 freeze | **54/54** |
| Synthetic cleanup to zero | **PASS** |
| Employee-app allowlist | **unchanged** (Talal only) |
| **Controlled migration of four reals** | **NO-GO** |

**GO** for keeping Wave 2B live in production under synthetic canary only.  
**NO-GO** for enabling SEED/HR_MUTATE on reals or applying the four-real backfill.

Next main steps: (1) controlled real checklist migration, (2) UX/final qualification.

---

## Deployment

| Item | Value |
|---|---|
| Prod SHA before | `a73ee60b…` (Wave 1B) |
| Prod SHA after | `d160e9b2…` (`app.py`) |
| `onboarding_wave2.py` | `1d133473…` |
| `action_registry.py` | `7da46c9e…` |
| Backup | `/opt/wathefni/backups/production-pre-onboarding-wave2b-20260802T011738Z/` |
| Rollback | `BACKUP/ROLLBACK.sh` (executed → Wave 1B restored → Wave 2B redeployed) |
| Drop-in | `zz-onboarding-wave2b-synthetic-canary.conf` |

**Deployed capabilities:** `default_kuwait@2.0.0`, template version pinning, due dates + dependencies, optimistic `row_version`, `onboarding_audit_events`, delayed/reschedule/cancel/abandon.

---

## Synthetic canary gate

| Flag | Production |
|---|---|
| `WATHEFNI_ONBOARDING_SEED` | **off** |
| `WATHEFNI_ONBOARDING_HR_MUTATE` | **off** |
| `WATHEFNI_ONBOARDING_SYNTHETIC_CANARY` | **on** |
| Phone prefixes | `965523` |
| Name prefix | `W2B-SYNTH\|` |

Four reals are hard-blocked even with canary on. Mutations require synthetic markers.

### Synthetic IDs (first canary run)

| Field | Value |
|---|---|
| Tag | `ad4a3254` |
| Primary | `WATHEFNI-96552356722` |
| Abandon twin | `WATHEFNI-96552356729` |
| Name | `W2B-SYNTH\|Prod Canary ad4a3254` |

Post-rollback canary used a fresh tag; both runs cleaned to **zero** residue.

---

## Proofs exercised

- Duplicate-safe seed/start; delayed start + unattended activation  
- Reschedule updates open due dates  
- Dependency enforcement; stale mutation fail-closed  
- Employee/HR document store; HR mark/waive/reminder  
- Bank plaintext rejected (ESS-only)  
- Cancel + abandon preserve history; idempotent repeats  
- Cross-tenant empty; out-of-scope/terminal fail-closed  
- Four-real fingerprint unchanged (19 rows)  
- Cleanup: employees/items/assignments/audit → 0  

---

## Remaining blockers (before real migration)

1. Dedicated dual-control migration wave with backup + item-level audit  
2. Brian partial checklist handling (preserve `personal_photo`)  
3. Map/retire obsolete `education_cert` / `medical` only via audited migration  
4. ESS bank allowlist still empty — real bank collection remains ESS-gated  
5. Dashboard UX not redesigned for delayed/cancel/version fields  
6. Do **not** flip production SEED/HR_MUTATE for reals in that wave without explicit approval  

---

## GO / NO-GO

| Decision | |
|---|---|
| Keep Wave 2B production synthetic canary | **GO** |
| Controlled migration of four real checklists | **NO-GO** (next dedicated wave) |
| Enable production SEED / HR_MUTATE for reals | **NO-GO** |
