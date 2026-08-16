# Leave Wave 2 — Policy & Balance Correctness (local/staging)

**Stamp:** `20260802T160222Z`  
**Scope:** local + staging only (`wathefni_staging`). No production deploy.  
**Module:** `leave_policy_wave2.py` v2.0.0 · pack `kw_private_sector_v2`  
**Flags:** `WATHEFNI_LEAVE_POLICY_WAVE2=on` (staging), `WATHEFNI_LEAVE_BALANCES=on` observe-only  
**Hard rules held:** `enforced=false`, `legal_reviewed=false`, no payroll money, no UI redesign, frozen modules untouched.

---

## Verdict

| Gate | Result |
|------|--------|
| Staging migrate + smoke (35/35) | **GO** |
| Employees 360 / Onboarding / Attendance freezes | **GO** (57 / 54 / 26) |
| Production synthetic canary (Wave 2) | **NO-GO** (not in scope; Wave 1B authority canary remains the prod leave gate) |
| Controlled real balance enforcement | **NO-GO** |

---

## Policy-pack model

Versioned pack keyed by `(pack_code, version)` + company binding:

| Concept | Implementation |
|---------|----------------|
| Jurisdiction / worker category | `KW` / `private_sector` on `leave_policy_packs` + `leave_company_policy_bindings` |
| Weekend / holidays / TZ | Pack defaults Fri+Sat, `exclude_public_holidays=true`, `Asia/Kuwait` |
| Annual | 30 days/year, monthly accrual, eligibility default **6 months** (conflict noted) |
| Sick | Art.69-style bands; pay fractions stored but **Payroll-owned** (not applied) |
| Unpaid | Catalogue / payroll boundary only — no wage calc |
| Carryover | Rules present (`max_years=2`, consent) but **writers hard-disabled** until `carryover_enabled && legal_reviewed` |
| Honesty | Pack and company policies remain `enforced=false`, `legal_reviewed=false` |

Seed path: `ensure_leave_policy_wave2_schema` → `seed_kuwait_private_policy_pack` → `bind_company_policy_pack` → `seed_fixed_kuwait_holidays`.

---

## Official-source verification matrix

Classifications: **statutory** | **configurable_company_policy** | **payroll_owned** | **manual** | **unresolved**

| Field | Pack value | Classification | Confidence | Notes |
|-------|------------|----------------|------------|-------|
| `annual_days_per_year` | 30 | statutory | high | Law 6/2010 Art.70; Law 85/2017 commentary; PAM summary |
| `annual_eligibility_months` | 6 (pack default) | **unresolved** | medium | PAM/Ogletree cite 6; HLB EN cites 9 — Arabic Art.70 must confirm before `legal_reviewed=true` |
| `annual_excludes_weekends_holidays_sick` | true | statutory | high | Law 85/2017 commentary — chargeable-day calc excludes weekends + public holidays |
| `weekend_days_default` | fri,sat | configurable_company_policy | medium | Weekly rest is statutory; pair is employer calendar |
| `sick_tiers_art69` | 15/10/10/10/30 @ 1/0.75/0.5/0.25/0 | statutory (structure) | medium | EN/HLB Art.69; pay fractions **payroll_owned** — Leave never computes money |
| Fixed Gregorian holidays | 1 Jan, 25 Feb, 26 Feb | statutory | high | Seeded with provenance |
| Islamic movable holidays | *not invented* | manual | high | Yearly decree required; calendar `yearly_review_status=pending_yearly_review` |
| Carryover | architecture only, disabled | unresolved | low | Secondary guides only |
| Unpaid leave | catalogue boundary | payroll_owned | high | No Leave wage deduction |
| Timezone | Asia/Kuwait | configurable_company_policy | high | All Wave 2 as-of / midnight boundaries |

Full machine-readable matrix: `OFFICIAL_SOURCE_MATRIX` in `leave_policy_wave2.py` (also stored on pack row as `source_matrix` jsonb).

---

## Holiday-calendar model

| Piece | Detail |
|-------|--------|
| Calendar | `leave_holiday_calendars.calendar_code = kw_public_v2` |
| Provenance cols on `public_holidays` | `source_provenance`, `effective_from`, `effective_to`, `review_status`, `calendar_code` |
| Fixed seeds | New Year, National Day, Liberation Day per company/year |
| Islamic / movable | **Not dated** in Wave 2 — review status stays `pending_yearly_review` |
| Chargeable days | Inclusive range; exclude configured weekend names + holiday dates with `review_status <> 'invalid'` |

---

## Ledger / reservation architecture

```
request  → reservation (idempotent per leave_id)
approve  → reservation_release + consume (each idempotent once)
reject / cancel(pending) / stale expire / lifecycle decline → reservation_release
cancel(approved) → reversal (idempotent)
rollup   → leave_balances.{accrued,consumed,reserved,current_balance}
available = current_balance - reserved
```

| Property | Behavior |
|----------|----------|
| Observe-only | `observe_only=true`; never sets `enforced` |
| Concurrent overspend | Advisory xact lock + available check; insufficient → `insufficient_balance_observe` **without** posting reservation |
| Sick / non-accruing | Tier banding posted without accrued-pool gate (structure only) |
| Unpaid | Skipped — payroll boundary |
| Accrual | Existing monthly idempotent unique index retained |
| Reconcile | `reconcile_ledger_to_balances` → `leave_balance_reconcile_runs` |

Indexes: accrual (existing), consume/reversal (existing), reservation/reservation_release (`idx_leave_ledger_reservation_idem`).

---

## Staging proof (required scenarios)

Evidence: `ops/evidence/leave-wave2-policy-20260802T160222Z/`  
Smoke: `tests/leave-w2-smoke.out` — **35 passed, 0 failed**

| Scenario | Result |
|----------|--------|
| Weekends + holidays excluded (Feb 2026 National/Liberation week → 3 chargeable) | PASS |
| Span months/years (+ New Year holiday) | PASS (unit) |
| Concurrent requests cannot double-reserve | PASS (`insufficient_balance_observe`) |
| Approve converts reservation → consume exactly once | PASS |
| Reject / cancel pending / expire release reservation | PASS |
| Reversal restores balance | PASS |
| Insufficient balance observe-only (request still created) | PASS |
| Sick-tier banding (payroll_owned flags) | PASS |
| Asia/Kuwait midnight boundary | PASS |
| Ledger ↔ rollup reconcile exact | PASS |
| Attendance reverse path remains list-safe | PASS |
| Freezes E360 / Onboarding / Attendance | PASS |

---

## Remaining blockers

1. **Eligibility months 6 vs 9** — unresolved; counsel must confirm Arabic Art.70 before `legal_reviewed=true`.
2. **Islamic holiday dates** — require yearly PAM/government decree; not inventable.
3. **Carryover** — architecture only; disabled until verified statute + counsel.
4. **Sick pay fractions** — structure only; Payroll must own money application.
5. **`enforced=false` / `legal_reviewed=false`** — intentional until public-source pack is counsel-complete.
6. **Production Wave 2 canary** — not run; Wave 2 is staging-only by design.
7. Partial-day leave / attachments / UI — explicitly out of scope.

---

## GO / NO-GO

| Decision | Call |
|----------|------|
| Staging Wave 2 policy/balance correctness | **GO** |
| Production synthetic canary for Wave 2 balances | **NO-GO** (do not deploy Wave 2 to prod yet; Wave 1B authority synthetic canary remains separate) |
| Eventual controlled real balance enforcement | **NO-GO** until: legal_reviewed pack, Islamic calendar yearly review, eligibility conflict closed, prod synthetic balance canary green, explicit enforcement flip plan |

---

## Artifacts

| Path | Role |
|------|------|
| `wathefni-orchestrator/leave_policy_wave2.py` | Authority module |
| `ops/sql/leave_policy_wave2_v2.sql` | Schema pack |
| `ops/migrate-leave-policy-wave2.sh` | Staging migrate (refuses prod DB) |
| `ops/qualify-leave-policy-wave2-staging.sh` | Qualify runner |
| `smoke-test-leave-policy-wave2.py` | Smoke |
| `ops/evidence/leave-wave2-policy-20260802T160222Z/` | This stamp |

**Local SHAs (20260802T160222Z):**

```
fa78619f…  leave_policy_wave2.py
1a76a187…  app.py
f2dfbabb…  employee_lifecycle_wave3c.py
ad906eec…  leave_authority_wave1.py
```
