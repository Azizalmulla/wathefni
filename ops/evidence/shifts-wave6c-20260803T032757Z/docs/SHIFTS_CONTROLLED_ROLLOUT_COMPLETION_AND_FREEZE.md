# Shifts — controlled rollout completion and freeze

**Status:** Production-qualified for controlled WATHEFNI use and **FROZEN**  
**Authority evidence:** `ops/evidence/shifts-wave6c-<STAMP>/REPORT.md` (`PROD_CONTROLLED_WAVE6C_SHIFTS_GO`)  
**Production stamp:** `<STAMP>`  
**Prior waves:** 1B (authority) · 2B/2C (integrity) · 3A/3B (controlled UX readiness) · 4/4B (templates & recurrence) · 5/5B (publish, open shifts, coverage) · 6/6A (rotations, compliance, PAM export) · 6B (multi-channel notification outbox, mock) · **6C (controlled real rollout + freeze)**

## Final posture (do not weaken)

| Scope | Verdict |
|---|---|
| HR production scheduling | **GO** — controlled, named allowlist (one operator: `96599338566`) |
| Scoped manager production scheduling | **NO-GO** — no manager identity, scope, branch or team exists in production |
| Talal employee-app schedule access | **GO** — `WATHEFNI-96550252254`, read + acknowledge only |
| Real notification canary | **GO** — one recipient, channels `app` + `email`, consent recorded |
| Reminder / reconciliation timers | **NO-GO** — manual invocation only |
| Broad employee-app rollout | **NO-GO** |
| PAM automated submission | **NO-GO** — export only, `manual_submission_required` |
| Payroll monetary impact | **NO-GO** |
| Overall Shifts completion and freeze | **GO (controlled)** |

Employees 360, Onboarding, Attendance and Leave freezes are unchanged.

## Architecture (frozen layers)

1. **L0 authority** — `shift_assignments` is the single source of truth for a published schedule. Drafts and rotations are proposals until published.
2. **Version immutability** — a published `shift_schedule_versions` row is never mutated in place; changes publish a new version.
3. **Controlled real gate** — `WATHEFNI_SHIFTS_REAL_MUTATION_GATE` + `WATHEFNI_SHIFTS_HR_ALLOWLIST` (phone digits). Empty allowlist means no real mutation by anybody.
4. **Notification outbox** — one canonical business event (`shift_notification_events`, unique on `dedupe_key`) fans out to per-channel attempts (`shift_notification_deliveries`) and is acknowledged exactly once (`shift_notification_acks`).
5. **Real delivery guards** — seven fail-closed layers: wave enabled, kill switch, real delivery enabled, recipient allowlisted, subject not excluded, channel approved, consent recorded.
6. **Controlled subject exclusions** — `shift_controlled_exclusions` plus `WATHEFNI_SHIFTS_EXCLUDED_SUBJECTS` keep orphan-quarantine residue and the real-denial probe out of every Wave 6C path.
7. **Operator jobs** — `shift_controlled_job_runs` records every bounded batch under an advisory lock; overlapping execution records `skipped_locked` instead of running.

## Production flags and allowlists (live contract)

```
WATHEFNI_SHIFTS_WAVE6C=1
WATHEFNI_SHIFTS_WAVE6C_COMPANIES=WATHEFNI
WATHEFNI_SHIFTS_HR_ALLOWLIST=96599338566
WATHEFNI_SHIFTS_MANAGER_ALLOWLIST=
WATHEFNI_SHIFTS_REAL_MUTATION_GATE=1
WATHEFNI_SHIFTS_NOTIFY_REAL_DELIVERY=1
WATHEFNI_SHIFTS_NOTIFY_REAL_ALLOWLIST=WATHEFNI-96550252254
WATHEFNI_SHIFTS_NOTIFY_REAL_CHANNELS=app,email
WATHEFNI_SHIFTS_NOTIFY_KILL=0
WATHEFNI_SHIFTS_EXCLUDED_SUBJECTS=WATHEFNI-ORPHAN-,-REALBLOCK-
WATHEFNI_SHIFTS_CONTROLLED_JOBS=1
WATHEFNI_SHIFTS_OPERATOR_TIMERS=0
WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=0
WATHEFNI_SHIFTS_INTEGRITY_JOBS=0
WATHEFNI_SHIFTS_REAL_REMINDERS=0
WATHEFNI_SHIFTS_NOTIFICATIONS_REAL_DELIVERY=0
WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST=WATHEFNI-96550252254
WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST=on
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
```

`WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY` is `0` so Wave 1 authority can evaluate real employees. Safety comes from the actor allowlist and the real-mutation gate, not from that flag: with an empty allowlist no actor can mutate a real subject regardless.

### Controlled subjects

| Role | Identity | Notes |
|---|---|---|
| HR operator | Aziz Almulla · `96599338566` · owner · `shifts.manage` | only actor permitted to mutate real shifts |
| Employee-app canary | Talal Fadhli · `WATHEFNI-96550252254` | read + acknowledge; also the only real notification recipient |
| Consented destination | `talalabdalla89@gmail.com` | `shift_notification_consent`, policy `shifts-notify@1.0.0` |
| Excluded | `WATHEFNI-ORPHAN-*`, `*-REALBLOCK-*` | residue and probe rows; never mutated or notified |

Fouad (`f.burhama@disruptv.tech`) is **not** allowlisted: his dashboard phone is stored as `66363363` and would never match the digit comparison against `96566363363`.

## Hard bans for future modules / PRs

1. Do not weaken canonical L0 authority or publish-version immutability.
2. Do not bypass lifecycle or leave gates for authority subjects.
3. Do not remove self-decision bans on swaps or open-shift claims.
4. Do not weaken manager scope enforcement or its fail-closed default.
5. Do not drop concurrency tokens or idempotency keys from real mutations.
6. Do not change overnight/split semantics or template regeneration detach safety.
7. Do not weaken notification deduplication, ack-once, or tenant isolation.
8. Do not deliver to a recipient, channel or subject outside the allowlists, or without consent.
9. Do not remove `WATHEFNI_SHIFTS_NOTIFY_KILL` or make real delivery default-on.
10. Do not populate `WATHEFNI_SHIFTS_MANAGER_ALLOWLIST` without a new owner-approved wave.
11. Do not broaden `WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST` beyond Talal.
12. Do not enable operator timers, real reminders or integrity jobs.
13. Do not calculate Payroll money, mutate Leave balances, or mutate Attendance authority from Shifts.
14. Do not automate PAM submission.
15. Do not change frozen Employees 360, Onboarding, Attendance or Leave to unblock Shifts.

## Allowed without a new wave

- Bugfixes restoring freeze invariants
- Ops evidence and documentation
- `smoke-test-shifts-freeze-regression.py`
- Kill switches and `ROLLBACK.sh`
- Synthetic canary work under SHW1–SHW6C markers / 965528–965538 phone prefixes

## Not allowed without owner change-control

- Real scoped-manager scheduling
- Additional real notification recipients or channels
- Broad employee-app schedule write access
- Enabling reminder/reconciliation timers
- Automated PAM submission
- Any Payroll monetary calculation from Shifts

## Rollback

Removing `/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzz-shifts-wave6c-controlled.conf` and restarting restores the Wave 6B synthetic-only posture: empty allowlists, real delivery off, authority synthetic-only back on. Full code + config + data rollback: `<BACKUP>/ROLLBACK.sh`.

## Known manual boundaries (do not automate)

- PAM submission stays a human action against the exported Arabic/English pack.
- Compliance profiles stay **warn**, never **block**, until the legal items below are verified.
- Adding a real notification recipient requires an owner decision plus a consent row.

## Unresolved legal / customer-configurable items

1. Sector-specific Ramadan maximum hours and midday outdoor work windows.
2. Weekly rest weekday convention per company (`shift_authority_settings.rest_weekdays` is `{4}`, Friday only, today).
3. Official PAM form field mapping versus `pam-export@1.0.0`.
4. Hitch travel-day ownership between Shifts and Payroll allowances.
5. Which external providers (WhatsApp / Teams / Telegram / SMS) are contracted before any second real channel.

## Regression gates

- `wathefni-orchestrator/smoke-test-shifts-freeze-regression.py`
- `wathefni-orchestrator/canary-prod-shifts-wave6c.py` (controlled, requires approved allowlists)
- Wave 1B–6B canaries for coexistence
- `.cursor/rules/shifts-freeze.mdc`
- Sibling freezes: Employees 360, Onboarding, Attendance, Leave

## Freeze declaration

Shifts is closed for feature work. Any change that touches the invariants above requires a new owner-approved wave with its own evidence pack.
