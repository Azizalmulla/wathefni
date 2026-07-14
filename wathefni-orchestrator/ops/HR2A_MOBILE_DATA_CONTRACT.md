# HR-2A Mobile Data Contract

Status: local implementation complete; staging connection intentionally paused for HR-2 visual review.

## Authority

Every route below depends on the HR-1 operator-mobile context. Company, user, role,
permissions, modules, lifecycle and manager scope are recomputed by the backend.
Employee, browser and shared legacy tokens remain rejected by HR-1 before an
HR-2A handler runs.

The client never supplies company, role, permissions, workspace or manager scope.

## First-slice reads

- `GET /dashboard/mobile/priorities`
  - Returns separate authoritative sections; it does not invent cross-domain urgency.
  - Items include `type`, `target_id`, safe `summary`, `status`, timestamp/due
    context, permitted actions, destination and backend severity when present.
- `GET /dashboard/mobile/leave`
- `GET /dashboard/mobile/leave/{leave_id}`
  - Tenant and manager scope are independently enforced.
  - The DTO contains safe employee context, date/duration, reason, conflicts,
    authoritative balance context when enabled and exact allowed actions.
- `GET /dashboard/mobile/candidates`
- `GET /dashboard/mobile/candidates/{app_key}`
  - Ranking is explicitly advisory.
  - Facts, evidence, concerns and missing evidence are separate fields.
  - Raw application JSON and candidate phone are omitted.
- `GET /dashboard/mobile/candidates/{app_key}/cv`
- `GET /dashboard/mobile/candidates/{app_key}/cv/preview`
  - Reuse the accepted audited HR-0 CV paths.

## Explicit confirmation and idempotency

Sensitive mutation routes:

- `POST /dashboard/mobile/leave/{leave_id}/decision`
- `POST /dashboard/mobile/candidates/{app_key}/decision`

Prepare:

```json
{
  "action": "approve",
  "reason": null,
  "idempotency_key": "client-generated-unique-key",
  "confirm": false
}
```

The backend creates a tenant/operator-bound confirmation, calls the existing action
registry preflight, and returns:

```json
{
  "ok": false,
  "status": "needs_confirmation",
  "confirmation": {
    "confirmation_id": "uuid",
    "confirmation_hash": "sha256",
    "summary": "Exact target",
    "consequence": "Exact consequence",
    "current_state": "requested",
    "expires_at": "ISO-8601"
  }
}
```

Confirm by resending the same route/action/idempotency key with `confirm: true`,
`confirmation_id` and `confirmation_hash`. The adapter verifies current target
state before allowing the existing registry pending action to execute.

Properties:

- duplicate prepare with the same material returns the original confirmation;
- an idempotency key reused with different material returns `idempotency_conflict`;
- concurrent confirmation returns `action_in_progress`;
- changed target state returns `stale_decision`;
- completed confirmation replay returns the backend-authoritative stored result;
- registry confirmation becoming unavailable fails closed;
- no mobile mutation bypasses the registry, policy or audit path.

## Narrow V1 read adapters

- `/dashboard/mobile/onboarding`
- `/dashboard/mobile/onboarding/{employee_key}`
- `/dashboard/mobile/attendance`
- `/dashboard/mobile/shifts`
- `/dashboard/mobile/employees`
- `/dashboard/mobile/employees/{employee_key}`
- `/dashboard/mobile/delivery-alerts`

These are thin response adapters over existing dashboard functions. Employee
search/profile still requires the grant-only `employees.read` permission.

## Intentionally unavailable

- new-candidate push
- interview rescheduling
- unrestricted Kanban/stage mutation
- bulk import
- job or pipeline configuration
- AI scoring configuration
- Setup Console or platform operations
- automatic hiring or rejection

## Staging checkpoint

Do not deploy or connect the frontend until the three-screen preview is accepted.
The next verifier must prove tenant isolation, manager-scope isolation, live
grant/module revocation, confirmation replay, stale decisions, CV audit,
employee/browser/legacy token rejection and company disable behavior.
