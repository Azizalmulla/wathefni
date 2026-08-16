# Setup → AI parity — platform phases (2026-08-10)

Audit-driven platform work before HR Mobile Assistant. No mobile AI UI shipped.

## Contract
Setup Console modules + configured channels → AI capabilities → RBAC/manager scope → canonical `action_registry` workflows.

## P0 — PASS (core channel + session)

**Done**
- `assistant_dashboard_context` — workspace/module-aware chat gate (not `pre_hiring`-only)
- Chat/capabilities/session routes use it
- `assistant_channel_readiness.py` — canonical Setup → catalog → execution readiness
- `_visible_tools` hides Setup SKU tools when module off; hides email/WA tools when unconfigured
- `notify_candidate` / `send_email` fail-closed + WA routes with `company_code` + `audience=candidate`
- Hard-refuse SMS / Telegram / Teams-chat in prompt + router
- Setup channel policy email aligned to same readiness probe

**Tests:** `test_assistant_p0_setup_ai_parity.py`

**Setup→AI parity (P0 scope):** **PASS** for module hide/show + channel hide/show + multi-tenant matrix

**Debt remaining after P0**
- Candidate email still uses `candidate_communication_router` (not employee `deliver_to_employee` ladder) — intentional for candidates; company WA routing fixed
- Dual-path employee reminders still flag-gated on outbound flows

---

## P1 — PASS (offers + reads + HR reads)

**Done**
- Tools: `list_assessment_attempts`, `list_live_interviews`, `list_video_interviews`, `list_candidate_offers`, `approve_employment_offer`, `send_employment_offer`
- Catalog IDs: `interviews_read`, `employment_offers`
- `employment_offers` + `calendar` marked `toolcall_gated`
- `assistant_hr_reads_enabled` defaults **ON** (Setup-driven); `WATHEFNI_ASSISTANT_HR_READS=off` emergency hide; global kill retained

**Tests:** `test_assistant_p1_setup_ai_parity.py`

**Setup→AI parity (P1 scope):** **PASS** for offers/assessment/interview/video reads + onboarding/compliance list offerability

**Debt**
- Offer *draft/create* still web-first (approve/send only via Assistant)
- Assessment/video detail report bodies intentionally compacted for privacy

---

## P2 — PARTIAL → near-PASS

**Done**
- `list_calendar_events` (calendar module)
- Catalog awareness: `calendar_module`, `employee_app`, `push_notifications` (no Assistant push-send tool — honesty)
- Wave1 company gate uses env allowlist (not hard single-tenant equality)

**Tests:** `test_assistant_p2_setup_ai_parity.py`

**Setup→AI parity (P2 scope):** **PARTIAL**
- Calendar read: PASS
- Employee App / push: awareness PASS; no send-push ActionSpec (correct honesty)
- Remaining `WATHEFNI_*_COMPANIES` freezes for Leave/Attendance/Payroll/Shifts *real authority* and Action Inbox wave still apply — those are module freezes, not Assistant catalog bugs

**Debt (do not confuse with Assistant catalog)**
- Module freezes / synthetic-only / company allowlists for real mutations in Leave, Attendance, Shifts, Payroll, Onboarding HR mutate
- Wave1 spine tools still dashboard-channel + env company list
- No Assistant push/SMS/Telegram/Teams-chat send tools (hard refuse)

---

## Overall Setup→AI parity

| Area | Status |
|---|---|
| Module on → tools appear / off → disappear | **PASS** |
| Channel configured → email/WA tools / else hidden+refuse | **PASS** |
| RBAC permission filter (gated modules) | **PASS** |
| Manager scope at execute (existing SoA) | **PASS** (unchanged) |
| Confirmation / SOD on sensitive mutates | **PASS** |
| Offers / calendar / assessment·interview·video reads | **PASS** |
| Employee push as Assistant send | **N/A (refuse)** — awareness only |
| All product freezes removed | **NO** — retained by design |

**Mobile AI UI:** not started (per plan).
