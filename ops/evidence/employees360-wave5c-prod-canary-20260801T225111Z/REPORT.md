# Employees 360 Wave 5C — Production synthetic canary (ESS self-service)

**Stamp:** `20260801T225111Z`  
**Evidence:** `ops/evidence/employees360-wave5c-prod-canary-20260801T225111Z/`  
**Remote:** `/opt/wathefni/production-evidence/employees360-wave5c-prod-canary/20260801T225111Z/`  
**Backup:** `/opt/wathefni/backups/production-pre-employees360-wave5c-20260801T225111Z/`  
**Schema:** `employees360-wave5b-selfservice-v1`  
**Allowlist:** phones `965549*`, names `W5C-SYNTH|`  
**Company:** WATHEFNI only

**Boundary honored:** real lifecycle stays `SYNTHETIC_ONLY=on` · Wave 3F/3H + Wave 4 flags unchanged · `WATHEFNI_EMPLOYEE_APP=off` · four reals untouched · no Wave 6 / UI redesign / pre-hire / Wave D changes · no real-employee onboarding or classification.

---

## Separate GO / NO-GO verdicts

| Track | Verdict | Notes / blocker |
|---|---|---|
| **Synthetic production self-service** | **GO** | Canary **45/45**; ESS live for WATHEFNI synthetic allowlist only |
| **Employee identity readiness** | **GO** (synthetic) | Bind→person/employment; `session_epoch` wired to `/app` session auth; revoke invalidates tokens |
| **Encrypted bank-data readiness** | **GO** (synthetic) | Fernet `ess_bank_v1` at rest; mask default; plaintext writes fail; unmask audited; rotate/re-wrap OK |
| **Controlled real-user rollout readiness** | **NO-GO** | `ESS_V5_SYNTHETIC_ONLY=on` (required) · `EMPLOYEE_APP=off` · four reals still unclassified / not onboarded · real lifecycle still synthetic-only |

---

## Production SHAs (after)

| File | SHA256 |
|---|---|
| `app.py` | `1c33707f3ede082b47a6a48f46f91717511bc256dba2dedb1e26ca171549f193` |
| `employee_selfservice_wave5.py` | `942a440a404284cbac0bd7e3193db205150e878ee63a35ab87d135b2157fc7ca` |
| `canary-prod-wave5c-ess.py` | `31a2224d008255cda33428bb83340e7fbe56daf52f41e9315152a1dccaa2551c` |
| `employee_org_wave4.py` (unchanged) | `2828df20cbedca6905ec15adf602994abfa96f678648947ffdf1d3577f2bb5f5` |
| `employee_lifecycle_wave3c.py` (unchanged) | `dad7fbc7aabb8d2eb859ce697a6459b4ce54ca5414077992ced77a8f3637d696` |
| `employee_policy_packs_wave3h.py` (unchanged) | `31e0a7c5f8ea0ce61814363956e3bcbc321513a80112a1da946e5a5cb7fc3b19` |

**Before:** ESS module absent; 0 `employee-ess` routes; no `employee_ess_*` tables.  
Artifacts: `preflight/before.txt`, `preflight/after-deploy.txt`, `verify/final-prod-state.txt`.

---

## Flags (live)

```
WATHEFNI_EMPLOYEE_ESS_V5=on
WATHEFNI_EMPLOYEE_ESS_V5_COMPANIES=WATHEFNI
WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_ONLY=on
WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_PHONE_PREFIXES=965549
WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_NAME_PREFIX=W5C-SYNTH|
WATHEFNI_ESS_BANK_SECRET_KEY=<redacted via EnvironmentFile>
WATHEFNI_ESS_BANK_SECRET_KEY_PREVIOUS=<redacted via EnvironmentFile>

# preserved
WATHEFNI_EMPLOYEE_ORG_V4=on (WATHEFNI)
WATHEFNI_EMPLOYEE_LIFECYCLE_V3=on + SYNTHETIC_ONLY=on (965522 / W3D-SYNTH|)
WATHEFNI_EMPLOYEE_POLICY_PACKS_V3H=on
WATHEFNI_EMPLOYEE_AUTHORITY_V2=on
WATHEFNI_EMPLOYEE_APP=off
```

Drop-in: `/etc/systemd/system/wathefni-orchestrator.service.d/employee-ess-v5.conf`  
Lifecycle timer: still **enabled/active** (`wathefni-lifecycle-effective.timer`).

---

## Backup + rollback proof

- Backup: `/opt/wathefni/backups/production-pre-employees360-wave5c-20260801T225111Z/`
- Contains pre-deploy `app.py`, Wave 3F/3H + Wave 4 modules, lifecycle/org drop-ins, schema dump, four-reals CSV, executable `ROLLBACK.sh`
- Validated: `bash -n`, executable bit, removes ESS module + `employee-ess-v5.conf`, restores prior app + flags (`verify/rollback-tested.txt`)
- Full rollback **not executed** after GO canary (would remove live ESS); script is ready for ops use
- Additive schema only (`employee_ess_*`); no destructive shared-table alters

---

## Key provisioning proof (no secret material)

| Item | Evidence |
|---|---|
| Path | `/root/.openclaw/secrets/wathefni-ess-bank.production.env` |
| Mode / owner | `600` / `root:root` |
| Keys present | `WATHEFNI_ESS_BANK_SECRET_KEY`, `WATHEFNI_ESS_BANK_SECRET_KEY_PREVIOUS` |
| Fingerprints (sha256[:8]) | primary `8d180c0c`, previous `1e09fabb` |
| Lengths | 44 / 44 (Fernet url-safe) |
| Loaded in orchestrator proc | yes (presence counts only; values redacted in evidence) |
| Not in health / OpenAPI | `keys/api-exposure-proof.txt` |
| Not in evidence payloads | `evidence_secret_scan_clean=true` |
| Not in audit journal as env secret | `keys/journal-secret-scan.txt` → `0` |
| Drop-in | `EnvironmentFile=-…`; **no inline key values** |

Staging keys were **not** copied; new production keys generated on host.

---

## Schema evidence

`employee_ess_schema_meta`: `employees360_wave5=employees360-wave5b-selfservice-v1`

Tables: `employee_ess_audit_journal`, `employee_ess_bank_profiles`, `employee_ess_document_versions`, `employee_ess_identity_bindings`, `employee_ess_letter_orders`, `employee_ess_overlay_conflicts`, `employee_ess_personal_profiles`, `employee_ess_request_events`, `employee_ess_requests`, `employee_ess_schema_meta`, `employee_ess_sensitive_access_log`

Also: `employee_sessions.ess_session_epoch` (additive).

**13** `employee-ess` OpenAPI routes registered.

---

## Synthetic IDs (canary tag `6b3adb25`)

| Role | employee_key |
|---|---|
| Employee | `WATHEFNI-96554919301` |
| Manager | `WATHEFNI-96554919302` |
| Report | `WATHEFNI-96554919303` |
| Dup-phone | `WATHEFNI-96554919304` |
| Terminated | `WATHEFNI-96554919305` |
| Suspended | `WATHEFNI-96554919306` |

All cleaned afterward (leftover count **0**).

---

## Identity / session evidence

- Bind matched Wave 2 `person_id` + `employment_id` for employee
- `/app` session stamped with `ess_session_epoch`; auth succeeded pre-revoke
- `revoke_employee_sessions` bumped epoch + revoked app sessions (`app_sessions_revoked=1`, reason `ess_session_epoch_bump`)
- Stale token → `employee_by_session` returns `None`
- Duplicate phone bind → `phone_already_bound`
- Terminated → `session_not_allowed`; suspended bank → `suspended_employee_request_blocked`

---

## Encryption / rotation evidence

| Check | Result |
|---|---|
| At-rest schema | `ess_bank_v1` with ciphertext (no plaintext IBAN in blob) |
| Fingerprint | `5425959aa0fc0391` |
| Masked default | IBAN `****` / has_bank_on_file |
| Plaintext write | `plaintext_bank_forbidden` |
| Authorized unmask | plaintext visible to HR unmask perm; row in `employee_ess_sensitive_access_log` |
| Rotation / re-wrap | `rotate_bank_encryption` → version **2**, data retained |

---

## Request routing / application evidence

| Flow | Result |
|---|---|
| Personal + emergency | applied to ESS overlays |
| Bank | `pending_hr` → `pending_payroll` → `approved` → separate `apply` → applied; retry idempotent |
| Documents | civil_id versions ≥2 preserved |
| Transfer + manager-change | applied via Wave 4 `apply_assignment_change`; history grew |
| Approve ≠ apply | bank stayed `approved` until apply |
| Stale overlay | `overlay_conflict` → state `needs_review` |
| Self-approval / cross-tenant / manager OOS | fail-closed |
| Real employee ESS | blocked by synthetic gate |

---

## Cleanup + four reals untouched

- Synthetic leftovers: **0**
- Real ESS requests: **none**
- Snapshot equality for all four reals (before vs after canary)
- Reals after: Talal / Fouad / mohammad / Brian still `active` / `active` (see `verify/final-prod-state.txt`)

---

## Canary summary

**45 passed, 0 failed** — `canary/canary-run.log`, `canary/canary-evidence.json`, `canary/canary-rc.txt` = `0`

---

## Explicit non-goals (still closed)

- Do **not** onboard or classify the four real employees
- Do **not** enable real lifecycle actions
- Do **not** start Wave 6 or UI redesign
- Do **not** change pre-hiring / Wave D behavior
- Do **not** turn on `WATHEFNI_EMPLOYEE_APP` for real users yet

**Next authorized step for real-user rollout** requires a separate pack: lift ESS synthetic-only under explicit policy, classify/onboard reals, enable employee app with session_epoch ops runbook, and keep bank key rotation/DR documented.
