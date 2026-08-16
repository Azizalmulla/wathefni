# Leave controlled rollout — completion and freeze

**Status:** **FROZEN** — Leave is closed for feature/redesign expansion beyond controlled WATHEFNI HR/manager UX + Talal employee-app leave, with real decisions limited to a named allowlist.  
**Authority evidence:** `ops/evidence/leave-wave4-20260802T171521Z/` (REPORT.md).  
**Production stamp:** `20260802T171521Z` — Wave 4 canary **60/60** · allowlist on · `enforced=false` · employee-app Talal-only.  
**Prior waves:** Authority 1/1B → Policy 2/2B/2C → Workflow 3/3B → **Wave 4 UX + controlled real-op readiness + freeze**.

---

## Final posture (do not weaken)

| Concern | Verdict |
|---|---|
| **HR production Leave use (WATHEFNI)** | **GO (controlled)** — queue, detail, partial/unpaid, RFI/withdraw/cancel, dual-control stale, honesty banners; real decisions require named allowlist |
| **Manager production Leave use** | **GO (scoped)** — manager scope + global self-approval ban; real decisions still allowlist-gated |
| **Talal employee-app Leave use** | **GO (unchanged allowlist)** — `WATHEFNI-96550252254` only |
| **Broad employee-app rollout** | **NO-GO** — do not expand `EMPLOYEE_APP_REAL_ALLOWLIST` |
| **Real balance enforcement** | **NO-GO** — `enforced=false`, `legal_reviewed=false`, balances non-binding |
| **Payroll monetary impact** | **NO-GO / none** — unpaid handoff is classification/duration only |
| **Overall Leave completion** | **GO for controlled WATHEFNI Leave** — not a broad enforcement or Payroll money rollout |

---

## Hard bans for future modules / PRs

1. **Self-approval ban** — keep `self_decision_denied` / `self_approval_forbidden` global; never allow actor phone == employee phone to approve/reject/RFI.
2. **Lifecycle gates** — keep `lifecycle_gate` for authority subjects; do not bypass employment-status blocks.
3. **Policy versions** — keep policy pack honesty (`enforced=false` / `legal_reviewed=false`) until an explicit owner-authorized enforcement wave.
4. **Ledger idempotency** — keep reservation/consumption idempotency (`leave_id` + `entry_kind` / dedicated unique indexes); no double-post on retry.
5. **Attachment privacy** — keep sensitive attachments masked by default; audit access; do not return plaintext medical evidence to unauthorized viewers.
6. **Attendance reversal safety** — keep leave-derived attendance reverse event-before-delete ordering; do not orphan FK deletes.
7. **Frozen modules** — do not change Employees 360, Onboarding, or Attendance freezes to unblock Leave.
8. **Real decision allowlist** — keep `WATHEFNI_LEAVE_REAL_DECISION_GATE` + named `WATHEFNI_LEAVE_REAL_DECISION_ALLOWLIST` while Leave remains controlled; empty allowlist + gate on ⇒ fail closed.
9. **Dual-control stale** — resolving real stale pending requires two different allowlisted actors; same-actor confirm denied.
10. **Do not set `enforced=true`**, calculate Payroll money, or broadly onboard employees without a new owner-approved wave.
11. **Synthetic markers** — keep `SYNTHETIC_ONLY` authority markers for canaries; do not use real phones as synthetic prefixes.
12. **Kill switch** — `WATHEFNI_LEAVE_WAVE4_KILL=on` must disable Wave 4 real-allowlist enrichment path without expanding real decisions.

---

## Allowed without a new wave

- Bugfixes restoring freeze invariants
- Ops evidence / documentation
- Running `smoke-test-leave-freeze-regression.py` and E360/Onboarding/Attendance freeze smokes
- Soft-kill via `WATHEFNI_LEAVE_WAVE4_KILL` and restore from production backup `ROLLBACK.sh`

## Not allowed without owner change-control

- Enabling `enforced=true` / `legal_reviewed=true`
- Payroll money calculation from unpaid leave
- Broadening `EMPLOYEE_APP_REAL_ALLOWLIST` beyond Talal
- Disabling real-decision gate or emptying allowlist while claiming production Leave is open
- Weakening self-approval, attachment privacy, ledger idempotency, or Attendance reverse safety

---

## Regression gates

- `wathefni-orchestrator/smoke-test-leave-freeze-regression.py`
- `smoke-test-employees360-freeze-regression.py`
- `smoke-test-onboarding-freeze-regression.py`
- `smoke-test-attendance-freeze-regression.py`
- Cursor rule: `.cursor/rules/leave-freeze.mdc`

---

## Production flags (expected)

```
WATHEFNI_LEAVE_AUTHORITY=on
WATHEFNI_LEAVE_AUTHORITY_COMPANIES=WATHEFNI
WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_ONLY=on
WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_KEY_MARKERS=…,LVW4,LVW4-SYNTH|
WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965525,965526,965527
WATHEFNI_LEAVE_POLICY_WAVE2=on
WATHEFNI_LEAVE_BALANCES=on
WATHEFNI_LEAVE_WORKFLOW_WAVE3=on
WATHEFNI_LEAVE_WAVE4=on
WATHEFNI_LEAVE_WAVE4_KILL=off (unset)
WATHEFNI_LEAVE_REAL_DECISION_GATE=on
WATHEFNI_LEAVE_REAL_DECISION_ALLOWLIST=<named WATHEFNI HR/manager phones>
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST=on
WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST=WATHEFNI-96550252254
```

Honesty pins: all `leave_policies.enforced=false` and `legal_reviewed=false` for WATHEFNI; balances observe-only.

Real leave history after Wave 4 dual-control cleanup of Fouad stale pending may show that request as `expired_stale` (audited) — approved/rejected sick fingerprints for the other two real rows must remain unchanged unless an explicit owner wave says otherwise.
