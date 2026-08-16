# Wathefni Calendar — C1 Kickoff Design Note

**Date:** 2026-07-29 (Asia/Kuwait)  
**Status:** **KICKOFF LOCKED** — operational prerequisites 14–16 resolved  
**Mode:** Design note only — **do not implement Calendar features in this task**  
**Parent specs:** `ops/WATHEFNI_CALENDAR_C0_SPEC.md` (incl. Amendment A1), `ops/WATHEFNI_CALENDAR_ARCHITECTURE_REVIEW.md`  
**Preserves:** Multi-User Waves 1–6  

---

## Kickoff verdict

**PASS — ready to begin C1 coding** after this note is accepted.

| C0 §17 item | Decision | Gate |
|---|---|---|
| **14** Module entitlement `calendar` | Reserved below (§1) | **PASS** |
| **15** Interview → Calendar ensure | **Durable outbox** after interview commit (§2) | **PASS** |
| **16** OrgScope adapter paths | Locked module paths (§3) | **PASS** |

C0 items 1–13 remain PASS. No remaining architectural blockers.  
**This document does not start C1 implementation.**

---

## 1. Module entitlement (prerequisite 14)

### Decision

| Field | Lock |
|---|---|
| Canonical module key | **`calendar`** |
| Compatibility aliases | **None required** for launch. Optional normalize-only aliases (not separate products): `wathefni_calendar` → `calendar` if ever seen in imports — **do not** alias `interviews` or Google/Meet keys to `calendar` |
| Catalog home | `wathefni-orchestrator/module_catalog.py` → `MODULE_CATALOG` |
| Alias map home | `module_catalog.py` → `MODULE_ALIASES` (only if alias added) |
| Tenant enablement | `company_modules` row (`company_code`, `module_key='calendar'`, `enabled`) — registry authoritative via `configured_company_modules` / `company_has_module` |
| Runtime gating | `require_entitlement(context, "calendar", "<calendar.* permission>")` and/or `company_has_module(company, "calendar")` on Calendar routes |
| Platform master flag | **None** for C1 (same pattern as most catalog modules). Dark-launch via `company_modules.enabled=false` by default until operator enables |
| Suite / placement | `suite="pre_hire"`, `audience="hr"`, `order=28` (after `interviews`=25), `depends_on=()`, `recommended_with=("pre_hiring", "interviews")` |
| Legacy implications | **Do not** add `calendar` to `LEGACY_IMPLIED_MODULES` from `pre_hiring` — Calendar is opt-in |
| Setup Console protection | **Not** in `SETUP_PROTECTED_COMPATIBILITY_MODULES` for C1 |

### Catalog entry (C1 code shape — not applied in this kickoff)

```python
ModuleDefinition(
    "calendar",
    "Calendar",
    "pre_hire",
    "hr",
    28,
    depends_on=(),
    recommended_with=("pre_hiring", "interviews"),
    recommendation_copy=(
        "Company calendar with My/Team/Company projections. "
        "Works without Google or Outlook. Recommended with Pre-Hiring and Interviews."
    ),
)
```

### Gating authority chain

```text
MODULE_CATALOG / MODULE_BY_KEY  (product definition)
        │
        ▼
company_modules.enabled         (tenant entitlement)
        │
        ▼
company_has_module / effective_company_modules
        │
        ▼
require_entitlement(..., "calendar", "calendar.read|manage|...")
        │
        ▼
ROLE_PERMISSIONS calendar.*     (Wave 1 role authority — extend, don’t fork)
```

### Permissions added in C1 (from C0 §3 — not new authorities)

`calendar.read`, `calendar.manage`, `calendar.company`, `calendar.sync`, `calendar.conflict_override` on existing `ROLE_PERMISSIONS` / `KNOWN_DASHBOARD_PERMISSIONS`.

### Navigation

C1 Calendar **shell** may appear in dashboard nav only when `calendar` is effective **and** actor has `calendar.read`. No Overview mini-calendar until C3 (excluded from C1).

---

## 2. Interview → Calendar ensure (prerequisite 15)

### Chosen approach

**Durable outbox after interview commit** — **not** same-transaction dual-write that can roll back Interview truth.

### Why (matches kickoff guarantees)

| Requirement | How outbox satisfies |
|---|---|
| Interview truth commits safely | Interview schedule/reschedule/cancel commits first; outbox row written in **same interview transaction** as a durable intent, or immediately after commit via transactional outbox pattern |
| Calendar ensure idempotent | Worker keys on unique link + idempotency key; `ensure` upserts one event |
| Failures retryable | Outbox `pending` → worker retry with backoff |
| No duplicate linked events | DB unique active `(company_code, source_workflow, source_record_id)` on `calendar_event_links` |
| Interview not rolled back if Calendar fails | Calendar worker failure leaves interview committed; outbox stays `pending`/`failed` for replay |

**Rejected:** Pure same-DB-transaction “interview + calendar event must commit together” as the **only** path — a Calendar schema/lock failure would undo a valid interview. Optional **best-effort sync call after commit** may exist for latency, but **authority for durability is the outbox**.

### Transaction boundaries

```text
[Interview request]
   │
   ├─ BEGIN
   │    mutate candidate_interviews / assignments / schedule_operations
   │    INSERT calendar_link_outbox (pending)  -- same TX as interview commit
   │  COMMIT   ← interview truth durable
   │
   └─ (async) Calendar outbox worker
         BEGIN
           claim outbox row
           ensure_calendar_event (idempotent)
           UNIQUE link prevents duplicates
           mark outbox processed | failed
         COMMIT
```

Alternative acceptable implementation of “same TX as interview”: classic transactional outbox (row in interview TX). **Not acceptable:** requiring Calendar event row success inside the interview TX as a hard dependency.

### Outbox schema (C2 implements; locked now for C1 awareness)

`calendar_link_outbox`

| Column | Type | Notes |
|---|---|---|
| `outbox_id` | uuid PK | |
| `company_code` | text NOT NULL | |
| `source_workflow` | text NOT NULL | e.g. `interview` |
| `source_record_id` | text NOT NULL | e.g. `interview_id` |
| `operation` | text NOT NULL | `ensure\|cancel\|complete\|sync_attendees` |
| `idempotency_key` | text NOT NULL | See below |
| `payload` | jsonb NOT NULL | Snapshot needed for ensure (times, panel refs, app_key, person_key, …) |
| `status` | text NOT NULL | `pending\|processing\|processed\|failed\|dead` |
| `attempt_count` | int NOT NULL DEFAULT 0 | |
| `next_attempt_at` | timestamptz | |
| `last_error` | text NULL | |
| `processed_at` | timestamptz NULL | |
| `created_at` / `updated_at` | timestamptz | |
| **UNIQUE** `(company_code, idempotency_key)` | | |
| Index `(status, next_attempt_at)` | | claim queue |

**C1 note:** Outbox table may be created in C1 schema migrations as **unused infrastructure**, or deferred to C2 — either is fine. **Interview integration code that enqueues/processes is C2-only.**

### Idempotency key

```text
idempotency_key = "{source_workflow}:{source_record_id}:{operation}:{interview_schedule_operation_id|event_version_token}"
```

Examples:

- `interview:{interview_id}:ensure:{schedule_operation_id}`  
- `interview:{interview_id}:cancel:{cancel_operation_id}`  

Replay of the same key is a no-op success after first process.

### Ensure uniqueness enforcement

```text
calendar_event_links
  UNIQUE (company_code, source_workflow, source_record_id)
  WHERE link_status = 'active'
```

`ensure_calendar_event`:

1. Lookup active link → update existing `event_id`  
2. Else insert event + active link  
3. Race: unique violation → re-select link and update  

### Failure and replay

| State | Behavior |
|---|---|
| Worker crash mid-process | Row returns to `pending` after lease timeout; retry safe due to idempotency + unique link |
| Repeated failure | `failed` with backoff; after N attempts → `dead` + admin audit / sync health signal (C5+) |
| Manual replay | Operator/admin replays `dead`/`failed` by idempotency key; still cannot duplicate links |
| Calendar module disabled | Outbox may still queue; worker no-ops or defers until module enabled — **interview remains valid** |

### C1 vs C2

| Concern | Wave |
|---|---|
| Lock outbox design (this note) | Kickoff |
| Optionally create empty outbox table in migrations | C1 allowed |
| Interview service enqueue + worker + ensure from interview | **C2 only** |

---

## 3. Organization scope adapter paths (prerequisite 16)

### Locked module layout (flat orchestrator modules — match existing style)

| Symbol | Path | Responsibility |
|---|---|---|
| `OrgScopeRef`, `OrgScopeMembership` | `wathefni-orchestrator/calendar_org_scope.py` | Dataclasses / TypedDicts for opaque scopes |
| `OrgScopeAdapter` (Protocol) | `wathefni-orchestrator/calendar_org_scope.py` | Interface only — **no** SQL to `manager_scopes` |
| `ManagerScopesOrgAdapter` | `wathefni-orchestrator/calendar_org_scope.py` | **Current** adapter implementation reading `manager_scopes` / `manager_scope_members` |
| `get_org_scope_adapter()` | `wathefni-orchestrator/calendar_org_scope.py` | Factory; default `ManagerScopesOrgAdapter`; swap later without Calendar ACL changes |
| Scope resolution helpers | `wathefni-orchestrator/calendar_org_scope.py` | `list_memberships`, `resolve_scopes`, `primary_scope_for_user`, `actor_in_any` |
| Event↔scope bindings | Table `calendar_event_org_scopes`; accessors in `wathefni-orchestrator/calendar_events.py` (or `calendar_store.py`) | Persist opaque `org_scope_id` only |
| ACL / projections | `wathefni-orchestrator/calendar_acl.py`, `calendar_projections.py` | Call **only** `OrgScopeAdapter` + bindings — **never** import/query `manager_scopes` directly |
| HTTP routes | `app.py` (thin) | Delegate to calendar_* modules |

### Interface contract (locked)

```text
OrgScopeAdapter
  list_memberships(company_code, user_id) -> list[OrgScopeMembership]
  resolve_scopes(company_code, org_scope_ids) -> list[OrgScopeRef]
  primary_scope_for_user(company_code, user_id) -> str | None   # org_scope_id
  actor_in_any(company_code, user_id, org_scope_ids) -> bool
```

### Future adapter replacement

1. Implement e.g. `CompanyTeamsOrgAdapter` in same module or `calendar_org_scope_company_teams.py`.  
2. Switch `get_org_scope_adapter()` (env/settings).  
3. Backfill `calendar_event_org_scopes.org_scope_id` mappings.  
4. **No** changes to ACL matrix or projection rules in `calendar_acl.py` / `calendar_projections.py`.

### Forbidden couplings

- `calendar_acl.py`, `calendar_projections.py`, Calendar routes must **not** `SELECT` from `manager_scopes`.  
- Smoke test (C1): grep/import guard or unit test that projection code uses adapter mocks only.

---

## 4. C1 implementation contract

### In scope (exact deliverables)

| # | Deliverable |
|---|---|
| 1 | Schema + migrations: `calendar_events`, `calendar_attendees`, `calendar_guests`, `calendar_event_links`, `calendar_event_org_scopes`, `calendar_event_audit`, recurrence/resource **nullable columns/tables per C0** (unused), optional empty `calendar_link_outbox` |
| 2 | Role permissions: add C0 calendar.* keys to `KNOWN_DASHBOARD_PERMISSIONS` / `ROLE_PERMISSIONS` |
| 3 | Module gating: `calendar` in `MODULE_CATALOG` + route entitlement checks |
| 4 | Event OCC: Wave 5 `concurrency_safety` / `expected_version` on PATCH |
| 5 | Audit: `calendar_event_audit` + `record_admin_audit` where appropriate |
| 6 | ACL evaluator: detail levels `full\|limited\|busy_only\|hidden` (C0 §3 / §10) |
| 7 | Projections: **My** + **Company** only (Team projection APIs may stub 501/empty until C3 — or implement read path behind adapter if cheap; **Team UI switch not required in C1**) |
| 8 | Busy-only serialization |
| 9 | Manual timed events create/edit/cancel (non–interview-linked) |
| 10 | Internal attendees via Wave 6 people picker API |
| 11 | External guests with `person_key`/`app_key` fields (no interview ensure yet) |
| 12 | Workflow link table + uniqueness (manual/`personal_block` links as needed) |
| 13 | **Calendar shell only**: route + minimal page chrome (list/agenda or simple day strip) — not full week/month product UX |
| 14 | `OrgScopeAdapter` + `ManagerScopesOrgAdapter` + bindings write path on create |
| 15 | Feature flag / enablement: module off by default for existing tenants unless explicitly enabled in evidence plan |

### Explicitly excluded from C1

| Excluded | Deferred to |
|---|---|
| Interview integration (enqueue, worker, ensure from interview APIs) | **C2** |
| Full week / month UX, Team switch polish, Overview ≤5 panel | **C3** |
| Notifications + RSVP guest token flows | **C4** |
| Reminders worker | **C4** |
| Google sync / `GOG_ACCOUNT` migration execution | **C5** |
| Recurrence product / expansion | **C7+** |
| Resources product + EXCLUDE activation | **C7+** |
| Free/busy polish API productization | **C6** |
| Per-user OAuth / Outlook / two-way sync | Later |

### C1 API minimum (shell)

| Method | Path | C1 |
|---|---|---|
| GET | `/dashboard/calendar/events?scope=mine\|company&start=&end=` | Yes |
| GET | `/dashboard/calendar/events/{id}` | Yes |
| POST | `/dashboard/calendar/events` | Yes (manual / personal_block) |
| PATCH | `/dashboard/calendar/events/{id}` | Yes + OCC; reject interview-linked authority fields if link exists |
| GET/PUT | `/dashboard/calendar/policy` | Optional thin stub OK |

Interview routes unchanged in C1.

---

## 5. Implementation order (C1 coding sequence)

1. `module_catalog.py` — add `calendar`  
2. Permissions on roles  
3. Schema migrations (events, attendees, guests, links, org_scopes, audit; optional outbox)  
4. `calendar_org_scope.py` — Protocol + ManagerScopes adapter + factory  
5. `calendar_events` / store helpers — CRUD + OCC  
6. `calendar_acl.py` — detail level  
7. `calendar_projections.py` — My + Company  
8. Thin `app.py` routes + entitlement  
9. Dashboard shell page (minimal) + nav gate  
10. Smokes + qualification (§6)  
11. Evidence stamp, health, rollback drill  

---

## 6. Safety and qualification

### Migration rollback

- Migrations must be reverse-friendly: drop new calendar_* tables / columns in down migration or documented SQL rollback pack under evidence.  
- Module catalog entry removal is code rollback; `company_modules` rows for `calendar` left disabled or deleted in rollback script.  
- **Never** migrate by rewriting `candidate_interviews` as the calendar store.

### Feature flags / enablement

| Lever | Use |
|---|---|
| `company_modules.calendar` | Primary tenant gate (default **disabled** until enable in deploy plan) |
| Code deploy | Routes 403 when module off |
| Optional env | Not required; avoid new master_flag unless dark-launch needs platform kill switch later |

### Required tests (C1)

| Class | Assert |
|---|---|
| Cross-tenant | Event for company A never returned for company B context |
| ACL | busy_only / hidden / full per C0 matrix for My/Company |
| Candidate privacy | Candidate-linked (even manual sensitivity) redacts for non-attendee Company view |
| Concurrency | Stale PATCH → 409 with Wave 5 envelope |
| Adapter isolation | Projections/ACL unit tests use mock adapter — no direct manager_scopes |
| Uniqueness | Two active links same source → DB/ensure rejection |
| Module gate | No `calendar.read` / module off → 403 |
| Waves 1–6 regression | Run existing wave smokes 1–6 after C1 deploy |

### Explicit non-regressions

- No changes to Wave 2 visibility policy defaults  
- No changes to ownership / personal work / concurrency contracts except **reuse**  
- No Google operator calendar behavior change in C1  
- No interview schedule path behavior change in C1  

---

## 7. PASS/FAIL readiness to begin C1 coding

| Gate | Status |
|---|---|
| C0 + A1 accepted | **PASS** (prior) |
| Kickoff §1 module key reserved | **PASS** |
| Kickoff §2 outbox chosen | **PASS** |
| Kickoff §3 adapter paths locked | **PASS** |
| C1 scope / exclusions clear | **PASS** |
| Safety plan defined | **PASS** |
| Calendar feature code written | **FAIL** (correct — not started) |

### Final decision

**READY TO BEGIN C1 IMPLEMENTATION** in a subsequent task that explicitly says “implement C1.”

**This kickoff task stops here.**

---

## 8. Sign-off

| Field | Value |
|---|---|
| Document | `ops/WATHEFNI_CALENDAR_C1_KICKOFF.md` |
| Prerequisites 14–16 | **Resolved PASS** |
| Ensure mechanism | Durable outbox (interview commits independently) |
| Module key | `calendar` @ `module_catalog.MODULE_CATALOG` |
| Adapter | `calendar_org_scope.py` :: `OrgScopeAdapter` / `ManagerScopesOrgAdapter` |
| Next task | **Implement C1** (separate explicit request) |

**Stop after kickoff note. Do not begin C1 implementation yet.**
