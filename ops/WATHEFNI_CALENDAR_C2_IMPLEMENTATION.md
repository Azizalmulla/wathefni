# Wathefni Calendar — C2 Implementation

**Date:** 2026-07-29 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Stamp:** `20260729T135556Z`  
**Durability amendment stamp:** `20260729T140835Z` (see § Durability amendment)  
**Evidence:** `/opt/wathefni/production-evidence/wathefni-calendar-c2/20260729T135556Z/`  
**Durability evidence:** `/opt/wathefni/production-evidence/wathefni-calendar-c2-durability/20260729T140835Z/`  
**Authority:** C0 (+ A1), C1 kickoff, C1 implementation  
**Scope:** C2 Interview → durable outbox → native Calendar ensure only  
**Preserves:** Waves 1–6, Calendar C1, current Google operator-calendar path  
**Tenants with `calendar` enabled:** **0** (no broad enablement)

---

## Verdict

**PASS** (including C2 durability amendment). Live Interview schedule/reschedule/cancel/complete/panel changes insert a required `calendar_link_outbox` intent **atomically** with Interview truth. Genuine outbox insert failure rolls back the Interview mutation with a retryable error. Worker/processing failure after commit does **not** undo Interview. Duplicate idempotency keys are success. Module-disabled policy: always enqueue, worker defers; backfill remains authoritative for historical gaps. Google operator sync unchanged. Health **200**. C3 not started.

---

## Durability amendment

**Problem:** C2 initially described same-TX outbox insert **and** “fail-soft” enqueue (`try/except: pass`), which allowed Interview to commit without a durable Calendar intent.

### Previous behavior (incorrect)

- Outbox enqueue called inside Interview TX, but wrapped in bare `except Exception: pass`.
- A genuine INSERT failure could leave Interview committed with **no** outbox row.
- Docs claimed both atomic intent and fail-soft enqueue — contradictory.

### Corrected behavior (locked)

| Rule | Behavior |
|---|---|
| Atomic intent | Interview mutation + required outbox INSERT commit in **one** DB transaction |
| Async processing | Calendar event ensure/cancel/complete/sync remains worker-only; never required inside Interview TX |
| Worker failure | Leaves Interview committed; outbox stays `pending`/`failed`/`dead` for retry/replay |
| Outbox INSERT failure | Raises `CalendarOutboxError` → Interview TX **rolls back**; HTTP **503** retryable (`calendar_outbox_enqueue_failed`) |
| Duplicate idempotency key | Treated as **idempotent success** (not failure) |
| Module disabled | Policy **`always_enqueue_defer_until_enabled`**: still enqueue; worker defers until module on. **Backfill** remains authoritative for pre-C2 / historical interviews when enabling Calendar later |

### Code changes (amendment)

| File | Change |
|---|---|
| `calendar_outbox.py` | `CalendarOutboxError`, `require_enqueue_from_interview`, raise on genuine INSERT failure; module policy constant |
| `interview_service.py` | `_require_calendar_outbox_intent` — no fail-soft swallow |
| `app.py` | Dashboard complete/cancel uses `require_enqueue_from_interview` + `conn.rollback()` on failure |
| `smoke-test-calendar-c2-durability.py` | Transactional proofs |

### Durability tests (prod)

`smoke-test-calendar-c2-durability.py` → **22 PASS / 0 FAIL**

- Forced outbox failure → Interview **not** committed, no orphan outbox  
- Commit then forced worker `dead` → Interview still `scheduled`, intent retained  
- Duplicate enqueue → idempotent success  
- Module disabled → intent still enqueued; worker defers  

Regression: C2 **37/0**, C1 **53/0**, Wave 6 **PASS**. Rollback/restore health **200**.

---

## C2 PASS/FAIL matrix

| # | Requirement | Result |
|---|---|---|
| 1 | Same-TX outbox enqueue from canonical Interview ops | **PASS** |
| 2 | Idempotency key + no duplicate outbox intents | **PASS** |
| 3 | Interview commit independent of Calendar **worker** | **PASS** (worker async; enqueue is hard requirement) |
| 3b | Outbox INSERT failure rolls back Interview | **PASS** (durability amendment) |
| 4 | No enqueue from deprecated Interview paths | **PASS** |
| 5 | Worker claim / lease / reclaim / backoff / dead | **PASS** |
| 6 | Manual replay API (`replay_outbox`) | **PASS** |
| 7 | `ensure_calendar_event` for live timed only | **PASS** |
| 8 | Reschedule updates same `event_id` | **PASS** |
| 9 | Cancel/complete mirrors status | **PASS** |
| 10 | Panel sync attendees (no dupes; RSVP preserved) | **PASS** |
| 11 | Async video → no timed event | **PASS** |
| 12 | Candidate guest uses `app_key`/`person_key` | **PASS** |
| 13 | `interview_authority_required` preserved | **PASS** |
| 14 | Legacy Google coexistence unchanged | **PASS** |
| 15 | Agenda prefers native when module enabled | **PASS** |
| 16 | Backfill dry-run + tenant-scoped design | **PASS** |
| 17 | Cross-tenant isolation | **PASS** |
| 18 | Candidate privacy busy_only | **PASS** |
| 19 | C1 + Wave 6 regression | **PASS** |
| 20 | No broad production enablement | **PASS** (0 enabled) |
| 21 | Durability amendment (atomic intent) | **PASS** |

---

## Architecture

```text
Interview schedule/reschedule/cancel/complete/panel
   │
   ├─ BEGIN
   │    mutate candidate_interviews (+ assignments / ops)
   │    optional inline Google sync (unchanged)
   │    INSERT calendar_link_outbox (pending)  -- REQUIRED; failure → ROLLBACK
   │  COMMIT  ← Interview truth + durable intent
   │
   └─ wathefni-calendar-outbox.timer (1m)
         claim FOR UPDATE SKIP LOCKED + lease
         ensure | sync_attendees | cancel | complete
         UNIQUE active (company, interview, source_workflow)
         (module disabled → defer, keep intent)
```

**Idempotency key:** `interview:{interview_id}:{operation}:{schedule_operation_id|token}`

**Module disabled:** `always_enqueue_defer_until_enabled` — enqueue always; worker defers (`pending`, `next_attempt_at=+30m`). Enabling Calendar later processes deferred intents; **backfill** covers interviews that never got an intent (pre-C2).

---

## Files changed

| File | Change |
|---|---|
| `wathefni-orchestrator/calendar_schema.py` | Additive `lease_owner` / `lease_expires_at` + lease index |
| `wathefni-orchestrator/calendar_interview_link.py` | **New** — ensure / sync_attendees / cancel / complete |
| `wathefni-orchestrator/calendar_outbox.py` | Enqueue/claim/process/replay + durability require API |
| `wathefni-orchestrator/calendar-link-outbox-worker.py` | **New** — oneshot worker |
| `wathefni-orchestrator/calendar-c2-backfill.py` | **New** — dry-run / tenant / cursor / process |
| `wathefni-orchestrator/interview_service.py` | Required outbox hooks; agenda native authority when module on |
| `wathefni-orchestrator/app.py` | Dashboard status complete/no_show required enqueue |
| `wathefni-orchestrator/smoke-test-calendar-c2.py` | C2 proofs |
| `wathefni-orchestrator/smoke-test-calendar-c2-durability.py` | Durability amendment proofs |
| `ops/WATHEFNI_CALENDAR_C2_IMPLEMENTATION.md` | This document |
| systemd | `wathefni-calendar-outbox.service` + `.timer` (enabled) |

---

## Migration

Additive only on existing C1 `calendar_link_outbox`:

- `lease_owner text`
- `lease_expires_at timestamptz`
- partial index `idx_calendar_link_outbox_lease`

**Rollback notes:** restore pre-amendment / pre-C2 code; stop outbox timer; leave tables (C1 spine). Durability amendment rollback/restore proven (`health.rollback.code.txt` / `health.restore.code.txt`).

---

## Worker / lease behavior

| Behavior | Detail |
|---|---|
| Claim | `status IN (pending,failed)` + `next_attempt_at <= now()` + `FOR UPDATE SKIP LOCKED` |
| Lease | `processing` + `lease_owner` + `lease_expires_at` (default 120s) |
| Crash recovery | `reclaim_expired_leases()` → `pending` |
| Backoff | 30s → 2h ladder; max attempts 8 → `dead` |
| Replay | `replay_outbox(outbox_id=…\|idempotency_key=…)` |
| Module off | Defer without burning attempts toward dead |

---

## Backfill

`calendar-c2-backfill.py` — dry-run / company / cursor / process. Authoritative for historical interviews when enabling Calendar (complements deferred live intents under module-disabled policy).

---

## Test results

| Suite | Result |
|---|---|
| `smoke-test-calendar-c2-durability.py` | **22 PASS / 0 FAIL** |
| `smoke-test-calendar-c2.py` | **37 PASS / 0 FAIL** |
| `smoke-test-calendar-c1.py` | **53 PASS / 0 FAIL** |
| `smoke-test-multi-user-wave6-final.py` | **PASS** |
| Health after durability deploy / restore | **200** |

---

## Remaining for C3

- Shared conflict service  
- Team Calendar projection + UI switch  
- Overview ≤5 panel  
- Full day/week/month Calendar UX  

**Stop after C2 (including durability amendment). Do not begin C3.**
