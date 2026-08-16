# Shifts Wave 6B — production synthetic rotations, compliance, PAM export & multi-channel notifications canary

**Stamp:** `20260803T021530Z`  
**Evidence:** `ops/evidence/shifts-wave6b-20260803T021530Z/`  
**Staging gate:** `ops/evidence/shifts-wave6-20260803T013352Z` (**PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO**)  
**Modules:** `shifts_enterprise_wave6.py` **v6.0.0** · `shifts_notifications_wave6b.py` **v6.1.0** · cleanup **1.4.0**  
**Prior attempt:** canary #1 failed once on `terminal_failed_reached` (unsupported channel not escalated) — fixed in notifications module before this GO run.

## Scope
Production WATHEFNI synthetic-only canary. Markers **SHW6B** / **965537***.  
Empty HR/manager allowlists · real mutation gate on · real reminders off · real notification delivery off (mock only) · integrity jobs 0 · CAPTURE_INGEST off · no PAM submission · no Payroll money.

## Gate result
`PROD_SYNTHETIC_WAVE6B_ENTERPRISE_GO`

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 6 (rotations/remote/compliance/PAM export) | **GO** |
| Production synthetic multi-channel notifications (Wave 6B outbox) | **GO** |
| Controlled HR scheduling | **NO-GO** |
| Controlled manager scheduling | **NO-GO** |
| Talal employee schedule read and notification canary | **NO-GO** |
| Real employee reminders | **NO-GO** |
| PAM submission | **NO-GO** |
| Overall readiness for Wave 6C | **NO-GO** (synthetic green; controlled rollout not started) |

---

## Production SHAs / flags (after redeploy #2)

| Path | SHA |
|---|---|
| `app.py` | `3ddcdda3ef35fa3b85f8e047f4994872e2fe6fa3ea898c9e1cc8b6fb5125e34d` |
| `shifts_enterprise_wave6.py` | `fc390a8d93a814174563d199bab37f891b46e96e93c68a958ae550c6fa366168` |
| `shifts_notifications_wave6b.py` | `33ab0fb9b86bff3f24b537a96e35c82e24a8b2cee59b1a75bffe0a68536e71c1` |
| `shifts_synthetic_cleanup.py` | `eb08e2b67a5858c6330f452c98fc299062fc8a9bee548ca945b7522d1defcb41` |

Flags: `WAVE6=1` · `NOTIFICATIONS_WAVE6B=1` · `NOTIFICATIONS_REAL_DELIVERY=0` · markers `SHW6B,SHW6B-SYNTH|` · phones `965537` · allowlists empty · `REAL_REMINDERS=0` · `CAPTURE_INGEST=off`  
Full dumps: `remote/preflight/`, `remote/verify/`, `remote/flags/shifts-wave6b-synthetic.conf`

---

## Rotation / remote-roster evidence (canary #2 tag `729C2418`)

| Item | ID / proof |
|---|---|
| Period | `3bbc75cf-8b08-4aca-aa9a-05013395df07` |
| Versions | `e2c8155b-…`, `d5ff4889-…` |
| Employees | `WATHEFNI-SHW6B-729C2418`, `WATHEFNI-SHW6B-B-729C2418` |
| Patterns proven | four_on_four_off · panama_223 · six_on_one_off · alternating_day_night · hitch_n_n 14/14 · custom work/rest/travel/standby |
| Remote hitch | camp/transport/accommodation/mobilization metadata present; travel counts in preview |
| Offsets | employee-specific cycle offsets differ |
| Publish | draft → review → return → approve → publish; non-work skipped; L0 authoritative |
| Cycle edit | regenerate leaves published L0 fingerprint unchanged |
| Cancelled-held | soft-cancel → regenerate → held class |

Canary #1 (pre-rollback) period `9f0aba8c-…` tag `A9E144AD` — see `remote/canary/canary1/ids.json`.

---

## Compliance / PAM export evidence

- Ramadan / midday / daily hours / weekly rest / holiday profiles evaluated (warn default)
- PAM export: fingerprint · csv_en · csv_ar · report_en · report_ar · status `manual_submission_required` · `submission: false`
- Contract `pam-export@1.0.0`; no government API invented or called

---

## Notification event / outbox / delivery model

| Table | Role |
|---|---|
| `shift_notification_events` | Canonical business event + dedupe_key (one business notification) |
| `shift_notification_deliveries` | Per-channel attempts with provider/correlation IDs (mock) |
| `shift_notification_acks` | One ack per event regardless of channel |
| `shift_channel_preferences` | Company + employee channel order / enabled set / fallback |

**Events covered in canary:** schedule_published, shift_assigned, shift_changed, upcoming blocked from drafts, invalidate on cancel.

**Channel preference / fallback proven:**
- App-first default ladder
- WhatsApp fallback present in default plan
- Teams-preferred employee plan
- Telegram / email / SMS available in enabled set
- Duplicate suppression on same dedupe_key
- Ack via WhatsApp then App → `already_acked`
- Transient fail-once → retry recovers
- Unsupported channel → `terminal_failed`
- Drafts never notify
- Tenant isolation (or no other-company probe available)
- Cancel/reschedule invalidates pending notifications
- `real_sent: false` on all mock deliveries

---

## Browser / UI reconciliation

- Dashboard build: **DASHBOARD_BUILD_OK**
- UI probe: wave6 honesty 6.0.0 · notifications honesty 6.1.0 · `enterprise_panel_asset True` (`PostHire-DYChMpNb.js`) · health_ok
- Screenshots: not captured as image files; UI proof via production dist marker + API canary exercising the same actions
- API/UI/DB: board payload exposes `wave6` + `notifications_wave6b`; schema tables present after deploy

---

## Rollback / cleanup

| Item | Evidence |
|---|---|
| Backup | `/opt/wathefni/backups/production-pre-shifts-wave6b-20260803T021530Z` |
| Rollback | **YES** — `tests/rollback.out` → `ROLLBACK_OK` |
| Redeploy | `tests/deploy2.out` → `DEPLOY_SHIFTS_W6B_OK` |
| Residual after canary #2 | **0** (`residual-final.json`) |
| Real fingerprints | unchanged before/after (assignments, periods, versions, rotations, compliance, notifications prefs/events) |

---

## Test counts

| Suite | Canary #1 | Canary #2 (after rollback+redeploy) |
|---|---|---|
| Wave 6B prod canary | **169 passed, 0 failed** | **169 passed, 0 failed** |
| W1B / W2B / W3B / W4B / W5B coexist | — | 57 / 108 / 31 / 75 / 83 · all 0 failed |
| W1 / W2 / W3 UX | — | 90 / 82 / 43 · 0 failed |
| Freezes | local + staging | all rc=0 |

---

## Unresolved legal / customer questions

1. Sector-specific Ramadan max hours and midday outdoor windows before any **block** profiles  
2. Weekly rest weekday conventions (Fri vs Fri/Sat) per company  
3. Official PAM form field mapping vs `pam-export@1.0.0`  
4. Hitch travel-day vs Payroll travel-allowance ownership  
5. Named HR/manager allowlists and Talal notification preferences for Wave 6C  
6. Which real providers (WA / Teams / Telegram / SMS) are contracted first for production delivery  

## Remaining intentional blockers

No real allowlists · no real provider messages · no real reminders/timers · no PAM submission · no Payroll money · no employee-app broadening · Wave 6C not started

## Next
**Wave 6C:** controlled HR/manager rollout, final qualification, formal Shifts freeze
