# HR-3 Frontend Contract

## Authority and navigation

`/dashboard/mobile/me` is the only workspace authority. The frontend checks the
workspace `enabled` value, feature `enabled` value and exact action list. It
does not infer access from `principal.role`, labels, route names or record
status.

Route grants:

- `hr_tasks` exposes `/tasks`.
- `onboarding_review` exposes `/onboarding`.
- `document_review` exposes `/documents`.
- `attendance_exceptions` exposes `/attendance`.
- `today_shifts` or `shift_swap_decisions` exposes `/shifts`.
- `employee_search` or `employee_quick_profile` exposes `/employees`.
- `delivery_alerts` exposes `/delivery-alerts`.
- `candidate_rankings`, `candidate_summary` or `candidate_evidence` exposes
  `/candidates`.
- `interview_status` or `interview_notes` exposes `/interviews`.
- Settings remains available to an authenticated operator but contains no owner
  or Setup Console controls.

The HR-only fixture receives HR routes. The recruiter-only fixture receives
candidate and interview routes. Restricted managers receive only granted HR
features and retain their scope label. The multi-workspace fixture receives HR
and recruiting routes, including its explicit employee-search grant.

## Mobile endpoint assumptions

The frontend calls only these thin routes:

- `GET /dashboard/mobile/tasks`
- `GET /dashboard/mobile/onboarding`
- `GET /dashboard/mobile/onboarding/{employeeKey}`
- `POST /dashboard/mobile/onboarding/{employeeKey}/review`
- `GET /dashboard/mobile/documents`
- `GET /dashboard/mobile/documents/{employeeKey}/{documentType}`
- `POST /dashboard/mobile/documents/{employeeKey}/{documentType}/review`
- `GET /dashboard/mobile/attendance`
- `GET /dashboard/mobile/attendance/{attendanceId}`
- `POST /dashboard/mobile/attendance/{exceptionId}/resolve`
- `GET /dashboard/mobile/shifts?date=YYYY-MM-DD`
- `GET /dashboard/mobile/shift-swaps`
- `GET /dashboard/mobile/shift-swaps/{swapId}`
- `POST /dashboard/mobile/shift-swaps/{swapId}/decision`
- `GET /dashboard/mobile/employees`
- `GET /dashboard/mobile/employees/{employeeKey}`
- `GET /dashboard/mobile/delivery-alerts`
- `GET /dashboard/mobile/candidates`
- `GET /dashboard/mobile/interviews`
- `GET /dashboard/mobile/interviews/{interviewId}`
- `POST /dashboard/mobile/interviews/{interviewId}/notes`

Existing auth, priorities, leave detail/decision and candidate detail/decision
routes are preserved.

Collection normalization accepts an `items` array or the route-specific plural
key. Detail normalization accepts `item` or the route-specific singular key.
Only documented identifiers, display facts, timestamps, status and
`allowed_actions` are retained. Unknown fields never produce an action,
permission or score.

Candidate CV preview/download uses the backend-provided mobile path, rejects
paths outside `/dashboard/mobile/*`, fetches bytes with the bearer session, and
opens a temporary local file. Decision actions remain visible only when present
in `allowed_actions`; shortlist, reject and hire retain the two-step backend
confirmation handshake.

## State behavior

Every collection and detail supports loading, empty, generic error, offline,
stale, success, permission/scope denial, revoked or disabled operator,
disabled company, archived company and expired session states. Retryable states
do not imply that an action succeeded. Company and session states are also
handled at the authenticated shell.

Dates, date ranges and times are formatted through locale-aware `Intl`
formatters. Invalid backend dates render an em dash; raw ISO values are never
used as date display copy.

## Native blockers

- Authenticated CV preview/download is implemented, but iOS and Android PDF
  viewer handoff still needs testing in signed development builds.
- The DB-backed staging verifier is green for the mobile envelopes, isolation,
  manager scope, revocation, confirmation and audited mutations. Signed native
  development builds still need physical-device API and file-handoff testing.
- EAS credentials, production builds, push delivery, TestFlight and store
  workflows remain intentionally untouched.
