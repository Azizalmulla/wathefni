# Pre-hiring Unified Inbound CV Pipeline — Wave 1 Implementation

Date: 2026-07-27 (Asia/Kuwait) / stamp `20260726T234100Z`  
Scope: remaining Wave 1 after accepted Phase 0 (40/40 PASS)  
Production mutations: **none**  
Wave 2 started: **no**  
WhatsApp / manual cutover: **no**

Prerequisite accepted:

- `ops/PREHIRING_UNIFIED_INBOUND_CV_PIPELINE_ARCHITECTURE_REVIEW.md`
- `ops/PREHIRING_UNIFIED_INBOUND_CV_PIPELINE_PHASE_0_CONTRACT_FREEZE.md` (40/40 PASS)

## Four major waves (agreed grouping)

| Wave | Scope | Status |
|---|---|---|
| **0 / freeze** | Contract freeze + three risk reproductions | **Accepted** (not repeated here) |
| **Wave 1** | Generic intake envelope + email dual-write + three defect remediations | **This report — complete locally** |
| **Wave 2** | Shared security/processing authority (`cv_version_id`, scan/extract workers) | **Not started** |
| **Wave 3** | Manual + unsolicited WhatsApp adapters through envelope | Deferred |
| **Wave 4** | Person Registry / Talent Pool authority, CK person/subject refs, exact Job binding, universal gate | Deferred |

Wave 1 maps former architecture “Phase 1” plus the three Phase 0 entry blockers. Later micro-phases are grouped into Waves 2–4 and are out of scope for this task.

## Executive verdict

| Gate | Result |
|---|---|
| Shared channel-neutral intake envelope added | **PASS** |
| Email dual-write with exact parity hooks; live email path authoritative | **PASS** |
| Dual-write production-dark by default (`WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE` off) | **PASS** |
| Three frozen defects remediated and tested | **PASS** |
| Envelope proves no duplicate candidate/app/OCR/classification/CK writes | **PASS** |
| WhatsApp / manual cutover | **not done (correct)** |
| Production behavior / deploy | **unchanged (no deploy)** |
| Wave 2 implementation | **not started** |

### GO / NO-GO for Wave 2

| Decision | Result |
|---|---|
| **Wave 2 shared security/processing authority (local additive design)** | **GO — with blockers below** |
| Enabling envelope dual-write in production without staging parity proof | **NO-GO** |
| Cutting over WhatsApp or manual upload | **NO-GO** |
| Beginning Wave 2 before Wave 1 report acceptance | **NO-GO until accepted** |
| Treating live email outcomes as driven by envelope rows | **NO-GO** (email path remains authoritative through Wave 1) |

## What shipped in Wave 1

### 1. Channel-neutral intake envelope

New module: `wathefni-orchestrator/inbound_cv_intake.py`

Tables (additive `CREATE IF NOT EXISTS`):

- `intake_source_events` — channel/provider/external event identity + route/provenance + legacy inbound/submission links
- `intake_subjects` — provisional subject per event
- `intake_items` — CV intake items mapped 1:1 to stored documents when present
- `intake_item_documents` — document link table with content SHA

Legacy bridge columns:

- `intake_submissions.envelope_event_id`
- `intake_documents.envelope_item_id`
- `intake_documents.envelope_subject_id`

Stable UUID5 helpers: `stable_event_id`, `stable_subject_id`, `stable_item_id`.

Envelope version: `unified-inbound-cv-envelope-v1`.

### 2. Email dual-write (live path authoritative)

- Hooked inside `durable_email_ingress.durably_receive_postmark` **before** `before_commit` / `commit`, same DB transaction as durable email rows.
- Gated by `WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE` — **default OFF**.
- When OFF: zero envelope writes; email receive/scan/identity/extraction/classification/CK paths unchanged.
- When ON (local/staging only until authorized): idempotent mirror of receipt → event/subject/item/document links; updates legacy bridge columns.
- `ensure_schema` co-ensured from durable email schema and app bootstrap.
- Envelope module contains **no** `candidates` / `applications` inserts, no job enqueue, no OCR, no classification, no CK writes.

### 3. Three Phase 0 defects remediated

| Risk | Fix | Authority |
|---|---|---|
| Single-item Link-to-Job SQL | `WHERE app_key=%s AND company_code=%s` with 9 placeholders matching 9 args | `app.py::dashboard_prehire_import_assign` |
| Auto-admit when policy unset | `None` → **False** (fail closed) | `app.py::company_auto_admit_imports` |
| CK held sibling over-denial | Exact `app:<app_key>` uses `_anchor_actionability`; Job caps no longer AND across siblings | `candidate_knowledge_authority.resolve_exact` |

Notes:

- `_strictest_actionability` retained as a documented legacy helper; `resolve_exact` no longer calls it.
- Auto-admit fail-closed is an intentional remediation. It changes default **only after deploy**; production was not mutated in this wave.
- Phase 0 contract tests were updated to assert the remediated contracts (Wave 1 supersedes the frozen defective expectations for those three risks).

### 4. Explicit non-goals preserved

- No WhatsApp dual-write or cutover.
- No manual upload dual-write or cutover.
- No Wave 2 shared scan/extract/`cv_version_id` moves.
- No production flag flips, deploys, or Postmark/Octopus/Voyage calls from this task.

## Tests

Command:

```bash
cd wathefni-orchestrator
.venv/bin/python -m unittest test_unified_inbound_cv_phase0_contracts test_unified_inbound_cv_wave1
```

Result: **57/57 PASS** (Phase 0 suite + Wave 1 suite) at stamp `20260726T234100Z`.

Additional regression: `test_candidate_knowledge_phase1` → **28/28 PASS**.

Wave 1 coverage file: `wathefni-orchestrator/test_unified_inbound_cv_wave1.py`

| Area | Proof |
|---|---|
| Envelope schema + deterministic IDs | unit |
| Dual-write flag default OFF | unit |
| Dual-write idempotency (one event/subject/item/doc link) | recording cursor |
| Dual-write wired before commit; email path authoritative | source pin |
| No WhatsApp/manual cutover symbols | source pin |
| No envelope downstream authority writes | AST + source pin |
| Email provider/document idempotency preserved | source pin |
| Single-item assign SQL/tenant fix | source pin |
| Auto-admit fail closed | source pin |
| Live CK anchor not over-denied by held sibling | in-memory resolve_exact |

## Module fingerprints (Wave 1 local)

| Module | SHA-256 |
|---|---|
| `inbound_cv_intake.py` | `135bd8f813e61b73dcb9e9d1c02f2ebf71e9ac214d903d4ea073005e23946828` |
| `durable_email_ingress.py` | `769aeae9a89a45050e8a3ead6a2c74c5bdb638110e13bcd6b0603e65b3af7bd6` |
| `candidate_knowledge_authority.py` | `4466e1f4825fd79b8437221dcea5b9da4857aef508561303f0541dcac36d4b6b` |
| `app.py` | `49ccf4c4bce2ed84d099bafce3d7319f296dad2eab09cf2432c921ac548e5110` |

## Production posture

- No production deploy or env change from this task.
- Dual-write remains dark unless `WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE` is explicitly enabled under separate authorization.
- Live email path (`inbound_messages` / `intake_submissions` / `intake_documents` / processing jobs) remains the authority for retries, dead letters, scanning, extraction, classification, and candidate/application creation.

## Wave 2 entry blockers (must clear before/with Wave 2)

1. Accept this Wave 1 report.
2. Staging-only enablement of dual-write with parity counts (events == durable submissions; item/document link parity; zero extra candidates/apps/OCR/CK rows).
3. Explicit authorization before any production dual-write flag or defect-fix deploy.
4. Keep email wrappers authoritative while extracting shared scan/accepted-item workers.
5. Do not fold WhatsApp/manual cutover into Wave 2.

## Artifacts

- `wathefni-orchestrator/inbound_cv_intake.py`
- `wathefni-orchestrator/durable_email_ingress.py` (dual-write hook + schema co-ensure)
- `wathefni-orchestrator/app.py` (auto-admit fail-closed; single-item assign SQL; schema bootstrap)
- `wathefni-orchestrator/candidate_knowledge_authority.py` (anchor actionability)
- `wathefni-orchestrator/test_unified_inbound_cv_wave1.py`
- Updated Phase 0 fixtures/tests for remediated risk expectations
- This report: `ops/PREHIRING_UNIFIED_INBOUND_CV_PIPELINE_WAVE_1_IMPLEMENTATION.md`
