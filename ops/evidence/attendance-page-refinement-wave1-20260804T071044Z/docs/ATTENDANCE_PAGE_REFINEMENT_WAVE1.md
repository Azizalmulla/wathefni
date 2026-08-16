# Attendance Page Refinement Wave 1

**Stamp:** `20260804T071044Z`  
**Evidence:** `ops/evidence/attendance-page-refinement-wave1-20260804T071044Z/`  
**Deploy:** **NOT deployed** (await owner review)  
**Leave:** **NOT started**

## Confirmed page purpose

Help HR understand today’s attendance state, identify exceptions, and resolve them through **one** governed workflow: **Ops request → dual review → separate Apply**.

## Implementation-truth findings (pre-change)

The page was a stacked ops/lab/board console: oversized `NextAction`, full Ops + Capture panels first, five metric cards, then the daily board with competing **Correct** / **Mark absent** mutations that bypassed Ops dual-approve→apply.

## Authorities and correction paths

| Path | Before | After |
|---|---|---|
| Board inline Correct → `correct_attendance_record` | Competing | **Removed** from HR board |
| Board Mark absent → `mark_attendance_absent` | Competing | **Removed** from HR board |
| Ops request → dual review → Apply | Present but buried | **Sole correction authority** |
| Capture mapping / Import / Export | First-paint / board chrome | **Moved** behind collapsed Operations |
| Board Resolve | — | Deep-links into Ops exception focus |

Permissions unchanged: `attendance.read` / `attendance.manage`. Dual approval, apply separation, `expected_row_version`, payroll locks, manager self/scope denial, punch immutability, ingest-off freeze — preserved.

## Exact ledger

**Removed:** NextAction banner; fat overview metric grid as peer surface; board `AttendanceCorrectionRow`; board Correct/Mark absent wiring; first-paint Capture Ops.

**Moved:** Capture Ops, Import, Export → collapsed **Operations**.

**Combined:** Review banner + overview stats → `AttendanceAttentionStrip`; board mutations + Ops → single Ops resolve path.

**Retained:** Daily board + date chrome + day expand + payroll honesty; Ops dual review/apply/disputes/reopen/ConflictBanner; mutation integrity; tenant isolation; frozen backend contracts.

## Final structure

```
[purpose hint]                                    [Refresh]
[attention strip — compact counts]
┌ Attendance board + Today/7d/Month/dates ─────────┐
│ rows: view + Day detail; Resolve → Ops focus     │
└──────────────────────────────────────────────────┘
┌ Exceptions (Ops compact) ────────────────────────┐
│ employee · issue · date · impact · state         │
│ one primary: Assign / Request / Approve / Apply  │
└──────────────────────────────────────────────────┘
▶ Operations (collapsed): Import · Export · Capture
```

## Mutation / concurrency proof

- Contracts: `AttendanceWave1Contract` — **4/4 PASS** (`ui/vitest.out`)
- Mutation integrity client contract still **PASS**
- Ops retains `expected_row_version`, dual_pending, approve≠apply confirm copy
- Board no longer calls `correct_attendance_record` / `mark_attendance_absent`

## Screenshots (local fixtures)

- `screenshots/attendance-desktop-en.png`
- `screenshots/attendance-mobile-en.png`
- `screenshots/attendance-desktop-ar.png`
- `screenshots/attendance-mobile-ar.png`

## Verdict

| Decision | Result |
|---|---|
| Ship Wave 1 UI locally for review | **GO** |
| Freeze Attendance | **NO-GO until owner visual review** |
| Production deploy | **NO-GO** (explicit hold) |
| Begin Leave | **NO-GO** until Attendance reviewed |
