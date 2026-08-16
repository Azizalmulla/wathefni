# Onboarding Wave 3 — Controlled migration of four real checklists

**Stamp:** `20260802T012829Z`  
**Evidence:** `ops/evidence/onboarding-wave3-migration-20260802T012829Z/`  
**Template:** `default_kuwait@2.0.0`

---

## Verdict

| Gate | Result |
|---|---|
| Pre-migration 19-row fingerprint recorded | **PASS** |
| Backup + rollback script | **PASS** |
| Dual-control approval (requester ≠ approver) | **PASS** |
| Dry-run digest == commit digest | **PASS** |
| Rollback restored exact 19-row fingerprint | **PASS** |
| Reapply after rollback | **PASS** |
| Migration proofs | **51/51** |
| E360 freeze | **54/54** |
| SEED / HR_MUTATE | **remain off** |
| Employee-app allowlist | **Talal only** (unchanged) |
| Unresolved conflicts | **none** |
| **Controlled real HR onboarding operation** | **GO** (read + ESS paths live; enable `HR_MUTATE` only in a dedicated follow-up — still **no** general SEED) |

Next main step: UX / final qualification (and optional WATHEFNI-only `HR_MUTATE` enablement).

---

## Dual-control evidence

| Role | User ID | Email |
|---|---|---|
| Requester | `88b17ca9-aff4-4721-a553-c1b5514ef95f` | azizalmulla16@gmail.com |
| Approver | `201d0b3b-6a6f-483f-914a-7a2356fd0a2e` | fslalmulla@gmail.com |
| First batch | `d01842ce-f80e-413d-bdb5-bb0ff4553001` | (rolled back in proof) |
| Final reapply batch | `74b7298b-0fe5-4a1e-b1ed-69c703f30a6d` | **committed** |
| Self-approval | **rejected** (`self_approval_forbidden`) | |

Planned starts (explicit, required): **2026-08-01** for all four.

---

## Per-employee before → after

| Employee | Before | After | Notes |
|---|---|---|---|
| Talal `…252254` | 6 | **38** (36 v2 + 2 retired) | History preserved; bank → ESS; pinned 2.0.0 |
| Fouad `…363363` | 6 | **38** | Reminders preserved; obsolete retired not deleted |
| Mohammad `…727743` | 6 | **38** | `civil_id`/`bank_details` received kept; bank value **redacted** |
| Brian `…411617` | 1 (`personal_photo`) | **36** | Photo preserved; partial expanded |

**Final totals:** 150 item rows · 6 `retired_legacy` (education_cert/medical ×3) · all `onboarding_template_version=2.0.0`

| Employee | pending | complete | status |
|---|---|---|---|
| Talal | 4 | 0 | in_progress |
| Fouad | 4 | 0 | in_progress |
| Mohammad | 2 | 2 | in_progress |
| Brian | 4 | 0 | in_progress |

---

## Migration & rollback evidence

| Proof | Result |
|---|---|
| Code/data backup | `/opt/wathefni/backups/production-pre-onboarding-wave3-20260802T012829Z/` |
| Module data rollback | Restored exact pre-migration fingerprint (19 rows) |
| Reapply | New dual-control batch committed successfully |
| Idempotent inserts | No duplicate canonical items on re-preview |
| Bank outside ESS | Still blocked (`bank_via_ess_required`) |
| Counts/summaries | Reconciled after recompute (`retired_legacy` excluded from pending) |

Artifacts: `migration/per-employee-before-after.json`, `commit.json`, `rollback.json`, `reapply-commit.json`, `final-counts.json`, `dual-control-approval.json`.

---

## Unresolved conflicts

**None.** Missing planned starts fail closed (offline proof: 4× `planned_start_required`).

---

## Flags (unchanged)

| Flag | Value |
|---|---|
| `ONBOARDING_SEED` | **off** |
| `ONBOARDING_HR_MUTATE` | **off** |
| `EMPLOYEE_APP` allowlist | `WATHEFNI-96550252254` only |
| Wave 3 migration gate | process-local to migrator only |

---

## GO / NO-GO

| Decision | |
|---|---|
| Keep migrated `default_kuwait@2.0.0` checklists as production truth | **GO** |
| Controlled real HR onboarding **operation** (mark/waive/remind on reals) | **GO** pending a **narrow** follow-up that turns on `HR_MUTATE` for WATHEFNI only — **not** done in this wave |
| Enable general production SEED | **NO-GO** |
| Broaden employee-app access | **NO-GO** |

Remaining for final qualification: dashboard UX for v2 fields, deliberate `HR_MUTATE` enablement, soak on real HR workflows.
