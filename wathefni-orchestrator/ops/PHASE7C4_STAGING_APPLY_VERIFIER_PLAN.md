# Phase 7C.4 — Staging apply-mode verifier implementation plan (plan only)

**Status:** Implemented — staging throwaway apply verifier green (`P7C4STG01`).  
**Prerequisites:** 7C.2 dry-run closed · 7C.3 apply-mode plan accepted.  
**Code:** `ops/staging-phase7c4-reconcile-docs.py`, `ops/staging-phase7c4-apply-verify.py`  

**Still forbidden in 7C.4:**

- Apply on production
- Apply on staging `WATHEFNI`
- `WATHEFNI_EMPLOYEE_APP=on`
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=on`
- Upload expansion / dual-write allowlist changes
- Fleet / `ALL` apply
- Deletes / compliance inserts / alias merges

Throwaway company for this phase: **`P7C4STG01`** (do not reuse live staging `WATHEFNI`).

---

## Goal

When coding is later approved, ship:

1. Guarded **apply mode** behind all 7C.3 gates (extending the 7C.2 dry-run CLI)
2. A **staging throwaway apply verifier** that exercises W1–W4 one-by-one under canary caps
3. Proof that blocked cases refuse with **zero writes**
4. Proof that production DSN apply remains impossible / refused in this phase

---

## 1. Implement apply mode behind all 7C.3 gates

### Deliverables (coding phase)

| Artifact | Role |
|----------|------|
| Extend `ops/staging-phase7c2-reconcile-docs-dryrun.py` **or** new `ops/staging-phase7c4-reconcile-docs.py` | Single CLI: dry-run (default) + guarded apply |
| `ops/staging-phase7c4-apply-verify.py` | Throwaway `P7C4STG01` harness |
| `ops/reports/phase7c4-*` | Redacted plan/apply JSONL + summaries from verifier runs |
| Update `ops/lib/doc_type_map.py` | Unchanged map; maybe shared helpers only |

Prefer **one CLI** that keeps dry-run default and adds apply, so plan-hash/token stay in-process.

### Unlock checklist (all required)

```text
mode=apply
AND WATHEFNI_RECONCILE_APPLY=1          # env gate; shell-only, not systemd
AND --company CODE                     # not ALL/*
AND --confirm-company CODE             # exact match
AND --i-understand-writes
AND --confirm-apply-token TOKEN        # from dry-run; TTL ≤ 30m; binds company+plan_hash
AND --employee-sample-id emp_…         # canary (required while --require-canary-caps default on)
AND --document-type TYPE               # canary
AND --max-writes 1                     # default 1 for 7C.4 verifier
AND staging DSN (wathefni_staging)     # refuse production-looking DSN; no --allow-production-dsn in 7C.4 verifier
```

### Dry-run additions needed for apply binding

Dry-run summary must emit:

| Field | Purpose |
|-------|---------|
| `plan_hash` | SHA-256 of canonical JSONL plan lines (`decision=plan` only, sorted) |
| `apply_token` | Short ephemeral token = HMAC/hash(`company|plan_hash|exp`) |
| `apply_token_expires_at` | ISO timestamp ≤ now+30m |

Apply must recompute `plan_hash` from the plan it will execute and refuse on mismatch (`wrong_plan_hash`).

### Apply execution rules

- Execute only `decision=plan` events whose `action` ∈ W1–W4
- Re-validate before-image; stale → abort (canary default `--on-stale abort`)
- Stop when `--max-writes` applied count reached
- Never DELETE; never INSERT `compliance_documents`; never alias-merge
- Write apply audit JSONL + summary (§5)

---

## 2. Apply only on staging throwaway data

| Constraint | 7C.4 rule |
|------------|-----------|
| Allowed company | `P7C4STG01` only in the verifier |
| Staging DSN | Required (`wathefni_staging` / staging env file) |
| Staging `WATHEFNI` | **Out of scope** — verifier must refuse if `--company WATHEFNI` |
| Production DSN | Refuse apply (and verifier must assert refuse) |
| Cleanup | Verifier deletes only rows it created under `P7C4STG01` |

Harness may use a read-write connection **only** for seed/cleanup/apply-under-test. Dry-run planning stays on a separate read-only connection where practical.

---

## 3. Canary shape: one employee + one document type + `--max-writes 1`

Every successful apply invocation in the verifier must pass:

```bash
--employee-sample-id emp_<hash> \
--document-type <type> \
--max-writes 1
```

Flow per W-action:

1. Seed **one** employee fixture for that action  
2. Dry-run filtered to that sample_id + document_type  
3. Capture `plan_hash` + `apply_token`  
4. Snapshot before-image  
5. Apply with caps  
6. Assert exactly **one** `decision=applied` (or zero if testing a block)  
7. After-image + re-dry-run  

Do not company-wide apply in 7C.4 even on throwaway (except optional final smoke that still loops canary caps per event — prefer strict one-at-a-time).

---

## 4. Verify W1–W4 one by one

Throwaway fixtures (separate employees):

| Case | Seed | Apply action | After expect |
|------|------|--------------|--------------|
| **W1** | ED received + OI `pending` for `civil_id` | `mark_onboarding_received` | OI `status=received` |
| **W2** | Compliance received + file; no ED for `medical` | `insert_employee_document_from_file` | ED row exists; file unchanged; no compliance delete |
| **W3** | ED expiry older than compliance for `passport` | `sync_expiry` on ED | ED expiry == newer winner |
| **W4** | Compliance `received` null expiry; ED has date for `education_cert` | `fill_compliance_expiry_from_ed` | Compliance expiry filled from ED |

Each case is its own dry-run→apply→verify cycle with `--max-writes 1`.

Also assert:

- Idempotent second apply on same scope → `applied=0` (empty plan or no matching plan events)
- No cross-talk between fixture employees

---

## 5. Verify audit JSONL

For each successful W apply, assert apply JSONL contains one line with:

| Field | Assert |
|-------|--------|
| `mode` | `apply` |
| `decision` | `applied` |
| `action` | expected W1–W4 action |
| `plan_event_id` | matches dry-run event_id |
| `plan_hash` | matches dry-run summary |
| `sample_id` / `document_type` or `item_id` | canary match |
| `before` / `after` | match snapshots |
| `rowcount` | `1` |
| `guards.no_delete` | `true` |
| `guards.alias_merge` | `false` |

Summary sidecar asserts: `applied=1`, `failed=0`, `max_writes=1`, `no_deletes=true`, canary fields set.

No phones/emails/raw employee keys/storage URLs in logs.

---

## 6. Verify before/after snapshot

Per W case the verifier records:

**Before apply**

- Target row column subset (status and/or expiry)
- Company-scoped store counts
- Dry-run `planned_writes` for canary scope (≥1)

**After apply**

- Target row matches plan `after`
- Store counts: W1/W3/W4 → ED/compliance/file counts unchanged; W2 → `employee_documents` +1 only
- Apply JSONL `before` equals pre-snapshot

Fail the case if SQL “succeeded” but snapshot mismatch.

---

## 7. Verify re-dry-run improvement

Immediately after each successful apply:

1. Re-run dry-run with **same** `--company` + `--employee-sample-id` + `--document-type`
2. Assert `planned_writes == 0` for that canary scope (no remaining plan for the fixed drift)
3. Optionally run 7C audit for `P7C4STG01` and assert the targeted drift class did not increase; tenant/orphan keys remain 0

---

## 8. Verify blocked cases (zero writes)

Each block test: seed known state → attempt apply (or dry-run+apply) → assert non-zero exit **and** row counts / target before-image unchanged.

| # | Block | How | Expect |
|---|-------|-----|--------|
| B1 | Missing env gate | Omit `WATHEFNI_RECONCILE_APPLY` (or set `0`) but pass all CLI confirms | Refuse; no writes |
| B2 | Wrong token | Valid plan; `--confirm-apply-token` garbage | Refuse; no writes |
| B3 | Wrong plan hash | Tamper plan JSONL or pass mismatched `--plan-hash` if exposed; token for different hash | Refuse; no writes |
| B4 | `ALL` | `--company ALL` | Refuse at parse/scope; no writes |
| B5 | max-writes exceeded | Seed ≥2 plan events same employee/type if possible, or two sequential types without raising cap; `--max-writes 1` with a plan that would need 2 | Apply at most 1; second not applied; or refuse if policy is abort-when-plan-exceeds-max (**prefer abort when filtered plan size > max-writes** for canary clarity) |
| B6 | Alias merge | Seed `residency` + `residency_iqama`; attempt apply that would merge | No merge plan executable; apply of merge action impossible; `needs_operator_map` only |
| B7 | Older/null overwrite | Craft apply payload or live state where candidate expiry is older/null than existing; ensure executor refuses | No expiry change; skip/fail logged with `expiry_older_than_existing` or `expiry_candidate_null` |

Additional required refuses in verifier:

| # | Block | Expect |
|---|-------|--------|
| B8 | Missing canary caps | Apply without sample_id or document_type while require-canary-caps on | Refuse |
| B9 | Confirm company mismatch | `--confirm-company` ≠ `--company` | Refuse |
| B10 | Staging `WATHEFNI` | `--company WATHEFNI` in 7C.4 verifier wrapper | Refuse (phase policy) |
| B11 | Production DSN | Point env at prod DSN with apply flags | Refuse |

---

## 9. Keep production writes disabled

| Control | 7C.4 stance |
|---------|-------------|
| Verifier DSN | Staging only; abort if not staging |
| `--allow-production-dsn` | Not used by verifier; if CLI supports it, verifier asserts apply still refuses without separate prod approval artifact (and 7C.4 does not run prod) |
| Production canary | **Not in 7C.4** |
| Code comment / summary flag | `production_apply_authorized: false` |

---

## 10. Keep employee app / channel accounts OFF

Verifier end assertion (same as 7C.2 case 13):

- Process / staging unit: `WATHEFNI_EMPLOYEE_APP` ≠ on  
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS` ≠ on  
- No app code changes to upload paths in this phase  

---

## Suggested verifier case matrix (coding acceptance)

| ID | Name | Type |
|----|------|------|
| A1 | W1 apply + audit + snapshot + re-dry-run | happy |
| A2 | W2 apply + audit + snapshot + re-dry-run | happy |
| A3 | W3 apply + audit + snapshot + re-dry-run | happy |
| A4 | W4 apply + audit + snapshot + re-dry-run | happy |
| A5 | Idempotent re-apply → 0 applied | happy |
| B1–B11 | Gate / policy refuses | block |
| F1 | Protected flags still OFF | posture |

Target: all green on staging throwaway; cleanup `P7C4STG01`.

---

## Implementation order (when coding approved)

1. Add `plan_hash` + `apply_token` (+ expiry) to dry-run summary/CLI output  
2. Add canary filter flags to dry-run and apply  
3. Implement guarded apply executor (W1–W4 only) with before-image check  
4. Apply JSONL + summary emitters  
5. Build `staging-phase7c4-apply-verify.py` for A1–A5 + B1–B11 + F1  
6. Run on staging; store redacted reports under `ops/reports/`  
7. **Stop.** Do not touch staging `WATHEFNI` or production without a new approval (7C.5+)

---

## Explicit non-goals for 7C.4

- Compensation mode automation (optional single W1 restore drill may be included if cheap; not required to close 7C.4)
- Staging `WATHEFNI` apply
- Production dry-run or apply
- Company-wide apply without canary caps
- Employee-app / channel-account / upload work

**This document authorizes planning the staging apply verifier only. It does not by itself authorize apply-mode coding, staging WATHEFNI writes, or production reconciliation.**
