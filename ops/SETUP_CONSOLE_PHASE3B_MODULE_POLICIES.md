# Setup Console Phase 3B — Remaining Module Company Policies

**Status:** PASS (canary qualified) · **Frozen**  
**Depends on:** Setup Console Phases 1–3A (frozen) · Payroll working calendar SoT  
**Do not auto-start:** Roles/Permissions · Integrations UX · adaptive Employee App · Employee App P1 · HR App · Auth Wave 2 Phase 6

## Verdict

**PASS** — canary live smoke **44/0**

Evidence: `ops/evidence/setup-console-phase3b-20260808T031351Z`  
Canary: `/opt/wathefni/ops/evidence/setup-console-phase3b-20260808T031351Z`

Smoke: `wathefni-orchestrator/smoke-test-setup-console-phase3b.py`

## Product principle

| Setup Console | Operational modules |
|---|---|
| How should this company operate? | What is happening today? |

No transaction workflows (requests, punches, rosters, uploads, journeys) inside Setup.

## Ownership map

| Concern | Owner | Canonical models |
|---|---|---|
| Leave types / entitlement / eligibility / notice overlay | **Setup Console** | `leave_policies`, `company_modules.settings.leave_setup` |
| Leave requests / balances / approvals | **Leave ops** | `leave_requests`, `leave_balances`, ledger |
| Attendance grace / correction defaults | **Setup Console** | `company_modules.settings.attendance_setup` (+ optional stamp on approved payroll policy grace) |
| Attendance → pay mode | **Setup Console Payroll** | payroll attendance UX / P3 policy |
| Attendance logs / exceptions / corrections | **Attendance ops** | attendance authority tables |
| Shifts leave-conflict / overnight / publish defaults | **Setup Console** | `shift_authority_settings`, `company_modules.settings.shifts_setup` |
| Working calendar (rest + holidays) | **Setup Console Payroll (3A)** | `payroll_company_settings.setup_extras`, `public_holidays` |
| Shift templates / rosters / publish | **Shifts ops** | schedule / draft / publish tables |
| Document required types + warning windows | **Setup Console** | `company_modules.settings.documents_setup` (compliance module) |
| Uploads / reviews / renewals | **Documents/Compliance ops** | `compliance_documents` |
| OCR / extraction | **Wathefni** | platform — not customer-configurable |
| Onboarding template bind (new hires) | **Setup Console** | `companies.metadata.onboarding_template`, `company_modules.settings.onboarding_setup` |
| Active onboarding journeys | **Onboarding ops** | Wave 2A lifecycle projection (unchanged) |

## Progressive disclosure

Every module card: **Required → Optional → Advanced**. Disabled modules show preserved policy read-only.

## Cross-module dependency map

```
Payroll working calendar (3A)
  ├── Leave leave_policies.weekend_days   (synced, not separately edited)
  └── Shifts shift_authority_settings.rest_weekdays (synced)

Payroll attendance → pay
  └── Attendance Setup card (reference + deep link)

Documents Setup requirements
  └── Compliance classifier warning_days overlay
  └── Onboarding document steps (category-aware seed unchanged)

Onboarding template bind
  └── New seed only — historical assignment pins preserved
```

## Retired / gated duplicate writers

| Former / risk | Action |
|---|---|
| Shifts compliance profile `rest_weekdays` / `holiday_dates` rules | Soft-stripped in `upsert_compliance_profile`; calendar owned by Payroll Setup |
| Ops leave/attendance/shifts/onboarding/compliance policy editors | Replaced with **Configure in Setup Console** banners; ops keep transactions |
| Second working calendar | Not created — consumers sync from 3A |

## Gaps (honest)

| Gap | Notes |
|---|---|
| Leave pack/type enable UI | Seeded presets exist; Setup edits fields on existing `leave_policies` rows — no separate pack marketplace yet |
| Role/department document overlays | Company required-types + warnings only; category-aware seed remains code-level |
| Department-specific onboarding | Flag stored; full overlay editor deferred |
| Capture location/device restrictions | Explicitly Capture Ops / platform — not company Setup under freeze |
| Attendance overlay → runtime enforcement depth | Grace stamped onto payroll policy when column present; full capture-path wiring remains attendance ops |

## API

- `GET /dashboard/superadmin/setup/companies/{code}/module-policies`
- `GET/PATCH …/module-policies/{leave|attendance|shifts|documents|onboarding}`
- Writes refused with `409 module_disabled` when module off (history preserved)

## Smoke

```bash
cd wathefni-orchestrator
WATHEFNI_API_BASE=… WATHEFNI_SETUP_TOKEN=… WATHEFNI_SETUP_PHONE=… \
  python3 smoke-test-setup-console-phase3b.py
```
