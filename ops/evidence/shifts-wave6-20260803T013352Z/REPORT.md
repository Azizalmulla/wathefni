# Shifts Wave 6A — rotations, remote roster metadata, compliance, PAM export (local/staging)

**Stamp:** `20260803T013352Z`  
**Evidence:** `ops/evidence/shifts-wave6-20260803T013352Z/`  
**Module:** `shifts_enterprise_wave6.py` **v6.0.0** · cleanup contract **1.3.0**  
**Prior attempt:** `ops/evidence/shifts-wave6-20260803T012814Z` (**NO-GO** — missing `idempotency_key` on rotation classify; bash `|` in unquoted marker exports)  
**Scope:** local + staging only. **No production deploy. No real employees. No PAM submission. No Payroll money.**  
**Markers:** **SHW6** / **965536***

## Gate result
`PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO`

## GO/NO-GO

| Gate | Result |
|---|---|
| Staging Wave 6A (rotations, remote, compliance, PAM export, publish/cycle-edit/cancelled-held) | **GO** |
| Production synthetic Wave 6 canary readiness | **GO** (canary itself not run — Wave 6B) |
| Controlled real rotation / draft / publishing | **NO-GO** |
| PAM submission (government API) | **NO-GO** |
| Payroll money calculation | **NO-GO** |
| Real HR/manager allowlists / reminders / timers | **NO-GO** (prepared, empty/off) |
| Broad employee-app access | **NO-GO** |

---

## Rotation and hitch model
- Table `shift_rotation_patterns` with kinds: `n_on_m_off`, `alternating_day_night`, `panama_223`, `four_on_four_off`, `six_on_one_off`, `hitch_n_n`, `custom_sequence`
- Canonical `cycle_sequence` of `{kind: work|rest|travel|standby, template_slot}`
- `shift_rotation_assignments`: target employee/crew/team/site/role, `cycle_offset`, `cycle_anchor_date`, effective start/end
- Planning only → Wave 5 draft rows (`source_kind=rotation`); publish remains Wave 5 gate; L0 is sole authority
- Hitch 14/14 with travel edges proven (28-day cycle: 2 travel + 13 work + 13 rest)

## Remote-site model
Assignment fields (never monetary): `remote_site_key`, `camp_key`, `transport_required`, `transport_group`, `pickup_location`, `accommodation_required`, `mobilization_date`, `demobilization_date`, `access_warnings`, `certification_warnings`, `remote_meta`  
Money keys stripped on write.

## Policy / compliance model
`shift_compliance_profiles` with company/sector profiles; default **warn**; **block** only when rule/profile says so.  
Rule types: Ramadan hours, midday outdoor windows, daily/weekly hours, break/consecutive-hours metadata, weekly rest weekdays, public-holiday warnings.  
Publish API evaluates Wave 6 compliance when enabled and blocks on `blocks_publish`.

## PAM export schema and samples
- Contract `pam-export@1.0.0` — see `docs/PAM_EXPORT_SCHEMA.md`
- Deterministic EN/AR CSV + printable reports; fingerprint over payload
- Status always `manual_submission_required`; `submission: false`
- Staging smoke: pam export ok · csv_en/ar · report_en/ar · fingerprint present

## UX architecture
- Progressive tabs: board (always) → templates (W4) → Publish & coverage (W5, full browser actions) → Rotations & compliance (W6)
- Simple companies keep direct scheduling board without enterprise chrome
- Details: `ui/UX_ARCHITECTURE.md`
- Screenshots: not captured in this run; build + API/smoke prove the same actions (`data-testid=shifts-enterprise-panel`)

## Permission and rollout matrix
See `docs/PERMISSION_ROLLOUT_MATRIX.md`. Real mutation still requires permission/scope, allowlist, audit reason, concurrency token, policy eval, kill-switch — allowlists remain empty.

## Tests and evidence
| Suite | Result |
|---|---|
| Wave 6A staging smoke | **96 passed, 0 failed** |
| Wave 5 | 62/0 |
| Wave 4 | 54/0 |
| Wave 3 UX | 43/0 |
| Wave 1 | 90/0 |
| Wave 2 | 82/0 |
| Freezes E360/ONB/ATT/LEAVE | green |

Proven: 4-on/4-off · alternating day/night overnight · 14/14 hitch preview · offsets · travel/rest/work · draft→review→approve→publish · non-work skipped · L0 fingerprint stable on regen · cancelled_held · PAM export · residual 0 · Waves 1–5 green.

Artifacts: `tests/staging-regressions.out`, `tests/staging-deploy.out`, sources under `sources/`.

## Unresolved items (Kuwait customer / legal)
1. Confirm Ramadan daily max hours and midday outdoor window per sector (construction vs office vs oil/gas) before any **block** profiles go live.
2. Confirm weekly rest weekday conventions (Fri/Sat vs Fri-only) per company policy.
3. Confirm PAM declaration field set vs current Ministry/PAM forms; export is foundation only — **no submission path**.
4. Hitch travel-day counting vs payroll travel allowance ownership (Payroll must own money; Shifts keeps metadata only).
5. Named HR/manager allowlists and Talal read-only scope for Wave 6C controlled rollout.
6. Whether public-holiday calendars are company-supplied vs nationally published feeds.

## Remaining intentional blockers
- No production deploy / Wave 6B canary not run in this wave  
- No real allowlists, reminders, timers, employee claim broadening  
- No PAM submission, no Payroll money

## Next
- **Wave 6B:** production synthetic final canary  
- **Wave 6C:** controlled HR/manager rollout, final qualification, formal Shifts freeze
