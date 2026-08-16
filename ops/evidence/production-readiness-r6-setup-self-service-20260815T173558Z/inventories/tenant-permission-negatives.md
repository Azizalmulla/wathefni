# R6 tenant / permission negatives

## Permissions

| Principal | Setup company routes | Proved |
|---|---|---|
| Ordinary HR (`leave.read`, `employees.read`) | **403** `not_permitted` | Staging G |
| Company admin (`settings.manage`) | **200** for own session company | Staging G |
| Setup / platform operator | `/dashboard/superadmin/setup/companies/{code}/...` only | Live: operator Setup not public |
| Module-specific policy admin | Domain cards still require Setup write + module entitlement | Existing Wave 1–6 Setup |

Ordinary HR access does not imply unrestricted Setup authority. Enforcement is server-side (`_company_self_service_setup_context` → `settings.manage`).

## Tenant isolation

| Attempt | Result | Proved |
|---|---|---|
| Tenant A admin GET own Setup | 200; Intelligence + delivery present | Staging G |
| Tenant B GET own Setup | 200; does **not** inherit A's `conservative` preset | Staging G |
| Tenant A PATCH with `X-Company-Code: B` | Session company wins; B preset is not `frontline` | Staging G |
| Tenant A PATCH operator route for B | **401/403/404** | Staging G |
| Client `company_code` expanding authority | Denied by `dashboard_context` (existing R2) and by company-scoped routes (no URL company) | Live + staging |

Live service: `/dashboard/setup/company/module-policies` and operator Setup are not public (401/403/503).

## Failed save

Empty audit reason on Comp enable → status ≥ 400. Response is not a successful-looking Enabled switch.
