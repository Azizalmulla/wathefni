# Leave Wave 3B — Production synthetic workflow canary

**Stamp:** `20260802T164738Z`  
**Evidence:** `ops/evidence/leave-wave3b-prod-canary-20260802T164738Z/`  
**Remote:** `/opt/wathefni/production-evidence/leave-wave3b-prod-canary/20260802T164738Z/`  
**Company:** WATHEFNI only · synthetic markers `LVW3B` / `LVW3B-SYNTH|` / phone prefix `965527`  
**Module:** `leave_workflow_wave3` **@ 3.0.0**

---

## Separate verdicts

| Concern | Verdict |
|---|---|
| **Synthetic production Wave 3 workflows** | **GO** — canary **62/62** (initial + post-redeploy); duration/overlap/reservation/unpaid/attachments/RFI/withdraw/cancel proved; `enforced=false` |
| **Controlled real HR leave operation** | **NO-GO** — `SYNTHETIC_ONLY=on` retained; no real-employee leave decisions enabled |
| **Real balance enforcement** | **NO-GO** — `enforced=false`, `legal_reviewed=false`, `balances_binding=false` |
| **Payroll monetary impact** | **NO-GO / none** — unpaid handoff is classification/duration only; `monetary_fields_present=false` |

---

## Production SHAs and flags (final)

| File | SHA256 |
|---|---|
| `app.py` | `b18e4b7d8986bb71380b4508001033030ce3efab8a135b8ca16203048dcd3c75` |
| `leave_workflow_wave3.py` | `c8dad47eaca79e57be84dbecb6bd5891768e3554db035a45404e35f88be4e7d4` |
| `leave_policy_wave2.py` | `809d427c8163395ee92bf7b1e15446450d122c662b95a985146283ac9286d5b7` |
| `leave_authority_wave1.py` | `b153a0cf6154d82698f3f54342efa15e1591c6e6df14c05b5d47ca45b9ee8e8a` |
| `employee_lifecycle_wave3c.py` | `f2dfbabb717dc8a4d912619663681973b1346f2224e69b45a5fe26c912161099` |

| Flag | Value |
|---|---|
| `WATHEFNI_LEAVE_WORKFLOW_WAVE3` | **on** |
| `WATHEFNI_LEAVE_POLICY_WAVE2` | **on** |
| `WATHEFNI_LEAVE_BALANCES` | **on** (observe-only) |
| `WATHEFNI_LEAVE_AUTHORITY` | **on** |
| `WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_ONLY` | **on** |
| `WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_KEY_MARKERS` | `LVW1B,LVW1B-SYNTH|,LVW2C,LVW2C-SYNTH|,LVW3B,LVW3B-SYNTH|` |
| `WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES` | `965525,965526,965527` |
| `WATHEFNI_ATTENDANCE_CAPTURE_INGEST` | **off** |
| `WATHEFNI_ONBOARDING_SEED` | **off** |
| Accrual timer `wathefni-leave-accrual.timer` | **enabled / active** |

Drop-ins:
- `zzzzzz-leave-workflow-wave3b.conf` (`LEAVE_WORKFLOW_WAVE3=on`)
- `zzzzz-leave-policy-wave2c.conf` (retained)
- `zzzz-leave-authority-wave1b-synthetic.conf` (markers extended for LVW3B / 965527)

---

## Backup and rollback evidence

| Item | Evidence |
|---|---|
| Backup | `/opt/wathefni/backups/production-pre-leave-wave3b-20260802T164738Z/` |
| Fingerprints | `leave-requests/balances/ledger-fingerprint.csv` + `SHA256SUMS` |
| Rollback | `ROLLBACK_OK` — removed `leave_workflow_wave3.py` + wave3b drop-in; Wave 1B/2C restored |
| Redeploy + canary | `ROLLBACK_REDEPLOY_OK` · post-redeploy **62/62** |
| Accrual timer | enabled/active before and after |

---

## Synthetic IDs (initial canary `4127dd9e`)

| Item | Value |
|---|---|
| Tag / phone | `4127dd9e` / `965527141279` |
| Half-day leave | `bbbaa172-f598-475b-8f52-0fcc0c4880a6` (chargeable **0.5**, reservation posted) |
| Hourly leave | `3052a8a7-a083-49ad-8ef4-777dd212d19c` |
| Post-redeploy tag | `b5dc061a` / `965527150610` (**62/62**) |

Cleanup (initial): attachments 3, audit 4, handoff 1, events 19, ledger 21, requests 12, attendance reverse-safe, employee 1 → residual **0**.

---

## Duration / reservation evidence

Proved **62/62** ×2:

- Half-day AM + PM (no mutual overlap); full-day vs partial **denied**
- Hourly (2h), overnight (23:00–01:00 on 22:00–06:00 shift), split-shift second window
- Concurrent AM+PM fractional reservations
- Approve → attendance derived; cancel future → reverse list-safe
- Reject / needs_info / resubmit / withdraw
- Already taken → `leave_already_taken`; already started → `leave_already_started`
- Stale concurrency + self-approval denial

---

## Attachment / privacy evidence

- Upload → replace (v2) → reject + audit (≥3 audit rows)
- Sensitive medical attachment **masked** for denied viewer (`deny_sensitive`)
- Tables: `leave_request_attachments`, `leave_attachment_audit`

---

## Attendance and Payroll boundary evidence

- Approve half-day: attendance derivation ≥1 update
- Cancel future approved: `attendance_reversed` list-safe (event-before-delete ordering)
- Unpaid: reservation **skipped**; approve records `leave_payroll_handoff_events` with `monetary_fields_present=false`
- Handoff contains classification/duration only (`salary_deduction` / `pay_fraction` / amounts absent)
- `CAPTURE_INGEST=off` throughout

---

## Real leave / ledger / balances (unchanged)

| leave_id | status | type | fp |
|---|---|---|---|
| `e3217e0e-…` | approved | sick | `abf4cba7cb8702b2d7c067db795d0701` |
| `51cd940f-…` | rejected | sick | `8f6d67e3cc4fbf5ee321af235ecbb20d` |
| `dbf82ecf-…` | requested | annual | `34c7cf18a4d758698bbf7cac6da70d1f` |

Company totals preflight **and** post-cleanup: **3** requests · **10** events · **28** ledger · **4** balances.

---

## Freeze regressions

| Suite | Result |
|---|---|
| Employees 360 | **57/57** |
| Onboarding | **54/54** |
| Attendance | **26/26** |

---

## Remaining blockers

1. Real HR leave decisions still behind `SYNTHETIC_ONLY`
2. `enforced=false` / `legal_reviewed=false` — no real balance gate
3. No Leave UI redesign / no broad employee app access
4. Partial attendance remains day-level `approved_leave` stamp (finer banding deferred)
5. Payroll money path intentionally absent

## Scripts

- `ops/deploy-leave-workflow-wave3b-prod.sh`
- `ops/migrate-leave-workflow-wave3b-prod.sh`
- `ops/run-leave-workflow-wave3b-prod-canary.sh`
- `canary-prod-leave-workflow-wave3b.py`
