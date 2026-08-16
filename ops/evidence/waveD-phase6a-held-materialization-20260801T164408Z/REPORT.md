# Wave D6A — Durable → Held materialization repair

**Stamp:** `20260801T164408Z`  
**Scope:** Local-only repair of the D6 gate failure `durable_to_held_materialization_synthetic`  
**Constraints honored:** no external tenants enabled; no post-hiring; no production deploy

---

## Verdict

**Local repair: PASS — ready to deploy behind existing WATHEFNI-only canary**

| Claim | Result |
| --- | --- |
| Durable inbound CV always yields Held app **or** auditable blocked/review | **PASS** |
| Short/synthetic CVs with contact keys materialize Held (accepted path) | **PASS** (3×3 deterministic) |
| Opaque / low-quality CVs materialize Held with terminal reason + warning | **PASS** (`held_intake_materialization`) |
| Identity conflict materializes **separate** Held app (no supersede) | **PASS** |
| Duplicate MessageID remains idempotent | **PASS** |
| Dedup / tenant isolation / quarantine / quotas / explicit admit preserved | **PASS** (no auto-admit on held-review path) |
| External tenants / post-hiring | **Not started** (as required) |

**Production-readiness:** code is ready for a **WATHEFNI-only** deploy + re-run of the D6 synthetic gate. External-tenant GA remains **NO-GO** until that prod re-gate passes. Premium mailbox sync stays dark.

---

## Root cause

Bridge audited:

```
process_postmark_inbound
  → intake_validation → file_safety_scan
  → cv_identity_resolution
      ├─ accepted → accepted_intake_preparation → register_imported_cv (Held)
      └─ blocked  → (previously STOPPED) → job completed with no Held row
```

**Primary cause (D6 finding):**  
Synthetic / low-quality PDFs failed `cv_text_quality_ok` (and often OCR when Mistral is disabled). `cv_identity_resolution` recorded `possible_match` / extraction failure, set submission `identity_review_required`, **did not enqueue any Held materialization**, and still marked the identity job **completed**. From Held Intake’s POV this was silent completion.

**Not** the main cause: async wait-window alone, queue/retry storms, or Held admit UX (admit worked once an application existed).

**Secondary causes found during repair:**

1. Soft contact was never scraped from PDF bytes when `pdftotext`/OCR produced empty text, so short CVs that visibly contain `Email …` still failed closed.
2. Held-review `import_surrogate_phone` preferred **email over checksum**, so a conflict Held app collapsed onto the legitimate email-keyed application (same `app_key`).

---

## Exact fix

| Change | Where |
| --- | --- |
| New worker job `held_intake_materialization` | `durable_email_ingress.py` `JOB_TYPES` + worker dispatch in `app.py` |
| Non-accepted identity outcomes **always enqueue** Held materialization (idempotent re-enqueue if resolution exists without `app_key`) | `_resolve_clean_inbound_document_identity` |
| Soft contact scrape from CV bytes when extract/OCR is empty or low-quality | `_soft_contact_from_cv_bytes` → contact-only resolve path |
| Held-review registration: surrogate phone **checksum-scoped**; never auto-admit; `identity_review_warning` + `identity_terminal_reason` on application | `register_imported_cv` / `_materialize_held_intake_from_blocked_identity` |
| Held Intake API surfaces warning + terminal reason + identity outcome | Held intake list payload |
| Conflict smoke expects separate warned Held app | `smoke-test-inbound-email.py` + new D6A smoke |

Invariant now enforced: a successful durable CV cannot finish as a completed identity job with **neither** a Held `app_key` **nor** a queued/auditable held-review materialization.

---

## Timing evidence (local worker stages)

Sequential drain: `intake_validation` → `file_safety_scan` → `cv_identity_resolution` → `accepted_intake_preparation` → `held_intake_materialization`.

Representative short-PDF run (matrix run 1):

| Stage | processed | elapsed_ms |
| --- | ---: | ---: |
| intake_validation | 1 | ~100 |
| file_safety_scan | 1 | ~14 |
| cv_identity_resolution | 1 | ~70 |
| accepted_intake_preparation | 1 | ~30 |
| held_intake_materialization | 0 | ~2 |

Opaque / no-contact path (matrix ×3): `held_intake_materialization` **processed=1**, **~16–17 ms**, terminal `low_quality_text`, submission `held_identity_review`, `identity_review_warning=true`.

Conflict path: separate `app_key` from rich candidate; `warned=true`; outcome `conflict`.

Duplicates: same Postmark `MessageID` → durable duplicate / same `inbound_id` (asserted every short run).

---

## Tests

**Primary:** `wathefni-orchestrator/smoke-test-inbound-held-materialization-d6a.py`

Proves across **3 full matrix repetitions**:

1. Short synthetic PDF ×3 → Held `needs_role` (contact-only → accepted preparation)
2. MessageID replay idempotent
3. Rich CV → `new_candidate` Held without warning
4. Conflict (same email, disjoint name) → separate warned Held app
5. Opaque CV (no contact) → Held via `held_intake_materialization` with terminal reason
6. Cleanup archives proof apps / sterilizes surrogate identity pollution

**Artifacts:** `verify/local-d6a-matrix-run{1,2,3}.json`, `verify/local-d6a-summary.json`, `artifacts/smoke-test-inbound-held-materialization-d6a.py`

**Note:** `smoke-test-inbound-email.py` still expects post-Held `cv_extraction` promotion; local host lacks `pdftotext`, so that later stage was not used as the D6A gate. Materialization coverage is in the D6A smoke (including conflict held worker).

---

## Production-readiness

| Item | Status |
| --- | --- |
| Local D6A gate (deterministic ×3) | **PASS** |
| Silent completed-identity-without-Held | **Fixed** |
| Conflict does not supersede legitimate CV | **Fixed** |
| Explicit admit still required | **Preserved** (`auto_admit=False` on held-review) |
| External tenants | **Remain disabled** |
| Post-hiring | **Not started** |
| Prod deploy of this patch | **Not done** (local-first per request) |
| Re-run D6 synthetic gate on prod after deploy | **Required** before claiming full durable→Held GA |

**Recommendation:** Deploy D6A to production under current WATHEFNI-only allowlist, re-run `durable_to_held_materialization_synthetic`, then keep external-tenant GA gated on that result.

---

## Evidence path

`ops/evidence/waveD-phase6a-held-materialization-20260801T164408Z/`
