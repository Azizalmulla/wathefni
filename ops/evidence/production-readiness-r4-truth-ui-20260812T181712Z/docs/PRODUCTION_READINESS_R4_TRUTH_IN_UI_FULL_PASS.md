# PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS

**Status:** QUALIFIED / frozen for owner review
**Stamp:** `PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS`
**Phase:** R4 — Truth-in-UI (remediation, scoped)
**Date:** 2026-08-12
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Baseline:** `ops/PRODUCTION_READINESS_R1_AUDIT.md` (owner accepted)
**Qualify:** `ops/qualify-production-readiness-r4-truth-in-ui.sh`
**Freeze:** `ops/PRODUCTION_READINESS_R4_TRUTH_IN_UI_FREEZE_AMENDMENT.md`
**Evidence:** `ops/evidence/production-readiness-r4-truth-ui-20260812T181712Z/`

**Scope:** R1 P0-7, P1-10, P1-11, P1-12, P1-13, P1-14, P1-16, P1-17, plus directly related truth-state defects found while qualifying. No broad redesign. No Wave 4/6 surface build. R2 and R3 stay frozen.

---

## 1. Result

| Gate | Result |
|---|---|
| Dashboard vitest (named + full suite) | **89 files, 481 passed, 0 failed** |
| Local unit contracts (no DB) | **40 passed, 0 failed** (`R4_TRUTH_IN_UI_UNIT_PASS`) |
| Classified truth-state scan | **0 P0 named-surface leftovers** (`R4_SCAN_OK`; 315 pattern hits classified) |
| Staging deploy of orchestrator sources | **STAGING_COPY_OK** |
| Staging DB notification suppression | **9 passed, 0 failed** (`R4_TRUTH_IN_UI_DB_PASS`) |
| Live deployed staging service | **5 passed, 0 failed** (health 200) |
| Waves 1–6 unit freezes + C1–C7 + authority contracts | **green** (all rc=0, 0 failed) |
| R2 security unit + staging DB | **84/0 unit, 69/0 DB** |
| R3 data-safety unit + staging DB | **61/0 unit, 18/0 DB** |
| Internal-auth staging | **10/0, ALL CHECKS PASSED** |
| Open R4 blockers | **none** |

This stamp is **not** `PRODUCTION_READY` and authorises no rollout. Stop here for owner review. **Do not begin R5** (Wave 4/6 Surface Programme) automatically.

---

## 2. What changed

### Shared data-state primitive

`apps/wathefni-dashboard/src/pages/shared/dataState.tsx` is the reusable contract:

| Kind | Meaning |
|---|---|
| `loading` | Request in flight; skeleton, not an empty list |
| `empty` | Successful read returned no items |
| `error` | Network/server failure; retry; **never** “no interviews / no work” |
| `unavailable` | Capability off or not included |
| `forbidden` | Actor lacks permission |
| `ready` | Successful non-empty payload |

`resolveListDataState()` refuses to collapse `error` into `empty`. Named blocker surfaces use `ResourceState` (EN/AR). Other pages were not redesigned.

### P0-7 — API failure is not empty success

| Surface | Failure | Genuine empty |
|---|---|---|
| Interviews | `listError` → error/retry (`interviews-list-error`) | Successful `[]` → `interviewEmpty` (`interviews-list-empty`) |
| Overview work queue | `workQueueError` → error/retry (`overview-work-error`) | Successful empty items → scoped empty copy (`overview-work-empty`) |
| PostHire departments | `orgDepartmentsError` + retry; free-text still available | Empty org list only after a successful load |
| PostHire app access | `appAccessLoadError` → error/retry; session shows Unknown, not “Not active” | Inactive session only after a successful read |
| PostHire pending status | `pendingStatusLoadError` → error/retry | Pending card mounts only when requests exist |

App passes `interviewsError` / `interviewsLoading` from the query. Failed interviews never render `interviews?.interviews \|\| []` as a queue.

### P1-12 — Overview composition

`workspaceAuthority.overview.showWorkQueue` and `showRolePriority` are passed into `OverviewPage` and control mounting.

- Capability hidden → section does not mount (no empty shell).
- Sparse tenant: no work-queue shell, no role-priority shell, calendar already gated.
- Recruiter composition matrix updated: settings group no longer appears without manage permission.

### P1-10 / P1-11 / P1-17 — dead affordances

- `PostHireDeliveryCenter` and `PostHireDeliveryCenterPlaceholder` removed. `LazyPostHireDeliveryCenter` removed.
- Governed profile no longer shows disabled “Link to Job / Not implemented in this phase”. Hidden until the capability ships.
- `?page=migration-sync` remaps to `employees` + `view=migration` and opens `MigrationSyncShell`. Setup/ops hrefs and Setup Console catalog cards use `/dashboard?page=employees&view=migration`. No fake page was added.

### P1-13 — role strings

Removed nonexistent `'hr'` / `'admin'` fallbacks from Requisitions, Probation, Preboarding, and `canViewRestrictedCandidates`. UX gating is permission-based. Backend stays authoritative. Canonical roles (`owner`, `hr_admin`, `hr_manager`, `manager`, …) remain the server contract.

### P1-14 — Alerts & Delivery page gate

`nav.notifications` now requires `permissionAnyOf` matching the existing action gate (`users.manage` or `{leave,onboarding,compliance,attendance,shifts,payroll}.manage`).

Unauthorized user:

- no nav entry
- `openPage` / sticky URL remap fail closed (same `pageAvailableForSummary` / `navIds` path as other gated pages)
- page itself renders `ResourceState` forbidden if reached

Authorized user with a manage permission still opens Alerts.

### P1-16 — notification module suppression

Central gate inside `deliver_employee_notification` (no second engine):

| Flow | Source module |
|---|---|
| `leave_decision` / `leave` | `leave` |
| `shift` | `shifts` |
| `onboarding` | `onboarding` |
| `compliance` | `compliance` |
| `bank` | `employee_app` |
| `app_activation` | `employee_app` |
| `payroll` / `attendance` | matching module |
| unmapped | still allowed (safe debt) |

Disabled module → `{ ok: False, error: source_module_disabled, delivery_status: module_disabled, suppressed: True }` and **no new** `employee_messages` row. Historical rows stay. Re-enable allows a new send.

Outbound-shift, reminder-frequency, and soak harnesses now entitle the modules they exercise.

---

## 3. Error / empty state matrix (named surfaces)

| Surface | Loading | Genuine empty | Error | Unavailable / hidden | Forbidden |
|---|---|---|---|---|---|
| Interviews | skeleton | “No interviews match this queue…” | “Could not load interviews” + retry | Interviews nav already module-gated | interview.manage is action-level |
| Overview work queue | skeleton | “No personal/company work…” | “Could not load your work” + retry | `showWorkQueue === false` → not mounted | same capability |
| Overview role priority | n/a (summary payload) | not mounted when no role | n/a | `showRolePriority === false` → not mounted | same capability |
| PostHire departments | n/a (inline) | empty select after success | error + retry, type-in remains | n/a | employees.manage on add |
| PostHire app access | existing card | inactive after success | error + Unknown session | company app-off banner | roster manage |
| PostHire pending status | n/a | card hidden when none | error + retry | n/a | status permissions |
| Alerts & Delivery | existing loading | “No delivery issues…” | existing error banner | module relevance | page + nav forbidden |

EN and AR copy exists for the named ResourceState surfaces.

---

## 4. Role / capability matrix (R4)

| Actor (fixture) | Alerts nav/page | Work queue | Role priority | Restricted candidates view |
|---|---|---|---|---|
| Owner (`users.manage` + hiring perms) | yes | yes | yes | yes (`users.manage`) |
| Recruiter (hiring operate, no `*.manage` for delivery) | **no** | yes (`candidates.read` / `candidate.manage`) | yes (`jobs.create` / `candidate.manage`) | no |
| Viewer (`prehire.read` only) | no | no | no | no |
| Leave operator (`leave.manage`) | yes (if Alerts module-relevant) | depends on hiring perms | depends | no |

Frontend remains UX gating only.

---

## 5. Notification suppression proof (staging)

Isolated tenants `R4ONEF1D1A` / `R4OFFEF1D1A` on `wathefni_staging`:

- leave **on** → send is not `source_module_disabled`
- leave **off** → suppressed; **no new** `employee_messages` row
- historical row on the disabled tenant **preserved**
- leave re-enabled → send is not suppressed

Live staging process (health 200) exposes `source_module_for_notification_flow` with the same map.

---

## 6. Dead-affordance cleanup

| Item | Disposition |
|---|---|
| `PostHireDeliveryCenter` always-null export | removed |
| `PostHireDeliveryCenterPlaceholder` | removed |
| `LazyPostHireDeliveryCenter` | removed |
| Link to Job / “Not implemented in this phase” | hidden |
| `?page=migration-sync` | remapped to Employees Migration Sync |
| Setup Console connected-systems hrefs | `/dashboard?page=employees&view=migration` |

---

## 7. Qualification commands

```bash
bash ops/qualify-production-readiness-r4-truth-in-ui.sh
```

Staging: `root@76.13.63.68`, orchestrator `/opt/wathefni/staging/orchestrator`, DB `wathefni_staging`, marker `wathefni-staging-hr2-isolation-v1`. No production customer data.

Direct URL reauthorization: dashboard `openPage` + sticky remap use `workspaceAuthority.navIds` (server bootstrap permissions). Alerts APIs remain backend-authoritative.

---

## 8. Blockers

None for this scoped R4 stamp.

---

## 9. Safe debt (explicitly not R4)

- Remaining `data \|\| []` / `?? []` after a **successful** payload or for local UI chrome (scan: 82 named-review, 229 display defaults). Not treated as P0 when the read already distinguished error.
- R1 P2 Leave tab `{ ok: true, types: [], balances: [], requests: [] }` — not expanded.
- Legacy `send_custom_employee_message` when an outbound **flow flag** is off is not the shared engine; the central gate is `deliver_employee_notification`.
- Unmapped notification flows still send.
- HR Web SPA is proven by vitest; this stamp deployed the **orchestrator** notification gate to staging. Shipping the dashboard JS to a host is a release step, not R5.
- P1-1..P1-9 (HR mobile / Wave 4–6 completeness), P1-15 (restricted-candidates **server** enforcement), P1-18+, remaining P2.
- Waves 4 and 6 still have no product surfaces. That is R5.

---

## 10. Freeze

R4 is frozen. See `ops/PRODUCTION_READINESS_R4_TRUTH_IN_UI_FREEZE_AMENDMENT.md`.

**Stop. Do not begin R5 automatically.**
