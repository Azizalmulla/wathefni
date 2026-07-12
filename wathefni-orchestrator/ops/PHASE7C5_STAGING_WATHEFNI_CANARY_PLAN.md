# Phase 7C.5 — Staging WATHEFNI canary apply plan (plan only)

**Status:** Executed on staging — W1 `civil_id` canary for `emp_2c08123fca34` applied once.  
**Prerequisites:** 7C.4 throwaway apply verifier green · 7C staging audit baseline for `WATHEFNI`.  
**Code/report:** `ops/staging-phase7c5-wathefni-canary.py`, `ops/reports/phase7c5-wathefni-canary-report.json`

**Target:** staging database only · company `WATHEFNI` · **one** canary write.  
**Not in scope:** production apply · broad staging reconcile · employee app · channel accounts · upload expansion.

**Keep OFF:**

- `WATHEFNI_EMPLOYEE_APP`
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS`

---

## Goal

Prove gated apply against **real staging `WATHEFNI` data** with the smallest safe mutation:

1. Dry-run first  
2. Pick exactly one drift from the known 6  
3. Apply one write under canary caps  
4. Verify before/after, re-dry-run, no collateral changes, dashboard health  
5. Stop  

Production canary remains a **separate** later gate (7C.6+).

---

## Gate change required for 7C.5 (when coding/run is approved)

Phase 7C.4 hard-refuses apply on `WATHEFNI`. For 7C.5 only, unlock staging `WATHEFNI` apply when **all** of the following hold:

```text
mode=apply
AND company=WATHEFNI
AND staging DSN (wathefni_staging)
AND --allow-staging-wathefni-canary
AND WATHEFNI_RECONCILE_APPLY=1
AND all 7C.3/7C.4 confirmations + canary caps
AND --max-writes 1
```

Still refuse:

- production DSN  
- `--allow-production-dsn`  
- company-wide apply without canary caps  
- `ALL`  
- more than one write  

This flag must **not** appear in systemd unit drop-ins.

---

## 1. Run dry-run on staging `WATHEFNI`

```bash
WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  python3 ops/staging-phase7c4-reconcile-docs.py \
    --company WATHEFNI \
    --mode dry-run \
    --jsonl-out /tmp/p7c5-wathefni-plan.jsonl \
    --summary-out /tmp/p7c5-wathefni-summary.json
```

Also re-run the Phase 7C audit for a fresh mismatch snapshot:

```bash
... ops/staging-phase7c-compliance-docs-audit.py --company WATHEFNI \
  --json-out /tmp/p7c5-audit.json --md-out /tmp/p7c5-audit.md
```

Save both under `ops/reports/` (redacted) before any apply.

---

## 2. Select exactly one safe drift item

### Known staging `WATHEFNI` drift (from closed 7C audit)

| # | Class | Sample (redacted) | Type | Candidate action |
|---|-------|-------------------|------|------------------|
| 1 | `employee_doc_without_received_item` | `emp_2c08123fca34` | `civil_id` | **W1** mark onboarding received |
| 2 | `employee_doc_without_received_item` | `emp_2c08123fca34` | `bank_details` | W1 |
| 3 | `compliance_without_employee_doc` | `emp_2c08123fca34` | `medical` | W2 only if file exists |
| 4 | `compliance_without_employee_doc` | `emp_2c08123fca34` | `passport` | W2 only if file exists |
| 5 | `expiry_status_conflicts` | `emp_2c08123fca34` | `civil_id` | W3 sync newer expiry |
| 6 | `null_expiry_on_received_compliance` | `emp_2c08123fca34` | `medical` | W4 fill from ED if ED has date |

### Recommended first canary (default)

**Pick #1 — W1 `civil_id` for `emp_2c08123fca34`.**

Why safest:

- Checklist-only `UPDATE` on `onboarding_items.status`  
- Does not invent files, compliance rows, or expiry  
- ED already proves receipt  
- Easy before/after (`pending` → `received`)  
- Easy re-dry-run proof for that sample_id + document type  

### Explicitly defer for later canaries

| Item | Why defer |
|------|-----------|
| #3 / #4 W2 | Needs confirmed matching `file_registry` row; risk of inventing ED if file link is wrong |
| #5 W3 | Touches expiry authority; do after W1 success |
| #6 W4 | Depends on ED expiry presence; couple with medical orphan review |
| #2 `bank_details` W1 | Also safe, but second canary — do not combine with #1 |

Fresh dry-run must still show a `decision=plan` / `mark_onboarding_received` for that canary before apply. If drift already healed, **stop** and pick nothing.

---

## 3. Canary limits (mandatory)

```text
--company WATHEFNI
--confirm-company WATHEFNI
--employee-sample-id emp_2c08123fca34   # or refreshed sample_id from dry-run
--document-type civil_id
--max-writes 1
--allow-staging-wathefni-canary
```

Plus existing gates: `WATHEFNI_RECONCILE_APPLY=1`, `--i-understand-writes`, `--confirm-apply-token`, `--apply-token-expires-at`, `--expect-plan-hash`.

Abort if filtered plan size ≠ 1.

---

## 4. Capture before snapshot

Before apply, record:

| Snapshot | Contents |
|----------|----------|
| Target row | `onboarding_items` for that employee + `civil_id` (`status`, `updated_at`) |
| Canary plan | plan event JSON (redacted) + `plan_hash` / token / expiry |
| Store counts | company-scoped counts for OI / ED / compliance / file_registry |
| Hash fingerprint | optional: `md5(employee_key||item_id||status)` for all other WATHEFNI onboarding rows (or count + checksum aggregate) |
| Audit totals | 7C mismatch_totals |
| Health | staging orchestrator `/health` (or equivalent) 200 |

No PII in saved reports (use `sample_id` only).

---

## 5. Apply once

Single command shape (when approved):

```bash
WATHEFNI_RECONCILE_APPLY=1 \
WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  python3 ops/staging-phase7c4-reconcile-docs.py \
    --company WATHEFNI \
    --mode apply \
    --confirm-company WATHEFNI \
    --i-understand-writes \
    --allow-staging-wathefni-canary \
    --confirm-apply-token "$TOKEN" \
    --apply-token-expires-at "$EXPIRES" \
    --expect-plan-hash "$HASH" \
    --employee-sample-id emp_… \
    --document-type civil_id \
    --max-writes 1 \
    --apply-jsonl-out /tmp/p7c5-apply.jsonl \
    --summary-out /tmp/p7c5-apply-summary.json
```

Expect: `applied=1`, `failed=0`, `skipped=0`.

---

## 6. Capture after snapshot

| Check | Expect |
|-------|--------|
| Target OI status | `received` |
| Apply JSONL | `decision=applied`, matching `plan_hash`, `rowcount=1`, redacted `sample_id` |
| Target `updated_at` | advanced |
| Store counts | ED / compliance / file_registry unchanged; OI count unchanged |

---

## 7. Re-dry-run — selected drift resolved

```bash
... dry-run --company WATHEFNI \
  --employee-sample-id emp_… --document-type civil_id
```

Expect: `planned_writes=0` for that canary scope (no remaining W1 for `civil_id`).

Company-wide dry-run / audit may still show the **other** 5 drifts — that is expected. Do not “fix” them in 7C.5.

---

## 8. Confirm no other rows changed

| Check | Method |
|-------|--------|
| Other onboarding statuses | Aggregate checksum / count of non-target OI rows equals before |
| ED / compliance / files | Row counts + optional checksum of `(employee_key, document_type, expiry, status)` unchanged |
| Other companies | Counts for `company_code <> 'WATHEFNI'` unchanged |
| Apply summary | `applied=1` only |

If collateral change detected → stop; compensate W1 by restoring `before.status` from apply audit (no DELETE).

---

## 9. Confirm dashboard still loads

On staging:

1. Health endpoint 200  
2. Dashboard bootstrap / login path for staging WATHEFNI still 200  
3. Spot-check employee profile / documents hub load for the canary employee (no PII in logs)

No requirement to change UI. Fail 7C.5 if dashboard/bootstrap regresses.

---

## 10. Confirm no production writes

| Proof | Expect |
|-------|--------|
| DSN used | staging `wathefni_staging` only |
| Production CLI refuse | still refuses apply without staging canary path; production DSN still refused |
| Prod DB spot check | optional read-only count fingerprint for WATHEFNI docs unchanged (operator) |
| Flags | employee app + channel accounts OFF on staging and prod |

---

## 11. Production canary remains a separate approval gate

Accepting/executing 7C.5 does **not** authorize production apply.

Production requires a later phase (suggested **7C.6**) with:

- Written approval naming company, sample_id, document_type, window  
- Production dry-run review  
- Same one-employee / one-type / `--max-writes 1` shape  
- Explicit production unlock distinct from `--allow-staging-wathefni-canary`  

---

## Execution checklist (when run approved)

1. [ ] 7C.4 still green on throwaway (optional reconfirm)  
2. [ ] Add `--allow-staging-wathefni-canary` gate (tiny CLI change)  
3. [ ] Staging dry-run + audit saved  
4. [ ] Confirm recommended W1 `civil_id` plan still present  
5. [ ] Before snapshots  
6. [ ] Apply once  
7. [ ] After snapshots + apply JSONL  
8. [ ] Re-dry-run canary scope = 0  
9. [ ] Collateral unchanged  
10. [ ] Dashboard/health OK  
11. [ ] Flags OFF; no prod writes  
12. [ ] File report + commit hash; **stop**  

---

## Explicit non-goals

- Applying more than one of the 6 drifts  
- Staging company-wide reconcile  
- Production dry-run or apply  
- Enabling employee app / channel accounts  
- Upload path changes  
- Deletes / compliance inserts / alias merges  

**This document is plan only. It does not authorize the staging WATHEFNI canary run or any production reconciliation.**
