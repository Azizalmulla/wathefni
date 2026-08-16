# Employees 360 Wave 1C — Production data hygiene + Wave 2 migration readiness

**Stamp:** `20260801T195138Z`  
**Evidence:** `ops/evidence/employees360-wave1c-hygiene-local-20260801T195138Z/`  
**Mode:** Audit (production read-only) + local implementation + staging synthetic proof  
**Production data mutated:** **No**  
**Production deploy:** **NOT DONE — awaiting owner approval**

---

## Verdict

**PASS** (local/staging qualification). Production remediation is prepared but **not applied**.

| Gate | Result |
|---|---|
| Audit known null statuses with hiring/onboarding/activity evidence | PASS |
| Classify 3 `WATHEFNI-P0-DUP-1` orphan messages as synthetic | PASS |
| Confirm no additional employee-linked orphans after Wave 1 | PASS (only the known 3) |
| Refuse to guess missing statuses | PASS (classifier + smoke) |
| Quarantine/archive path (not silent delete) | PASS |
| Idempotent + reversible remediations | PASS (staging smoke) |
| Migration-readiness map for all employee_keys | PASS (4 employees) |
| Uniqueness constraints / Wave 2 schema / frozen baselines | **Not touched** |
| Production apply | **Blocked pending approval** |

---

## Classification of every affected row

### Null `employment_status` (2)

| employee_key | Name | Classification | Proposed | Confidence |
|---|---|---|---|---|
| `WATHEFNI-96597727743` | mohammad alqattan | `null_should_be_active` | **active** | high |
| `WATHEFNI-96550252254` | Talal Fadhli | `null_should_be_active` | **active** | high |

**Evidence (both):**
- Application `status=hired` via hire-linked `app_key`
- `onboarding_status=in_progress` with onboarding + compliance rows
- Live activity (attendance / shifts; leave for 7743)
- Zero `employee_status_changes` / left markers
- Runtime already coerces null→active — remediation makes stored truth match behavior

**Additional null statuses beyond the known two:** none.

### Orphan `employee_messages` (3)

| message_id | flow / template | status | Classification |
|---|---|---|---|
| `9131f0be-0330-4527-856d-6d254e494faa` | shift / shift_assigned | failed | synthetic orphan |
| `593f8836-3a12-43d4-aec2-17c79b9416b6` | shift / shift_assigned | delivered_whatsapp | synthetic orphan |
| `35be03eb-bae6-4cc5-9153-e9e4291f064e` | leave_decision / leave_request_approved | delivered_whatsapp | synthetic orphan |

**Employee key:** `WATHEFNI-P0-DUP-1`  
**Classification:** `synthetic_orphan_quarantine` (high confidence)

**Evidence:**
- Synthetic naming (`P0-DUP`)
- No `employees` row
- Zero refs in applications / attendance / onboarding / compliance / docs / sessions / invites
- Created 2026-07-20 as harness residue

### Integrity after Wave 1

`total_orphans=3` — **only** `employee_messages` → `WATHEFNI-P0-DUP-1`. No new orphan classes.

---

## Proposed remediation (production — not applied)

Source: `verify/proposed-remediation-plan.json`

1. **Set employment_status NULL → `active`** for both employees above  
   - Idempotency keys: `wave1c-null-status:<employee_key>:active`  
   - Journaled in `employee_hygiene_remediation_journal` with full before/after + evidence reasons  
   - Only when classifier returns `null_should_be_active` + confidence `high`

2. **Quarantine/archive** the 3 orphan messages  
   - Copy full rows into `employee_messages_quarantine`  
   - Remove from live `employee_messages` (archive move, not silent delete)  
   - Idempotency key: `wave1c-quarantine:WATHEFNI-P0-DUP-1`

3. **Do not** mint `person_id` for `WATHEFNI-P0-DUP-1`

---

## Rollback plan

| Action | Reverse |
|---|---|
| Null→active | `rollback_null_employment_status(idempotency_key)` restores prior `employment_status` (NULL) from journal |
| Quarantine messages | `restore_quarantined_employee_messages(idempotency_key)` re-inserts archived rows to live table |
| Journal | `employee_hygiene_remediation_journal` retains applied/rolled_back history (audit preserved) |
| Schema | Additive only (`IF NOT EXISTS`); no DROP of business data |

All remediations are idempotent on replay of the same idempotency key.

---

## Migration-readiness map

Source: `verify/migration-readiness-map.json`

Deterministic UUIDv5 (namespace `6b1c0f3a-9d2e-4a7b-8c5d-1e2f3a4b5c6d`):

| employee_key | person seed | Notes |
|---|---|---|
| `WATHEFNI-96550252254` | `person:WATHEFNI:phone:96550252254` | → person_id + employment_id + primary assignment_id |
| `WATHEFNI-96566363363` | phone-canonical | active today |
| `WATHEFNI-96597727743` | `person:WATHEFNI:phone:96597727743` | → person_id + employment_id + primary assignment_id |
| `WATHEFNI-96599411617` | phone-canonical | active today |
| `WATHEFNI-P0-DUP-1` | **excluded** | quarantine only; no person/employment mint |

**Wave 2 schema migration is not started.** Map is recomputable and non-authoritative until Wave 2.

---

## Implementation (local)

| Artifact | Path |
|---|---|
| Hygiene module | `wathefni-orchestrator/employee_hygiene_wave1c.py` |
| Unit smoke | `wathefni-orchestrator/smoke-test-employee-wave1c-hygiene-unit.py` |
| Staging DB smoke | `wathefni-orchestrator/smoke-test-employee-wave1c-hygiene.py` |
| Prod read-only audit | `verify/wave1c_readonly_audit.py` |
| Prod audit JSON | `raw/prod-audit/` |

---

## Tests

| Suite | Result |
|---|---|
| Unit (classifier + map) | **13/13 PASS** — `tests/wave1c-unit.txt` |
| Staging synthetic smoke (dry-run → apply → rollback) | **18/18 PASS** — `tests/wave1c-staging-smoke.txt` |

Staging proof covered: refuse-guess, status dry-run/apply/idempotent/rollback, orphan quarantine/archive/restore, integrity no longer lists smoke orphan key, migration map mint/exclude.

---

## Explicit non-actions

- Production remediation **not applied** (nulls still NULL; 3 orphans still live)
- Hygiene tables **not created on production**
- No uniqueness constraints
- No Wave 2 schema migration
- Frozen pre-hiring + Wave D unchanged
- Audit history preserved by design (journal + quarantine archive)

---

## Approval ask

Owner approval required to apply the two null→active remediations and quarantine the three synthetic orphan messages on production using the journaled, reversible Wave 1C module.
