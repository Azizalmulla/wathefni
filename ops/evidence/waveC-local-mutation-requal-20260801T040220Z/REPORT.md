# Wave C — local synthetic mutation requal + Assistant email readiness fix

**Stamp:** `20260801T040154Z` (matrix) · evidence pack created `20260801T033857Z` window → see path below  
**Mode:** Local only (`wathefni_local_boundary`, `WATHEFNI_ENV=test`, `dry_run`). **No deploy. Wave D not started.**

**Evidence:** `ops/evidence/waveC-local-mutation-requal-20260801T040220Z/`  
*(If stamp differs, use the `waveC-local-mutation-requal-*` folder under `ops/evidence/`.)*

---

## 1) Assistant email readiness — root cause & fix

### Root cause
`assistant_capability_catalog._email_configured` only probed `WATHEFNI_EMAIL_PROVIDER` / SMTP / Resend / SendGrid. It ignored Wathefni’s real default transport (`WATHEFNI_POSTMARK_SERVER_TOKEN` + From) and did not consult Settings (`public_email_sending_view` → `current_sender` / `status`).

Result: integrations could report `wathefni` / `ready` while Assistant marked `email` as `enabled_but_not_configured`.

### Fix (local product change)
File: `wathefni-orchestrator/assistant_capability_catalog.py`

- `_email_configured(legacy, company_code)` now:
  1. Reads `tenant_email_authority.public_email_sending_view` when DB is available  
  2. **`status == ready` ⇒ configured** (covers wathefni/Postmark and ready Microsoft / company-domain)  
  3. **Branded modes (`microsoft_mailbox`, `postmark_company_domain`) that are not ready stay fail-closed** (even if Postmark exists globally)  
  4. Falls back to `outbound_postmark_available()` / Postmark env probes for default Wathefni path

Also fixed during Wave C (fail-closed found in mutation path):

- `offer_service.public_offer_preview` now rejects **expired** tokens (same as `respond_via_token`) so compensation cannot leak via preview.

### Tests
`test_assistant_capability_catalog.py` — new cases:

- Postmark env recognized  
- `outbound_postmark_available` recognized  
- Integrations `wathefni`/`ready` ⇒ email offerable  
- Microsoft `setup_required` ⇒ not configured (fail-closed)  
- Microsoft `ready` ⇒ configured  

Result: **capability unit PASS** · **empty-state capability matrix PASS**  
Artifacts: `assistant-email-fix/`

---

## 2) Wave C mutation matrix

**Harness:** `ops/waveC-local/waveC-local-mutation-requal-matrix.py`  
**DB:** `wathefni_local_boundary` · marker `waveC-local-mutation-requal-v1` · phones `+9658869…`  
**Tenants:** `WCAVLO` `WCALXO` `WCAXVO` `WCAXXO` `WCXVLO` `WCXXXO` `WCNOOF` `WCPEER`

| Suite | Passed | Failed | Gates |
|---|---:|---:|---:|
| Wave C local | **546** | **15** | **561** |
| Cleanup residue | **PASS** | 0 | companies/apps/candidates for `WC*` / `+9658869*` = **0** |

### PASS/FAIL per mutation class

| Mutation | Result |
|---|---|
| Create/update job (version token) | **PASS** 8/8 |
| Publish job + apply identity | **PASS** 8/8 |
| Create candidate/application + CV lifecycle | **PASS** 8/8 |
| Ranking (no lifecycle mutation) | **PASS** |
| Stage changes (shortlist) | **PASS** 8/8 |
| Assessment assign/send | **PASS** 5/5 (module ON) |
| Assessment cancel | **PASS** 5/5 |
| Assessment retry after cancel | **PASS** 5/5 |
| Interview create | **PASS** 4/4 (live ON) |
| Interview reschedule (same id) | **PASS** 4/4 |
| Interview cancel | **PASS** 4/4 |
| Offer create/approve/send | **PASS** 7/7 |
| Duplicate send blocked after sent | **PASS** 7/7 |
| Offer accept (token) | **PASS** 7/7 |
| Offer token expiry blocks accept | **PASS** 7/7 |
| Hire (atomic) + confirmation single-use | **PASS** 8/8 |
| Reject | **PASS** 8/8 |
| Withdraw | **PASS** 8/8 |
| Tenant isolation / cross-tenant probes | **PASS** (isolation gates ok) |
| Full cleanup / zero residue | **PASS** |

### Remaining FAIL gates (15) — not core mutations

| Gate | Count | Severity | Root cause |
|---|---:|---|---|
| `tool_schedule_interview_gated_by_interviews` | 8 | **Medium** | Tool entitlement lists `pre_hiring` only; expected `interviews` module in required_entitlement_modules (boundary drift vs Jul 25 freeze) |
| `assistant_live_tools_follow_interviews_module` | 4 | **Medium** | Live interview tools still visible when `interviews` module OFF |
| `mobile_omits_assessments_when_off` | 3 | **Medium** | Mobile surface still lists `assessments` when module OFF |

These are optional-module **surface/gating** regressions relative to the frozen boundary matrix. Core lifecycle mutations (job → hire/reject/withdraw, assessment cancel/retry, interview reschedule/cancel, isolation, cleanup) **PASS**.

---

## 3) Synthetic record IDs (sample)

See `SYNTHETIC_IDS.json`.

**WCAVLO** (full modules ON):

| Kind | ID |
|---|---|
| Apps | `WCAVLO-WC-main`, `WCAVLO-WC-bare`, `WCAVLO-WC-ardoc` |
| Phones | `+965886987660`, `+965886994394`, `+965886938357` |
| Apply | `APPLY-WCAVLO-WC_ROLE` |
| Assessment cancelled → retry | `cc0fef98-…` → `3edd641a-…` |
| Video interview | `f098e951-16a2-426e-b1e6-f957d76a88d5` |
| Offer | `b9985c8f-6e0b-41e0-9aec-f21c9b896af7` |
| Employee after hire | `WCAVLO-965886987660` |

**WCPEER** (isolation peer): apps `WCPEER-WC-*`, employee `WCPEER-965886986856`, offer `0101d7e7-…`

All eight `WC*` tenants + `+9658869*` phones removed after cleanup.

---

## 4) Cleanup proof

- Matrix gate `cleanup_zero_residue` **PASS** (`{}`)
- Post-run SQL: `companies` with `WC%` = 0 · `applications` WC% = 0 · `candidates` `+9658869%` = 0

---

## 5) Blockers by severity

| Severity | Item | Status |
|---|---|---|
| **Fixed (this wave)** | Assistant under-reports Postmark/wathefni ready | Fixed + tests |
| **Fixed (this wave)** | Expired offer preview leaked compensation | Fixed in `public_offer_preview` |
| **Medium** | Interview tools not gated to `interviews` module in tool entitlements / Assistant visibility when OFF | Open — surface drift |
| **Medium** | Mobile still exposes assessments when module OFF | Open — surface drift |
| — | Wave D ingestion | **Not started** |
| — | Production deploy | **Not done** (local only) |

---

## 6) Files touched (local)

- `wathefni-orchestrator/assistant_capability_catalog.py`
- `wathefni-orchestrator/test_assistant_capability_catalog.py`
- `wathefni-orchestrator/test_assistant_empty_state_catalog.py`
- `wathefni-orchestrator/offer_service.py` (expired token preview fail-closed)
- `ops/waveC-local/waveC-local-mutation-requal-matrix.py` (new local harness)
