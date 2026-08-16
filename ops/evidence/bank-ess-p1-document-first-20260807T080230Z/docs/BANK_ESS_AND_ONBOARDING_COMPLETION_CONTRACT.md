# Bank ESS + onboarding completion — canonical contracts

Status: production **broad rollout** live for WATHEFNI (Bank ESS allowlisted real
employees except Talal negative control; onboarding completion company-wide).
**P0** verified-at-HR accepted (`ops/evidence/bank-ess-p0-verified-at-hr-20260807T074024Z/`).
**P1** document-first Kuwait bank certificate OCR on WATHEFNI canary
(`CONTRACT_VERSION=bank_ess_v1_p1_document_first`). Live qualification evidence
under `ops/evidence/bank-ess-p1-document-first-*/`.
Auth Wave 2 Phase 6: **not started**.
Verdicts: Bank ESS `fully_proven` (P0) · P1 document-first shipping on canary ·
Onboarding completion `fully_proven`.

These two contracts are the single authority for their domain. No surface may
recompute, re-map, or hand-maintain either one.

---

## 1. Onboarding completion contract

Module: `wathefni-orchestrator/onboarding_completion_contract.py`
(`CONTRACT_VERSION` is stamped into every persisted snapshot.)

### Item classification

Every checklist row resolves to exactly one class. The class is derived, never
stored:

| class | meaning |
|---|---|
| `satisfied_accepted` | verified/accepted by the reviewer |
| `satisfied_waived` | explicitly waived; counts as done |
| `satisfied_not_applicable` | not required for this employee; excluded from required totals |
| `waiting_employee` | open, and the employee owes the next action |
| `waiting_hr` | open, and HR/a verifier owes the next action |
| `waiting_other` | open, owed by system/payroll/another rail |
| `blocked` | open, but a dependency is unsatisfied |

`submitted` is never `verified`: legacy `received` classifies as `waiting_hr`,
only `accepted`/`verified`/`complete` classes satisfy.

Ownership uses the lifecycle module's `responsible_party` when importable, so the
completion state and the rendered checklist can't disagree about who is waiting.

### Employee-level states

Precedence is strict, top to bottom:

| state | condition |
|---|---|
| `blocked` | assignment `cancelled`/`abandoned`, or every open required item is dependency-blocked |
| `completed` | required items exist and none are open |
| `reopened` | previously completed (`first_completed_at` set) and required work is open again |
| `not_started` | onboarding not launched and no item has progress |
| `waiting_on_employee` | open required work the employee owes |
| `waiting_on_hr` | open required work HR owes |
| `in_progress` | progress exists but no actor is asked (system/payroll rails) |

An assignment status in `{in_progress, started, active, delayed}` counts as
progress: once HR launches onboarding, the process is underway even with zero
submissions, so the employee is `waiting_on_employee`, not `not_started`.

### Next action — one item, one owner, every surface

`select_next_item(items)` is the only way a surface may name "what happens
next". It filters to required, open items and walks the classes in the order
`waiting_employee → waiting_hr → waiting_other → blocked`, tie-broken by
unblocked-first, then soonest due date. Because it uses the same rows and the
same filter as `compute_completion`, the named item always explains the state.
Selecting per surface is what let the HR queue name one item while the drawer
and the app named another.

`next_action(snapshot)` gives the owner and the copy. `reopened` records *when*
work appeared, not *who* owns it, so its owner comes from `current_actor()` —
the snapshot's own waiting buckets, in the same priority. A bank change under
review therefore reads "HR needs to review" on all four surfaces instead of
telling the employee to act.

Clients render the contract's message. A local state→copy table is a second
source of truth and will contradict the contract the moment a state can have
more than one owner; the mobile per-state string is an offline fallback only
(asserted by `verify-capability-foundation.py`).

### Persistence

- `employee_onboarding_completion` — one snapshot per (company, employee),
  including `first_completed_at`, `reopened_at`, `reopen_count` and append-only
  `completion_evidence`. Completion history is never removed when checklist
  definitions change.
- `employee_onboarding_completion_events` — append-only transition log.
- `recompute()` is the only writer. It is idempotent: re-running with no change
  writes no new event.

### Legacy mirror

`recompute()` mirrors `employees.documents_pending`, `documents_complete` and
`onboarding_status` so older readers agree, and **deliberately does not touch
`employees.updated_at`**. That column is ESS's hub optimistic-concurrency token;
bumping it for derived counters made unrelated in-flight employee requests fail
`stale_data` whenever any checklist item moved.

### Surfaces

All of these read the same snapshot, and the live matrix asserts they return an
identical `state` (a missing value fails the check):

- `GET /app/onboarding` → `completion`, `next_action`, `status`
- `GET /app/profile` → `onboarding.completion`
- `GET /dashboard/posthire/onboarding/{employee_key}` → `completion`
- `GET /dashboard/posthire/onboarding` (queue) → `completion_state`,
  `satisfied_count`, `open_count`, `completion_next_action`, `next_owner`
- `GET /dashboard/posthire/employees/{employee_key}/onboarding-completion`
- SQL predicates (`sql_satisfied_predicate`, `sql_open_predicate`,
  `sql_employee_action_list`) for queues, reminders, calendar and reporting

### Bank item reconciliation on read

Bank state lives in Bank ESS, so the `bank_details` checklist row is a mirror.
Every one of the four surfaces calls `reconcile_onboarding_bank_item` before it
computes completion, and the reconcile is idempotent — an already-correct row is
not rewritten, so reads cause no churn and no event spam. Authority order is
fixed in `desired_onboarding_bank_state`: an open request first, then the live
`employee_bank_effective` row, and only then terminal history. Without that
order an older `rejected` request outranked a newer `applied` one and every HR
read reverted a completed bank item.

Reminders use `reminder_targets(snapshot)`, whose `dedup_key` is stable
regardless of item ordering, so retries and multiple channels cannot double-send.

---

## 2. Bank ESS contract

Module: `wathefni-orchestrator/employee_bank_ess.py`, driven through
`employee_selfservice_wave5.py` change requests.

### Three-layer authority

| layer | table | written by |
|---|---|---|
| employee-submitted (proposed) | `employee_ess_requests.proposed_values` (sealed ciphertext) | employee |
| HR-verified | `employee_bank_verified` | **HR approval** (`decide` at `pending_hr`) |
| payroll-effective | `employee_bank_effective` (effective-dated, `superseded_at`) | **Payroll Apply only** |

Product rule (P0): employee submission = proposed; HR approval = verified;
Payroll Apply = payroll-effective. Verified must remain distinct from
payroll-effective. Employee/OCR must never write verified or effective rows.

Employee input is always a change request. Nothing an employee submits becomes
payroll truth without dual control, and the matrix asserts that the effective
fingerprint is unchanged while a request is pending — including after HR has
already stamped verified.

### Request state machine

```
draft ──submit──> pending_hr ──HR approve──> pending_payroll ──payroll approve──> approved ──Apply──> applied
  │                    │                         │ (verified stamp)                              │
  │                    ├──reject(reason)──> rejected ──employee corrects──> replace/resubmit     └─ effective row
  │                    └──return_for_information──> needs_information (replaceable)
  └──withdraw──> withdrawn (onboarding checklist sync; soft-revoke verified for this request if any)
```

Employee-facing `submission_state` values (never tell the employee to “Apply”;
never describe `approved` as already used for payroll):

| state | meaning |
|---|---|
| `pending_hr` | awaiting HR review |
| `pending_payroll` | HR verified, awaiting payroll |
| `approved` | payroll approved but **not** yet effective |
| `applied` | payroll-effective |

- Exactly one active request per employee (advisory lock + `assert_no_duplicate_active`);
  a second concurrent submit gets `409 bank_request_already_active`.
  Recoverable overlays (`needs_information`, `needs_review`) are replaceable
  instead of dead-ending on that error.
- Rejection or correction of a bank request **requires** a reason
  (`422 decision_reason_required`), so the employee never lands on a dead end.
- Stale HR decisions lose: `409 stale_concurrency_version`.
- Kuwait IBAN (`kw_iban`) is **enforced at submit** so invalid accounts cannot
  survive HR/payroll review and only fail at Apply.
- Apply is idempotent by key and leaves exactly one current effective row.
  Apply does **not** invent a new verified stamp when HR already verified the
  request; legacy apply-only rows may backfill verified without superseding.

### Sensitive data

- Proposals are sealed before storage; plaintext bank payloads are rejected
  (`plaintext_bank_forbidden`). Encryption unavailable ⇒ the write is refused,
  never downgraded.
- Responses expose a masked `display` projection plus a fingerprint. Reveal
  requires `employees.ess.unmask` and is audited. For backward compatibility the
  masked values are also mirrored at the top level with `<field>__masked`.
- Evidence is stored under private local storage (`private/bank-evidence/...`,
  mode 0600), never a public URL, and served only through authorized endpoints.

### Retention and deletion

- Evidence rows carry `retention_until`; soft delete revokes access immediately.
- `purge_bank_evidence_bytes()` destroys the blobs for expired/soft-deleted rows
  and stamps `purged_at`. With `include_orphans` it also removes blobs whose row
  is gone, so no readable bank evidence can survive a row deletion.
- All four bank tables have `ON DELETE CASCADE` to `employees(employee_key)`:
  bank authority rows can never outlive the employee they describe.

### Format neutrality

Account validation is a registry keyed by account kind, so Kuwait IBAN checks,
salary-transfer requirements and payroll integrations can be added without
changing the request model or the authority layers.

### P1 — Document-first Kuwait bank certificate (OCR)

Primary employee path: upload a bank certificate / IBAN letter (PDF or image).
Extraction reuses `kuwait_gcc_document_intelligence` (`bank_certificate` type,
Mistral Document AI). Extracted fields are **non-authoritative proposals**
stored on `employee_bank_evidence.extraction_json`. The employee confirms or
corrects them, then sealed submit writes the **proposed** layer only.

OCR never writes `employee_bank_verified` or `employee_bank_effective`.
If extraction is uncertain or fails, the employee gets a clean manual fallback
while the original evidence remains linked. HR sees proposed vs verified,
evidence, and a concise extraction status/confidence/warnings — not raw OCR.

---

## Rollback

Flags (systemd drop-in
`/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzzzzzz-bank-ess-onboarding-completion.conf`):

- `WATHEFNI_BANK_ESS_V1=off` — disables the employee/HR bank endpoints. Existing
  verified and effective rows stay intact and readable.
- `WATHEFNI_ONBOARDING_COMPLETION_CONTRACT=off` — `recompute()` falls back to the
  legacy count path; the snapshot tables are left in place and stale, and
  surfaces fall back to legacy counts.

`systemctl daemon-reload && systemctl restart wathefni-orchestrator` after either.

No destructive migration is required to roll back: every schema change is
additive (new tables, `purged_at` column, cascade constraints).
