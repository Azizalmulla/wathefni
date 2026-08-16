# Admin / Manager / AI Recruiter Mobile — Scope Freeze

**Status:** Amended (unified public binary / dual principal)  
**Date:** 2026-07-14 (original) · **Amended:** 2026-08-09  
**Prerequisite audit:** Admin / Manager / AI Recruiter Mobile Audit (accepted)  
**Integration assessment:** unified Wathefni app dual-principal foundation

This document freezes durable product and security boundaries for operator mobile
work inside the public Wathefni app.

---

## Product decision — one public binary / two principals

### Public app

**Wathefni** (`ai.wathefni.employee`) is the only public native app / store listing /
approved icon. There is **no** second public HR App Store product.

### Principals (remain separate)

| Principal | Identity | Sessions | API | Client package |
| --- | --- | --- | --- | --- |
| Employee | `employees` | `employee_sessions` | `/app/*` | existing Employee shell |
| Operator (HR) | `dashboard_users` | `dashboard_operator_mobile_sessions` | `/dashboard/mobile/*` | isolated `src/hr` workspace inside the same binary |
| Platform admin | Setup Console | env-gated | `/dashboard/superadmin/*` | out of Wathefni mobile |

### Capability-selected shells

- Employee-only session → Employee shell (automatic)
- HR-only session → HR shell `/hr/*` (automatic)
- Both sessions present → last-used preference, else silent Employee default; workspace switcher is **Settings-only** after authentication (never a cold-start chooser)
- Neither session → single Wathefni sign-in entry with two **methods** (phone OTP vs work email/password). Methods are not product/principal labels; the app never probes or auto-links identity by email/phone.
- Returning signed-in users → local unlock (when Employee PIN applies) then straight into the resolved workspace

### Hard identity rules (unchanged)

1. **Do not create a unified employee/operator session.**
2. **Do not link identities** merely by matching email, phone, employee title, or role name.
3. Do **not** move HR permissions into `GET /app/me`.
4. Do **not** reuse `/app/auth/*` for operators.
5. Do **not** register HR push on `/app/push` until a dedicated operator push model exists.
6. Employee App capability contract, PIN / Face ID, deep links, and frozen Employee UX remain owned by the Employee principal.

### Retired ship target

`apps/wathefni-hr-mobile` / bundle `ai.wathefni.hr` is **source legacy only** — not a
public ship target, not TestFlight, not OTA. New HR mobile work lands in the
unified Wathefni binary under `/hr/*`.

---

## Parallel workstreams (historical)

| Stream | Status |
| --- | --- |
| Employee App — isolated Expo SDK migration | Continues on Expo 54 (canary runtime) |
| **HR-0 / HR-0A** | Closed green |
| **HR-1** | Operator mobile auth + `/dashboard/mobile/me` |
| Unified binary HR workspace foundation | **In progress (2026-08-09)** — dual principal, no HR redesign |

---

## Durable model notes (HR-0)

### Manager scope

**Selected durable model:** role-aware fail-closed resolution with preferred `dashboard_user_id` binding.

- Operator identity (`dashboard_user_id`) is the preferred manager-scope authority; phone remains a transitional binding for existing `manager_scopes` rows and WhatsApp.
- The `manager` role never implies company-wide employee visibility without an explicit scope assignment (including explicit `scope_type=company`).
- Missing phone/user binding or missing active scope rows for `manager` → empty restricted scope + deterministic `configuration_error` (`manager_scope_binding_missing` / `manager_scope_unconfigured`).
- Owners / HR managers retain only backend-current authorized access (permissions + modules); they are not “managers without phone.”

### Dashboard authority

- Shared dashboard tokens and client-supplied phone/company/role/permission claims must not establish authority outside an explicit test-only harness (`WATHEFNI_ALLOW_LEGACY_DASHBOARD_TOKEN_AUTH` + `WATHEFNI_ENV=test|pytest|harness`) that fails startup elsewhere.
- `/health` and `/ready` advertise `permission_authority: backend_current_required`.
