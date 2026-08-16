# Pre-hiring Unified Inbound CV — Legacy Job Binding Read-Only Audit

Date: 2026-07-27 (Asia/Kuwait) / stamp `20260727T003453Z`  
Scope: all `WATHEFNI` applications missing a verified `application_job_bindings` row  
Database: `wathefni` (production) — **read-only**  
Mutations: **none** (no INSERT/UPDATE/DELETE)  
Enforcement: **not enabled**  
Channel cutover: **not performed**  
Backfill: **not performed**

Evidence:
- Remote: `/opt/wathefni/production-evidence/unified-inbound-cv-legacy-binding-audit/20260727T003453Z/audit.json`
- Local: `ops/screenshots/unified-inbound-cv-legacy-binding-audit/audit.json`
- Script: `ops/unified-inbound-cv-legacy-binding-read-only-audit.py`

Post-audit verification: `application_job_bindings` verified count for WATHEFNI still **0**; applications still **18**; process `ENFORCE` **absent**.

---

## Executive answer

**Missing bindings are almost entirely because these applications predate Wave 4’s `application_job_bindings` authority.**  
Production-dark dual-write is ON for *new* exact Job confirms, but **no legacy backfill has been run** (and this audit did not run one).

| Population | Count |
|---|---|
| WATHEFNI applications | **18** |
| Verified job bindings | **0** |
| Missing verified bindings | **18 / 18** |

| Classification | Count | Meaning |
|---|---|---|
| `safe_to_backfill_after_owner_approval` | **11** | Real live Job apps; canonical `positions` row exists; Job link looks trustworthy; missing binding is legacy gap only |
| `ambiguous` | **5** | Smoke-test / quarantine residue — Job row exists but should not be treated as production hiring truth |
| `held` | **2** | Talent Pool held imports (`needs_role`, empty position) — must **not** be backfilled as Job bindings |
| `malformed` / `orphaned` | **0** | No broken FK-style orphans found |

**Real data problems:** none that explain the missing binding table itself.  
Secondary hygiene issues exist (5 smoke-test apps; 2 held imports; sparse `application_lifecycle_events` on all 18), but they are **not** evidence that Wave 4 dual-write is broken.

---

## Why no verified binding rows exist

1. `application_job_bindings` was introduced in Wave 4 and enabled in production-dark (`20260727T002415Z`) in **shadow / dual-write** mode only.
2. Every audited application was created **before** that authority wrote bindings (`created_at` from 2026-04-13 through 2026-07-26).
3. Production-dark explicitly **did not backfill**.
4. Therefore every shadow-deny of `verified_job_binding_missing` on these rows is **expected pre-authority gap**, not an identity/Job corruption signal.

All 18 rows also have **zero** `application_lifecycle_events`. That is a separate legacy instrumentation gap (lifecycle ledger was not populated for these rows), not a binding-table defect.

---

## Per-application audit

### A) Safe to backfill only after owner approval (11)

Common pattern:
- Canonical Job exists (`positions.status=open`, matching `apply_code` / title)
- Current Job link assessed **trustworthy** (live status + position present)
- Source channel: **legacy unspecified** (`data_source=production`; no WhatsApp/email/manual channel marker)
- Created as legacy rows without lifecycle events
- Why no binding: **predated Wave 4; no backfill**

| app_key | status | candidate | Job | created | channel | Job canonical? | Job link trustworthy? | class |
|---|---|---|---|---|---|---|---|---|
| `96597727743-WATHEFNI-FULLSTACK_DEVELOPER` | awaiting_cv | MOHAMMAD QATTAN (`96597727743`) | FULLSTACK_DEVELOPER | 2026-04-13 | legacy_unspecified | yes | yes | safe* |
| `96599338566-WATHEFNI-FULLSTACK_DEVELOPER` | screening_complete | Aziz Almulla (`96599338566`) | FULLSTACK_DEVELOPER | 2026-04-13 | legacy_unspecified | yes | yes | safe* |
| `96597727743-WATHEFNI-MARKETING_SPECIALIST` | hired | MOHAMMAD QATTAN (`96597727743`) | MARKETING_SPECIALIST | 2026-05-03 | legacy_unspecified | yes | yes | safe* |
| `96550252254-WATHEFNI-SOCIAL_MEDIA_MANAGER` | hired | Talal Fadhli (`96550252254`) | SOCIAL_MEDIA_MANAGER | 2026-05-04 | legacy_unspecified | yes | yes | safe* |
| `96599652277-WATHEFNI-SOCIAL_MEDIA_MANAGER` | shortlisted | Faisal Almulla (`96599652277`) | SOCIAL_MEDIA_MANAGER | 2026-05-04 | legacy_unspecified | yes | yes | safe* |
| `96597485758-WATHEFNI-HR` | shortlisted | Hamad Almulla (`96597485758`) | HR | 2026-05-05 | legacy_unspecified | yes | yes | safe* |
| `96598900677-WATHEFNI-ACCOUNTING` | review_pending | AZIZ ALMULLA (`96598900677`) | ACCOUNTING | 2026-05-05 | legacy_unspecified | yes | yes | safe* |
| `96598900677-WATHEFNI-FINANCE` | screening | AZIZ ALMULLA (`96598900677`) | FINANCE | 2026-05-05 | legacy_unspecified | yes | yes | safe* |
| `96598900677-WATHEFNI-HR` | shortlisted | AZIZ ALMULLA (`96598900677`) | HR | 2026-05-05 | legacy_unspecified | yes | yes | safe* |
| `96566363363-WATHEFNI-IT_MAINTENANCE` | hired | Fouad Burhamad (`96566363363`) | IT_MAINTENANCE | 2026-05-06 | legacy_unspecified | yes | yes | safe* |
| `96597485758-WATHEFNI-ACCOUNTING_EXCEL` | screening_complete | Hamad Almulla (`96597485758`) | ACCOUNTING_EXCEL | 2026-05-14 | legacy_unspecified | yes | yes | safe* |

\* `safe_to_backfill_after_owner_approval` — not an instruction to backfill now.

**Lifecycle history:** empty for all 11.  
**Originally created:** inferred `legacy_row_without_lifecycle_event` (no Stage-B / intake_admit event rows).  
**Trust basis:** open canonical position + matching apply_code/title + non-held live status.

---

### B) Ambiguous — smoke-test / quarantine (5)

These point at real Jobs, but `data_source=smoke_test` and `data_source_detail=quarantined_by_cleanup_script`. They must not be treated as production hiring bindings.

| app_key | status | candidate | Job | created | class |
|---|---|---|---|---|---|
| `96555550132-WATHEFNI-ACCOUNTING` | awaiting_cv | phone `96555550132` (no name) | ACCOUNTING | 2026-05-15 | ambiguous |
| `96555550133-WATHEFNI-ACCOUNTING` | screening | Test Candidate (`96555550133`) | ACCOUNTING | 2026-05-15 | ambiguous |
| `96555550134-WATHEFNI-ACCOUNTING_EXCEL` | awaiting_cv | phone `96555550134` (no name) | ACCOUNTING_EXCEL | 2026-05-15 | ambiguous |
| `96555550135-WATHEFNI-ACCOUNTING_EXCEL` | awaiting_cv | phone `96555550135` (no name) | ACCOUNTING_EXCEL | 2026-05-15 | ambiguous |
| `96555550136-WATHEFNI-ACCOUNTING_EXCEL` | awaiting_cv | phone `96555550136` (no name) | ACCOUNTING_EXCEL | 2026-05-15 | ambiguous |

**Why no binding:** predated Wave 4 **and** not production authority.  
**Safe to backfill:** **no** (until explicit cleanup/owner decision).  
**Lifecycle:** empty.

---

### C) Held — Talent Pool / unassigned (2)

| app_key | status | candidate | Job | created | source evidence | class |
|---|---|---|---|---|---|---|
| `imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT` | needs_role | Esraa Aziz (`imp-wathefni-06ffffc36d7fd375`) | *(empty)* | 2026-06-01 | bulk import batch `cdf19dc3-…` | held |
| `imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT` | needs_role | yasser al dossary (`imp-wathefni-837eb9b1bf14506b`) | *(empty)* | 2026-07-26 | bulk import batch `4d7e58c6-…` | held |

**Job exists canonically:** no (no `position_code`).  
**Current Job link trustworthy:** no.  
**Why no binding:** predated Wave 4 **and** held Talent Pool records must not receive verified Job bindings without exact Job confirmation / `intake_admit`.  
**Safe to backfill:** **no**.  
**Lifecycle:** empty.

---

## Predate vs real data problem

| Question | Finding |
|---|---|
| Are missing bindings simply because apps predate the new system? | **Yes — primary cause for all 18.** |
| Is dual-write failing to write bindings for these rows? | **No evidence.** These rows were not created under the new exact-confirm path after dark enablement. |
| Any malformed/orphan applications? | **None** in this set. |
| Any untrustworthy live Job links among the 11? | **No** — each matches an open canonical `positions` row. |
| Any hygiene issues unrelated to binding authority? | **Yes:** 5 smoke-test quarantined apps; 2 held imports; universal empty lifecycle event history. |

---

## Recommendation (no action taken)

1. **Do not backfill yet** (per owner instruction) — remain production-dark / shadow-only.
2. When a backfill is authorized later, run it in **three buckets**:
   - **A (11):** audited mechanical backfill of verified bindings from canonical `position_code` + `apply_code` + optional synthetic consent provenance labeled `legacy_backfill`.
   - **B (5):** exclude by default; delete/archive or mark non-hiring before any binding.
   - **C (2):** never bind until explicit Job selection / admit.
3. Keep **`ENFORCE` OFF** until bucket A is backfilled (or explicitly waived) — otherwise shadow denials become hard denials on legitimate legacy live apps.
4. Keep **channel cutover NO-GO** until backfill policy is approved and forward dual-write is observed on new exact Job confirms.
5. Optional follow-up (separate from binding backfill): decide whether empty `application_lifecycle_events` for these legacy apps should be reconstructed or left as historical gaps.

**Stop after this audit. No rows inserted or updated. Enforcement off. No channel cutover.**
