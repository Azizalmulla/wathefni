# Analytics Wave 1 — Attention Contract (staging)

**Stamp:** `20260803T155142Z`  
**Evidence:** `ops/evidence/analytics-wave1-20260803T155142Z/`  
**Qualify:** `ops/qualify-analytics-wave1-staging.sh`  
**Staging gate:** `STAGING_ANALYTICS_WAVE1_ATTENTION_GO`

## Verdicts

| Scope | Verdict |
|---|---|
| Staging Analytics Attention Contract | **GO** |
| Production synthetic qualification | **NO-GO** (staging-only wave by design) |
| Production controlled / real | **NO-GO** |

## What shipped (staging)

- Dashboard analytics passes full actor identity (`viewer_phone`, `viewer_user_id`, `actor_role`)
- Ranked `attention[]` with severity, reason EN/AR, subject, location/team, source module, deep link
- `as_of`, Kuwait MTD `window`, `definitions[]`, `freshness.stale_after_seconds`
- Partial-source disclosure when producing modules are disabled (counts masked for unavailable sources)
- Read-only drill-through into Attendance / Leave / Shifts / Employees (`?employee=` for people)
- EN/AR Analytics page parity; Assistant chip corrected away from “Headcount summary”
- Honest **Hours above schedule (non-payroll)** wording; vanity scheduled-shifts / best-attendance demoted/removed
- Authority flags: read-only, not money authority, Hiring Reports separate, Alerts & Delivery owns communication

## Explicit out of scope (held)

AI · decorative charts · custom BI · payroll cost analytics · Compliance metrics · mobile apps · frozen module contract changes · production deploy

## Proof

| Check | Result |
|---|---|
| Local `smoke-test-analytics-attention-wave1.py` | passed |
| Staging same smoke | passed |
| Live staging `workforce_analytics` contract | `analytics_attention_wave1`, `as_of` Kuwait, headlines without scheduled_shifts |
| UI dist Attention EN/AR copy | `UI_ATTENTION_COPY_OK` |
| Headcount leak absent | `UI_HEADCOUNT_GONE` |
| Responsive grid tokens | `UI_RESPONSIVE_GRID_OK` |
| Sibling freezes local | E360 57 · Onboarding 54 · Attendance 26 · Leave 35 · Shifts 96 — all 0 failed |
| Sibling freezes staging | E360/Onboarding/Attendance/Leave green; Shifts **96/0** after freeze canary sources present |
| Analytics-touched TS | clean (`ANALYTICS_TS_CLEAN`); pre-existing Payroll workspace TS errors not reopened |

## SHA

- `app.py` `99ee829cfb0c74b018dc47014d0f140d1151eb80f5e5b5411457dd235a44ea93`

## Next

Owner-approved production-synthetic canary wave only if staging soak is accepted. Do not treat this stamp as prod GO.
