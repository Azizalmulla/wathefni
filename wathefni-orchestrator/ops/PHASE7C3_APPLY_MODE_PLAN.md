# Phase 7C.3 — Controlled apply-mode readiness plan (plan only)

**Status:** Plan for review. **Do not implement apply writes** until this plan is accepted **and** a separate coding approval is given.  
**Prerequisites:** Phase 7C audit closed · 7C.1 write-path plan accepted · 7C.2 dry-run planner closed (`66e9499`).

**Keep OFF:**

- `WATHEFNI_EMPLOYEE_APP`
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS`

**Out of scope for 7C.3 plan / future apply v1:**

- Production writes without canary approval (§10)
- Fleet / `ALL`-company apply
- Deletes / destructive SQL
- Silent alias merges (`residency_iqama`↔`residency`, `medical_check`↔`medical`)
- Employee-app enablement
- Document upload expansion / dual-write allowlist changes
- OCR / template editor / onboarding seed activation

---

## Goal

Define how apply mode will be unlocked **safely** so that planned W1–W4 events from the 7C.2 dry-run planner can be executed under:

1. Explicit multi-flag confirmation
2. Company scope
3. Optional one-employee / one-document-type canary caps
4. Full applied-write audit JSONL
5. Before/after verification
6. Compensation (not destructive rollback) for mistakes

This document is **plan only**. Coding is a later gate.

---

## 1. How apply mode will be unlocked safely

Apply stays **hard-disabled** until 7C.3 implementation is approved. Unlock is layered:

| Layer | Mechanism |
|-------|-----------|
| A. Code gate | Replace 7C.2 hard `SystemExit` with a guarded apply path that still defaults to refuse |
| B. Env gate | Require `WATHEFNI_RECONCILE_APPLY=1` in the **operator shell only** (not a systemd long-lived service flag). Absent → refuse apply even if CLI flags present |
| C. CLI gate | Require **all** confirm flags in §2 |
| D. Scope gate | Company required; optional `--employee-sample-id` and/or `--document-type` canary caps (§4) |
| E. Plan binding | Apply only events from a **fresh dry-run** in the same process (or a reviewed `--plan-jsonl` that is re-validated against live DB before write) |
| F. DSN gate | Staging DSN default; production DSN requires `--allow-production-dsn` **and** §10 canary approval checklist checked by operator |

No cron, no dashboard button, no API endpoint in apply v1.

**Recommended unlock phrase (implementation later):**

```text
apply enabled only when:
  mode=apply
  AND env WATHEFNI_RECONCILE_APPLY=1
  AND --confirm-company matches --company
  AND --i-understand-writes
  AND --confirm-apply-token equals a short ephemeral token printed by the preceding dry-run
  AND (staging DSN OR (--allow-production-dsn AND explicit canary caps))
```

Dry-run remains the default when `--mode` is omitted.

---

## 2. Required confirmations

All of the following must be present for apply; any missing → refuse with no writes:

| Flag / input | Rule |
|--------------|------|
| `--company CODE` | Required; exact `company_code` |
| `--mode apply` | Explicit; never implied |
| `--confirm-company CODE` | Must equal `--company` (case-insensitive) |
| `--i-understand-writes` | Boolean acknowledgment |
| `WATHEFNI_RECONCILE_APPLY=1` | Process env for this invocation only |
| `--confirm-apply-token TOKEN` | Must match token emitted by the dry-run that produced the plan (TTL ≤ 30 minutes; bind company + plan hash) |

Optional canary caps (required for first staging apply and any production canary):

| Flag | Rule |
|------|------|
| `--employee-sample-id emp_…` | Apply only events for that hashed sample |
| `--document-type TYPE` | Apply only events whose natural_key type/item matches |
| `--max-writes N` | Hard cap (default `1` for canary; raise only after review) |

Refuse if:

- `--company` is `ALL` / `*` / empty
- confirm company mismatch
- token missing/expired/mismatch
- plan contains non-W1–W4 actions
- any event has `decision != plan`
- canary caps absent when `--require-canary-caps` is set (default **on** until an explicit `--allow-company-wide-apply` is separately approved later — **not** in first apply coding)

---

## 3. Company-scoped only

Unchanged from 7C.1 / 7C.2:

- Every SELECT/UPDATE/INSERT filtered by `company_code` and employee membership in that company
- Cross-tenant / orphan keys → never auto-applied (`manual_only`)
- No multi-company loops
- Protected historical tenants (e.g. production `WATHEFNI`) are not special-cased in code for “skip,” but **process** requires §9–§10 approvals before touching them

---

## 4. One employee / one document-type canary first

**First apply path (mandatory sequence):**

1. Dry-run company → review JSONL  
2. Re-dry-run with `--employee-sample-id` + `--document-type` filters (planner should support filter flags in 7C.3 coding)  
3. Apply with same caps and `--max-writes 1`  
4. Before/after verify (§7)  
5. Only then widen to more types/employees on the **same staging throwaway company**

Canary selection preference:

1. Throwaway staging company (`P7C2STG01` / `P7C3STG01`) — always first  
2. Staging `WATHEFNI` — only after throwaway apply green + operator approval  
3. Production — only after §10 gate  

Never start with production or company-wide apply.

---

## 5. Exact allowed write actions (W1–W4 only)

Apply may execute **only** events whose `action` is one of:

| Action | SQL shape | Tables | Notes |
|--------|-----------|--------|-------|
| **W1** `mark_onboarding_received` | `UPDATE` | `onboarding_items` | Set `status='received'` where pending-like; do not invent rows; do not change required/owner |
| **W2** `insert_employee_document_from_file` | `INSERT` | `employee_documents` | Only if no ED and matching `file_registry`; copy sha/storage_status/expiry if non-null; never invent files |
| **W3** `sync_expiry` | `UPDATE` | `employee_documents` and/or `compliance_documents` | Newer non-null wins; never write null/older |
| **W4** `fill_compliance_expiry_from_ed` | `UPDATE` | `compliance_documents` | Fill null expiry from ED non-null only |

**Still forbidden in apply v1:**

- `DELETE` / truncate / status-void cleanup  
- `INSERT` into `compliance_documents`  
- Alias remaps / merges  
- Soft-expiry task auto-complete  
- Company_code repairs  
- Any `decision=skip` or `manual_only` event  

Re-validate each event against live DB immediately before write (optimistic concurrency): if before-image no longer matches, **skip** that event with `skip_reason=stale_before_image` and continue or abort per `--on-stale {abort,skip}` (default `abort` for canary).

---

## 6. Audit log format for applied writes

Extend the 7C.2 JSONL envelope. Each applied (or attempted) write emits one line:

```json
{
  "event_id": "uuid",
  "plan_event_id": "uuid-from-dry-run",
  "ts": "ISO-Z",
  "schema_version": 1,
  "mode": "apply",
  "actor": "phase7c3-reconcile-apply",
  "operator": "shell-user-or-unknown",
  "host": "hostname",
  "company_code": "P7C3STG01",
  "sample_id": "emp_…",
  "drift_class": "…",
  "action": "mark_onboarding_received",
  "decision": "applied" | "skipped" | "failed",
  "skip_reason": null,
  "table": "onboarding_items",
  "op": "UPDATE",
  "natural_key": {"sample_id": "emp_…", "item_id": "civil_id"},
  "before": {"status": "pending"},
  "after": {"status": "received"},
  "rowcount": 1,
  "tx_id": "optional-pg-txid",
  "plan_hash": "sha256-of-plan-file",
  "guards": {"expiry_rule": null, "no_delete": true, "alias_merge": false}
}
```

Also write a summary sidecar:

```json
{
  "mode": "apply",
  "company_code": "…",
  "applied": 0,
  "skipped": 0,
  "failed": 0,
  "max_writes": 1,
  "canary": {"employee_sample_id": "…", "document_type": "…"},
  "plan_hash": "…",
  "no_deletes": true
}
```

Logs go to operator-chosen paths (e.g. `ops/reports/phase7c3-apply-*.jsonl`). No PII (hashed `sample_id` only).

Optional later: insert into an `audit_events` table in the **same transaction** as the mutation — nice-to-have, not required for first apply coding.

---

## 7. Before/after verification

Every apply run (especially canary) must:

### Before
1. Run dry-run planner for the same scope → save plan + `plan_hash`  
2. Run Phase 7C audit for the company → save mismatch totals  
3. Snapshot row counts for the four stores (company-scoped)  
4. Snapshot the target row(s) before-images (status/expiry/document_id)

### After
1. Re-read target row(s); assert after-image matches plan `after`  
2. Re-run dry-run for the same canary scope → **zero** planned writes for that key/type  
3. Re-run 7C audit → target drift class count decreased; file/orphan/tenant mismatch must not increase  
4. Confirm apply JSONL `rowcount` and `decision=applied`  
5. Confirm protected flags still OFF  

Fail the run (non-zero exit) if verification fails, even if SQL succeeded (surface for compensation §8).

---

## 8. Rollback / compensation approach

**No destructive rollback** (no DELETE to “undo”).

| Applied action | Compensation if wrong/unwanted |
|----------------|--------------------------------|
| W1 mark OI received | Manual/ops `UPDATE` status back to prior `before.status` using apply audit before-image; log `compensate_restore_onboarding_status` |
| W2 insert ED | Soft quarantine: set ED `status='needs_review'` (or leave received and flag in ops notes) — **do not DELETE**; link remains for audit |
| W3 / W4 expiry updates | Restore previous non-null expiry from apply audit `before` if compensation approved; never compensate to null if that would erase a known date without operator override |

Compensation rules:

- Same confirm gates as apply (or stricter: `--mode compensate` + token)  
- Company + canary caps required  
- Always JSONL-logged  
- Prefer human-reviewed one-row compensate over scripts  

Pre-apply safety: take a logical snapshot note (audit JSON + plan JSONL + before-images). Physical DB backup/snapshot is recommended before staging `WATHEFNI` apply or any production canary, but is an ops step outside the tool.

---

## 9. Staging apply test before any production canary

Mandatory staging ladder (coding phase later):

| Step | Target | Mode | Caps |
|------|--------|------|------|
| 9.1 | Keep 7C.2 dry-run verifier green | dry-run | n/a |
| 9.2 | New throwaway `P7C3STG01` apply verifier | apply | `--max-writes 1` per case, then batch |
| 9.3 | Assert W1–W4 each apply once on throwaway | apply | one type/employee |
| 9.4 | Idempotent re-apply → 0 writes | apply | same caps |
| 9.5 | Stale before-image abort | apply | force drift mid-flight in harness |
| 9.6 | Compensation drill on throwaway (W1 restore) | compensate | one row |
| 9.7 | Optional staging `WATHEFNI` **dry-run only** review | dry-run | n/a |
| 9.8 | Staging `WATHEFNI` apply — **separate approval** | apply | one employee + one document-type |

**Do not** proceed to production until 9.2–9.6 are green.

Deliverables when coding is approved (not now):

- Extend CLI with guarded apply  
- `ops/staging-phase7c3-apply-verify.py` (throwaway)  
- `ops/PHASE7C3_APPLY_CANARY_RUNBOOK.md` (inactive until prod gate)

---

## 10. Production canary approval gate

Production apply is **not** authorized by accepting this plan.

Required before any production write:

1. Staging ladder §9 green  
2. Written approval naming: company, employee sample_id (or agreed test employee), document_type, max-writes, window  
3. Production dry-run JSONL reviewed by operator  
4. Predeploy / DB snapshot note recorded  
5. Protected flags confirmed OFF  
6. Canary caps enforced in the actual command  
7. Immediate after-verify (§7) and stop  

**First production canary shape:**

```text
one company + one employee_sample_id + one document_type + max-writes=1
```

Then stop. No fleet reconcile. No employee-app. No upload expansion.

---

## Implementation gate (when coding approved)

Suggested ship order:

1. Add plan-hash + apply-token to dry-run output  
2. Implement guarded apply executor for W1–W4 only  
3. Add canary filter flags + `--max-writes`  
4. Applied JSONL + summary  
5. Staging throwaway apply verifier + compensation drill  
6. Runbook for staging `WATHEFNI` / prod canary (inactive)  
7. Stop for production canary approval (§10)

**This document does not authorize apply-mode implementation, staging `WATHEFNI` writes, or any production reconciliation.**
