# Employees 360 — Controlled rollout completion & freeze

**Status:** **FROZEN — production-qualified under controlled rollout**  
**Freeze date:** 2026-08-02 (stamp family `20260801T233514Z`)  
**Tenant scope:** WATHEFNI only  
**Decision:** Close further Employees 360 feature/redesign work. Operate and expand allowlists only via explicit owner change control.

---

## 1. Final posture (authoritative)

| Track | Verdict |
|---|---|
| **HR production use** | **GO** |
| **Manager production use** | **GO** |
| **Employee app** | **Talal allowlisted canary only** (`WATHEFNI-96550252254`) |
| **Normal lifecycle** | **Controlled readiness GO** (no broad real termination campaign) |
| **Exceptional / high-risk lifecycle** | **Manual only** |
| **Payroll** | **Owns monetary calculations** |
| **Unsupported jurisdictions** | **Fail closed** |
| **Synthetic-only + named allowlists** | **Remain active** |

**Overall Employees 360 completion:** **PASS (controlled)** — not a license for broad real-user onboard.

---

## 2. Architecture (frozen layers)

```
Pre-hiring / Wave D  ── FROZEN (do not change for E360 work)
        │
Wave 0–1  Identity hygiene / phone canon / quarantine
        │
Wave 2    Authority map (person ↔ employment ↔ assignment ↔ employee_key)
        │
Wave 3    Lifecycle + public-law policy + KW packs (3H/3I)
        │
Wave 4    Org units + assignment history + transfers/migration
        │
Wave 5    ESS requests + identity bind + bank encryption + session_epoch
        │
Wave 6–7  Workforce UX + production qualification
        │
Final     Named real allowlists (ESS / App / Lifecycle) under synthetic-only
```

**Authority rule:** UI never grants power. Mutations go through Wave 2–5 APIs. Approve ≠ apply. Remediation classification is dual-control and does not execute lifecycle.

**Payroll rule:** Lifecycle/ESS may surface settlement *packets* / readiness; they must not compute or own pay amounts (`monetary_calculations_owner=payroll`).

---

## 3. Production flags & allowlists (live contract)

Synthetic-only **stays ON**. Real access is **additive allowlist only**.

| Variable | Required posture |
|---|---|
| `WATHEFNI_EMPLOYEE_AUTHORITY_V2` | `on` (WATHEFNI) |
| `WATHEFNI_EMPLOYEE_ORG_V4` | `on` (+ activate-due as deployed) |
| `WATHEFNI_EMPLOYEE_LIFECYCLE_V3` | `on` |
| `WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY` | **`on`** |
| `WATHEFNI_EMPLOYEE_LIFECYCLE_V3_REAL_ALLOWLIST` | four classified reals |
| `WATHEFNI_EMPLOYEE_POLICY_PACKS_V3H` | `on` |
| `WATHEFNI_EMPLOYEE_ESS_V5` | `on` |
| `WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_ONLY` | **`on`** |
| `WATHEFNI_EMPLOYEE_ESS_V5_REAL_ALLOWLIST` | `WATHEFNI-96550252254` |
| `WATHEFNI_EMPLOYEE_ESS_V5_BANK_REAL_ALLOWLIST` | **empty** |
| `WATHEFNI_EMPLOYEE_APP` | `on` |
| `WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST` | **`on`** |
| `WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST` | `WATHEFNI-96550252254` |

**Drop-in (must sort after `setup-console-v2.conf`):**  
`/etc/systemd/system/wathefni-orchestrator.service.d/zz-employee-final-controlled-rollout.conf`

**Classified reals (all `KW_PRIVATE_SECTOR@1.0.0`):**

| Key | Name | Role in freeze |
|---|---|---|
| `WATHEFNI-96550252254` | Talal Fadhli | ESS + App canary |
| `WATHEFNI-96566363363` | Fouad Burhamad | Lifecycle allowlisted; classified |
| `WATHEFNI-96597727743` | mohammad alqattan | Lifecycle allowlisted; classified |
| `WATHEFNI-96599411617` | Brian Saleh | Lifecycle allowlisted; classified |

**Only verified pack enabled:** `KW_PRIVATE_SECTOR`. SA / UAE / domestic / oil / gov remain reserved or unsupported → fail closed.

---

## 4. Evidence packs (index)

| Wave / stage | Evidence path |
|---|---|
| Wave 0 truth | `ops/evidence/employees360-wave0-prod-truth-20260801T184148Z/` |
| Wave 1 / 1C | `…-wave1-1b-prod-deploy-…` / `…-wave1c-hygiene-prod-apply-…` |
| Wave 2 authority | `…-wave2-authority-prod-deploy-20260801T202518Z/` |
| Wave 3 lifecycle / packs | `…-wave3*` through `…-wave3i-prod-deploy-20260801T220707Z/` |
| Wave 4 org | `…-wave4c-prod-deploy-20260801T221934Z/` |
| Wave 5 ESS | `…-wave5c-prod-canary-20260801T225111Z/` |
| Wave 6 UX | `…-wave6-ux-20260801T231034Z/` |
| Wave 7 prod qual | `…-wave7-prod-qual-20260801T232347Z/` |
| **Final controlled rollout** | **`ops/evidence/employees360-final-controlled-rollout-20260801T233514Z/`** |
| **Freeze closure** | **`ops/evidence/employees360-freeze-closure-20260801T235140Z/`** |
| Remote final | `/opt/wathefni/production-evidence/employees360-final-controlled-rollout/20260801T233514Z/` |

Final canary: **56/56** (`canary-prod-employees360-final.py`).

---

## 5. Rollback paths

| Scope | Path |
|---|---|
| Pre-final modules + drop-in | `/opt/wathefni/backups/production-pre-employees360-final-20260801T233514Z/ROLLBACK.sh` |
| Wave 7 UI | `/opt/wathefni/backups/production-pre-employees360-wave7-20260801T232347Z/` |
| Wave 5C ESS | `/opt/wathefni/backups/production-pre-employees360-wave5c-20260801T225111Z/` |

**Soft kill (preferred first):** clear or shrink  
`WATHEFNI_EMPLOYEE_ESS_V5_REAL_ALLOWLIST`,  
`WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST`,  
`WATHEFNI_EMPLOYEE_LIFECYCLE_V3_REAL_ALLOWLIST`  
then `daemon-reload` + restart. Keep `*_SYNTHETIC_ONLY=on`.

**Hard kill:** set `WATHEFNI_EMPLOYEE_APP=off` and/or `WATHEFNI_EMPLOYEE_ESS_V5=off` via drop-in; revoke canary sessions (`revoke_employee_sessions`).

---

## 6. Known manual boundaries (do not automate)

1. Exceptional / summary dismissal / disputed termination / Art. 41–42–48 judgment  
2. Broad ESS or employee-app allowlist expansion  
3. Real bank-detail changes (bank allowlist empty)  
4. Executing real terminations as a campaign  
5. Enabling unsupported jurisdictions or reserved packs  
6. Dual-control classification for *new* hires still requires two operators  
7. Physical OTP handset UX packaging (API `session_epoch` path is qualified)  
8. Pre-hiring and Wave D product behavior  

---

## 7. Operating runbook

### Daily / weekly
- HR: Employees + Workforce hub (org, remediation, requests) under owner/manager scopes  
- Confirm remediation queue stays clean for classified reals  
- Do not lift synthetic-only without a written allowlist change request  

### Add one more ESS/app canary
1. Dual-control classify if not already `KW_PRIVATE_SECTOR@1.0.0`  
2. Append key to `ESS_V5_REAL_ALLOWLIST` and `EMPLOYEE_APP_REAL_ALLOWLIST`  
3. Bind identity → session revoke → re-login proof  
4. Keep `BANK_REAL_ALLOWLIST` empty unless explicitly approved  
5. Record evidence under a new `ops/evidence/employees360-allowlist-…` stamp  

### Lifecycle readiness (normal)
- Key must be classified + on `LIFECYCLE_V3_REAL_ALLOWLIST`  
- Use impact preview / dual-control request flow  
- Never auto-apply exceptional cases  
- Cancel probes; do not leave live termination requests without owner intent  

### Incident
1. Soft-kill allowlists  
2. Revoke canary/app sessions  
3. If UI/API regression: run `ROLLBACK.sh` from the matching backup  
4. Re-run `smoke-test-employees360-freeze-regression.py` before re-opening  

---

## 8. Regression gates (mandatory for future post-hire PRs)

**Script:** `wathefni-orchestrator/smoke-test-employees360-freeze-regression.py`  
**Cursor rule:** `.cursor/rules/employees360-freeze.mdc`

Future post-hiring work **must not**:

| Gate | Forbidden change |
|---|---|
| Wave 2 authority | Bypass `employee_key_authority_map` / scope checks for hub mutations |
| Wave 4 history | Overwrite or delete assignment history slices except audited rollback APIs |
| Wave 3 packs | Soft-enable reserved/unsupported jurisdictions; skip `assert_pack_resolved` |
| ESS identity / encryption | Weaken bind uniqueness, `session_epoch` revoke, or bank Fernet-at-rest |
| Dual-control | Allow self-approval on classification, status, or lifecycle |
| Jurisdictions | Expose non-`KW_PRIVATE_SECTOR` packs as enabled |
| Pre-hire / Wave D | Modify frozen pre-hiring or Wave D ingress/behavior “for E360 convenience” |

Also forbidden without a new owner-approved wave: redesign of Employees/Workforce UX, broad allowlist, or turning `*_SYNTHETIC_ONLY=off`.

---

## 9. Freeze declaration

Employees 360 is **closed for feature/redesign**. Allowed work after freeze:

- Bugfixes that restore freeze invariants  
- Allowlist edits under this runbook  
- Evidence / ops documentation  
- Next **non-E360** post-hire module audits  

Signed closure stamp: final evidence pack `employees360-final-controlled-rollout-20260801T233514Z`, freeze closure `employees360-freeze-closure-20260801T235140Z`, and this document.

---

## 10. Recommended next post-hiring module

**Onboarding** — **completed and frozen** (see `ops/ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md`, Wave 4 `20260802T014652Z`).

**Next:** **Attendance** — audit next.

| Criterion | Why Attendance |
|---|---|
| Commercial value | Daily operational truth for Kuwait workforce; reduces manual timesheet friction |
| Dependency order | Needs frozen E360 identity + Onboarding readiness; precedes Leave → Shifts → Payroll |
| Production risk | Lower blast radius than Payroll; can ship dark/canary like prior modules |
| Fit | Post-hire Attendance surface already exists; must not weaken E360 / Onboarding / pre-hire freezes |