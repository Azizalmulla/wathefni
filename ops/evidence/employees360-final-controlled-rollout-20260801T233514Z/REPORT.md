# Employees 360 — Final controlled rollout closure

**Stamp:** `20260801T233514Z`  
**Evidence:** `ops/evidence/employees360-final-controlled-rollout-20260801T233514Z/`  
**Remote:** `/opt/wathefni/production-evidence/employees360-final-controlled-rollout/20260801T233514Z/`  
**Backup:** `/opt/wathefni/backups/production-pre-employees360-final-20260801T233514Z/`  
**Company:** WATHEFNI only

**Boundary honored:** no broad onboard · no real termination executed · exceptional/high-risk remains manual · Payroll owns monetary calculations · pre-hire / Wave D untouched · synthetic-only gates stay ON with named real allowlists.

---

## Overall Employees 360 completion: **PASS (controlled)**

Controlled real-user gates removed safely for a **single ESS/app canary** and **four classified employments**. Broad rollout is still intentionally blocked by allowlists.

---

## Separate verdicts

| Track | Verdict | Notes |
|---|---|---|
| **HR production use** | **GO** | Directory/Workforce live; all four reals classified `KW_PRIVATE_SECTOR@1.0.0`; remediation queue **0**; dual-control classification proven. |
| **Manager production use** | **GO** | Scope restrictions + self-approval denials intact; manager ESS for non-allowlisted reals still blocked by synthetic/allowlist gate. |
| **Controlled real employee-app use** | **GO (canary only)** | Canary **Talal Fadhli** `WATHEFNI-96550252254`: bind → session → revoke (`session_epoch`) → re-login; own-data only; other reals denied; bank changes denied; app require-allowlist on. |
| **Normal real lifecycle readiness** | **GO (readiness only)** | Four reals on lifecycle allowlist; pack resolved; impact preview OK; self-approval denied; **no real termination executed**. |
| **Exceptional / high-risk lifecycle** | **NO-GO (manual)** | Summary dismissal / exceptional path fail-closed without escalation note; `exceptional_cases_manual_only=true`; counsel/high-risk stay outside automated authority. |

---

## What changed

### 1) Dual-control classification (four reals)
Requester `azizalmulla16@gmail.com` → approver `f.burhama@disruptv.tech` (distinct actors).

| employee_key | Name | Pack |
|---|---|---|
| `WATHEFNI-96550252254` | Talal Fadhli | `KW_PRIVATE_SECTOR` `1.0.0` |
| `WATHEFNI-96566363363` | Fouad Burhamad | `KW_PRIVATE_SECTOR` `1.0.0` |
| `WATHEFNI-96597727743` | mohammad alqattan | `KW_PRIVATE_SECTOR` `1.0.0` |
| `WATHEFNI-96599411617` | Brian Saleh | `KW_PRIVATE_SECTOR` `1.0.0` |

Fields bound: `KW` · `private_sector` · `unlimited` · `monthly` · `probation_status=completed`.  
Unsupported jurisdiction (SA) fail-closed. Classification self-approval denied. All still `active`.

### 2) Quarantined synthetic remediation (8 rows)
Confirmed Wave 3/4c synthetic leftovers with `wave4c_quarantine.reason=confirmed_synthetic_canary_leftover`.  
**Employment history preserved** (`quarantined_synthetic_test` count still **8**).  
Queue filter now excludes quarantined/archived synthetics → remediation **count=0**. No genuine history deleted.

### 3) Named allowlists (synthetic-only preserved)
| Gate | Value |
|---|---|
| `ESS_V5_SYNTHETIC_ONLY` | **on** |
| `ESS_V5_REAL_ALLOWLIST` | `WATHEFNI-96550252254` only |
| `ESS_V5_BANK_REAL_ALLOWLIST` | **empty** (real bank denied) |
| `LIFECYCLE_V3_SYNTHETIC_ONLY` | **on** |
| `LIFECYCLE_V3_REAL_ALLOWLIST` | all four reals |
| `EMPLOYEE_APP` | **on** |
| `EMPLOYEE_APP_REQUIRE_ALLOWLIST` | **on** |
| `EMPLOYEE_APP_REAL_ALLOWLIST` | `WATHEFNI-96550252254` only |

Drop-in: `/etc/systemd/system/wathefni-orchestrator.service.d/zz-employee-final-controlled-rollout.conf` (sorts after `setup-console-v2` so `EMPLOYEE_APP=on` wins).

### 4) Canary ESS / app proofs (Talal)
- Identity bind to WATHEFNI person/employment  
- Duplicate/idempotent bind reuse  
- Session live → revoke → `session_epoch` stale → re-login  
- Own profile read; bank masked/absent  
- Personal request + letter request + tracking  
- HR approve ≠ apply then apply (personal)  
- Self-approval denied  
- Real bank change denied  
- Other three reals inaccessible to canary actor / app session  
- ESS + APP kill-switch (clear allowlist) deny, then restore  
- Audit journal: no probe IBAN / `iban_plaintext`  
- Sessions revoked at end; binding retained for canary continuity  

**Device note:** proofs use the same `/app` session + `session_epoch` binding surface. Physical OTP handset UX was not separately instrumented in this pack.

### 5) Lifecycle readiness (no terminate)
- Allowlist admits classified canary  
- Impact preview readable  
- Policy: `exceptional_cases_manual_only`  
- `monetary_calculations_owner` = payroll  
- Exceptional `summary_dismissal_41a` without escalation note → fail-closed  
- Lifecycle self-approval denied  
- All four remain `active`

---

## Canary result

**56 passed, 0 failed** (`canary/canary-rc.txt` = `0`)  
Script: `tests/canary-prod-employees360-final.py`

---

## Production SHAs

| File | SHA256 |
|---|---|
| `app.py` | `0e3e10f1fb0596c3add6aedcd92a319deb8d75254167bbe3ee792c9fe37648e5` |
| `employee_selfservice_wave5.py` | `a8f65ab04fe5f9f53e75ce1ae0eb27b1398b2c2223e6348319151620db79e2a3` |
| `employee_lifecycle_wave3.py` | `7964a01790edf5b637ee1b459a25aba08f182ba980dcc5498467bd3edcf808e1` |
| `employee_policy_packs_wave3h.py` | `c0d9a80255745656446113b8b305936df972efececc2bb4bccc53e17d17f9254` |

---

## Backup / kill-switch / rollback

- Backup + `ROLLBACK.sh` ready (`verify/rollback-tested.txt`, `verify/rollback-ready.txt`)  
- Kill-switch proven in-process by clearing ESS/APP allowlists  
- Full rollback restores pre-final modules + removes `zz-employee-final-controlled-rollout.conf`  
- Full rollback **not executed** post-GO (would remove canary enablement)

---

## Remaining (intentionally out of scope)

1. Broad ESS/app allowlist expansion beyond Talal  
2. Real bank-detail allowlist (still empty)  
3. Executing any real termination / notice apply  
4. Automating exceptional/high-risk legal judgment  
5. Physical device OTP UX screenshot pack  
6. Onboarding additional real employees  

---

## Explicit non-goals (honored)

No broad employee onboard · no real termination · no unsupported jurisdictions enabled · no pre-hiring / Wave D changes · no Payroll calculation ownership change.
