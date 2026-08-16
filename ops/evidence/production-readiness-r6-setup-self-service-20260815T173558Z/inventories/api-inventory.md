# R6 Setup API inventory

## Company administrator (session tenant only)

- `GET /dashboard/setup/company/module-policies`
- `GET /dashboard/setup/company/module-policies/{module_key}`
- `PATCH /dashboard/setup/company/module-policies/{module_key}`

Company is taken from `dashboard_context`. Requires `settings.manage`. No URL company code.

## Platform Setup operator (unchanged path)

- `GET /dashboard/superadmin/setup/companies/{company_code}/module-policies`
- `GET /dashboard/superadmin/setup/companies/{company_code}/module-policies/{module_key}`
- `PATCH /dashboard/superadmin/setup/companies/{company_code}/module-policies/{module_key}`

## Module keys added/owned in R6

- `wave5_analytics` / `analytics` / `intelligence` / `hr_intelligence`
- `notifications` / `delivery` / `notification_preset`

Comp/WFP enable without company JA returns **409** `dependency_unmet`.
Ordinary HR returns **403** `not_permitted`.
Empty audit reason returns **≥400**.
