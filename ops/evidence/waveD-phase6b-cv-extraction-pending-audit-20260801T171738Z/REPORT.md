# Wave D6B — Audit only: pending `cv_extraction` classification

**Stamp:** `20260801T171738Z`  
**Mode:** Read-only audit. No replay, delete, migrate, deploy, external enablement, or post-hiring.  
**Host:** `root@76.13.63.68` / DB `wathefni`

---

## Headline

The “32 pending `cv_extraction` jobs” from the D6A deploy close are **not legacy pipeline debt** and **not organic production stuck work**.

They are **current durable-ingress jobs** created by **Wave D6A production synthetic gates** (`wave_d6a_prod_proof`), now mostly still **retrying** after expected quality/OCR failures on thin proof PDFs.

| Bucket | Count now | Notes |
|---|---:|---|
| Open (`retrying`) | **28** | All `d6a_prod_synthetic` |
| Same window `completed` | 5 | D6A gate jobs that finished extract |
| Earlier today `dead_letter` (D6 held-admit seed) | 3 | Also synthetic `email_inbound`; `ocr_required_mistral_disabled` |
| Legacy old CV pipeline (open set) | **0** | — |
| Genuine customer stuck (open set) | **0** | — |

**Reconcile 32 → 28:** snapshot at D6A close counted open jobs; some have since completed or advanced attempts. All remaining open jobs still classify as D6A synthetics.

---

## Exact classification (all open jobs)

**Class for every open job (28/28):**

1. **Not** legacy old CV pipeline  
2. **Yes** current durable-ingress schema (`source_channel=email_inbound`, `intake_document_id`, `candidate_document_id`, `activation_epoch=1`, `subject_type=candidate_document`)  
3. **Yes** test/synthetic leftovers (`subject=wave_d6a_prod_proof CV`, `provider_message_id` like `d6a-prod-*`, intake label `wave_d6a_prod_proof general`)  
4. **Not** genuinely stuck production customer traffic  

**Tenant:** `WATHEFNI` only.

**Worker expected to process?** **Yes.**  
`durable-email-ingress-worker.py --limit 1` claims all `JOB_TYPES`, including `cv_extraction`. Jobs are being attempted (attempts 1–3 / max 5), not ignored.

### Field summary (open set)

| Field | Value |
|---|---|
| created_at | `2026-08-01 17:01:22Z` → `17:05:03Z` |
| updated_at | continuing through audit (~`17:18Z`) as retries fire |
| payload markers | `source_channel=email_inbound`, `app_key`, `intake_document_id`, `candidate_document_id` |
| metadata | `activation_epoch=1` |
| Held / import app exists | **28/28** (26 `import_archived`, 2 still `needs_role`) |
| Errors | `cv_extraction_failed` **17** (`low_quality_text` / `ocr_required_mistral_disabled`); `intake_document_not_clean` **11** |

Full per-job dump: `verify/jobs-enriched.txt`, `verify/open-cv-extraction-catalog.json`

---

## Is any a real current-pipeline blocker?

**No — not for live customer traffic.**

- Every open job is a D6A proof leftover with a Held/import application already materialized (D6A success path).  
- Failures match thin/synthetic PDF reality (quality/OCR), not a missing worker registration.  
- The separate D6B product question (“canonical extraction promotes governed CV” in smoke) remains a **quality/promotion behavior** issue for extractable CVs — it is **not** evidenced by these 28 as orphaned legacy work.

Caveat for later D6B engineering (still audit-only here): several jobs report `intake_document_not_clean` while joined `intake_documents.safety_state=clean` — worth investigating as a **retry noise / authority-check mismatch** on held-review docs, but still only on synthetics today.

---

## Safe archive / migrate / ignore

| Set | Action recommendation |
|---|---|
| 28 open `d6a_prod_synthetic` retrying jobs | **Safe to cancel / dead-letter / ignore** after explicit ops approval (Held apps already exist; proofs archived). Do **not** migrate. |
| 3 `dead_letter` from D6 held-admit seed (16:22Z) | **Safe to ignore** (already terminal; synthetic). |
| 5 completed in D6A window | **Ignore** (done). |
| Any future non-synthetic `email_inbound` `cv_extraction` with customer subjects | **Do not archive** — treat as real pipeline. |

No delete/replay performed in this audit.

---

## Recommended next action

1. **Ops (separate change window):** cancel or terminal-close the 28 `wave_d6a_prod_proof` `cv_extraction` retries so they stop consuming the `--limit 1` worker.  
2. **D6B product investigation (next wave):** reproduce `cv_extraction` promotion with a **rich, extractable** production-like CV (not thin synthetic), and separately inspect `intake_document_not_clean` false retries when `safety_state=clean`.  
3. Keep external tenants disabled; no post-hiring.

---

## Evidence path

`ops/evidence/waveD-phase6b-cv-extraction-pending-audit-20260801T171738Z/`

Key files:
- `assess/classification-summary.json`
- `verify/jobs-enriched.txt`
- `verify/open-cv-extraction-catalog.json`
- `verify/aggregate-by-class.txt`
- `verify/today-window-and-deadletter.txt`
- `verify/worker-expects-cv-extraction.txt`
