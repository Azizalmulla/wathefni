# Wave D6B — cv_extraction repair / qualification

**Stamp:** `20260801T172536Z`  
**Scope:** Local implementation + prod cleanup of 28 D6A synthetic jobs only  
**Deploy:** Not deployed (local-first; no external tenants; no post-hiring)

## Verdict: **LOCAL PASS** (deploy pending)

---

## 1. Cleanup proof (28 synthetic D6A jobs)

| Field | Value |
| --- | --- |
| Classified set | 28 `cv_extraction` jobs, all `wave_d6a_prod_proof` / `d6a-prod-*` |
| Customer / legacy | **0** |
| Action | Cancelled only; metadata `d6b_cancelled` + reason `synthetic_wave_d6a_prod_proof_leftover` |
| Cancelled count | **28** |
| Remaining open after cancel | **1** (out of scope — `wave_d6_ga_proof` / `d6ga-*-kill`, not in the 28) |

Evidence:
- `before/synthetic-28-pre-cancel.json` — pre-cancel classification
- `cleanup/cancel-proof.json` — 28 cancelled job IDs + statuses
- `cleanup/cancel-synthetic-28.sql.log` — cancel SQL transcript

---

## 2. Root cause: `intake_document_not_clean` vs `safety_state=clean`

**Bug:** The `cv_extraction` job handler treated **failed ownership binding** (Held / conflict / non-accepted identity) as `intake_document_not_clean`, even when the intake document was already scan-clean.

**Why it mattered:** D6A materializes Held review apps for conflict / weak CVs **without** ownership binding. Post-Held extraction then failed the binding gate and was mislabeled as “not clean”, then retried indefinitely.

A second gate in `process_candidate_cv_document` returned `document_current_authority_not_proven` for the same Held/conflict cases, so even after splitting error codes in the job handler, extraction still could not complete.

---

## 3. Exact fix (local)

### A. Accurate authorization errors + Held scan-clean extraction
- Split clean-scan vs binding failures:
  - `intake_document_not_clean` — only when `safety_state != clean`
  - `durable_clean_scan_authority_missing` — clean row but no durable clean scan authority
  - `identity_binding_not_authorized` — accepted-path binding failed
- New helper `held_review_extraction_authorized()` in `inbound_cv_authority.py`
- Held / conflict / possible_match (and held-materialized metadata) may extract under `authorization_mode=held_identity_review_scan_clean` when scan-clean
- Same allowance applied inside `process_candidate_cv_document` (fixes `document_current_authority_not_proven` for Held)

### B. Soft-complete terminal extraction failures
Quality/OCR/`file_not_found` errors soft-complete as `extraction_soft_failed` so jobs leave `pending`/`retrying` instead of retrying forever. Held review item + warnings remain (D6A preserved).

### C. Semantic index without embedding provider
`upsert_application_semantic_document` defaults `provider=none` / `model=unembedded` when no embedding API (avoids NOT NULL on `semantic_documents.provider`).

### D. Identity name fill for conflict detection
When text parse returns email but drops name/phone, soft scrape + filename fallback still fill `full_name` so `conflicting_cv_name` can fire (D6A conflict semantics).

Files:
- `wathefni-orchestrator/app.py`
- `wathefni-orchestrator/inbound_cv_authority.py`
- `wathefni-orchestrator/smoke-test-inbound-cv-extraction-d6b.py`

SHA256: `artifacts/local-sha256.txt`

---

## 4. Rich-CV promotion evidence (local)

Smoke: `smoke-test-inbound-cv-extraction-d6b.py` → `verify/local-d6b-matrix.json`

| Check | Result |
| --- | --- |
| Rich PDF → Held (`needs_role`) | PASS |
| `cv_extraction` completes (`ok`, not soft-fail) | PASS |
| `authorization_mode` | `accepted_identity_binding` |
| Promoted email on candidate | PASS (`d6b.rich.*@example.com`) |
| Doc / app count | 1 / 1 (no duplicates) |

---

## 5. Retry / idempotency tests

| Check | Result |
| --- | --- |
| Second extraction drain processes 0 | PASS |
| Job count unchanged after re-drain | PASS |
| Duplicate Message-ID | PASS (no new inbound) |
| Conflict Held extraction | PASS — `held_identity_review_scan_clean`, completed, **not** `intake_document_not_clean` |
| Opaque weak CV | PASS — Held warning preserved; `extraction_soft_failed` / `low_quality_text`; attempts ≤ 2 |
| Open pending/retrying for company proof set | **0** |

---

## 6. Remaining blockers

1. **Not deployed to prod** — local PASS only; WATHEFNI canary deploy not requested.
2. **1 leftover open prod job** outside the cancelled 28: D6 GA synthetic (`wave_d6_ga_proof`). Cancel separately if desired.
3. **DOCX not separately smoked in D6B matrix** — rich path proven with PDF; DOCX shares the same job + authority gates but needs an explicit DOCX fixture before claiming DOCX promotion PASS.
4. **Prod Held apps from cancelled D6A jobs** still exist as Held review items (jobs cancelled only; intentional — no customer data touch). They will not re-extract until code is deployed + optional requeue.
5. Standing posture unchanged: mailbox sync off, no external tenants, no post-hiring.

---

## 7. PASS / FAIL

| Gate | Status |
| --- | --- |
| Cancel 28 D6A synthetic jobs only | **PASS** |
| Root-cause + fix `not_clean` mismatch | **PASS** (local) |
| Rich CV extraction + Held promotion | **PASS** (local PDF) |
| Idempotency / no duplicates | **PASS** (local) |
| No indefinite pending extraction | **PASS** (local) |
| Preserve D6A weak-CV Held + warnings | **PASS** (local) |
| Prod deploy / live re-proof | **NOT RUN** |

### Overall: **LOCAL PASS** — ready for controlled WATHEFNI deploy when requested.
