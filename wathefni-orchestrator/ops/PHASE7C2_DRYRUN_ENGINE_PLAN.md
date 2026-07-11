# Phase 7C.2 — Dry-run reconciliation engine implementation plan (plan only)

**Status:** Implemented (dry-run planner + throwaway verifier). Apply still disabled.  
**Prerequisites:** Phase 7C closed · Phase 7C.1 plan accepted.  
**Code:** `ops/staging-phase7c2-reconcile-docs-dryrun.py`, `ops/staging-phase7c2-dryrun-verify.py`, `ops/lib/doc_type_map.py`  

**Still forbidden until separately approved:**

- Apply / write mode
- Production reconciliation (dry-run or apply)
- `WATHEFNI_EMPLOYEE_APP=on`
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=on`
- Broad document upload expansion
- Deletes, alias merges, OCR, seed activation

---

## Goal

Ship a **company-scoped, read-only dry-run planner** that:

1. Reads the four document stores for one `company_code`
2. Emits structured **JSONL planned-write events** (+ summary JSON/Markdown)
3. Proves `transaction_read_only=on` and performs **zero writes**
4. Leaves `--mode apply` present but **hard-disabled** (refuse with clear message)

No production runs in 7C.2.

---

## 1. Dry-run planner only first

### Deliverables (when coding is approved)

| Artifact | Purpose |
|----------|---------|
| `ops/lib/doc_type_map.py` *(or inline in script if tiny)* | Shared type map + alias families from 7C.1 §1 |
| `ops/staging-phase7c2-reconcile-docs-dryrun.py` | CLI planner; default `--mode dry-run` |
| `ops/staging-phase7c2-dryrun-verify.py` | Throwaway company seed + 13-case dry-run verifier |
| `ops/reports/phase7c2-*.jsonl` | Example / CI output path (no PII) |

### Non-deliverables in 7C.2

- Any `UPDATE` / `INSERT` / `DELETE` execution path
- Cron / systemd timer
- Dashboard button / API endpoint
- Shared apply executor

### CLI contract

```bash
WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  python3 ops/staging-phase7c2-reconcile-docs-dryrun.py \
    --company P7C2STG01 \
    --mode dry-run \
    --jsonl-out /tmp/p7c2-plan.jsonl \
    --summary-out /tmp/p7c2-summary.json
```

Rules:

- Default mode = `dry-run` if `--mode` omitted
- `--mode apply` → **always refuse** in 7C.2 with:
  `apply mode disabled until Phase 7C.3 approval`
- Exit `0` when planning succeeds (even if drift found)
- Exit non-zero only for config/DB/scope errors

---

## 2. Company-scoped execution

| Guard | Behavior |
|-------|----------|
| `--company` required | Missing → refuse |
| Exact `company_code` | Uppercased; must exist in `companies` |
| Refuse `ALL` / `*` / empty | Even with any future unsafe flag — unimplemented in 7C.2 |
| Row filter | Employees of that company only; docs/files must match company **or** be flagged `manual_only` / `company_mismatch` (never planned as auto-write) |
| Staging default env | `postgres.staging.env`; refuse if DSN host/name looks like production **unless** `--allow-production-dsn` is explicitly passed **and** mode is dry-run — still **no prod runs in 7C.2 test plan** |

Planner never opens a read-write session.

---

## 3. Structured JSONL output

One JSON object per line. No phones, emails, names, storage URLs, or raw `employee_key`.

### Event envelope (every line)

```json
{
  "event_id": "uuid",
  "ts": "2026-07-12T00:00:00Z",
  "schema_version": 1,
  "mode": "dry-run",
  "actor": "phase7c2-reconcile-dryrun",
  "company_code": "P7C2STG01",
  "sample_id": "emp_<sha256[:12]>",
  "drift_class": "employee_doc_without_received_item",
  "action": "mark_onboarding_received",
  "decision": "plan" | "skip" | "manual_only",
  "skip_reason": null,
  "table": "onboarding_items",
  "op": "UPDATE" | "INSERT",
  "natural_key": {
    "sample_id": "emp_…",
    "item_id": "civil_id"
  },
  "before": { "status": "pending" },
  "after": { "status": "received" },
  "guards": {
    "expiry_rule": null,
    "no_delete": true,
    "alias_merge": false
  },
  "evidence": {
    "has_employee_document": true,
    "has_file_registry": false,
    "onboarding_status": "pending"
  }
}
```

### Summary JSON (sidecar)

```json
{
  "company_code": "…",
  "mode": "dry-run",
  "read_only": true,
  "transaction_read_only": "on",
  "no_writes": true,
  "apply_enabled": false,
  "planned_writes": 0,
  "skips": 0,
  "manual_only": 0,
  "by_action": {},
  "by_drift_class": {},
  "by_skip_reason": {}
}
```

Operator markdown optional (counts + redacted samples only).

---

## 4. The 13 staging throwaway cases (dry-run adapted)

Throwaway company: **`P7C2STG01`**. Verifier may **seed** fixture rows in a normal write connection (test harness only), then run the planner in a **separate read-only connection**. Apply assertions are replaced with **plan-shape assertions**.

| # | Case | Seed | Dry-run expect |
|---|------|------|----------------|
| 1 | Dry-run no writes | A–D drift present | `planned_writes ≥ 1`; DB checksums / row counts unchanged after planner; `transaction_read_only=on` |
| 2 | Refuse unscoped | n/a | Missing `--company` or `ALL` → refuse, exit ≠ 0 |
| 3 | Checklist catch-up | ED received + OI pending | Exactly one `plan` event: `mark_onboarding_received` / `UPDATE onboarding_items` |
| 4 | Compliance orphan + file | Compliance received, no ED, file present | `plan` `insert_employee_document_from_file` (`INSERT employee_documents`) |
| 5 | Compliance orphan, no file | Compliance only | `skip` + `skip_compliance_orphan_no_file`; no INSERT planned |
| 6 | Expiry newer wins | ED older, compliance newer | `plan` `sync_expiry` updating ED to newer (and/or confirming compliance already winner) |
| 7 | Expiry older rejected | Candidate older than existing | `skip` + `expiry_older_than_existing` |
| 8 | Null expiry fill | Compliance received null; ED has date | `plan` `fill_compliance_expiry_from_ed` |
| 9 | Null expiry no source | Both null | `skip` + `null_expiry_no_source` (or `manual_only` / `needs_review`) |
| 10 | Alias no-merge | Both `residency` + `residency_iqama` present | `manual_only` + `needs_operator_map`; **zero** auto `plan` for merge |
| 11 | Idempotency (plan) | Already consistent rows | Empty plan for those keys (`planned_writes=0` for fixture) |
| 12 | Re-audit alignment | After planning fixtures | Re-run 7C audit; planner `by_drift_class` covers audit buckets A–D; file/orphan/tenant remain 0 on fixtures |
| 13 | Flag posture | n/a | Verifier asserts employee-app + channel-accounts remain off in process env / known staging unit drop-ins |

**Note:** Cases 3–8 assert **planned write shapes**, not applied DB mutations. Case 11 is plan-idempotency (consistent data → empty plan), not apply-twice.

Cleanup: verifier deletes only `P7C2STG01` fixture rows it created.

---

## 5. Exact planned write shapes

Only these `op` + `table` + `after` shapes may appear as `decision=plan` in 7C.2.

### W1 — `mark_onboarding_received`

```text
op: UPDATE
table: onboarding_items
natural_key: (sample_id, item_id)
before: { status }
after:  { status: "received" }
# updated_at implied; not required in after payload
drift_class: employee_doc_without_received_item
```

Gates: ED exists for same item/type; OI status pending-like; same company.

### W2 — `insert_employee_document_from_file`

```text
op: INSERT
table: employee_documents
natural_key: (sample_id, document_type)
after: {
  document_type, item_id?, status: "received",
  content_sha256?, storage_status?,
  expiry_date?   # only if known non-null from compliance/file metadata
}
# do not copy storage_url into JSONL; reference file via content_sha256 / file_kind only
drift_class: compliance_without_employee_doc
evidence.has_file_registry: true
```

Gates: compliance received-like/valid/…; no ED; matching `file_registry` row for subject+type.

### W3 — `sync_expiry` (ED ← winner or compliance ← winner)

```text
op: UPDATE
table: employee_documents | compliance_documents
natural_key: (sample_id, document_type)
before: { expiry_date }
after:  { expiry_date: "<winner ISO date>" }
# if table=compliance_documents, after may also include days_until_expiry
drift_class: expiry_status_conflicts
guards.expiry_rule: "newer_non_null_wins"
```

May emit **one or two** plan lines (one per lagging table). Never null `after.expiry_date`.

### W4 — `fill_compliance_expiry_from_ed`

```text
op: UPDATE
table: compliance_documents
natural_key: (sample_id, document_type)
before: { expiry_date: null, status }
after:  { expiry_date: "<from ED>", days_until_expiry?: N }
drift_class: null_expiry_on_received_compliance
```

### Explicitly not planned in 7C.2

- Any `DELETE`
- `INSERT compliance_documents` (deferred; inverse gap was 0 on staging audit)
- Soft-expiry task auto-complete
- Alias remaps / merges
- Cross-tenant company_code repairs

---

## 6. Skip reasons

Closed vocabulary for `decision=skip` or `manual_only`:

| `skip_reason` / code | When |
|----------------------|------|
| `skip_compliance_orphan_no_file` | Compliance without ED and no matching file |
| `expiry_older_than_existing` | Candidate expiry older than existing non-null |
| `expiry_candidate_null` | Would null-out or copy null onto non-null |
| `null_expiry_no_source` | Received compliance null expiry; no ED/extraction date |
| `needs_operator_map` | Ambiguous alias family coexistence |
| `manual_only_unsupported_class` | Drift outside A–D auto set |
| `company_mismatch` | Row company ≠ scoped company |
| `orphan_employee_key` | Doc/file key not in company employees |
| `duplicate_rows` | >1 ED or compliance for same type (report only) |
| `onboarding_item_missing` | ED exists but no OI row to update (do not invent OI) |
| `type_not_in_reconcile_map` | Unknown/unmapped type for auto plan |
| `apply_disabled` | User requested apply in 7C.2 |

Every skip still emits a JSONL line (`decision=skip` or `manual_only`) so operators see coverage.

---

## 7. Read-only proof in dry-run

Same bar as Phase 7C audit:

1. `conn.set_session(readonly=True, autocommit=True)`
2. `SHOW transaction_read_only` / `current_setting('transaction_read_only')` must be `on`
3. Verifier case 1: optional write-probe on the **planner** connection must fail with `ReadOnlySqlTransaction`
4. Summary flags: `read_only=true`, `no_writes=true`, `transaction_read_only=on`
5. Print footer: `NO_WRITES=true` · `READ_ONLY_TRANSACTION=true` · `APPLY_ENABLED=false`

Harness seeding uses a **different** connection and must never share the planner connection.

---

## 8. Apply mode remains disabled

```python
if mode == "apply":
    raise SystemExit(
        "apply mode disabled until Phase 7C.3 approval "
        "(dry-run planner only in Phase 7C.2)"
    )
```

Even if someone passes `--confirm-company` / `--i-understand-writes`, 7C.2 ignores them and refuses.  
Those flags are reserved for 7C.3+ and must not enable writes early.

---

## 9. No production writes

| Constraint | 7C.2 stance |
|------------|-------------|
| Production DSN apply | Impossible (apply disabled) |
| Production DSN dry-run | **Not in test plan**; do not run against prod as part of 7C.2 |
| Staging `WATHEFNI` dry-run | Optional **after** throwaway verifier green; operator-requested only |
| Staging `WATHEFNI` apply | Forbidden |
| Fleet / ALL companies | Forbidden |

---

## 10. No employee app or upload expansion

Verifier case 13 + release notes must state:

- `WATHEFNI_EMPLOYEE_APP` remains **off**
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS` remains **off**
- No employee-app document upload expansion
- No change to upload dual-write allowlist in app code during 7C.2

7C.2 touches **ops planner scripts only** (plus optional tiny shared type-map module under `ops/`).

---

## Suggested implementation order (when coding approved)

1. Extract/freeze type map constants (match 7C.1 §1).
2. Implement read-only loader (reuse 7C audit query patterns).
3. Implement planners for W1–W4 + skip vocabulary.
4. JSONL + summary emitters.
5. CLI with apply hard-disabled.
6. Throwaway verifier for cases 1–13 (dry-run assertions).
7. Optional: dry-run against staging `WATHEFNI` and store redacted report under `ops/reports/`.
8. Stop. Open Phase **7C.3** only for apply-mode design/implementation approval.

---

## Acceptance criteria for 7C.2 coding phase

- [ ] Dry-run planner exists and defaults to dry-run
- [ ] `--company` required; `ALL` refused
- [ ] JSONL events match envelope + W1–W4 shapes
- [ ] Skip reasons use closed vocabulary
- [ ] Read-only transaction proof printed and verified
- [ ] Apply mode hard-refused
- [ ] Throwaway verifier 13/13 green on staging
- [ ] No production runs
- [ ] Employee app + channel accounts still off
- [ ] No apply SQL executed anywhere in the new code paths

**This document authorizes planning the dry-run engine only. It does not authorize apply-mode implementation or any production reconciliation.**
