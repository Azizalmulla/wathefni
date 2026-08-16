# HR Employee Profile detail — physical-surface qualification

Stamp: `20260810T175300Z` (approx from spine)  
Surface: `/hr/employees/[employeeKey]`  
Actor: Aziz owner `96599338566`  
Mode: **audit only — no redesign shipped**

## Functional verdict: **CONDITIONAL — do not lock yet**

People row already opens the **canonical** quick profile. RBAC, tenant isolation, and manager scope look sound. The surface is intentionally **facts-only** (not Employees 360). It should **not** freeze until manager honesty + empty/not-found states + cream migration land in one contained patch wave. Do **not** expand into a module dashboard in that wave.

---

## Entry → destination map (live)

| Entry | Lands on | Honest? |
| --- | --- | --- |
| People tab row | `/hr/employees/{employeeKey}` | Yes — canonical |
| `/hr/employees` list row (duplicate stack) | same | Yes |
| Delivery Alerts → `destination` | `/hr/employees/{key}` when gated | Yes |
| People onboarding chip (trailing) | `/hr/onboarding/{key}` | Intentional alternate — not profile |
| Assistant `employees` | `/hr/people` list only | Honest list; no detail deep-link |

Live: directory total **112**; sample Brian Saleh → quick profile with email/phone/start; **no `manager_name`**. Full E360 profile has sections `attendance/compliance/documents/leave/onboarding/payroll/shifts` — mobile DTO strips them. Missing key → **404 `employee_not_found`**.

---

## Profile facts vs API truth

| UI fact | API field | Live |
| --- | --- | --- |
| Name (title) | `employee.name` | Real |
| Status chip | `employment_status` | Raw (`active`) — not localized |
| Position | `position_title` | Often empty string on sample |
| Department | `department` | Often empty |
| Email / Phone | `email` / `phone` | Real on detail (directory omits contact) |
| Manager | `manager_name` | **Not in DTO** — UI claims it; always omitted silently |
| Start date | `started_on` ← `start_date` | Real |
| Actions | `allowed_actions: ["read"]` | Read-only; no CTAs |

Source: `mobile_employee_quick_profile` → `dashboard_employee_profile` card only (`operator_mobile_data.py`). Client still types/normalizes/renders `manager_name`.

---

## Intended mobile role (long-term)

**Best long-term role:** identity **quick profile** — confirm who someone is from People, with optional later **restrained, permission/module-aware deep-links** into already-shipped queues (Attendance / Leave / Onboarding / Documents / Shifts) as single destinations — **not** an embedded second dashboard / E360 clone.

| Option | Verdict |
| --- | --- |
| A Facts-only v1 (current intent) | **Lock this first** after honesty + cream |
| B Restrained module links (1–2 taps into existing lists/detail with employee context) | Later wave; keep out of freeze patch |
| C Web Employees 360 parity on mobile | **Reject** — blocked by `employees360-freeze.mdc` and wrong for phone |

Facts-only is the correct **v1**. Missing module destinations are intentional today, not a functional blocker for freeze — document as deferred product choice.

---

## RBAC / scope / modules / navigation

| Check | Result |
| --- | --- |
| Feature gate | `employee_search` / `employee_quick_profile` + `employees.read` |
| Tenant | Profile company-scoped |
| Manager scope | Out-of-scope / missing → 404 (no leak) |
| Module-off | List can 403 `module_disabled` when no readable post-hire modules; detail still card-only if feature granted — mild capability mismatch debt |
| Safe-back | Detail → `/hr/people`; list `/hr/employees` → More (mild IA debt) |
| Empty `employeeKey` | Query disabled → **ready** blank card — honesty gap |

---

## EN / AR / RTL / visual

| Area | Result |
| --- | --- |
| Labels | `@hr/i18n` EN+AR (`employees.*`, common.*) |
| Status value | Raw backend string |
| RTL | Fact rows respect `isRTL` |
| Visual | People list **cream**; profile detail **legacy** `@hr/theme` `OperationalDetailView` |

---

## Functional blockers (must fix before freeze)

None that break routing/RBAC for the facts-only scope.

## Honesty gaps (block lock)

1. **`manager_name`** claimed in UI/types/normalize; API never supplies it → silent omission (false promise).
2. **Empty `employeeKey` / hard-empty success** → ready blank card; no calm not-found / unavailable empty.
3. Optional: raw `employment_status` without localized label.

## Exact visual migration (no redesign / no E360)

Same Leave / Candidate / Attendance cream pattern:

1. Replace `OperationalDetailView` with cream `PageScreen` + `HrPushedNav`.
2. One cream surface: EditorialHeading name + StatusChip from real employment status.
3. Facts as ListRow / Fact rows (position, department, email, phone, start) — **drop Manager unless API adds resolved name**.
4. Keep facts-only; no module hub cards in the lock wave.
5. Loading / error / permission / not-found as calm ListRow states (not plum stack).

---

## Freeze after one contained patch?

**Yes — if scoped to honesty + cream only** (drop/flag manager, empty/not-found, cream chrome, keep facts-only).

**No — if** the patch adds E360 sections, module dashboards, or roster mutations (`employees360-freeze`).

Evidence: this folder (`spine-probe.txt`, this `VERDICT.md`).
