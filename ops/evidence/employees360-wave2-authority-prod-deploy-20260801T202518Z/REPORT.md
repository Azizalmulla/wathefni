# Employees 360 Wave 2 — Production deploy (WATHEFNI only)

**Stamp:** `20260801T202518Z`  
**Evidence:** `ops/evidence/employees360-wave2-authority-prod-deploy-20260801T202518Z/`  
**Remote:** `/opt/wathefni/production-evidence/employees360-wave2-authority/20260801T202518Z/`  
**Backup:** `/opt/wathefni/backups/production-pre-employees360-wave2-20260801T202518Z/`  
**Qualified from:** `ops/evidence/employees360-wave2-authority-local-20260801T201120Z/`

---

## Verdict

**PASS**

| Gate | Result |
|---|---|
| Health 200 | PASS |
| Schema + tenant-safe constraints | PASS (`employees360-wave2-authority-v1`) |
| Deterministic backfill 4/4 | PASS |
| Idempotent rerun | PASS |
| No duplicate person/employment/assignment | PASS (4/4/4) |
| Compatibility map complete | PASS |
| Hub API cards unchanged | PASS |
| Manual create/edit/hire shadow-sync | PASS |
| Local ↔ 965 phone aliases → same person | PASS |
| Cross-tenant fail-closed | PASS |
| Scoped rollback (hub business unchanged) | PASS |
| Restore-new | PASS |
| V2 allowlisted to WATHEFNI only | PASS |
| Wave 3 / redesign / child-table cutover | **Not started** |

---

## Production SHAs

| Artifact | SHA256 |
|---|---|
| `app.py` | `92addc3b7d132ee1d9f6900d6fe6d9625303c57e04589545be9da616c467b58b` |
| `hire_operations.py` | `6c00e31b3ea58fb5c8aea964677be515d5787d2c25cf6b7af22c3aefb4a7e587` |
| `employee_authority_wave2.py` | `d5e16ff81f933dcb8c51f7d17b43c38179b7442b26145a805d4781c89f8bd326` |
| `employee_hygiene_wave1c.py` | `e0a7d213a85430c40d143c2d54c5db42b20a149f86c51550325c5967bcd9befc` |

Pre-deploy `app.py`: `135e8d6edfe1055c2c797af1bbcd21fe6ee2275eb13fd335001f456ed64f1063`

---

## Schema version

`employees360-wave2-authority-v1`  
(recorded in `employee_authority_schema_meta`)

Runtime:
```
WATHEFNI_EMPLOYEE_AUTHORITY_V2=on
WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES=WATHEFNI
```

---

## Backfill IDs (approved Wave 1C map)

Journal ID: `54c41793-e6c0-4125-ac0e-52057716b07b`  
Idempotency: `wave2-backfill:WATHEFNI:approved-map-v1`

| employee_key | person_id | employment_id | assignment_id | employee_number |
|---|---|---|---|---|
| `WATHEFNI-96550252254` | `a0b0d348-addd-5da3-87d7-e0f94a5a466c` | `e25da3b1-13a3-558d-a147-42dd8445edf7` | `112ac62d-bfe5-5f5e-bb33-2f36fb32e2f3` | EMP-0003 |
| `WATHEFNI-96566363363` | `c24a9068-62a7-5a8e-9b60-d1004dd3c265` | `fe3359c9-2b14-53a6-88ac-4662e6c04902` | `e46040d8-c069-5b9d-aef8-bf507acc73cd` | EMP-0001 |
| `WATHEFNI-96597727743` | `9bf69b24-2ee3-5d36-9c4a-ed5756afbc50` | `8fe3358b-18c5-581c-84ea-94f120fd597f` | `def8f1c7-9c2a-55ee-a5c9-7a7b92b30d7f` | EMP-0002 |
| `WATHEFNI-96599411617` | `12966424-7e65-556a-9678-cc3f264836d0` | `7e51c028-f1db-5b3b-942a-da0f005ac2f1` | `fdf5845d-3e96-5f34-b78b-0194f61f438d` | EMP-0004 |

Counts after restore-new: **persons=4, employments=4, assignments=4**

---

## Compatibility matrix

Source: `compatibility-matrix.json` — each approved `employee_key` maps 1:1 to person/employment/assignment while remaining the live hub alias for Onboarding, Compliance, Shifts, Attendance, Leave, Payroll, and Employees APIs.

---

## Rollback proof

1. Scoped rollback removed authority maps for the 4 keys; hub `person_id/employment_id/assignment_id` nulled  
2. Hub business columns (phone, email, name, employment_status, onboarding, title, app_key) **unchanged**  
3. Restore-new re-backfill restored approved IDs 4/4  

Code rollback scripts: `$BACKUP/ROLLBACK.sh` / `RESTORE_NEW.sh`

---

## Freeze baseline (unchanged)

```
WATHEFNI_ENV=production
WATHEFNI_INBOUND_EMAIL=on
WATHEFNI_MAILBOX_SYNC=off
WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI
WATHEFNI_INTAKE_RETENTION_EXECUTE=off
```

---

## Explicit non-actions

- No external tenant enablement  
- No child-table migration / hard cutover  
- No phone merge policy / Wave 3 lifecycle  
- No Employees 360 redesign  
- No Wave 3 started  
