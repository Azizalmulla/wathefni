# Employees 360 Wave 1C — Production hygiene apply

**Stamp:** `20260801T200138Z`  
**Evidence:** `ops/evidence/employees360-wave1c-hygiene-prod-apply-20260801T200138Z/`  
**Remote:** `/opt/wathefni/production-evidence/employees360-wave1c-hygiene/20260801T200138Z/`  
**Qualified from:** `ops/evidence/employees360-wave1c-hygiene-local-20260801T195138Z/`

---

## Verdict

**PASS**

| Gate | Result |
|---|---|
| Both targets `null → active` | PASS |
| Other employment statuses unchanged | PASS |
| 3 orphan messages archived in quarantine (not deleted) | PASS |
| Integrity scan `total_orphans=0` | PASS |
| Journal has reversible before/after | PASS |
| Rollback drill → NULL + live orphans restored | PASS |
| Restore-new re-apply succeeds | PASS |
| Health 200 | PASS (`before` + `after`) |
| Wave 2 / uniqueness / other rows / freeze baselines | Untouched |

---

## Journal IDs (final applied state)

| remediation_id | action | target | idempotency_key |
|---|---|---|---|
| `4e3c08f1-75fc-47be-8e0f-e00fd022101e` | `set_employment_status` | `WATHEFNI-96597727743` | `wave1c-null-status:WATHEFNI-96597727743:active` |
| `5228deb9-25ae-4ac0-821f-5d21f56caee2` | `set_employment_status` | `WATHEFNI-96550252254` | `wave1c-null-status:WATHEFNI-96550252254:active` |
| `84c5c7cc-ac1f-44dc-a51d-d08002fe01b8` | `quarantine_employee_messages` | `WATHEFNI-P0-DUP-1` | `wave1c-quarantine:WATHEFNI-P0-DUP-1` |

Full before/after JSON + evidence reasons are in `employee_hygiene_remediation_journal` (captured in `prove-after-restore.json`).

---

## Before / after counts

| Metric | Before | After (final) |
|---|---|---|
| `WATHEFNI-96597727743` status | `null` | `active` |
| `WATHEFNI-96550252254` status | `null` | `active` |
| `WATHEFNI-96566363363` status | `active` | `active` (unchanged) |
| `WATHEFNI-96599411617` status | `active` | `active` (unchanged) |
| Live orphan messages (`P0-DUP-1`) | **3** | **0** |
| Quarantine active (`restored_at IS NULL`) | 0 | **3** |
| Integrity `total_orphans` | **3** | **0** |

Archived message IDs (unchanged from qualification):
- `9131f0be-0330-4527-856d-6d254e494faa`
- `593f8836-3a12-43d4-aec2-17c79b9416b6`
- `35be03eb-bae6-4cc5-9153-e9e4291f064e`

---

## Rollback proof

1. **Rollback drill:** both targets restored to `NULL`; 3 messages restored to live `employee_messages` (`after-rollback.json`, `rollback-summary.json`).
2. **Restore-new:** re-applied same idempotency keys → both `active`, 3 quarantined, integrity `0` orphans (`prove-after-restore.json`).
3. Journal rows revived via upsert (same remediation IDs retained; status `applied`).

---

## Freeze baseline (unchanged)

```
WATHEFNI_ENV=production
WATHEFNI_INBOUND_EMAIL=on
WATHEFNI_MAILBOX_SYNC=off
WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI
WATHEFNI_INTAKE_RETENTION_EXECUTE=off
```

Health: `health_before=200`, `health_after=200`

---

## Explicit non-actions

- No `person_id` / `employment_id` / `assignment_id` minting persisted
- No uniqueness constraints
- No other employee or message rows touched
- Wave 2 **not started**
- Pre-hiring + Wave D frozen

---

## Artifacts

- `final.json` — verdict + journal IDs + counts
- `before.json` / `prove-after-apply.json` / `prove-after-restore.json`
- `rollback-summary.json` / `after-rollback.json`
- `evidence-WATHEFNI-*.json` — live evidence gates used at apply
- `apply-all.log`
- Module on prod: `/opt/wathefni/orchestrator/employee_hygiene_wave1c.py`
