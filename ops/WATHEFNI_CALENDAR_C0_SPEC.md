# Wathefni Calendar — C0 Spec Lock

**Date:** 2026-07-29 (Asia/Kuwait)  
**Status:** **LOCKED** — architecture + product specification (**C0 amendment A1** applied)  
**Mode:** Spec only — **do not write Calendar code**  
**Amendment A1:** Org-scope adapter; reminder vs timed event; interview edit routing; recurrence/resource readiness; candidate guest identity  
**Preserves:** Multi-User Waves 1–6 (roles, visibility, ownership, personal work, concurrency, team privacy / people pickers)  
**Forbids:** Parallel role, visibility, ownership, notification, or concurrency authorities  
**Prior art:** `ops/WATHEFNI_CALENDAR_ARCHITECTURE_REVIEW.md`, `ops/MULTI_USER_TENANT_RBAC_AUDIT.md` §8  

---

## C0 verdict

**PASS (spec locked).** Wathefni Calendar is a single-tenant event store with My / Team / Company **projections**, server-computed ACL detail levels, unique workflow links, Wave 5 OCC, Wave 4/6 personal notifications, and optional provider-neutral sync. Google/Outlook are channels only. Shared `GOG_ACCOUNT` is legacy transitional — not product architecture.

**Do not start C1 until §17 prerequisites are all PASS.**

---

## 1. Calendar authority (locked)

| Rule | Decision |
|---|---|
| Source of truth | **Wathefni Calendar** (`calendar_events` and related tables) |
| Google / Outlook | Optional **sync channels** only |
| Works offline of providers | **Required** — full product without Google or Outlook |
| Event cardinality | **One canonical event row** per logical meeting |
| User calendars | **Projections** of the same row — never per-user duplicate event copies |
| Interview schedule authority | Interview lifecycle remains authority for interview fields; Calendar **ensures** a linked event (same transaction or durable outbox) |
| My work (Wave 4) | **Not** My Calendar — queues stay separate |
| Reminders vs blocks | A **reminder** notifies only; it does **not** occupy calendar time unless the user creates a **timed personal event** |
| Interview-linked edits | Time / panel / status / cancel **must** go through Interview scheduling services — Calendar never bypasses lifecycle |

### Architecture diagram

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Company / tenant domain                      │
│  Waves 1–6: roles · visibility · ownership · queues · OCC ·     │
│             team privacy · people pickers · personal notify       │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Wathefni Calendar authority                      │
│  calendar_events ── attendees ── guests ── links ── reminders   │
│       │                 resources*        recurrence*            │
│       │                 sync_bindings*                           │
│       ▼                                                          │
│  ACL evaluator → detail_level (full|limited|busy_only|hidden)    │
│       │                                                          │
│       ├── Projection: My                                         │
│       ├── Projection: Team   (org_scope adapter → memberships) │
│       ├── Projection: Company (calendar.company)                 │
│       └── Free/busy API (privacy-safe)                           │
└───────────────┬─────────────────────────────┬───────────────────┘
                │                             │
                ▼                             ▼
     Workflow emitters                  Sync channels (optional)
     (interview ensure_link)            Google / Outlook
     unique (company, workflow, id)     one-way out in V1
                                        never silent-delete truth
```

\* Schema-ready in C1; product features later.

---

## 2. Views (locked)

Views are **query scopes** over one store. They are not separate calendars.

### 2.1 Organization / team authority (locked — adapter, not permanent coupling)

Calendar **must not** permanently define the company organization model as `manager_scopes.team_key`.

Calendar consumes a **canonical organization-scope abstraction** through an **adapter**. Today’s implementation source may be `manager_scopes`; future sources may be departments, branches, divisions, reporting teams, project teams, or multiple memberships — **without rewriting Calendar ACLs, APIs, or event projection rules**.

#### Canonical abstraction (Calendar-facing contract)

| Concept | Calendar contract | Notes |
|---|---|---|
| Org scope ID | `org_scope_id` (opaque string/uuid) | Stable within `company_code`; **not** a Calendar-owned org registry |
| Scope kind | `org_scope_kind` | `team\|department\|branch\|division\|reporting_team\|project_team\|other` |
| Membership | `S(actor) → set[org_scope_id]` | Multiple memberships allowed |
| Event binding | `calendar_event_org_scopes` (0..N) | Events may attach to multiple scopes |
| Display label | Adapter-provided | Never parse provider-specific columns in Calendar core |

**Required adapter interface (logical):**

```text
OrgScopeAdapter
  list_memberships(company, user_id) -> [{org_scope_id, kind, label, ...}]
  resolve_scopes(company, org_scope_ids) -> [{org_scope_id, kind, label, ...}]
  primary_scope_for_user(company, user_id) -> org_scope_id | null
  actor_in_any(company, user_id, org_scope_ids) -> bool
```

Calendar core, SQL projections, and ACL code depend **only** on this contract + `calendar_event_org_scopes` — never on `manager_scopes` columns directly.

#### Current adapter: `ManagerScopesOrgAdapter` (C1 default)

| Adapter field | Current source |
|---|---|
| `org_scope_id` | `manager_scopes.scope_id` (preferred) or synthetic `team:{company}:{team_key}` when `scope_id` unavailable |
| `org_scope_kind` | Map `scope_type` when present; else `team` |
| Label | `team_key` / branch display |
| Membership | Active `manager_scopes` for `dashboard_user_id` or linked phone **∪** `manager_scope_members` |
| Supporting filters | `branch_key`, `team_key` exposed only as adapter metadata — **not** Calendar schema PK |

#### Migration-safe rules

1. Event rows store **opaque `org_scope_id` values** (and optional denormalized `kind`), never `manager_scopes.team_key` as the irreversible primary key.  
2. A legacy nullable `team_key` column may exist only as **read-through metadata** during migration; new writes go through `calendar_event_org_scopes`.  
3. Swapping adapters (e.g. to `company_teams` / departments) is a **data backfill of org_scope_id mappings**, not a Calendar ACL redesign.  
4. C1 ships `ManagerScopesOrgAdapter` behind the interface; no other module may import manager_scopes from Calendar feature code.

#### Actor scope set and event scopes

```text
S(actor) = OrgScopeAdapter.list_memberships(company, actor).org_scope_ids

E.scopes = org_scope_ids attached to event (calendar_event_org_scopes)
```

Empty `S(actor)` is allowed (common for Company Admin / HR Admin without a scope row).

**Default event scopes at create:**

1. Explicit scopes from the client/API if set, else  
2. Organizer’s `primary_scope_for_user` if any, else  
3. No scopes (attendee/company visibility only).

#### Team Calendar UI

- If `S(actor)` is non-empty → Team switch enabled.  
- If `S(actor)` is empty **and** actor lacks `calendar.company` → Team switch **hidden**.  
- If `S(actor)` is empty **and** actor has `calendar.company` → optional “No team scope” empty guidance; Company remains oversight.

### 2.2 My Calendar — inclusion

Include event `E` iff **any**:

| # | Rule |
|---|---|
| M1 | Actor is `owner_user_id` or `organizer_user_id` |
| M2 | Actor is an **internal attendee** with status ≠ `removed` |
| M3 | Actor is `creator_user_id` **and** `E.visibility = private` (drafts they created) |
| M4 | `E` is a **timed personal event** owned by the actor (`event_type = personal_block` or equivalent, actor is owner) |

**Not My-inclusion:** Owning a **reminder** on someone else’s (or a shared) event does **not** put that event on My Calendar as a time block. Reminders only trigger notifications (§2.6).

**Exclude:** events that ACL evaluates to `hidden` for the actor.

**Detail level:** normally `full` for M1–M4; never below what ACL grants.

### 2.3 Team Calendar — inclusion

Include `E` iff ACL ≠ `hidden` **and** **any**:

| # | Rule |
|---|---|
| T1 | Actor matches My rules (M1–M4) — always see own participation |
| T2 | `E.visibility ∈ {team, company}` **and** `E.scopes ∩ S(actor) ≠ ∅` |
| T3 | `E.visibility = team` **and** `E.scopes` empty **and** actor has `calendar.manage` **and** same company (rare — prefer attaching org scopes) |

**Default detail for T2/T3 when actor is not attendee/owner/organizer:**

- Non–candidate-linked → `limited`  
- Candidate-linked → `busy_only` (see §3.3)

### 2.4 Company Calendar — inclusion

Include `E` iff actor has **`calendar.company`** **and** ACL ≠ `hidden` **and** **any**:

| # | Rule |
|---|---|
| C1 | `E.visibility = company` |
| C2 | Oversight busy view: `E.visibility ∈ {team, attendees_only}` **and** company policy `company_calendar_oversight_busy = true` (default **true** for owner/hr_admin/hr_manager) → return as `busy_only` unless also attendee (then full) |
| C3 | Actor is attendee/owner/organizer (full via My rules) |

**Never** include `visibility = private` in Company projection unless actor is attendee/owner/organizer.

### 2.5 Free/busy API

Separate endpoint from event detail. Returns only `{start, end, busy: true}` (and optional opaque `busy_id`) for actors allowed to see busy blocks. No titles, attendees, or candidate refs.

### 2.6 Personal timed events vs reminders (locked)

| Concept | Occupies calendar time? | Creates notification? | How created |
|---|---|---|---|
| **Timed personal event** | **Yes** — a real `calendar_events` row on My Calendar | Optional, via attached reminders | Explicit user create (`event_type` personal/hold/block) |
| **Reminder** | **No** — never a duplicate busy block by itself | **Yes** — fires at `fire_at` / offset | `calendar_reminders` row on an existing event |

**Hard rules:**

1. Creating a reminder **must not** insert a second event that blocks the same interval.  
2. A reminder without an event is invalid; personal “nudge myself at 3pm” with no meeting is modeled as a **timed personal event** (optionally with a reminder at start).  
3. My Calendar inclusion uses M1–M4 only — **not** “has reminder.”  
4. Reminder delivery uses Wave 4/6 personal notification routing (`audience=personal`).

---

## 3. Permissions and privacy (locked)

### 3.1 Permission keys (existing role authority only)

Add to `KNOWN_DASHBOARD_PERMISSIONS` / `ROLE_PERMISSIONS` in **C1** (not C0 code):

| Permission | Meaning |
|---|---|
| `calendar.read` | Open Calendar module; call projection APIs for scopes the actor is allowed |
| `calendar.manage` | Create/edit/cancel events where actor is organizer/owner or policy allows; manage attendees on those events |
| `calendar.company` | Company Calendar projection + oversight busy (C2) |
| `calendar.sync` | Connect/disconnect company sync; view sync health |
| `calendar.conflict_override` | Save despite attendee/resource conflicts (warning + audit required) |

Module gate: company module `calendar` (or entitlement alias agreed in C1). Pre-hire interview emitters also require existing `interviews` module where applicable.

### 3.2 Permission matrix by role

| Permission | owner | hr_admin | hr_manager | recruiter | hiring_manager | interviewer | payroll_operator | viewer | manager |
|---|---|---|---|---|---|---|---|---|---|
| `calendar.read` | Yes | Yes | Yes | Yes | Yes | Yes | **No** | Yes | Yes |
| `calendar.manage` | Yes | Yes | Yes | Yes | Limited* | **No** | **No** | **No** | Limited* |
| `calendar.company` | Yes | Yes | Yes | **No** | **No** | **No** | **No** | **No** | **No** |
| `calendar.sync` | Yes | Yes | **No** | **No** | **No** | **No** | **No** | **No** | **No** |
| `calendar.conflict_override` | Yes | Yes | Yes | **No** | **No** | **No** | **No** | **No** | **No** |

\*Limited = may manage events they organize / own / attend as organizer; may not edit others’ events; may not set `visibility = company` unless also oversight.

**Interviewer:** `calendar.read` only for projections that include assigned/attended events (My + busy where permitted). No create of company hiring events from Calendar (scheduling stays on interview APIs; linked event appears automatically).

**Payroll Operator:** no Calendar module (unless a future grant); payroll deadlines are later emitters.

### 3.3 Detail levels (locked)

| Level | Payload |
|---|---|
| `full` | Title, description, location, meet link, attendees (internal labels), guests (as permitted), source link summary, reminders, RSVP, status |
| `limited` | Title, time, location, busy; **no** candidate identity, **no** private notes, **no** full guest PII |
| `busy_only` | `start`, `end`, `busy=true`; title replaced with generic “Busy” / AR equivalent; no attendees/source |
| `hidden` | Omitted from result set |

Server computes `detail_level` on every read. UI must not infer from raw fields.

### 3.4 Candidate-linked protection (locked)

An event is **candidate-linked** when:

- `calendar_event_links.source_workflow` ∈ hiring sources (`interview`, `assessment_deadline`, `offer_deadline`, `candidate_followup`, …), **or**
- `calendar_events.sensitivity = candidate_confidential`, **or**
- metadata flag `candidate_linked = true`.

**Rules:**

1. Non-attendee / non-organizer / non-owner without `calendar.company` → at most `busy_only` (Team/Company).  
2. With `calendar.company` but not attendee → default `busy_only` for candidate-linked; policy may raise to `limited` (never full candidate dossier via Calendar).  
3. Full candidate name/app_key only at `full`, and only if Wave 2 application visibility would also allow the actor to see that application (reuse `require_prehire_application_visibility` / plan — **do not fork**).  
4. External sync titles for candidate-linked events use **limited external title** (e.g. “Interview” / role title only — no candidate name) unless policy `sync_include_candidate_name = true` (default **false**).  
5. Exports / ICS / WhatsApp / email apply the same detail level as the acting principal.

### 3.5 Organizer / owner / creator (locked)

| Field | Meaning | Default |
|---|---|---|
| `creator_user_id` | Who created the row | Actor at insert; immutable |
| `organizer_user_id` | Scheduling authority (edits, cancel, attendee changes) | Creator, or interview scheduler |
| `owner_user_id` | Accountability owner (may equal organizer) | Organizer; may follow job recruiter for interview-linked |

**Edit rights (non–interview-linked):** organizer or owner with `calendar.manage`, or oversight with `calendar.company` + manage.  
**Transfer:** organizer/owner or oversight; audited.  
**Interview-linked:** see §5.3 / §5.4 — Calendar UI and Calendar PATCH **must not** change interview time, panel, status, or cancellation directly.

---

## 4. Long-term event model (locked schema)

C1 implements tables; C0 locks names/columns/semantics. Recurrence and resources are **nullable / satellite tables** — no product UI until later waves.

### 4.1 `calendar_events`

| Column | Type | Notes |
|---|---|---|
| `event_id` | uuid PK | |
| `company_code` | text NOT NULL | Tenant |
| `event_type` | text NOT NULL | `meeting\|interview\|personal_block\|deadline\|hold\|out_of_office\|other` — **not** `reminder` (reminders are §4.5 rows) |
| `title` | text NOT NULL | |
| `title_ar` | text NULL | |
| `description` | text NULL | |
| `description_ar` | text NULL | |
| `visibility` | text NOT NULL | `private\|attendees_only\|team\|company` |
| `sensitivity` | text NOT NULL DEFAULT `normal` | `normal\|candidate_confidential\|sensitive` |
| `status` | text NOT NULL | `tentative\|confirmed\|cancelled\|completed` |
| `start_at` | timestamptz NOT NULL | UTC instant |
| `end_at` | timestamptz NOT NULL | |
| `timezone` | text NOT NULL | IANA; default company TZ |
| `all_day` | boolean NOT NULL DEFAULT false | |
| `location` | text NULL | |
| `meeting_url` | text NULL | |
| `org_scope_kind_hint` | text NULL | Optional denormalized kind; membership via `calendar_event_org_scopes` |
| `legacy_team_key` | text NULL | **Migration-only** metadata; not ACL authority |
| `creator_user_id` | text NOT NULL | |
| `organizer_user_id` | text NOT NULL | |
| `owner_user_id` | text NULL | |
| `version` | int NOT NULL DEFAULT 1 | Wave 5 OCC |
| `created_at` / `updated_at` | timestamptz | |
| `updated_by_user_id` | text NULL | |
| `cancelled_at` | timestamptz NULL | Soft cancel |
| `completed_at` | timestamptz NULL | |
| `recurrence_rule` | text NULL | RRULE; unused in V1 product — see §4.8 |
| `recurrence_timezone` | text NULL | IANA TZ for RRULE evaluation; may differ from display `timezone` |
| `recurrence_series_id` | uuid NULL | Stable series identity across versions |
| `recurrence_series_version` | int NOT NULL DEFAULT 1 | Bumps on series-wide edits |
| `recurrence_parent_id` | uuid NULL | Exception / moved occurrence → master instance |
| `is_recurrence_exception` | boolean NOT NULL DEFAULT false | |
| `recurrence_original_start_at` | timestamptz NULL | Original occurrence start for moved/cancelled singles |
| `metadata` | jsonb NOT NULL DEFAULT `{}` | |

**Indexes:** `(company_code, start_at, end_at)`, `(company_code, visibility, start_at)`, `(company_code, organizer_user_id, start_at)`, `(company_code, status, start_at)`, `(company_code, recurrence_series_id)`.

### 4.1b `calendar_event_org_scopes`

| Column | Notes |
|---|---|
| `event_id` + `company_code` | |
| `org_scope_id` | Opaque — from OrgScopeAdapter |
| `org_scope_kind` | Copied at attach time for filtering |
| Unique `(event_id, org_scope_id)` | |

This is the **only** org binding Calendar ACL uses for Team projection.

### 4.2 `calendar_attendees` (internal)

| Column | Notes |
|---|---|
| `attendee_id` uuid PK | |
| `event_id` + `company_code` | |
| `user_id` text NOT NULL | `dashboard_users` |
| `role` | `organizer\|required\|optional\|resource_owner` |
| `rsvp_status` | `needs_action\|accepted\|declined\|tentative\|removed` |
| `response_at` | |
| `is_organizer` boolean | |
| Unique `(event_id, user_id)` where not removed | |

### 4.3 `calendar_guests` (external)

| Column | Notes |
|---|---|
| `guest_id` uuid PK | |
| `event_id` + `company_code` | |
| `email` / `phone` / `display_name` | Contact channels / labels only — **not** a second candidate master |
| `guest_kind` | `candidate\|external\|other` |
| `person_key` | Prefer existing **candidates** authority when known |
| `app_key` | Prefer existing **applications** authority when known |
| `rsvp_status` | Same enum as attendees |
| `invite_channel` | `email\|whatsapp\|none` |
| `last_invited_at` | |

**Identity rules (locked):**

1. External guests are **never** `dashboard_users`.  
2. Candidate guests **must reference** existing candidate/application authority (`person_key` and/or `app_key`) when available — Calendar must **not** invent a parallel candidate identity store.  
3. Email/phone/display_name on the guest row are **delivery and snapshot fields** for invites; canonical hiring identity remains candidates/applications.  
4. If only an email is known at invite time, store it for delivery and **link** `person_key`/`app_key` as soon as the workflow provides them (interview ensure path).  
5. ACL / Wave 2 visibility for candidate-linked events continues to use application visibility — not guest-row free text.

### 4.4 `calendar_event_links` (workflow uniqueness)

| Column | Notes |
|---|---|
| `link_id` uuid PK | |
| `company_code` | |
| `event_id` | |
| `source_workflow` | text — see §5 |
| `source_record_id` | text |
| `link_status` | `active\|detached\|superseded` |
| **UNIQUE** `(company_code, source_workflow, source_record_id)` WHERE `link_status = 'active'` | |

### 4.5 `calendar_reminders`

| Column | Notes |
|---|---|
| `reminder_id` | |
| `event_id`, `company_code` | **Required** — reminder always attaches to an existing event |
| `user_id` NULL | NULL = all internal attendees; set for per-user personal notify prefs |
| `kind` | `event\|personal` — notification preference only; **does not** create a time block |
| `offset_minutes` | int (relative to event start) **or** absolute via `fire_at` |
| `channel` | `in_app\|whatsapp\|email` |
| `fire_at` | timestamptz |
| `sent_at` / `status` | |

See §2.6: reminders never duplicate calendar busy blocks.

### 4.6 `calendar_event_audit`

Append-only: `event_id`, `company_code`, `actor_user_id`, `action`, `before`, `after`, `created_at`, `request_id`.  
Also call existing `record_admin_audit` for company Activity where appropriate.

### 4.7 Resources-ready (no product yet)

`calendar_resources (resource_id, company_code, resource_type, name, capacity, timezone, metadata, is_active)`  
`calendar_resource_bookings (booking_id, event_id, resource_id, company_code, status, start_at, end_at)`  

Unused by V1 UI; conflict service may ignore until resources are activated.

**Activation requirement (locked):** when resource booking ships, overlap protection **must** be enforced with **database-enforced exclusion** (e.g. PostgreSQL `EXCLUDE USING gist` on `(resource_id, tstzrange(start_at,end_at))` WHERE status active) **or** equivalent transactional locking that prevents two concurrent confirmed bookings of the same resource over overlapping intervals. Application-only checks are **not** sufficient for activation.

### 4.8 Recurrence-ready (no product yet — requirements locked)

V1 creates **single instances only** (`recurrence_rule IS NULL`). When recurrence is enabled later, the model **must** support without redesign:

| Requirement | Spec |
|---|---|
| Recurrence timezone | `recurrence_timezone` (IANA) drives RRULE occurrence generation; distinct from display `timezone` when needed |
| Series identity | `recurrence_series_id` stable across edits |
| Series versioning | `recurrence_series_version` increments on series-wide changes; OCC still uses per-row `version` for the master / written instances |
| Occurrence exceptions | Exception rows with `is_recurrence_exception = true`, `recurrence_parent_id` → master, `recurrence_original_start_at` identifying the logical occurrence |
| Moved occurrences | Exception with new `start_at`/`end_at` and same `recurrence_original_start_at` |
| Cancelled single occurrences | Exception (or tombstone row) with `status = cancelled` for that `recurrence_original_start_at` — **do not** delete series history silently |
| Expansion | Expand only inside requested `[start,end]` windows; never materialize unbounded series |

Do **not** implement recurrence product or expansion engines in C1–C4.

### 4.9 Sync (provider-neutral)

**`calendar_sync_connections`**

| Column | Notes |
|---|---|
| `connection_id` | |
| `company_code` | |
| `provider_key` | `google\|microsoft\|…` |
| `mode` | `company\|user\|legacy_operator` |
| `owner_user_id` NULL | For per-user OAuth later |
| `status` | `not_connected\|connected\|error\|disconnected` |
| `credentials_ref` | Encrypted secret pointer |
| `external_calendar_id` | |
| `last_sync_at` / `last_error` | |

**`calendar_sync_bindings`**

| Column | Notes |
|---|---|
| `binding_id` | |
| `company_code`, `event_id`, `connection_id` | |
| `provider_event_id` | |
| `sync_status` | `queued\|synced\|partially_synced\|failed\|conflict` |
| `last_pushed_version` | Matches `calendar_events.version` |
| `last_error` | |
| Unique `(connection_id, event_id)` | |
| Unique `(connection_id, provider_event_id)` WHERE provider_event_id IS NOT NULL | |

### 4.10 Company calendar policy (settings)

Stored under company settings (Wave 5 OCC) key `calendar_policy`:

```json
{
  "timezone": "Asia/Kuwait",
  "work_week": [0,1,2,3,4],
  "work_day_start": "09:00",
  "work_day_end": "17:00",
  "booking_hold_seconds": 120,
  "company_calendar_oversight_busy": true,
  "sync_include_candidate_name": false,
  "external_delete_policy": "ignore",
  "default_event_visibility": "attendees_only",
  "default_interview_visibility": "attendees_only"
}
```

---

## 5. Workflow uniqueness (locked)

### 5.1 Rule

```text
ensure_calendar_event(company, source_workflow, source_record_id) -> event_id

At most ONE active link per (company_code, source_workflow, source_record_id).
```

- Create if missing; update same `event_id` on reschedule; cancel/complete mirrors workflow.  
- Detach only with `calendar.company` + audit (`link_status = detached`).  
- Prefer durable **outbox** after workflow commit if not same DB transaction.

### 5.2 V1 source allowlist

| `source_workflow` | Creates timed event? | Notes |
|---|---|---|
| `interview` | **Yes** for live types | `source_record_id = interview_id` |
| `manual` | Yes | Optional link; user-created meetings |
| `personal_block` | Yes | Explicit timed personal event (§2.6) — **not** a reminder row |
| `interview_async_deadline` | Only if explicit deadline set | Not default for async video |

**Not a source_workflow:** plain `calendar_reminders` — they attach to events and do not create linked timed duplicates.

**Async video interviews:** do **not** emit `interview` timed events. Optional later deadline emitter uses `interview_async_deadline`.

### 5.3 Live interview sync semantics

| Interview action | Calendar |
|---|---|
| Schedule | Interview service commits → `ensure` linked event; attendees = panel; guest references candidate/application authority |
| Reschedule | **Only** via Interview reschedule service → updates same linked event |
| Cancel | **Only** via Interview cancel path → `status = cancelled` on linked event |
| Complete / no-show / status | **Only** via Interview status APIs → mirror onto linked event |
| Assign interviewer / panel | **Only** via Interview assign APIs → upsert Calendar attendees |

### 5.4 Interview-linked editing authority (locked)

**Interview scheduling remains the business authority** for interview-linked calendar events.

| Mutating field / intent | Allowed writer |
|---|---|
| `start_at` / `end_at` / timezone / duration | Interview schedule / reschedule service only |
| Panel / internal attendees (interview panel) | Interview assign / reschedule service only |
| Interview status / cancellation | Interview lifecycle / cancel / status APIs only |
| Meeting link when owned by interview Meet path | Interview / video invitation path |
| Non-interview cosmetic fields (optional notes display) | May be Calendar-managed only if explicitly allowlisted and **cannot** diverge schedule truth |

**Hard rules:**

1. `PATCH /dashboard/calendar/events/{id}` on an event with active `source_workflow = interview` **must reject** schedule/panel/status/cancel changes (`409` / `422` `interview_authority_required`) and direct clients to Interview APIs.  
2. Calendar **must never** bypass interview lifecycle validation, conflict rules, module gates, or assignment scope.  
3. `ensure_calendar_event` is a **projection/sync** from Interview → Calendar, not a second scheduler.  
4. Guest candidate identity on ensure uses §4.3 (`person_key` / `app_key` from the application).

---

## 6. Scheduling rules (locked)

### 6.1 Timezone

- Store `start_at`/`end_at` in UTC.  
- Persist `timezone` for display and working-hours evaluation.  
- Default timezone = company calendar policy (fallback `Asia/Kuwait`).  
- All-day: date in event timezone → UTC bounds per policy.

### 6.2 Working hours

Conflict service flags (warning) when event falls outside policy work week/hours for **required internal attendees**, unless `all_day` or override.

### 6.3 Conflict checks (V1)

| Check | Authority |
|---|---|
| Attendee double-book | Overlap on `calendar_attendees.user_id` vs other non-cancelled events |
| Organizer double-book | Same |
| Leave overlap | Read `leave_requests` approved overlapping dates (soft warning if tables present) |
| Shift overlap | Read `shift_assignments` (soft warning) |
| Working hours | Policy (§4.10) |
| Interview legacy | Fold existing panel/candidate interview conflict into **shared conflict service** so Interviews and Calendar do not diverge |

**Booking hold (V1.1 acceptable if needed for UX):** optional `calendar_holds` TTL = `booking_hold_seconds` (default 120).

### 6.4 Conflict override

- Requires `calendar.conflict_override`.  
- Client must send `override_conflicts=true` + `override_reason`.  
- Audit: actor, conflicts snapshot, reason, event_id, version.  
- Without permission → `409 scheduling_conflict` with conflict list (no silent save).

### 6.5 External guest RSVP / reschedule

| Action | Behavior |
|---|---|
| Invite | Email and/or WhatsApp; personal to guest channel — not HR broadcast |
| Accept / decline / tentative | Tokenized public/candidate link updates `calendar_guests.rsvp_status` |
| Reschedule request | Creates request record / pending action; **does not** move event until organizer confirms — interview-linked confirms **only** via Interview reschedule |
| Reminder | Personal to guest + internal attendees per reminder rows |

---

## 7. External sync policy (locked)

| Topic | Decision |
|---|---|
| No provider | Full product works |
| V1 direction | **Wathefni → provider only** |
| V1 providers | Google optional; Outlook **not implemented** |
| Inbound external delete | **`external_delete_policy = ignore`** (default) — never silent-delete Wathefni |
| Inbound external edit | Ignored in V1 |
| Idempotency | Push keyed by `(connection_id, event_id, event_version)` via bindings |
| Retry | `queued` → backoff → `failed`; manual retry; never duplicate provider events (unique provider id) |
| Disconnect | Mark connection `disconnected`; keep Wathefni events; stop pushes; bindings retained for reconnect |
| Reconnect | Resume push from current versions; repair bindings |
| Candidate titles | Limited external title; `sync_include_candidate_name` default false |
| Legacy `GOG_ACCOUNT` | `mode = legacy_operator` transitional only |

### 7.1 Migration off shared operator calendar

1. C1–C2: native events + interview ensure; dual-write legacy Google path.  
2. Agenda UI reads **Wathefni projections**.  
3. Backfill interviews with `calendar_event_id` → event + link + binding (`legacy_operator`).  
4. Flag `WATHEFNI_CALENDAR_AUTHORITY=native`.  
5. New tenants: prefer no operator calendar / company connection later.  
6. Deprecate operator channel per tenant when native + (optional) company connection healthy.  
7. UI never labels operator Google as “your Wathefni Calendar.”

---

## 8. Product UX (locked direction)

Inspiration constraints → Wathefni direction (premium, compact, bilingual-ready):

| Surface | Lock |
|---|---|
| Primary desktop view | Compact **week** grid (default) |
| Range switch | Day / Week / Month |
| Scope switch | My / Team / Company (Team per §2.1 visibility rules) |
| Filters | Event type, status, candidate-linked busy vs full, mine-only |
| Event cards | Time, short title (ACL-safe), attendance dots, status chip |
| Detail | Side workspace / drawer — not a cluttered modal dump |
| Attendees | People-picker (Wave 6); show name + role; no raw UUIDs |
| Mobile | **Agenda-first** list by day; week optional secondary |
| Overview | Mini calendar + **max 5** upcoming items + “View full calendar” |
| Empty states | Clear; Team hidden when `S(actor)` empty (no org memberships) |
| Motion | Subtle; 2–3 intentional transitions max |
| EN/AR + RTL | First-class via existing locale/`dir` |

**Not in Core UX:** resource room finder, recurrence editor, Outlook connect, two-way sync conflict UI.

---

## 9. Core release vs later

### Core Calendar release (= C1–C4 product outcome)

- Canonical event authority + OCC + audit  
- My + Company projections; Team when rules apply  
- Live interview integration (unique link)  
- Manual events + timed personal blocks + event reminders (no duplicate blocks)  
- Conflict checking + override permission  
- RSVP (internal + guest) + reminders  
- Full Calendar page UX (§8)  
- Overview panel (≤5)  

### Later

- Rooms/resources product  
- Advanced recurrence  
- Additional workflow emitters (assessments, offers, onboarding, leave, shifts, payroll, …)  
- Per-user OAuth  
- Outlook  
- Two-way sync  

---

## 10. ACL matrix (role × visibility → max detail)

Legend: F=`full` L=`limited` B=`busy_only` H=`hidden`  
Assumes actor is **not** attendee/organizer/owner unless noted. Attendee/organizer/owner always get **F** (subject to Wave 2 for deep candidate fields).

### 10.1 Non–candidate-linked

| Role | private | attendees_only | team (in S) | team (not in S) | company |
|---|---|---|---|---|---|
| owner / hr_admin / hr_manager (`calendar.company`) | H* | B | L | B | L |
| recruiter / hiring_manager / manager | H | H | L | H | H |
| interviewer / viewer | H | H | B if in S else H | H | H |
| payroll_operator | H | H | H | H | H |

`S` = actor org-scope memberships from OrgScopeAdapter (§2.1).

\*Private remains H for oversight unless attendee — no silent private browse.

### 10.2 Candidate-linked

| Role | private | attendees_only | team (in S) | company |
|---|---|---|---|---|
| owner / hr_admin / hr_manager | H* | B | B | B |
| recruiter / HM (not on event) | H | H | B if in S else H | H |
| interviewer (not assigned) | H | H | H | H |
| viewer | H | H | H | H |

Attendee/assigned interviewer/organizer: **F**, with candidate identity only if Wave 2 application visibility allows.

---

## 11. Notification policy (reuse Waves 4–6)

| Trigger | Audience | Source example |
|---|---|---|
| Invited / time changed / cancelled | Personal → internal attendees + organizer | `calendar_event_changed` |
| Reminder due | Personal | `calendar_reminder` |
| RSVP required / received | Personal | `calendar_rsvp` |
| Attendee added/removed | Personal to affected user | `calendar_attendee_changed` |
| Conflict detected on save attempt | Personal to actor | `calendar_conflict` |
| Guest invite / reminder | Guest channel only | `calendar_guest_invite` |
| Company-wide event created | Company or team per visibility | `calendar_company_event` |
| Sync failure (company connection) | Company ops / admins with `calendar.sync` | `calendar_sync_failed` |

No broadcast of personal calendar changes to all HR. Every send includes `audience` + `source`.

---

## 12. Concurrency (reuse Wave 5)

- Mutations require `expected_version` (and/or `expected_updated_at`).  
- Stale → **409** with conflict envelope + human message.  
- No hard page locks; optional booking hold only.  
- Same FE message pattern as Wave 5.

---

## 13. Implementation waves C1–C6

| Wave | Name | Deliverable | Code? |
|---|---|---|---|
| **C0** | Spec lock | This document | No |
| **C1** | Event spine | Schema, permissions on roles, OCC, audit, My + Company APIs, busy_only, people-picker attendees, manual events, Calendar shell UX | Yes |
| **C2** | Interview link | Unique links; live interview ensure/update/cancel; async excluded; dual-write legacy Google; agenda reads native | Yes |
| **C3** | Conflicts + Overview + Team | Shared conflict service; Team projection; Overview ≤5; day/week/month | Yes |
| **C4** | Notify + RSVP + reminders | Personal calendar notifications; guest RSVP links; reminder worker | Yes |
| **C5** | Google channel v2 | Sync connections/bindings; one-way out; migrate off `GOG_ACCOUNT` for new flows | Yes |
| **C6** | Free/busy polish + policy UX | Free/busy API, working-hours UX, sync health settings | Yes |

**Core release exit:** C1–C4 green in production with Waves 1–6 regression, cross-tenant proofs, candidate busy_only proofs, health 200, rollback/restore.

**C7+ (backlog):** resources, recurrence UI, more emitters, per-user OAuth, Outlook, two-way sync.

---

## 14. API sketch (non-binding paths; C1 may refine names)

| Method | Path | Purpose |
|---|---|---|
| GET | `/dashboard/calendar/events?scope=mine\|team\|company&start=&end=` | Projection list (ACL applied) |
| GET | `/dashboard/calendar/events/{id}` | Detail at computed level |
| POST | `/dashboard/calendar/events` | Manual create (`expected` N/A) |
| PATCH | `/dashboard/calendar/events/{id}` | Update + `expected_version`; **rejects** interview schedule/panel/status/cancel (§5.4) |
| POST | `/dashboard/calendar/events/{id}/rsvp` | Internal RSVP |
| GET | `/dashboard/calendar/free-busy?user_ids=&start=&end=` | Busy blocks |
| GET | `/dashboard/prehire/overview/calendar` | ≤5 upcoming + mini metadata |
| GET/PUT | `/dashboard/calendar/policy` | Policy with Wave 5 OCC |

Interview schedule/reschedule/cancel remain under existing interview routes and call `ensure_calendar_event`.

---

## 15. Exact projection pseudocode

```text
function project(scope, actor, window):
  rows = query events in company ∩ time window ∩ status not irrelevant
  out = []
  for E in rows:
    level = acl_detail(actor, E)   # may be hidden
    if level == hidden: continue
    if scope == mine and not matches_my(actor, E): continue
    if scope == team and not matches_team(actor, E): continue
    if scope == company and not matches_company(actor, E): continue
    out.append(serialize(E, level))
  return out
```

`matches_*` as §2. `acl_detail` as §3 + §10.

---

## 16. Conflict authority summary

| Authority | Owner |
|---|---|
| Canonical time truth | `calendar_events.start_at/end_at`; interview-linked times **only** via Interview schedule/reschedule |
| Double-book detection | Shared conflict service over Calendar attendees (+ legacy interview check folded in) |
| Override | `calendar.conflict_override` + reason + audit |
| Leave/shift | Advisory warnings in V1 (do not hard-block unless policy later says so) |
| Provider free/busy | Not V1 |

---

## 17. PASS/FAIL prerequisites before C1

| # | Prerequisite | Gate |
|---|---|---|
| 1 | C0 + amendment A1 accepted by product + eng | **PASS** (this amendment) |
| 2 | Waves 1–6 remain authoritative; no parallel RBAC planned | **PASS** (stated) |
| 3 | Org-scope **adapter** contract accepted; `manager_scopes` is current adapter only | **PASS** (locked §2.1 A1) |
| 4 | Permission keys + role matrix accepted | **PASS** (locked §3) |
| 5 | Candidate-linked busy_only rules accepted | **PASS** (locked §3.4) |
| 6 | V1 sources: interview live + manual + personal_block; reminders ≠ blocks | **PASS** (locked §2.6 / §5) |
| 7 | Interview-linked edits route only through Interview services | **PASS** (locked §5.4) |
| 8 | Sync = optional one-way out; no silent external delete | **PASS** (locked §7) |
| 9 | `GOG_ACCOUNT` migration sequence accepted | **PASS** (locked §7.1) |
| 10 | Core UX direction accepted (week default, Overview ≤5) | **PASS** (locked §8) |
| 11 | Candidate guests reference person_key/app_key authority | **PASS** (locked §4.3) |
| 12 | Recurrence + resource readiness documented (not implemented) | **PASS** (locked §4.7–4.8) |
| 13 | No Calendar code until C1 kickoff | **PASS** (this task) |
| 14 | Module entitlement name (`calendar`) reserved in catalog plan | **PASS** — `ops/WATHEFNI_CALENDAR_C1_KICKOFF.md` §1 |
| 15 | Outbox vs same-transaction ensure choice recorded in C1 design note | **PASS** — durable outbox (`C1_KICKOFF` §2) |
| 16 | C1 design note names `OrgScopeAdapter` + `ManagerScopesOrgAdapter` module paths | **PASS** — `calendar_org_scope.py` (`C1_KICKOFF` §3) |

**C1 coding may begin when items 1–16 are PASS and a subsequent task explicitly requests C1 implementation.** Kickoff note: `ops/WATHEFNI_CALENDAR_C1_KICKOFF.md`.

### Remaining architectural blockers before C1 code

| Blocker | Severity | Resolution |
|---|---|---|
| Module / outbox / adapter kickoff locks | **None** | Resolved in `WATHEFNI_CALENDAR_C1_KICKOFF.md` |
| Future org model beyond manager_scopes | **None for C1** | Adapter contract already migration-safe |
| Recurrence / rooms | **None for C1** | Explicitly deferred; schema-ready |

---

## 18. Non-goals (C0 / Core)

- Building Calendar UI or schema in this wave  
- Implementing recurrence or rooms  
- Outlook / two-way sync  
- Replacing Wave 4 Overview work queues with Calendar  
- Using shared Google operator calendar as multi-user ACL  
- Parallel notification or OCC frameworks  

---

## 19. Source map (future implementation)

| Concern | Planned home (C1+) |
|---|---|
| Spec | `ops/WATHEFNI_CALENDAR_C0_SPEC.md` (this file) |
| Review | `ops/WATHEFNI_CALENDAR_ARCHITECTURE_REVIEW.md` |
| Roles / permissions | `app.py` `ROLE_PERMISSIONS` (extend, don’t fork) |
| Org scopes | `OrgScopeAdapter` ← current `ManagerScopesOrgAdapter` (`manager_scopes` / members) |
| Event↔org | `calendar_event_org_scopes` (opaque `org_scope_id`) |
| People pickers | `prehire_team_directory` + `/dashboard/team/people` |
| OCC | `concurrency_safety` |
| Personal notify | `notify_prehire_personal_assignees` / calendar equivalents with audience+source |
| Interview ensure | `interview_service` / lifecycle → calendar link outbox |
| Legacy Google | `interview_service` `_google_*` → bindings `legacy_operator` |

---

## 20. Sign-off

| Field | Value |
|---|---|
| Spec version | C0 / 2026-07-29 + **amendment A1** |
| Architecture | Locked (A1 clarifications applied) |
| Product UX direction | Locked |
| Implementation | **Not started** |
| Next wave | **C1 Event spine** (only after §17; still no code in this task) |

### Amendment A1 changelog (exact)

1. **Team authority** — Replaced permanent `manager_scopes.team_key` coupling with `OrgScopeAdapter` + opaque `org_scope_id` / `calendar_event_org_scopes`; documented `ManagerScopesOrgAdapter` as current implementation.  
2. **Personal reminders** — Separated timed personal events (blocks) from reminders (notify-only); My inclusion no longer treats reminders as calendar blocks.  
3. **Interview-linked editing** — Added §5.4: schedule/panel/status/cancel only via Interview services; Calendar PATCH rejects authority bypass.  
4. **Recurrence readiness** — Documented timezone, exceptions, moved/cancelled occurrences, series versioning (§4.8).  
5. **Resource readiness** — Required DB EXCLUDE / transactional overlap protection when activated (§4.7).  
6. **Candidate guest identity** — Guests reference `person_key` / `app_key`; no parallel candidate authority (§4.3).

**Stop after C0 amendment. Do not write Calendar code. Do not begin C1.**
