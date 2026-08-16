# Wathefni Calendar — Long-Term Architecture Review

**Date:** 2026-07-29 (Asia/Kuwait)  
**Mode:** Read-only architecture review — **do not build yet**  
**Audience:** Product + engineering decision record before Calendar implementation  
**Related:** `ops/MULTI_USER_TENANT_RBAC_AUDIT.md` §8 / calendar gaps; Waves 1–6 multi-user foundation  

---

## Executive verdict

**The core vision is the right long-term model.**

Canonical single-event authority inside Wathefni, with My / Team / Company as **projections** (not duplicated event copies), Google/Outlook as **optional sync channels**, and full operation without either provider — that matches how durable calendar systems scale and correctly refuses to make today’s shared `GOG_ACCOUNT` primary calendar the product truth.

What must change before implementation is mostly **scope discipline and missing contracts**, not a rewrite of the vision:

1. Treat My / Team / Company as **views over one event store**, not three event stores.
2. Define **event ACL detail levels** (`full` / `limited` / `busy_only` / `hidden`) as first-class, computed server-side.
3. Put **workflow linkage uniqueness** and **interview migration** in the foundation.
4. Cut V1 ruthlessly: interviews + reminders + conflicts + Overview strip first; full HR universe and two-way OAuth later.
5. Plan an explicit **exit from the shared Google operator calendar** — Calendar cannot ship by pretending `GOG_ACCOUNT` is multi-user.

**Do not build Calendar until the prerequisites in §8 are decided in writing.**

---

## 1. Is this the best long-term model?

### Keep (strong)

| Principle | Why it is correct |
|---|---|
| Wathefni is calendar authority | Survives provider outages, disconnects, and multi-provider future |
| One event, many authorized projections | Avoids fan-out copies, sync storms, and divergent edits |
| Google / Outlook optional | Matches current interview design (Wathefni commit → optional sync) |
| Role + ownership + assignment + attendees + policy | Reuses Waves 1–6 instead of parallel RBAC |
| Workflow-linked uniqueness | Prevents interview + calendar + task triple booking |
| Async video ≠ scheduled slot | Correct product semantics |
| Personal notifications for personal changes | Matches Wave 4/6 notify contract |
| Date-range / indexed / paginated queries | Required for large tenants |
| Overview = compact strip only | Prevents Overview becoming a second calendar product |

### Adjust (important)

| Vision wording | Better long-term framing |
|---|---|
| “Each company has one shared calendar system” | One **tenant calendar domain** (one store + policies), not one mega shared calendar everyone reads |
| “Team calendar” as peer of My/Company | A **filter / audience**, backed by team membership rules — not a separate calendar database |
| “Work assigned to me” on My calendar | **My work ≠ My calendar**. Queue items become events only with a real time window or explicit reminder |
| Full event model in one shot | Ship a **core schema** early; defer recurrence exceptions, rooms, two-way sync |

### Reject / avoid

| Anti-pattern | Risk |
|---|---|
| Duplicate event rows per employee | Divergent edits, impossible truth, sync hell |
| Overloading `candidate_interviews` as company calendar | Blocks leave/shifts/payroll; pollutes hiring lifecycle |
| Treating shared `GOG_ACCOUNT` as “the company calendar” | No per-user ACL; not multi-user |
| Parallel role / visibility / ownership / notify / OCC stacks | Breaks Waves 1–6 |
| Two-way sync as V1 default | Conflict resolution dominates before product value |

**Bottom line:** Projection-based single store is best. Implement as **events + attendees + links + ACL evaluator + projections**, not three calendars that sync to each other.

---

## 2. What is missing

### A. Foundational contracts (must decide before code)

1. **Projection algebra** — exact rules for My / Team / Company inclusion.
2. **Detail ACL levels** — `full` | `limited` | `busy_only` | `hidden` (hidden = not returned).
3. **Team definition** — `manager_scopes`? department? explicit calendar teams? Without this, Team calendar is undefined.
4. **Organizer vs owner vs creator** — who edits, cancels, transfers, overrides conflicts.
5. **Guest model** — external candidates are not `dashboard_users`; email/WhatsApp invite + RSVP mirrored on the event.
6. **Source link uniqueness** — `(company_code, source_workflow, source_record_id)` → at most one active calendar event.
7. **Working-hours / company calendar policy** — timezone, work week, holidays, booking rules, conflict override policy.
8. **Module entitlement** — `calendar.read` / `calendar.manage` / `calendar.company` / `calendar.sync` under existing permission authority.
9. **Confidentiality for candidate-linked events** — busy-only default for non-attendees even under `shared_company`.
10. **Migration policy** for existing interview `calendar_event_id` rows and old Google events.

### B. Data model pieces not named clearly enough

| Missing piece | Why |
|---|---|
| `calendar_events` (first-party) | Does not exist today; greenfield required |
| `calendar_attendees` (internal user_id **or** external guest) | Panel today is interview-specific only |
| `calendar_event_links` (unique source binding) | Dedup authority |
| OCC / version fields | Reuse Wave 5 pattern |
| `calendar_resources` + bookings | Optional later; schema should allow |
| `calendar_sync_connections` + `calendar_sync_bindings` | Company vs per-user OAuth, provider IDs, retry |
| Soft-delete / cancel tombstones | Sync + audit need cancelled rows |
| Recurrence master + exceptions | Only if recurrence is in scope; else defer |
| Free/busy API separate from detail API | Privacy-critical |

### C. Behavioral gaps

- Short TTL **booking hold** during multi-attendee scheduling (DB conflict alone is not enough UX).
- Idempotent workflow emitters (`ensure` calendar event for source X).
- Disconnect semantics: remove external mirrors without deleting Wathefni (default).
- External inbound delete: ignore / conflict / optional policy — default **never silent delete**.
- EN/AR + RTL for chrome and invitation copy.
- Cross-tenant leakage tests as a Calendar ship gate.

### D. Product boundaries vs existing surfaces

| Existing surface | Relationship |
|---|---|
| Overview My work / Company work (Wave 4) | Action debt queue — **not** the calendar |
| Interviews agenda API | Consumer/adapter during migration |
| Post-hire leave/shifts upcoming | Future emitters; not V1 |
| Shared Google operator sync | **Channel to retire**, not the ACL model |

---

## 3. What is overcomplicated (simplify)

1. **Every HR workflow as V1 emitters** — multi-quarter program, not first ship.
2. **Team + Company + personal + resources + recurrence + two-way Google + Outlook** together.
3. **“Work assigned to me” as calendar by default** — spam risk; prefer explicit reminders.
4. **Per-user OAuth + company mailbox + two-way sync** as day-one.
5. **Hard page locks** — keep Wave 5 OCC + optional short booking holds.
6. **Materialized per-user copies for performance** — premature; indexes + server ACL first.

### Simplified mental model

```text
Workflow truth (interview, leave, …)
        │ ensure_link (unique)
        ▼
 calendar_events  ←── attendees / resources / reminders
        │
        ├── ACL evaluator → detail level
        ├── Projection APIs: mine | team | company | free_busy
        └── Sync adapters (optional): Google / Outlook
```

One store. Many projections. Optional channels.

---

## 4. What must exist before implementation

### Already shipped (reuse — do not reinvent)

| Wave | Reuse |
|---|---|
| 1 Role taxonomy | Calendar permissions on existing roles |
| 2 Visibility policy | Candidate-linked confidentiality vs shared/assigned/hybrid |
| 3 Ownership | Organizer/owner; recruiter/HM as optional default attendees |
| 4 Personal work | Personal notify routing — no company broadcast of RSVPs |
| 5 Concurrency | `expected_version` + 409 conflict envelope |
| 6 Team privacy + people pickers | Attendee pickers via `/dashboard/team/people` |

### Must decide / spec before coding (C0)

1. Team membership definition for Team calendar.
2. Permission keys and who sees Company calendar.
3. Default visibility for interview-linked events.
4. Busy-only rules for non-attendees.
5. Sync strategy V1 (recommend: Wathefni → Google **one-way**, optional).
6. Migration plan for existing interview Google events.
7. V1 source allowlist (recommend: **live interviews + manual events + personal reminders**).
8. Module gating / tenant entitlement.
9. Conflict override permission + audit.
10. Recurrence in V1? (**Recommend: out** — single instances only.)

### Must not block on

- Custom `tenant_control_roles` cutover.
- Outlook.
- Full leave/shift/payroll emitters.
- Realtime collaborative presence.

---

## 5. V1 vs later

### V1 — Canonical Calendar spine

- `calendar_events` + attendees + source links + OCC + audit.
- Projections: **My** + permissioned **Company**; **Team** only with a locked team definition (else defer label).
- ACL detail levels including **busy-only**.
- Auto ensure/update/cancel from **live interviews only**; async video excluded unless explicit deadline event.
- Manual create/edit/cancel for entitled users.
- Conflict check: Wathefni overlaps + working hours + leave (read) + attendee double-book; override with permission + audit.
- Personal notifications for create/change/cancel/reminder/RSVP.
- Overview: today + next + ≤5 items + “View full calendar”.
- Date-range APIs, indexes, pagination.
- External: optional Google **one-way out** — not required for Wathefni to work.

### V1.1 / V2

- Team polish + availability grid.
- Rooms/resources.
- Assessment / offer / onboarding deadline emitters.
- Per-user Google OAuth mirrors.
- Soft booking holds.
- Rich internal RSVP.

### Later

- Two-way sync + inbound conflict UI.
- Microsoft Outlook / Graph.
- Recurrence + exceptions.
- Payroll / training / probation / shift emitter catalog.
- Projection materialization if metrics demand it.

---

## 6. Personal / Team / Company views

These are **query scopes**, not storage partitions.

### My calendar

Include if actor is owner/organizer, internal attendee, or has a personal reminder (optional: workflow owner when policy says so).  
Exclude others’ private events.

### Team calendar

Include if visibility is team/company **and** actor shares team scope, or actor is attendee/owner.  
Non-attendee default: **limited or busy-only**.  
**Requirement:** pick one primary team resolver (`manager_scopes` or department).

### Company calendar

Include if actor has company-calendar permission **and** event/policy allows.  
Map to Wave 1 oversight (owner / hr_admin / hr_manager). Recruiter/HM/Interviewer/Viewer do not get full company detail by default.

### Response shape

Every list/detail returns `scope`, `detail_level`, omitted (not blanked) fields for non-full, and notification `audience`/`source` when relevant.

---

## 7. Event ACL model

### Inputs

Event visibility × actor role/permissions × attendee membership × team membership × linked workflow visibility × company policy.

### Levels

| Level | Sees |
|---|---|
| `full` | Title, description, attendees, location, link, source, candidate refs if permitted |
| `limited` | Title/time/location; no candidate PII / private notes |
| `busy_only` | Start/end/busy; no sensitive title |
| `hidden` | Not in result set |

### Hard rules

1. Server computes ACL — UI never decides.
2. Candidate-linked: non-attendees ≤ `busy_only` unless oversight + policy allow more.
3. Private: attendees + organizer only (default).
4. Export/ICS/WhatsApp/email use the same ACL.
5. Attendee pickers use Wave 6 collaboration directory (name + role).

---

## 8. External sync strategy

### Principles

- Wathefni event ID is primary.
- Provider IDs on `calendar_sync_bindings` (not forever only on interview rows).
- States: `not_connected | queued | synced | partially_synced | failed | conflict`.
- External delete does **not** delete Wathefni unless explicit policy — default ignore.
- Idempotent push keyed by `(connection_id, event_id, event_version)`.

### Connection modes

| Mode | V1? |
|---|---|
| None (pure Wathefni) | Yes — default |
| Company-connected calendar | Optional |
| Per-user OAuth | V2 |
| Platform `GOG_ACCOUNT` | Transitional legacy only |

### Direction

- V1: one-way out (Wathefni → provider).
- V2: optional inbound for user connections with conflict UI.
- Later: two-way company room calendars.

### Provider abstraction

Keep `provider_key` (`google`, `microsoft`, …). Do not Google-hardcode the product API; Outlook stays unimplemented until Graph OAuth is designed.

---

## 9. Workflow-linked events (dedup)

```text
ensure_calendar_event(company, source_workflow, source_record_id) -> event_id
UNIQUE ACTIVE (company_code, source_workflow, source_record_id)
```

- Create once; updates mutate the same event; cancel/complete mirrors status.
- **Live interviews** → ensure linked event (panel + candidate guest).
- **Async video** → no timed event by default.
- Interview lifecycle APIs remain interview authority; Calendar ensure via same transaction or durable outbox after commit.
- Recommended: `calendar_link_outbox` for retry/idempotency (same spirit as `interview_schedule_operations`).

---

## 10. Migrating off shared Google operator calendar

### Current constraint

Interviews optionally sync to `GOG_ACCOUNT` → Google `primary`. Candidate + panel are invitees on that **shared operator mailbox**. Fields live on `candidate_interviews`. This is **not** multi-user Calendar.

### Sequence

1. Ship Wathefni Calendar spine + interview emitters.
2. Dual-write: interview updates native event **and** legacy Google path.
3. Dashboard agenda reads Wathefni projections.
4. Add company-connected Google (tenant-owned) or per-user mirrors; stop new reliance on platform operator where possible.
5. Backfill: interviews with `calendar_event_id` → `calendar_events` + link + binding.
6. Cutover flag `WATHEFNI_CALENDAR_AUTHORITY=native`.
7. Deprecate operator calendar for migrated tenants; keep Meet path until replaced.
8. UI must not claim “your Google Calendar is Wathefni” during transition.

---

## 11. Security / privacy risks

| Risk | Mitigation |
|---|---|
| Company calendar leaks candidate names | Busy-only / limited ACL; Wave 2 interaction tests |
| Team directory PII for invites | Wave 6 people picker; explicit guest email with permission |
| Shared Google operator cross-talk | Migrate off; transitional only |
| Export/ICS bypasses ACL | Redact on every export path |
| Sync pushes sensitive titles to personal Google | Limited external title policy for candidate-linked events |
| Free/busy inference | Coarse buckets; rate limits |
| Notification broadcast of RSVP | Personal routing only (Wave 4/6) |
| Cross-tenant ID guessing | Tenant checks on every get |

---

## 12. Scale risks

| Risk | Mitigation |
|---|---|
| Full company calendar load | Require `[start,end]` window |
| ACL over huge sets in app memory | SQL predicates then redact |
| N×N conflict checks | Attendee overlap SQL; cap panel size |
| Heavy Overview joins | Compact endpoint; max 5; optional cached counts |
| Sync storms | Outbox + version + backoff |
| Recurrence expansion | Defer; expand only in window if added |

**Minimum indexes:** `(company_code, start_at, end_at)`, `(company_code, attendee_user_id, start_at)`, unique active source link, `(company_code, visibility, start_at)`.

---

## 13. Availability and conflicts

Vision is right; stage it.

- **V1:** Wathefni overlaps, working hours, timezone normalization, leave overlap (read), override with permission + warning + audit.
- **Later:** rooms, shifts, provider free/busy fetch.
- Fold existing interview panel/candidate conflict checks into a **shared conflict service** so Interviews and Calendar do not diverge.

---

## 14. Notifications

| Kind | Audience |
|---|---|
| Invited / changed / cancelled / reminder / RSVP | Personal → attendees + organizer |
| Conflict on my booking | Personal |
| Company-wide event | Company or team |
| Company connector sync failure | Company ops / admins |

Every send audit includes `audience` + `source`. Do not notify all HR on every interview reschedule.

---

## 15. Recommended implementation waves

| Wave | Name | Outcome |
|---|---|---|
| **C0** | Spec lock | ACL matrix, team definition, V1 allowlist, sync policy, Google migration signed off |
| **C1** | Event spine | Schema, OCC, audit, My + Company, busy-only, people-picker attendees |
| **C2** | Interview link | Unique workflow link; live interview ensure/update/cancel; async excluded |
| **C3** | Conflicts + Overview | Shared conflict service; Overview ≤5; full calendar page |
| **C4** | Personal notify | Attendee-targeted calendar notifications |
| **C5** | Google channel v2 | Bindings; one-way out; leave `GOG_ACCOUNT` for new flows |
| **C6** | Team + free/busy | Team scope; availability grid |
| **C7+** | Emitters / OAuth / Outlook / rooms / recurrence | Roadmap |

**V1 done = C1–C4 green** with Waves 1–6 regression + cross-tenant + busy-only ACL proofs.

---

## 16. Direct answers

| Question | Answer |
|---|---|
| Best long-term model? | **Yes** — single Wathefni authority + projections + optional sync |
| Missing? | ACL levels, team definition, link uniqueness, sync bindings, `GOG_ACCOUNT` migration, module perms, outbox, busy-only API |
| Overcomplicated? | Too many V1 sources; two-way sync; recurrence; Team as separate store; My work ≡ My calendar |
| Simplify? | Views not stores; V1 = interviews + manual + reminders; one-way sync later |
| Before implementation? | C0 decisions (§4 / §8) |
| V1 vs later? | §5 |
| Security / scale? | §11 / §12 |
| Views / ACLs / sync / dedup / migration / waves? | §§6–10, 15 |

---

## 17. Final recommendation

**Approve the vision as the north star**, with binding amendments before any build:

1. **Projections, not copies.**
2. **Server ACL detail levels including busy-only.**
3. **Unique workflow link table.**
4. **V1 source allowlist: live interviews + manual events + reminders.**
5. **Google/Outlook are channels; `GOG_ACCOUNT` is legacy transitional, not product architecture.**
6. **Reuse Waves 1–6 authorities only.**
7. **My work queues stay separate from My calendar.**
8. **No Calendar code until C0 spec is written and accepted.**

**Status:** Review complete. **Do not build Calendar yet.**

---

## Source map (current constraints)

| Current piece | Authority |
|---|---|
| Google operator sync | `interview_service.py` (`GOG_ACCOUNT` → `primary`) |
| Interview schedule truth | `candidate_interviews`, `candidate_interview_assignments`, `interview_schedule_operations` |
| First-party calendar entity | **Absent** — greenfield |
| Multi-user foundation | `ops/MULTI_USER_WAVE1` … `WAVE6` |
| Prior calendar NO-GO | `ops/MULTI_USER_TENANT_RBAC_AUDIT.md` §8 |

**Next artifact when ready (not this task):** `ops/WATHEFNI_CALENDAR_C0_SPEC.md` locking ACL matrix, team definition, V1 allowlist, and Google migration policy.
