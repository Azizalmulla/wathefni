# Onboarding — Controlled rollout completion & freeze

**Status:** **FROZEN — production-qualified for controlled WATHEFNI operation**  
**Freeze date:** 2026-08-02  
**Closure stamp:** `20260802T015200Z` (family: Wave 4 `20260802T014652Z`)  
**Tenant scope:** WATHEFNI only  
**Decision:** Close further Onboarding feature/redesign work. Operate under this runbook only; expand SEED or employee-app access only via explicit owner change control.

---

## 1. Final posture (authoritative)

| Track | Verdict |
|---|---|
| **HR production use** | **GO** |
| **Manager production use** | **scoped GO** |
| **Talal employee-app onboarding** | **GO** (`WATHEFNI-96550252254` allowlist only) |
| **Broad employee-app rollout** | **disabled** |
| **General automatic onboarding seed** | **disabled** |
| **Template authority** | **`default_kuwait@2.0.0`** |
| **Bank collection** | **ESS-owned** (encrypted; plaintext impossible via onboarding) |
| **Historical checklist / migrations** | **auditable** (retired_legacy retained; Wave 3 dual-control batches) |

**Overall Onboarding completion:** **PASS (controlled WATHEFNI HR operation)** — not a license for broad employee onboard or automatic seeding.

---

## 2. Architecture (frozen layers)

```
Pre-hiring / Wave D     ── FROZEN (do not change for Onboarding work)
Employees 360           ── FROZEN (identity / authority / ESS bank)
        │
Wave 0    Production truth snapshot (four reals)
        │
Wave 1 / 1B   Read authority — load_onboarding_items joins employees;
              no candidates.read; bank plaintext forbidden
        │
Wave 2 / 2B   Canonical default_kuwait@2.0.0 + synthetic canary
              (SEED/HR_MUTATE remain gated; canary path for synthetics)
        │
Wave 3    Controlled four-real migration (dual-control; history kept)
        │
Wave 4    WATHEFNI-only HR_MUTATE + UX queue/groups/actions + qualify
        │
Freeze    This document + regression smoke + Cursor rule
```

**Authority rules (frozen):**

- Checklist reads go through `load_onboarding_items` (tenant join + bank mask).
- Mutations require `onboarding.manage` + `WATHEFNI_ONBOARDING_HR_MUTATE` (+ company allowlist) or synthetic-canary path.
- Manager scope: list uses `_employee_scope_where`; detail uses `context_manager_allows_employee`.
- Bank: `authority=ess` / `collection_mode=ess_encrypted`; never plaintext mark/receipt.
- Template pin: assignment + item `template_version`; in-code template evolution must not silently rewrite pinned history.
- Optimistic concurrency: `row_version` / `expected_row_version` → `stale_item_version`.
- Audit: `onboarding_audit_events` on mark/waive/cancel/reschedule/migration.

---

## 3. Production flags (live contract)

| Variable | Required posture |
|---|---|
| `WATHEFNI_ONBOARDING_SEED` | **`off`** |
| `WATHEFNI_ONBOARDING_HR_MUTATE` | **`on`** (WATHEFNI operation) |
| `WATHEFNI_ONBOARDING_HR_MUTATE_COMPANIES` | **`WATHEFNI`** |
| `WATHEFNI_ONBOARDING_SYNTHETIC_CANARY` | `on` (synthetic lifecycle prove only) |
| `WATHEFNI_ONBOARDING_SYNTHETIC_PHONE_PREFIXES` | `965523` |
| `WATHEFNI_ONBOARDING_SYNTHETIC_NAME_PREFIX` | `W2B-SYNTH\|` |
| `WATHEFNI_EMPLOYEE_APP` | `on` |
| `WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST` | **`on`** |
| `WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST` | **`WATHEFNI-96550252254` only** |
| ESS bank real allowlist | **empty** (bank still ESS-owned; no plaintext fallback) |

**Drop-in:**  
`/etc/systemd/system/wathefni-orchestrator.service.d/zz-onboarding-wave4-hr-mutate.conf`

```
Environment=WATHEFNI_ONBOARDING_SEED=off
Environment=WATHEFNI_ONBOARDING_HR_MUTATE=on
Environment=WATHEFNI_ONBOARDING_HR_MUTATE_COMPANIES=WATHEFNI
```

**Four reals (pinned `2.0.0`):**

| Key | Name |
|---|---|
| `WATHEFNI-96550252254` | Talal Fadhli |
| `WATHEFNI-96566363363` | Fouad Burhamad |
| `WATHEFNI-96597727743` | mohammad alqattan |
| `WATHEFNI-96599411617` | Brian Saleh |

---

## 4. Permissions

| Permission | Use |
|---|---|
| `onboarding.read` | Queue / detail / profile read |
| `onboarding.manage` | Mark, waive, remind, reschedule, cancel (still gated by HR_MUTATE + company + manager scope) |

Self-approval of dual-control **migration** batches remains forbidden (`self_approval_forbidden`). HR item mutations are operator actions with audit — not dual-control approve/apply.

---

## 5. Template / version rules

| Rule | Contract |
|---|---|
| Canonical template | `default_kuwait` |
| Canonical version | **`2.0.0`** (`CANONICAL_TEMPLATE_VERSION` in `onboarding_wave2.py`) |
| Pinning | `employee_onboarding_assignments.template_version` + per-item `template_version` + `employees.onboarding_template_version` |
| Evolution | New template versions require an explicit migration wave; **no silent rewrite** of pinned rows |
| Obsolete items | `retired_legacy` status — retained for audit, excluded from pending counts |
| Bank item | `bank_details` → ESS authority only |
| Compliance mirrors | `*_expiry` / gov prompts — Compliance module remains source of truth |

---

## 6. Migration history (auditable)

| Wave | Stamp | Outcome |
|---|---|---|
| Wave 0 truth | `onboarding-wave0-prod-truth-20260801T235617Z` | Snapshot |
| Wave 1 / 1B | `…-wave1-loader-repair-…` / `…-wave1b-prod-deploy-20260802T003750Z` | Read authority |
| Wave 2 staging | `…-wave2-staging-20260802T010724Z` | Template + staging mutate |
| Wave 2B canary | `…-wave2b-prod-canary-20260802T011738Z` | Synthetic-only prod canary |
| Wave 3 migration | `…-wave3-migration-20260802T012829Z` | Four-real migrate; dual-control; rollback→reapply |
| Wave 4 HR + UX | `…-wave4-20260802T014652Z` | WATHEFNI HR_MUTATE + UX qualify |
| **Freeze closure** | **`ops/evidence/onboarding-freeze-closure-20260802T015200Z/`** | This freeze |

**Final Wave 3 reapply batch:** `74b7298b-0fe5-4a1e-b1ed-69c703f30a6d`  
**Live row volume (four reals):** 150 (incl. `retired_legacy`)

---

## 7. Rollback paths

| Scope | Path |
|---|---|
| Wave 4 code + HR_MUTATE drop-in | `/opt/wathefni/backups/production-pre-onboarding-wave4-20260802T014652Z/ROLLBACK.sh` |
| Wave 4 dashboard dist | `/opt/wathefni/backups/production-pre-onboarding-wave4-dashboard-20260802T014652Z/` |
| Wave 3 data | `onboarding_wave3_migration.rollback_batch` (+ Wave 3 backup) |
| Wave 2B synthetic canary | `/opt/wathefni/backups/production-pre-onboarding-wave2b-20260802T011738Z/ROLLBACK.sh` |

**Soft kill (preferred):** remove or empty  
`zz-onboarding-wave4-hr-mutate.conf`  
→ `HR_MUTATE` falls off / company gate closes; keep `SEED=off`.  
Proven: Wave 4 `verify/kill-switch-execute.txt`.

**Hard kill:** set `WATHEFNI_ONBOARDING_HR_MUTATE=off` explicitly; restore prior `app.py` / dashboard via ROLLBACK.sh if needed.

---

## 8. Operating runbook

### Daily HR (WATHEFNI)
- Open Post-hire → Onboarding queue
- Work in-scope employees: mark complete, waive, remind, reschedule, cancel
- Bank: send employee to encrypted ESS — never paste IBAN into checklist
- Do not enable SEED or broaden employee-app allowlist from the UI

### Manager
- Same actions only for employees inside manager scope
- Outside scope → fail closed (not found / outside manager scope)

### Add a new hire checklist (without general SEED)
- Prefer explicit start for that employee under HR_MUTATE (or future named allowlist wave)
- Do **not** turn `ONBOARDING_SEED=on` globally

### Incident
1. Soft-kill HR_MUTATE drop-in  
2. Confirm SEED still off + employee-app allowlist unchanged  
3. Code regression → Wave 4 `ROLLBACK.sh`  
4. Re-run `smoke-test-onboarding-freeze-regression.py` and `smoke-test-employees360-freeze-regression.py` before re-opening  

---

## 9. Known controlled-rollout limits

1. General automatic SEED remains **off**  
2. Employee-app onboarding remains **Talal-only**  
3. ESS bank **real allowlist empty** — tracking via ESS authority; plaintext impossible  
4. Synthetic WhatsApp remind may lack outbound company context (HR remind on reals is the production path)  
5. No redesign of Onboarding UX after this freeze  
6. Employees 360 / pre-hiring / Wave D stay frozen siblings  
7. Cross-tenant HR_MUTATE denied by company allowlist  

---

## 10. Regression gates (mandatory for future post-hire PRs)

**Script:** `wathefni-orchestrator/smoke-test-onboarding-freeze-regression.py`  
**Cursor rule:** `.cursor/rules/onboarding-freeze.mdc`

Future work **must not**:

| Gate | Forbidden change |
|---|---|
| Recruiter bleed | Reintroduce `candidates.read` (or recruiter entitlements) into onboarding loaders |
| Tenant / manager scope | Bypass company join, `_employee_scope_where`, or `context_manager_allows_employee` / `manager_scope_allows_employee` |
| Plaintext bank | Accept IBAN/bank plaintext via mark, receipt, or unmasked checklist `value` |
| Template history | Silently rewrite pinned `template_version` rows or delete `retired_legacy` without audited migration |
| Concurrency / audit | Remove `expected_row_version` / `stale_item_version` or stop writing `onboarding_audit_events` on mutations |
| Broad SEED / app | Enable general `ONBOARDING_SEED` or broaden `EMPLOYEE_APP_REAL_ALLOWLIST` without explicit rollout wave |
| Sibling freezes | Change frozen Employees 360 or pre-hiring / Wave D behavior “for onboarding convenience” |

Also forbidden without owner change-control: Onboarding redesign, new checklist product features, or turning company allowlist empty while HR_MUTATE is globally on.

---

## 11. Freeze declaration

Onboarding is **closed for feature/redesign**. Allowed work after freeze:

- Bugfixes that restore freeze invariants  
- Ops evidence / documentation  
- Explicit flag/allowlist change-control under this runbook  
- Next **non-Onboarding** post-hire module audits  

Signed by Wave 4 production qualification (`onboarding-wave4-20260802T014652Z`: canary 68/68, Wave1 38/38, E360 freeze 54/54, fingerprint unchanged) and this freeze closure pack.

---

## 12. Recommended next post-hiring module

**Attendance** — audit next.

| Criterion | Why Attendance |
|---|---|
| Dependency order | Needs frozen employee identity (E360) + onboarding readiness (device/access items); precedes Leave → Shifts → Payroll |
| Commercial value | Daily operational truth for Kuwait workforce; reduces manual timesheet friction |
| Production risk | Lower blast radius than Payroll; higher than Leave-only; can ship dark/canary like prior modules |
| Fit | Post-hire Attendance surface already exists; must not weaken Onboarding/E360 freezes |

**Not next:** Payroll (depends on attendance/leave + ESS bank maturity); broad employee-app or SEED (explicitly disabled).
