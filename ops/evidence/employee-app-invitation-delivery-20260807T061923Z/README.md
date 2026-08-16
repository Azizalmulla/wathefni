# Employee App — Invitation + Delivery (canary prove)

**Stamp:** see folder name  
**Verdict:** **PASS** (canary WATHEFNI)  
**Auth Wave 2 Phase 6:** not started  

## Architecture

Contract: `ops/EMPLOYEE_APP_INVITATION_DELIVERY_CONTRACT.md`

- Invitation/delivery owned by `employee_app_invitation.py` (separate from Auth Wave 2)
- Auto-invite on employee create + onboarding start (flag-gated)
- HR Resend / Re-invite deliver to employee — **no code in normal HR response**
- Code handoff (`hr_task_only`) is exception-only when `needs_attention`
- Channels: email / WhatsApp (SMS excluded)

## Shipped

| Surface | Change |
|---|---|
| Backend | `employee_app_invitation.py` + hooks in create/onboarding + dashboard routes |
| Outbound fix | `OctopusProvider.send_session` now passes `company_code` (was breaking activation delivery audit) |
| Flags | `WATHEFNI_EMPLOYEE_APP_AUTO_INVITE=on` · companies=`WATHEFNI` |
| Dashboard | App access card shows invitation status/channel; Resend / Re-invite; Show code only on needs_attention |

## Evidence

| Check | Result |
|---|---|
| Unit/smoke `smoke-test-employee-app-invitation.py` | PASS |
| OpenAPI invitation routes | present; activate still present; no `/app/devices` |
| Aziz live reinvite | **delivered via email**; no `activation_code` in response |
| Snapshot never discloses code | PASS |
| Dashboard UI needles | `PostHire-*.js`, `api-*.js` |

## Residual

- Physical HR walk of Resend / Re-invite on dashboard UI (EN+AR) still useful
- Employee activate with the emailed code (Auth Wave 2 unchanged) — optional physical confirm
- Failed synthetic phones stamp `failed` correctly (expected)

## Rollback

See `deploy/ROLLBACK.sh` — restore prior `app.py` / remove module + auto-invite drop-in / restore prior `outbound_delivery.py` / restart.
