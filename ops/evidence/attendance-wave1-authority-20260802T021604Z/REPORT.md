# Attendance Wave 1 — Authority and calculation foundation

**Stamp:** see evidence folder name  
**Mode:** Local/staging engineering only. **No production deploy.**  
**Flags:** `WATHEFNI_ATTENDANCE_AUTHORITY` default **OFF**; optional `WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES` allowlist.  
**Frozen modules untouched:** Employees 360, Onboarding, pre-hiring, Wave D (freeze regressions PASS).

## Verdict

**PASS** — 78/78 qualification checks.

| Gate | Result |
|---|---|
| Local qualification | PASS (78/0) |
| Employees 360 freeze | PASS |
| Onboarding freeze | PASS |
| Production deploy | NOT DONE (banned) |
| Device import / real clocking / QR/GPS/kiosk | NOT ENABLED |
| UI redesign | NOT DONE |

---

## 1. Architecture

```
Sources (WhatsApp | import | HR | leave | absence_scan | correction)
        │
        ▼
┌───────────────────────────────┐
│ AttendanceAuthorityService    │  ← single canonical write path (dark)
│  - append-only punch ledger   │
│  - Kuwait/overnight calculator│
│  - sessions + breaks          │
│  - versioned day projections  │
│  - correction workflow        │
│  - approved payroll snapshots │
└───────────────┬───────────────┘
                │
     ┌──────────┼──────────┐
     ▼          ▼          ▼
punches    day_proj    payroll_snapshots
(immutable) (versioned) (only money input)
     │
     ▼
compat mirror → attendance_records (legacy shape for dashboard/app/export)
```

When the company flag is **off** (default), all existing writers/readers stay on the legacy mutable `attendance_records` path — zero behavior change for production.

When **on** for an allowlisted company:

- check-in / check-out / absent / leave / reverse / correct route through the authority service
- `list_attendance` prefers projection compatibility reads
- `list_payroll_hours` consumes **approved snapshots only** (unapproved/incomplete excluded)

Process-local in-memory store is used for Wave 1 proof; Postgres DDL is installed via `ensure_schema` for the next persistence adapter wave.

---

## 2. Schema (DDL in `attendance_authority_wave1.SCHEMA_DDL`)

| Table | Role |
|---|---|
| `attendance_punches` | Append-only punches. `UNIQUE (company_code, source, source_event_id)`. Never UPDATE/DELETE. |
| `attendance_day_projections` | Versioned employee-day authority. `shift_key` (`''` when null shift) + partial unique current row. |
| `attendance_corrections` | request → approved \| rejected \| disputed |
| `attendance_payroll_snapshots` | Immutable approved payload for Payroll. Unique per projection version. |

Nullable shift IDs cannot fork duplicate employee-day authority: uniqueness keys on `shift_key` text, not nullable UUID.

---

## 3. State model

**Punch:** immutable event (`in` \| `out` \| `break_start` \| `break_end`) with source + source_event_id.

**Day projection statuses:** `incomplete` \| `present` \| `late` \| `completed` \| `absent` \| `approved_leave` \| `void`

**Exception states:** `none` \| `missing_check_in` \| `missing_check_out` \| `ambiguous_punches` \| `incomplete_session`

**Approval:** `unapproved` \| `approved` \| `rejected` \| `disputed`  
`payroll_eligible` only when `approval_status=approved` **and** `exception_state=none` **and** status not incomplete/void.

**Correction:** `requested` → `approved` \| `rejected` \| `disputed`  
Approve applies correction punches and creates a **new** projection version (`manual_correction=true`). Old versions remain.

**Manager self-correction:** if actor phone == employee phone and actor_is_manager → `manager_self_correction_denied`.

---

## 4. Calculation rules (Kuwait TZ `UTC+3`)

1. **Shift window:** if `end_time <= start_time`, end is next calendar day (overnight).
2. **Work date attribution:** punch maps to shift date when inside window ±4h grace; else Kuwait calendar date of punch.
3. **Sessions:** chronological pairing of in/out; multiple sessions allowed.
4. **Breaks:** `break_start`/`break_end`; `break_paid` distinguishes paid vs unpaid.
5. **Worked minutes:** sum(session worked) − unpaid break minutes. Paid breaks do not reduce worked.
6. **Late / early leave:** vs overnight-safe window start/end (fixes legacy `minutes_between_times` overnight=0).
7. **Absence vs check-in race:** absence refused if an `in` punch exists; later `in` supersedes prior absence via new version.
8. **Leave reverse:** refused when current projection has `manual_correction=true` (preserves later correction).

---

## 5. Dark flags

```
WATHEFNI_ATTENDANCE_AUTHORITY=on|off   # default off
WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES=ATTW1,...  # empty = all when master on
```

Helpers: `attendance_authority_enabled()`, `attendance_authority_enabled_for_company()`.

---

## 6. Tests proved

| Scenario | Result |
|---|---|
| Normal day 09–17 | PASS |
| Overnight 22:00–06:00 | PASS (480 scheduled, ~477 worked) |
| Checkout after midnight | PASS (attributes to shift date) |
| Multiple sessions + paid/unpaid breaks | PASS |
| Duplicate + concurrent punches | PASS (single punch_id) |
| Absence-scan vs late check-in race | PASS both orders |
| Missing check-in / checkout | PASS + approve denied |
| Correction reject / dispute / approve | PASS + history retained |
| Manager self-correction denial | PASS |
| Approved leave + reversal vs manual correction | PASS |
| Null shift_id single current authority | PASS |
| Approved → payroll snapshot reconcile | PASS; unapproved excluded |
| Tenant service isolation | PASS |
| Compat read shape | PASS |
| E360 + Onboarding freeze regressions | PASS |

Artifact: `verify/qualification.json`, `tests/qualification.out`.

---

## 7. Remaining risks

1. **In-memory store** — Wave 1 authority state is process-local. Postgres tables are created but not yet the live adapter; staging multi-worker persistence needs Wave 1B.
2. **Compat mirror still mutates `attendance_records`** when flag on — read compatibility only; punches remain the authority. Dual-write drift possible until clients fully cut over.
3. **Manager-scope SQL** on in-memory payroll path is approximate (shift/leave key set); full scope SQL lands with PG adapter.
4. **Legacy overnight bug remains** on the flag-off path (`minutes_between_times` / early-leave without overnight end).
5. **Correction UX** still dark — dashboard still calls legacy correct when flag off; when on, corrections are request/review (optional `auto_approve_correction` for staged tooling only).
6. **Import / device / QR / GPS / kiosk** intentionally not enabled.

---

## 8. Files

| Path | Change |
|---|---|
| `wathefni-orchestrator/attendance_authority_wave1.py` | New engine |
| `wathefni-orchestrator/smoke-test-attendance-authority-wave1.py` | Qualification |
| `wathefni-orchestrator/app.py` | Dark flags, schema ensure, gated write/read/payroll/leave |

---

## 9. PASS/FAIL

```
WAVE1_AUTHORITY=PASS
PASS=78
FAIL=0
DEPLOYED=false
AUTHORITY_DEFAULT=off
NEXT=Wave 1B Postgres adapter + staging DB qualification (still no prod enable)
```
