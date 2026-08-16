# Employees 360 Wave 1 + 1B — Production deploy

**Stamp:** `20260801T193257Z`  
**Evidence:** `ops/evidence/employees360-wave1-1b-prod-deploy-20260801T193257Z/`  
**Remote:** `/opt/wathefni/production-evidence/employees360-wave1-1b/20260801T193257Z/`  
**Backup:** `/opt/wathefni/backups/production-pre-employees360-wave1-1b-20260801T193257Z/`  
**Host:** `root@76.13.63.68`

---

## Verdict

**PASS**

| Gate | Result |
|---|---|
| Pre-deploy: every production tenant with employee status capability has ≥1 eligible separate approver | PASS (WATHEFNI: Fouad + Aziz after grant) |
| Production **not** allowlisted for `self_approved_internal_canary` | PASS (`CANARY_OVERRIDES_ABSENT`; `canary_allowed=false`) |
| Direct status mutation restricted to approved internal non-production canaries | PASS (`403 canary_not_allowed` in production) |
| Orchestrator + dashboard deployed same window | PASS (orch ~19:35Z, dash ~19:38Z) |
| Health after deploy | PASS (`:8010/health=200`, dashboard shell/assets `200`) |
| Post-deploy behavioral proofs | **37/37 PASS** |
| Integrity diagnostics expanded + scan captured | PASS (`employee_messages`/`file_registry` included; 3 P0-DUP orphans retained) |
| Rollback verified | PASS (`ROLLBACK.sh` → pre SHA; `RESTORE_NEW.sh` → Wave1/1B SHAs; health 200) |
| Frozen pre-hiring + Wave D baseline unchanged | PASS |
| Null statuses cleaned / orphans deleted / DB UNIQUE / Wave 2 / redesign | **NOT DONE** (as required) |

---

## Production SHAs (final restored state)

| Artifact | SHA256 |
|---|---|
| `app.py` | `135e8d6edfe1055c2c797af1bbcd21fe6ee2275eb13fd335001f456ed64f1063` |
| `hire_operations.py` | `ae172589c7c1b90294356352761f09531cff8e21000e3bcfbe62747642945083` |
| `employee_status_approval.py` | `e52e2516e0a07da4c887ae4aa17a5a5e9a9220a5c87109e95f2eafcf59231dd3` |
| `module_catalog.py` | `d2d5b7f3096f405efb3997777647bb57982fb65b1746a8c508185f7ad59bfabd` |
| dashboard `api-y-bKkeVn.js` | `0a954afe851d31b37a50150bde2ea2278cfe625f3ba58a5dc3f8d8efa1b35774` |
| dashboard `PostHire-Cl9X9NtJ.js` | `b496060cb9e0cb77a2e9cf50303dfcc0be50d79838b876225368894f242b19f0` |

Pre-deploy `app.py` (rollback target): `27c7e2f0d8fe110b2683a0173b29122c5293411a64a71fcb865cdab8d079e790`

---

## Pre-deploy approval gate

Initial inventory found Fouad as sole `employees.status.approve` holder among manage-capable users → **no separate approver**.

Granted `employees.status.approve` to Aziz (`88b17ca9-aff4-4721-a553-c1b5514ef95f`) with `review_reference=employees360-wave1b-prod-deploy-separate-approver` (`before/approver-grant.json`).

Post-grant: Fouad + Aziz both approvers → `has_eligible_separate_approver=true`.

---

## Approval-policy proof (production)

Source: `verify/approval-policy-proof.json`

| Field | Value |
|---|---|
| environment | `production` |
| canary_allowed | `false` |
| self_approval_allowed | `false` |
| production_safe_required | `true` |
| eligible_approver_count (Fouad requesting) | `1` (Aziz) |
| no-eligible shape | `status_change_available=false`, `blocked_reason=no_eligible_approver` |

---

## Post-deploy proofs (synthetic only)

Source: `verify/prod_postdeploy_proofs.log` / `.json` — **37 passed, 0 failed**

Covered:
- Phone alias: local `50001122` ↔ `96550001122` resolve same employee; duplicate create blocked
- Recruiting hire source marker (`canonical_employee_phone`); import alias helper present
- Stale employee edit → conflict `409`
- In-scope manager mutation works; out-of-scope fail-closed `404`
- Orphan-document fail-closed marker present (`manager_scope_or_orphan`)
- Self-approve forbidden; cancel / reject (employee unchanged) / approve (applies `left`)
- Stale request `409`; replay same-hash idempotent; different-hash `409`
- Production canary direct status denied (`canary_not_allowed`)
- No eligible approver fail-closed clearly
- Known null statuses preserved (`WATHEFNI-96597727743`, `WATHEFNI-96550252254`)
- Synthetic orphan messages preserved (`WATHEFNI-P0-DUP-*` count = 3)

---

## Integrity scan

Source: `verify/integrity-scan.json`

- Expanded specs live (includes `employee_messages`, `file_registry`, onboarding/docs, etc.)
- `total_orphans=3` — all `employee_messages` for `WATHEFNI-P0-DUP-*` (retained; not deleted)
- All other scanned tables: `0` orphans

---

## Freeze baseline (unchanged)

From live process env (`after/freeze-flags.txt`):

```
WATHEFNI_ENV=production
WATHEFNI_INBOUND_EMAIL=on
WATHEFNI_MAILBOX_SYNC=off
WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI
WATHEFNI_INTAKE_RETENTION_EXECUTE=off
WATHEFNI_CANONICAL_LIFECYCLE=true
WATHEFNI_ASSESSMENT_AUTHORING=false
```

Canary env override: absent (`after/canary-env.txt`).

---

## Screenshots

| File | What |
|---|---|
| `screenshots/01-dashboard-shell.png` | Live `https://api.wathefni.ai/dashboard/` shell |
| `screenshots/02-proof-summary.png` | Deploy proof summary |
| `screenshots/03-approval-policy.png` | Production approval-policy proof JSON |

Dashboard Wave 1B markers in deployed assets (`after/dashboard-posthire-markers.txt`): `Choose approver`, `Status change requested`, `Waiting for approval`, `designated_approver`.

---

## Rollback verification

Executed on production:

1. `ROLLBACK.sh` → `app.py` restored to pre SHA `27c7e2f0…`; `employee_status_approval.py` absent; alias/canary helpers gone; health returned `200`
2. `RESTORE_NEW.sh` → Wave 1/1B SHAs restored; `canary_allowed_WATHEFNI=False`; eligible approver count `1`; health `200`

Artifacts: `rollback/rollback.log`, `rollback/restore.log`, `rollback/*-sha256`, `rollback/*-behavior.txt`

---

## Explicit non-actions

- Did **not** clean the two null employee statuses
- Did **not** delete synthetic orphan messages
- Did **not** add database uniqueness constraints
- Did **not** start Wave 2
- Did **not** redesign Employees 360
- Did **not** allowlist production for `self_approved_internal_canary`
