# Employees 360 Wave 1B — Production-safe approval + staging qualification

**Stamp:** `20260801T191212Z`  
**Evidence:** `ops/evidence/employees360-wave1b-approval-staging-20260801T191212Z/`  
**Remote staging evidence:** `/opt/wathefni/staging-evidence/employees360-wave1b-20260801T191212Z/`  
**Mode:** local engineering + staging DB qualification — **no production deploy**

---

## Verdict

**PASS**

| Gate | Result |
|---|---|
| Production-safe approval model implemented | PASS |
| Dashboard no longer hardcodes canary-only | PASS |
| Canary restricted to allowlisted non-prod | PASS |
| Staging DB qualification (37 checks) | **37/37 PASS** |
| Production deploy | **NOT DONE** |
| Staging HTTP service restored healthy | PASS (`8011` = 200) |
| Production service untouched | PASS (`8010` = 200; prod `app.py` sha unchanged) |

---

## Recommended production approval model

**Two-person pending attestation (no fake approver, no silent auto-approve):**

| Situation | Behavior |
|---|---|
| Requester also has `employees.status.approve` (dual-grant) | May **request** a change; may **not** approve own request. Outside canary allowlist, self-approval is forbidden. |
| Separate approver required | Requester creates a pending request naming a designated eligible approver. Approver decides in their own session (`approve` / `reject`). |
| No eligible separate approver | Fail closed: `blocked_reason=no_eligible_approver`. Status changes unavailable until another teammate has `employees.status.approve`. |
| Rejected | Request → `rejected`; **employee row unchanged**; audited. |
| Cancelled | Requester cancels pending request; **employee unchanged**; audited. |
| Stale | Create/approve path checks `expected_status` + `expected_updated_at` → `409 employee_version_conflict`. |
| Replayed | Same idempotency key + same hash → idempotent success; different hash → `409 idempotency_conflict`. |
| Internal canary | Only when `employee_status_canary_allowed(company)` (default: company `WATHEFNI` + non-production envs). Direct `POST .../status` with canary. |

Existing atomic status transition / verification / audit path is reused on **approve** (preserves idempotency + expected-version + rollback semantics of Wave 1 / Phase 8C).

---

## Exact UI/API behavior

### API
- `GET /dashboard/posthire/employee-status/approval-policy` — canary flag, eligible approvers, blocked reason
- `GET /dashboard/posthire/employee-status/pending` — pending requests for actor
- `POST /dashboard/posthire/employees/{key}/status/requests` — create pending two-person request
- `POST /dashboard/posthire/employee-status/requests/{id}/cancel` — requester cancel
- `POST /dashboard/posthire/employee-status/requests/{id}/decide` — `{action: approve|reject}`
- `POST /dashboard/posthire/employees/{key}/status` — **canary only** when allowlisted; `separate_approval` rejected with `use_status_approval_request`

### UI (`PostHire.tsx`)
1. Load approval policy before status change.
2. If canary allowlisted: optional internal canary confirm; otherwise default to two-person request.
3. If no eligible approver: clear error, do not invent one.
4. Pending card: Cancel / Reject / Approve (server enforces actor).

---

## Staging evidence

Local pack:
- `tests/wave1b-staging-qual.txt` — **37 passed, 0 failed**
- `tests/staging-health-*.txt`, `staging-rsync-prod-parity.txt`
- `ui/` copies of dashboard API + PostHire (on remote)

Covered on staging DB (`wathefni_staging`):
- roster/manual phone canonicalization + alias match + duplicate prevention
- recruiting hire source marker (`canonical_employee_phone`)
- PATCH concurrency conflict/success
- manager out-of-scope mutation deny
- two-person request: create / cancel / reject / stale / replay / self-forbidden / approve
- canary denied when `WATHEFNI_ENV=production`
- direct `separate_approval` commit rejected
- integrity expansion + orphan-doc fail-closed markers
- dashboard/orchestrator client compatibility markers

---

## Migration / deployment order (when approved later)

1. **Grant hygiene:** ensure every production tenant that needs status changes has ≥1 eligible **separate** approver (not only a dual-grant owner).
2. Deploy **orchestrator** with `employee_status_approval.py` + Wave 1/1B `app.py` changes (schema auto-creates `employee_status_change_requests`).
3. Deploy **dashboard** in the same window (policy-aware UI + concurrency field from Wave 1).
4. Staging soak already green; repeat smoke on staging after deploy artifact freeze.
5. Production enablement only with explicit GO — do **not** add `production` to canary env allowlist unless intentionally keeping WATHEFNI-only canary.
6. Prefer production UI path = two-person requests only.

**Not in this wave:** uniqueness constraints, null-status cleanup, orphan deletes, Wave 2 person model, production deploy.

---

## Rollback plan

1. **Code:** revert orchestrator to pre-Wave1B artifact; revert dashboard dist; restart services.
2. **Data:** pending rows in `employee_status_change_requests` are non-destructive; leave them or mark cancelled. Committed `employee_status_changes` remain the durable audit (no silent undo).
3. **Grants:** revoke any temporary qualification grants (`review_reference=wave1b-staging-qual`) — already revoked by smoke cleanup.
4. **Staging restore note:** staging service was briefly broken by a full local `app.py` overlay; restored via production python module rsync. Production binary/hash was not modified for Wave 1B deploy.

---

## Exact local code surfaces

- `wathefni-orchestrator/employee_status_approval.py` (new)
- `wathefni-orchestrator/app.py` (policy/request/decide endpoints; canary-only direct status)
- `wathefni-orchestrator/hire_operations.py` (Wave 1 alias hire — carried forward)
- `apps/wathefni-dashboard/src/lib/api.ts` + `posthire/PostHire.tsx`
- `wathefni-orchestrator/smoke-test-employee-wave1b-staging.py`
