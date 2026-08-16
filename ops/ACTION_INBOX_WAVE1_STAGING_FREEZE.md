# Action Inbox Wave 1 — Staging Freeze (composition only)

**Gate:** `STAGING_ACTION_INBOX_WAVE1_GO`  
**Evidence:** `ops/evidence/action-inbox-wave1-20260803T165655Z`  
**Contract:** `action_inbox_wave1` v1.0.0

## Authority

Action Inbox **composes and ranks only**. Frozen modules remain systems of action:
Analytics, Compliance, Employees 360, Onboarding, Attendance, Leave, Shifts, Payroll.

- **Read-only** — no record mutations from inbox
- **Alerts & Delivery** owns notifications / reminders
- **Hiring Reports** stay separate
- **No AI**
- **No Compliance Wave 2 / Analytics Wave 2**
- **No Payroll money work**
- **No Attendance ingest / Shifts manager expansion**

## Proven on staging

- Tenant + manager scope wiring (`viewer_phone` / `actor_role` / `manager_scope_employee_keys`)
- Cross-source ranking + deep links to SoA modules
- Owner / deadline / escalation / evidence / authority display (EN/AR)
- Item clears when source resolves; E360 compliance dedupe under findings
- Empty / partial / stale / error UI states; mobile web responsive shell
- Sibling freezes green

## Production synthetic

**GO** for production **synthetic** qualification only (`SYNTHETIC_ONLY`, residual cleanup, markers `AIW1`).  
**NO-GO** for real HR production use until a separate Wave 1-B / controlled rollout gate.

Markers: `AIW1` / phones `965542*` (default synthetic prefixes).
