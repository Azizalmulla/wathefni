# Leave Wave 2C — Production synthetic policy & balance canary

**Stamp:** `20260802T161747Z`  
**Evidence:** `ops/evidence/leave-wave2c-prod-canary-20260802T161747Z/`  
**Remote:** `/opt/wathefni/production-evidence/leave-wave2c-prod-canary/20260802T161747Z/`  
**Company:** WATHEFNI only · synthetic markers `LVW2C` / `LVW2C-SYNTH|` / phone prefix `965526`  
**Pack:** `kw_private_sector_v2` **@ 2.1.0**

---

## Separate verdicts

| Concern | Verdict |
|---|---|
| **Synthetic production policy/balance authority** | **GO** — canary **63/63** (v3 + post-redeploy); pack live; reservations/reconcile proved; `enforced=false` |
| **Controlled real HR leave decisions** | **NO-GO** — Wave 1B `SYNTHETIC_ONLY=on` retained; real leave decisions not expanded |
| **Real balance enforcement** | **NO-GO** — `enforced=false`, `legal_reviewed=false`; Islamic holiday year remains `pending_review` (fail-closed for enforced) |
| **Payroll monetary calculations** | **NO-GO / none** — unpaid/sick pay fractions are classification inputs only; no money mutation |

---

## Production SHAs and flags (final)

| File | SHA256 |
|---|---|
| `app.py` | `27136bf5d7b453fa925990c2011d6b0b5a871f0c6b272cca8ac28c4e00f574aa` |
| `leave_policy_wave2.py` | `c57cb93c83400f100a5b468fb3eac5f1e14ba1323d8400513a7b77de0bbe9049` |
| `leave_authority_wave1.py` | `ad906eec780669b41b9ce26f75c91b3ba0e94e70ba91282b3eae1b46fba90aa2` |
| `employee_lifecycle_wave3c.py` | `f2dfbabb717dc8a4d912619663681973b1346f2224e69b45a5fe26c912161099` |

| Flag | Value |
|---|---|
| `WATHEFNI_LEAVE_POLICY_WAVE2` | **on** |
| `WATHEFNI_LEAVE_BALANCES` | **on** (observe-only) |
| `WATHEFNI_LEAVE_AUTHORITY` | **on** |
| `WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_ONLY` | **on** |
| `WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_KEY_MARKERS` | `LVW1B,LVW1B-SYNTH|,LVW2C,LVW2C-SYNTH|` |
| `WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES` | `965525,965526` |
| `WATHEFNI_ATTENDANCE_CAPTURE_INGEST` | **off** |
| `WATHEFNI_ONBOARDING_SEED` | **off** |
| Accrual timer `wathefni-leave-accrual.timer` | **enabled / active** (unchanged) |

Drop-ins:
- `zzzz-leave-authority-wave1b-synthetic.conf` (updated markers)
- `zzzzz-leave-policy-wave2c.conf` (`LEAVE_POLICY_WAVE2=on`)

---

## Policy pack / version evidence

- Pack binding: `kw_private_sector_v2` / **2.1.0**
- Annual: **30** days, **eligibility_months=6**, weekend fri/sat, holidays excluded
- Sick: Art.69 tiers present; `payroll_owned` banding
- Unpaid: reservation **skipped** (`unpaid_payroll_boundary`)
- Carryover writers **disabled**
- `enforced=false`, `legal_reviewed=false`
- Evidence: `remote/policy/pack-live.txt`, migrate `MIGRATE_OK leave_policy_wave2c_prod 2.1.0`

---

## Holiday-version evidence

- Fixed Gregorian seeded (`seeded_fixed`) for current year
- Year version status: **`pending_review`** (Islamic/decree load not invented)
- Enforced path **fail-closed** while pending (`holiday_year_not_approved`)
- Observe path excludes National/Liberation correctly (Feb week → 3 chargeable days)

---

## Reservation & ledger reconciliation (synthetic)

Proved in canary **63/63** (tag `22ada742` / post-redeploy `80753b2d`):

| Scenario | Result |
|---|---|
| 6-month eligibility `can_take_from` boundary | PASS |
| Weekend + approved/seeded holiday exclusion | PASS |
| Unreviewed year fail-closed for enforced | PASS |
| Concurrent requests cannot double-reserve | PASS |
| Approve converts reservation → consume once | PASS |
| Reject / cancel pending / expire / lifecycle decline release | PASS |
| Reversal restores balance; attendance reverse list-safe | PASS |
| Sick tiers + unpaid payroll boundary | PASS |
| Carryover writers disabled | PASS |
| Ledger ↔ rollup reconcile exact | PASS |
| No payroll money mutation | PASS |
| Synthetic residual 0 after cleanup | PASS |

---

## Real leave / ledger / balance fingerprints (unchanged)

| leave_id | status | type | fp |
|---|---|---|---|
| `e3217e0e-…` | approved | sick | `abf4cba7cb8702b2d7c067db795d0701` |
| `51cd940f-…` | rejected | sick | `8f6d67e3cc4fbf5ee321af235ecbb20d` |
| `dbf82ecf-…` | requested | annual | `34c7cf18a4d758698bbf7cac6da70d1f` |

Company totals preserved around canary windows: **3** real requests · **10** events · **28** ledger · **4** balances (preflight / post-cleanup real fps identical).

---

## Backup, rollback, redeploy

| Item | Evidence |
|---|---|
| Backup | `/opt/wathefni/backups/production-pre-leave-wave2c-20260802T161747Z/` |
| Fingerprints | `leave-requests/balances/ledger-fingerprint.csv` + `SHA256SUMS` |
| Rollback | `ROLLBACK_OK` — removed `leave_policy_wave2.py` + wave2c drop-in; Wave 1B authority restored |
| Redeploy + canary | `ROLLBACK_REDEPLOY_OK` · post-redeploy **63/63** |
| Accrual timer | enabled/active before and after |

---

## Freeze regressions

| Suite | Result |
|---|---|
| Employees 360 | **57/57** |
| Onboarding | **54/54** |
| Attendance | **26/26** |

---

## Remaining blockers (before real enforcement)

1. Islamic / decree holiday yearly load + `approved` year versions  
2. Counsel `legal_reviewed=true` for enforcement flip  
3. Carryover writers still intentionally off (Art.72 boundary recorded only)  
4. Controlled real HR leave decisions still behind Wave 1B synthetic-only gates  
5. Explicit enforcement flip plan (not this wave)

---

## What was not done

No `enforced=true` · no real balance mutation · no partial-day/attachments · no UI redesign · no frozen-module changes · no Payroll money engine.
