# Pre-Hiring Offers and Hiring — Staging Green

**Status:** staging-green  
**Production:** **not promoted / untouched**  
**Date:** 2026-07-25 (Kuwait)  
**Source worktree:** `/tmp/wathefni-c3-local`  
**Base commit:** `438241b10d5a55cdc8c84a01d2e66d71eac9e2d7`  
**Prior staging-green:** `c434d4b2076ccf22e4808b3f8739d48ba9b11f22ee05628915e8026e5f902cb9` (Interviews Google CLI)  
**This staging-green artifact:** `71dd4d10d51605968436885c5867a79ace73452e33849d64441ef23801f0ebf5`  
**Delivery:** `WATHEFNI_DELIVERY_MODE=dry_run`  
**Stop:** do **not** run `ops/deploy.sh production` until owner approval.

---

## Verdict

The exact Offers/Hiring local remediation was surgically promoted to isolated staging and fully qualified. Compensation redaction, expiry/stale-link privacy, durable send/resend, provider/DB recovery, one accepted offer, public XSS/CSP, sole hire authority, append-only versions/events, Arabic/English documents, hire-override confirmation/outcome, atomic hire, and GCC/Kuwait document metadata all passed on synthetic tenants. Frozen-module regressions, staging smoke, workers, health, and public routes passed. Synthetic residue is zero. **Stop for owner approval before production.**

---

## Artifact identity

| Item | Value |
|---|---|
| Staging artifact SHA | `71dd4d10d51605968436885c5867a79ace73452e33849d64441ef23801f0ebf5` |
| Staging-green file | `/opt/wathefni/staging/last-green.sha256` |
| Artifact record | `/opt/wathefni/staging/offers-hiring-artifact.sha256` |
| Contained remediation file SHAs | match local remediation (see below) |
| Host | `root@76.13.63.68` |
| Backend | `wathefni-orchestrator-staging.service` · `127.0.0.1:8011` |
| Database | `wathefni_staging` |
| Backup | `/opt/wathefni/backups/staging-pre-offers-hiring-20260724T224233Z` |
| Matrix tenants | **`OFFERSTG`** / **`OFFERISO`** · marker `offers-hiring-staging-matrix-v1` |
| Evidence | `ops/offers/offers-hiring-staging-matrix-20260724T224749Z.json` |

### Per-file SHA256 (deployed remediation bytes)

| File | SHA256 |
|---|---|
| `offer_lifecycle.py` | `6f817e23eeee14f39f035af6be382040a1e829688067dfacebcd8eebea9380c7` |
| `offer_service.py` | `a4f691dec596e2d688e17148be9a86c4f492d2c70a7cf8954884556d47ff5053` |
| `offer_routes.py` | `7f673cb0e336efff3d270ab79761115aed1bb2b09694e0aba9c5bd0e9867896f` |
| `offer-lifecycle-worker.py` | `bc27ac10d192eebd08c6ba3a284408f8ef06299f800f2b26971ccfc08ead46de` |
| `action_registry.py` | `75274646eb81a304ebaf9e8325c9cd462359d55abe3024fc0dd939bf3557b774` |
| `app.py` | `bd1c94eeb43e976e181ed63426dd6ca5558d310b360ba0946370834118f6ac8b` |
| `OfferPanel.tsx` | `5a9db2a5019b4c71b3b9f04cd4196c72db70ea7e992e74872decddec41b14124` |
| `offers-api.ts` | `e6f9d5196fd92b334cef73d94b47a08ec8dc3d977401778c0443e1ff51085ba8` |
| `App.tsx` | `d86f0c11a53a22a1af908678325f06bb1a9935650b17b52523b77ad080d2c201` |

Artifact SHA covers those sources + staging matrix/worker units + built dashboard `dist/`.

---

## Schema / config delta applied on staging

### Schema (idempotent via `ensure_schema` / `offer_service.ensure_schema`)

- Governance columns on `employment_offers`: country, legal entity, document language, template id/version/approval ref, policy version, signatory, configuration effective date.
- Status `CHECK` for canonical offer statuses.
- Unique partial index `employment_offers_accepted_app_uq` — at most one `accepted` offer per `(company_code, app_key)`.
- Append-only triggers on `employment_offer_versions` / `employment_offer_events`.
- Durable `employment_offer_delivery_operations` table (send/resend claim before provider).

### Staging-found data remediation (required for index)

Staging already had **two** `accepted` offers for `WATHEFNI` / `96597485758-WATHEFNI-HR`. The older row (`0f30c47e-…`) was withdrawn with a staging remediation event so the unique index could apply. Newest accepted row retained. This is a real pre-existing defect the new constraint correctly rejected.

### Config / workers

- Staging-only `WATHEFNI_OFFER_TOKEN_SECRET` via `/root/.openclaw/secrets/wathefni-offer-token.staging.env` and `wathefni-orchestrator-staging.service.d/offer-token.conf`.
- Installed and enabled `wathefni-offer-lifecycle-staging.service` + `.timer` (expiry worker, dry_run).
- Delivery remains `dry_run`.

---

## Deployed files (staging only)

Backend → `/opt/wathefni/staging/orchestrator/`:

- `offer_lifecycle.py`, `offer_service.py`, `offer_routes.py`, `offer-lifecycle-worker.py`
- `action_registry.py`, `app.py`
- `test_offers_hiring_local_remediation.py`, `smoke-test-offer-lifecycle.py`, `smoke-test-offer-hire-override.py`
- `ops/offers-hiring-staging-matrix.py`
- `ops/wathefni-offer-lifecycle-staging.service`, `ops/wathefni-offer-lifecycle-staging.timer`
- `ops/deploy.sh` (wires offers matrix + worker for future full staging deploys)

Dashboard → `/opt/wathefni/staging/dashboard-dist/` (built dist including OfferPanel confirmations / governance fields).

**Production orchestrator and production dashboard were not modified.**  
Production `app.py` remains `ba3f4a4a…`; production `offer_service.py` remains `9686a108…` (pre-remediation).

---

## Offers/Hiring staging matrix — full gate list

Evidence: `ops/offers/offers-hiring-staging-matrix-20260724T224749Z.json`  
**38/38 PASS**, zero residue after cleanup.

| Gate | Result |
|---|---|
| schema_governance_columns | PASS (9 GCC/Kuwait fields) |
| schema_accepted_unique_index | PASS |
| schema_append_only_triggers | PASS |
| schema_delivery_operations | PASS |
| gcc_fields_on_draft | PASS (KW / K.S.C.C. / template 2026.7 / KWD) |
| compensation_redacted_without_permission | PASS |
| pdf_denied_without_compensation_read | PASS |
| english_generated_pdf_readable | PASS |
| arabic_generated_path_rejected | PASS |
| arabic_uploaded_pdf_authority | PASS (confirmed upload bytes retained) |
| concurrent_send_one_provider_message | PASS (1 provider call) |
| durable_one_send_operation | PASS (1 op / 1 delivery) |
| public_preview_usable_after_send | PASS |
| raw_token_never_persisted | PASS |
| api_response_has_no_raw_token | PASS |
| resend_revokes_old_token | PASS |
| canonical_expiry_idempotent | PASS |
| stale_link_no_compensation | PASS |
| replacement_draft_after_expiry | PASS |
| known_provider_failure_retry_same_op | PASS |
| unknown_outcome_manual_review_no_autoresend | PASS |
| public_page_escapes_and_csp | PASS |
| one_accepted_offer_per_application | PASS |
| append_only_versions_and_events | PASS |
| no_legacy_direct_hire_bypass | PASS |
| prepare_hire_operation | PASS |
| accepted_offer_hire_gate_allows | PASS |
| hire_confirmation_minted | PASS |
| atomic_hire_one_employee_no_half_hire | PASS |
| hire_idempotent_no_second_employee | PASS |
| override_requires_explicit_confirm | PASS |
| override_audit_pending | PASS |
| override_confirmation_minted | PASS |
| override_final_outcome_completed | PASS |
| tenant_isolation_peer_has_no_primary_offers | PASS |
| expiry_worker_pass | PASS |
| dashboard_confirmations_present | PASS |
| cleanup_zero_residue | PASS |

### Privacy / expiry / send / resend proof

- Viewer/`prehire.read` alone cannot see salary, terms, wording, or PDF.
- Concurrent identical idempotency key → one DB operation, one provider message.
- Known provider failure → same operation retries; unknown post-provider DB failure → `manual_review`, no automatic second provider send.
- Resend requires a new idempotency key, revokes prior tokens, and creates a replacement delivery operation.
- Expiry moves `sent → expired`, revokes tokens, and stale public links do not disclose compensation.
- Raw response tokens are never stored; API responses do not return `raw_token`.

### Hire atomicity proof

- Accepted-offer path: gate allows without override → mint confirmation → `execute_hire_operation` → application `hired`, exactly one employee, hire operation `completed`.
- Replay does not create a second employee.
- Override path: confirm required; audit pending → hire executes → audit `execution_status=completed` with operation id + employee key.
- Source scan: no legacy direct `hired` bypass in `app.py`; `hire_operations` remains sole employee-creation authority.

### Arabic document proof

- Generated Arabic path rejected at approval (`arabic_upload_required`).
- Confirmed uploaded Arabic PDF becomes versioned authority; stored bytes match upload SHA `9fdee9d52c360801c6b3c85bd081edfb459b1e38e8dc4f15a43a510d612ff39c`.

### Cleanup proof

Post-matrix residue for `OFFERSTG` / `OFFERISO`:

| Table / entity | Count |
|---|---|
| offers / versions / events / tokens / deliveries / send ops | 0 |
| hire overrides / hire ops / employees / applications / companies | 0 |
| PDF files removed | 5 |

---

## Frozen-module regressions

| Suite | Result |
|---|---|
| Offer lifecycle smoke | **PASS** |
| Offer hire-override smoke | **PASS** |
| Staging smoke | **PASS** (`ALL STAGING SMOKE CHECKS PASSED`) — includes tenant isolation, dashboard/mobile-relevant HTTP, dry-run delivery, entitlement |
| Candidates C3 schema | **18/18** |
| Candidates C3 matrix | **49/49** |
| Ranking R0–R3 | **57/57** |
| Ranking presentation | **213/213** |
| Reports V1 | **80/80** |
| Assistant A0–A3 | **79/79** |
| Assessments Tenant ON/OFF | **35/35** (includes mobile assessments omission when off) |
| Interviews matrix | **45/45** |
| OfferPanel unit (local build) | **4/4** |
| Health `:8011/health` | **ok** / environment binding match |
| Offer expiry timer | **active** |
| Document reconcile timer | **active** |
| Public-route guard (edge) | **PASS** (API JSON, not SPA HTML; dashboard shell `#root`) |
| Production untouched | **PASS** (`app.py` `ba3f4a4a…`, `offer_service.py` `9686a108…`, prod health 200) |

---

## Residuals

1. **Pre-existing duplicate accepted offer on staging `WATHEFNI`** — older duplicate withdrawn to install `employment_offers_accepted_app_uq`. Production must be inspected for the same class before cutover; do not assume production is clean.
2. **No supersede operation** — second accept remains rejected (`accepted_offer_exists`). Intentional.
3. **Kuwait/GCC country-pack gaps remain deferred** — employee/onboarding still do not copy full offer governance fields into the employee record; documented in local remediation, not expanded here.
4. **Legacy `offer1-*-proof.py` harnesses** still expect historical `raw_token` in API responses; production APIs must not restore raw tokens. Matrix uses HMAC-derived in-memory token reconstruction for proofs.
5. **Full live WhatsApp send** was intentionally kept dry_run for this qualification pass.

---

## Owner UX steps (before production)

1. Review this green report and the matrix evidence JSON.
2. Spot-check staging dashboard offer panel: redacted viewer vs owner compensation, governance fields, confirm dialogs, Arabic upload path, resend.
3. Confirm staging expiry timer remains enabled and dry_run delivery stays on until live canary.
4. Before production: audit production for duplicate `accepted` offers; remediate or plan a gated migration for `employment_offers_accepted_app_uq`.
5. Only after explicit owner approval: promote the **exact** artifact `71dd4d10d51605968436885c5867a79ace73452e33849d64441ef23801f0ebf5` via the production gate (do not ship a different tree).

---

## Final status

Offers/Hiring is **staging-green** on isolated staging with zero synthetic residue and frozen-module regressions green.

**Production was not touched. Stop here for owner approval before production.**
