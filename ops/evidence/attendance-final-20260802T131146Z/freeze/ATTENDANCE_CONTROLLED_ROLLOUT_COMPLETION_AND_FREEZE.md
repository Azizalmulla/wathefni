# Attendance controlled rollout — completion and freeze

**Status:** **FROZEN** — closed for feature/redesign expansion beyond controlled WATHEFNI synthetic posture.  
**Authority evidence:** `ops/evidence/attendance-final-20260802T131146Z/` (REPORT.md).  
**Production stamp:** `20260802T131146Z` — PostHire `D8YjEnpm` · canary 33/33 · ingest off · synthetic-only.  
**Prior waves:** Authority Wave 1 → Capture 2E/2F/2G dark → Ops Wave 3 synthetic → UX Wave 4/4B staging → **Final production promote + freeze**.

---

## Final posture (do not weaken)

| Gate | Posture |
|---|---|
| HR production Attendance use (WATHEFNI) | **GO (synthetic-backed UX + ops)** — daily board, exceptions, corrections, disputes, dual approval, separate apply, payroll exclusion copy, connector health |
| Manager production Attendance use | **GO (scoped)** — manager scope + self-correction denial enforced |
| Real employee clocking | **NO-GO / disabled** |
| Real device ingestion | **NO-GO** — `WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off` |
| QR / GPS / kiosk | **NO-GO / off** |
| Attendance authority | **on**, `SYNTHETIC_ONLY=on`, companies `WATHEFNI` |
| Attendance ops | **on**, `SYNTHETIC_ONLY=on`, dual kinds `absence,early_leave` |
| Attendance-to-Payroll authority | **GO for approved synthetic eligibility snapshots only** — **NO-GO** for real payroll money impact |
| Employees 360 / Onboarding | **Frozen unchanged** |
| Overall Attendance completion | **GO for controlled WATHEFNI HR/manager UX + synthetic ops** — **not** a broad clocking/device rollout |

---

## Hard bans for future modules / PRs

1. **Punch immutability** — raw punches remain append-only; corrections create new projection versions, never rewrite punch ledger rows.
2. **Approval / version history** — keep `approve` ≠ `apply`; dual approval where configured; `row_version` / `stale_row_version` fail-closed.
3. **Manager self-denial** — keep `manager_self_correction_denied` for actor phone == employee phone.
4. **Manager scope** — keep `employee_outside_manager_scope` / unconfigured manager denials.
5. **Payroll snapshot locks** — keep `payroll_period_locked` and eligibility rules (`approved` + `exception_state=none`); do not invent real money payroll posts from incomplete days.
6. **Tenant isolation** — company_code filters on all attendance authority/ops/capture reads and writes.
7. **Secret handling** — no plaintext connector secrets in API payloads; capture credential key remains redacted in evidence.
8. **Synthetic-only** — do not disable `AUTHORITY_SYNTHETIC_ONLY` / `OPS_SYNTHETIC_ONLY` or enable `CAPTURE_INGEST` without an explicit owner-approved wave.
9. **Do not change frozen Employees 360 or Onboarding** to unblock Attendance work.
10. **Do not enable QR, GPS, kiosk, or broad employee clocking** without a new controlled rollout wave.

---

## Allowed without a new wave

- Bugfixes restoring freeze invariants
- Ops evidence / documentation
- Running `smoke-test-attendance-freeze-regression.py`, E360/Onboarding freeze smokes
- Soft-kill / restore of attendance drop-ins under the production rollback runbook

## Not allowed without owner change-control

- Enabling `CAPTURE_INGEST`
- Connecting customer biometric devices
- Broad employee-app clocking
- Real payroll money posting from attendance
- Weakening dual-approval or apply separation
- Rewriting historical punch rows

---

## Regression gates

- `wathefni-orchestrator/smoke-test-attendance-freeze-regression.py`
- `smoke-test-employees360-freeze-regression.py`
- `smoke-test-onboarding-freeze-regression.py`
- Cursor rule: `.cursor/rules/attendance-freeze.mdc`

---

## Production flags (expected)

```
WATHEFNI_ATTENDANCE_AUTHORITY=on
WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES=WATHEFNI
WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
WATHEFNI_ATTENDANCE_OPS=on
WATHEFNI_ATTENDANCE_OPS_COMPANIES=WATHEFNI
WATHEFNI_ATTENDANCE_OPS_STORE=postgres
WATHEFNI_ATTENDANCE_OPS_SYNTHETIC_ONLY=on
WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS=absence,early_leave
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
WATHEFNI_ATTENDANCE_IMPORT=off
WATHEFNI_ATTENDANCE_CAPTURE_OPS=on  # remediation UX only; ingest off
```

Legacy demo attendance: **42** `metadata.demo_seed=wathefni_v1` rows — must remain unchanged by canaries.
