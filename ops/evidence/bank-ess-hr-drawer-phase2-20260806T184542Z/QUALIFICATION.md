# Bank ESS HR onboarding drawer — Phase 2 fix

**Stamp:** `20260806T184542Z`  
**Verdict:** `deployed`  
**Auth Wave 2:** not started  

## Issues

1. Aziz Bank ESS request under review, but HR drawer showed generic Pending/Waive — no `BankReviewPanel`.
2. Drawer too dense; next action unclear.
3. Mobile showed literal `Submitted on {date}`.

## Fixes

### Backend
- Sync `bank_details` checklist on Bank ESS submit / reject / apply.
- `reconcile_onboarding_bank_item` on HR detail load (repairs in-flight requests).
- HR bank actions: `review_bank` while under review (waive not primary).

### Dashboard (Onboarding drawer)
- Mount canonical `BankReviewPanel` (masked values, Reject+reason, Approve, Apply by permission/state).
- Completion strip: state, progress, **Next**, **Owner**.
- Groups: Needs HR action · Waiting on employee · Waiting on payroll/other · Completed.
- Compact rows: name, status, due, owner, primary action; OCR/history/versions/waive under **View details**.

### Mobile
- i18n `{{date}}` for `bank.submittedAt` / verified / payroll-effective.

## Live prove

Aziz `WATHEFNI-96599338566`:
- ESS request `pending_hr` reconciled → checklist `processing`
- group `being_reviewed`, action `review_bank`
- completion `waiting_on_hr`

## Deployed

| Layer | Value |
|---|---|
| Dashboard | `PostHire-CUJvv77p.js` |
| Backend | modules + app.py reconcile · health 200 |
| OTA canary | group `59ec9dc5-2ffb-4018-b64c-788f3bb94b31` · runtime `0.1.0` |
| Backup | `/opt/wathefni/backups/bank-ess-hr-drawer-20260806T184542Z/` · dashboard-dist-bak same stamp |

## Continue Phase 2 physical

1. Hard-refresh HR dashboard → open Aziz onboarding drawer.
2. Confirm top strip (state / Next / Owner).
3. Bank under **Needs HR action** + full Bank review panel (masked, Approve / Reject+reason / Apply).
4. Mobile: force-quit → reopen → Bank shows real submitted date (not `{date}`).

## Out of scope

Auth Wave 2 · allowlist cleanup (still temporary until Phase 2 done).
