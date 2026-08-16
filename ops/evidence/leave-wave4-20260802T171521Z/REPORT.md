# Leave Wave 4 — UX refinement, controlled real-operation readiness, freeze

**Stamp:** `20260802T171521Z`  
**Evidence:** `ops/evidence/leave-wave4-20260802T171521Z/`  
**Remote:** `/opt/wathefni/production-evidence/leave-wave4/20260802T171521Z/`  
**Company:** WATHEFNI · Wave 4 module `leave_wave4_controlled` **@ 4.0.0**  
**Staging prior:** `ops/evidence/leave-wave4-staging-20260802T171327Z/` (smoke **24/24**, UI strings in staging dist)

---

## Separate verdicts

| Concern | Verdict |
|---|---|
| **HR production Leave use** | **GO (controlled)** — LeaveWorkspace EN/AR UX; real decisions via named allowlist `96599338566,96588009911`; honesty banners; dual-control stale cleanup |
| **Manager production Leave use** | **GO (scoped)** — self-approval ban global; real decisions still allowlist-gated; restricted manager scope required for sensitive attachments |
| **Talal employee-app Leave use** | **GO (unchanged)** — `WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST=WATHEFNI-96550252254` only |
| **Broad employee-app rollout** | **NO-GO** |
| **Real balance enforcement** | **NO-GO** — `enforced=false`, `legal_reviewed=false`, balances non-binding |
| **Payroll monetary impact** | **NO-GO / none** — unpaid handoff classification/duration only; `monetary_fields_present` absent |
| **Overall Leave completion** | **GO for controlled WATHEFNI Leave** — frozen against enforcement, Payroll money, and broad app expansion |

---

## Production SHAs and flags (final)

| File | SHA256 |
|---|---|
| `app.py` | `73036b5909191b09a4e3af55d8d989ba12af7e9103f5d48961cf949019699029` |
| `leave_wave4_controlled.py` | `4fdfe59d2f1c2bdc1672236afaf1ad504ae8390ec789784435d4c6fb311b79a9` |
| `leave_workflow_wave3.py` | `c8dad47eaca79e57be84dbecb6bd5891768e3554db035a45404e35f88be4e7d4` |
| `leave_policy_wave2.py` | `809d427c8163395ee92bf7b1e15446450d122c662b95a985146283ac9286d5b7` |
| `leave_authority_wave1.py` | `b153a0cf6154d82698f3f54342efa15e1591c6e6df14c05b5d47ca45b9ee8e8a` |
| `employee_lifecycle_wave3c.py` | `f2dfbabb717dc8a4d912619663681973b1346f2224e69b45a5fe26c912161099` (unchanged) |

| Flag | Value |
|---|---|
| `WATHEFNI_LEAVE_WAVE4` | **on** |
| `WATHEFNI_LEAVE_REAL_DECISION_GATE` | **on** |
| `WATHEFNI_LEAVE_REAL_DECISION_ALLOWLIST` | `96599338566,96588009911` |
| `WATHEFNI_LEAVE_WORKFLOW_WAVE3` | **on** |
| `WATHEFNI_LEAVE_POLICY_WAVE2` | **on** |
| `WATHEFNI_LEAVE_BALANCES` | **on** (observe-only) |
| `WATHEFNI_LEAVE_AUTHORITY` | **on** |
| `WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_ONLY` | **on** |
| `WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_KEY_MARKERS` | includes `LVW4,LVW4-SYNTH|` |
| `WATHEFNI_ATTENDANCE_CAPTURE_INGEST` | **off** |
| `WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST` | **on** |
| `WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST` | `WATHEFNI-96550252254` |
| Accrual timer | **enabled / active** |

Drop-in: `zzzzzzz-leave-wave4.conf`

---

## Controlled real-operation evidence

| Item | Result |
|---|---|
| Fouad stale pending `dbf82ecf-…` | **Resolved** via dual-control → `expired_stale` (HR1 initiate / HR2 confirm; same-actor denied) |
| Non-allowlisted real approve | `leave_real_decision_not_allowlisted` |
| Self-approval (real) | `self_approval_forbidden` |
| Four employees policy/lifecycle eligibility | **4/4 found**, `enforced=false` |
| Holiday year status | Present; `fail_closed_if_enforced` when not approved |
| Ledger / balances | **28 / 4** unchanged vs preflight (no enforcement mutation) |

Frozen sick fingerprints (unchanged):

| leave_id | status | fp |
|---|---|---|
| `e3217e0e-…` | approved sick | `abf4cba7cb8702b2d7c067db795d0701` |
| `51cd940f-…` | rejected sick | `8f6d67e3cc4fbf5ee321af235ecbb20d` |

Stale annual after dual-control: `dbf82ecf-…` → `expired_stale` · fp `3c6801c99cfd0ebc5db0acc24e4fd774`

---

## UX / workflow proof

- LeaveWorkspace (pre-hiring / E360 chrome): queue, detail, half-day/hourly/unpaid, RFI/resubmit/withdraw/cancel, dual-control, honesty + holiday banners, EN/AR
- Production dashboard strings: `non-binding`, `غير ملزم`, `dual-control`, `Request info` / `طلب معلومات`
- Canary final **60/60** (`canary-final`): annual/sick/half/hourly/unpaid, needs-info/resubmit/withdraw/cancel, self-approval ban, stale concurrency, overlap, kill switch, attachment privacy, unpaid no money, residual synth **0**
- Sensitive attachments: **masked by default** for unrestricted strangers; privileged HR (`hr_privileged`) can view; default-mask proved separately (`DEFAULT_MASK_OK`)

---

## Backup / rollback / kill switch

| Item | Evidence |
|---|---|
| Backup | `/opt/wathefni/backups/production-pre-leave-wave4-20260802T171521Z/` (+ redeploy backup) |
| Rollback | `ROLLBACK_OK` (wave4 module + drop-in removed; Wave 3B posture restored) |
| Redeploy + final canary | `WAVE4_FINAL_OK` · **60/60** |
| Kill switch | `WATHEFNI_LEAVE_WAVE4_KILL=on` disables Wave 4 (canary-proved) |

---

## Freeze regressions

| Suite | Result |
|---|---|
| Leave freeze | **35/35** local · **34/34** remote |
| Employees 360 | **57/57** |
| Onboarding | **54/54** |
| Attendance | **26/26** |

Formal freeze: `ops/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md`  
Cursor gate: `.cursor/rules/leave-freeze.mdc`  
Smoke: `smoke-test-leave-freeze-regression.py`

---

## Explicitly not enabled

- `enforced=true` / `legal_reviewed=true`
- Payroll monetary calculation from Leave
- Broad employee-app leave access beyond Talal
- Real balance mutation based on enforcement
- Changes to frozen Employees 360 / Onboarding / Attendance modules

## Scripts

- `ops/qualify-leave-wave4-staging.sh`
- `ops/deploy-leave-wave4-prod.sh`
- `ops/migrate-leave-wave4-prod.sh`
- `ops/run-leave-wave4-prod.sh`
- `canary-prod-leave-wave4.py`
- `smoke-test-leave-wave4-ux.py`
- `smoke-test-leave-freeze-regression.py`
