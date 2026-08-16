# Shifts Wave 1A — Lifecycle semantics & staging qualification closure

**Stamp:** `20260802T182104Z`  
**Evidence:** `ops/evidence/shifts-wave1a-20260802T182104Z/`  
**Mode:** local/staging only — **no production deploy**  
**Module:** `shifts_authority_wave1.py` **v1.1.0**  
**Prior:** Wave 1 foundation (`20260802T181052Z`); Wave 0 / 0B  

---

## Verdict

| Gate | Result |
|---|---|
| Staging qualify (lifecycle + overnight + swap + dashboard) | **GO** — **90/90** |
| Employees 360 / Onboarding / Attendance / Leave freezes | **GO** — 57 / 54 / 26 / 35 |
| Dashboard dist rebuild + concurrency token in deployed client | **GO** |
| WATHEFNI-only production synthetic canary | **NO-GO** |

**Staging Shifts Wave 1A: GO.**  
**Production canary: NO-GO** — not authorized; orphans remain untouched in prod.

---

## Corrected lifecycle matrix

Validation uses the shift’s **actual interval** (`shift_window`, overnight-aware). Gates evaluate overlap / start / end against employment facts — never calendar-date-only.

| Employment state | Rule | Default |
|---|---|---|
| **future_start** | Allow assignments **on or after** effective employment start; **block** intervals that start earlier | `block_future_start=true` |
| **notice_period** | **No blanket block.** Allow work through effective end (`last_working_day` / `termination_effective_on` / `end_date`) unless company policy prohibits | `block_notice_period=false` |
| **notice + garden leave** | Block assignments during notice when `garden_leave_during_notice` (or employment fact) is set | `garden_leave_during_notice=false` |
| **suspended** | Block only assignment intervals that **overlap** the effective suspension window (`suspended_on` … `suspension_ends_on`) | interval overlap |
| **terminated / left** | Block intervals **after** effective employment end; overnight that extends past end is blocked; terminated with no end date **fail-closed** | hard |
| **existing beyond end** | Flag via `shift_lifecycle_flags`; handle with audited **ack / soft-cancel** (`beyond_end_mode`); **never silently deleted** | `beyond_end_mode=require_ack` |

Unit proofs in smoke: future_start before/on start; notice through last day; garden leave; suspension overlap vs outside; terminated daytime on last day vs overnight past end; beyond-end requires ack.

---

## End-to-end swap evidence

Full fixture on staging (`tests/shifts-w1a-smoke.out`):

| Step | Result |
|---|---|
| Request (requester + target shifts) | PASS |
| Self-decision denial | PASS |
| Scoped decision (reject path) | PASS |
| Idempotent replay of same decision | PASS |
| First approve wins (assignment path) | PASS |
| Stale second decision denied / idempotent-reject | PASS |

Also: self-swap ban unit + wiring; nested `db_connect` deadlock fixed (load target shift before opening pooled connection).

---

## Dashboard build evidence

| Proof | Evidence |
|---|---|
| Local Vite rebuild | `ui/dashboard-build.out` — `tsc -b && vite build` succeeded |
| Dist embeds concurrency token | `ui/concurrency-token.txt` — `DASHBOARD_DIST_HAS_expected_updated_at=yes` in `api-4eghFNHt.js`, `PostHire-BXoMxfm_.js`, `dashboard-C5_9qaoH.js` |
| Staging dist rsync | `ui/remote-dist-token.out` — same assets under `/opt/wathefni/staging/dashboard-dist/` |
| Client payload | PASS `client payload includes expected_updated_at` |
| Overnight create + dashboard reschedule | PASS `overnight 22-06 create`, `dashboard overnight reschedule ok`, `ends_next_day` persisted, start moved |
| Stale concurrency | PASS `dashboard stale concurrency denied` |

---

## Orphan quarantine & restoration audit

| Step | Result |
|---|---|
| Quarantine | PASS |
| `shift_events` orphan_quarantined | PASS |
| Lifecycle flag open | PASS |
| Restore blocked while still orphan | PASS |
| Force restore → scheduled again | PASS |
| `shift_events` orphan_restored | PASS |
| Beyond-end flag / soft-cancel audited (no silent delete) | PASS |

---

## Test counts

| Suite | Count |
|---|---|
| Shifts Wave 1A staging smoke | **90 passed, 0 failed** (was 63 in Wave 1) |
| Employees 360 freeze | **57 / 0** |
| Onboarding freeze | **54 / 0** |
| Attendance freeze | **26 / 0** |
| Leave freeze | **35 / 0** |

Artifacts: `tests/shifts-w1a-smoke.out`, `tests/freeze-*.out`, `sources/`, `ui/`, `migrate/`.

---

## Remaining blockers

1. **No production deploy** — Wave 1A is staging-only.  
2. **Three Wave 0 prod orphans** still live; quarantine proven on staging only.  
3. **Employment data quality** (start/end/suspension/notice facts) still drives real gate accuracy.  
4. Templates / recurring / rotations / publish / open shifts / Payroll money / broad employee-app — out of scope.

---

## GO / NO-GO — WATHEFNI production synthetic canary

**NO-GO.**

Staging lifecycle, swap, overnight, dashboard concurrency, and orphan audit are closed. A future canary may proceed only with explicit owner authorization plus:

- Orchestrator sync to prod (not done)  
- `WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1`  
- `WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI`  
- `WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=1`  
- Audited quarantine of the three prod orphans  
- Synthetic-only create/cancel/overnight/reschedule smoke on prod  
- Freeze regressions still green  

Until then: **do not deploy; do not touch real employee shifts.**
