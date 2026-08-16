# R5F module-off proof

After `sync_catalog_entitlement(..., enabled=False)` on `R5FB7930E`:

- Historical `bn_coverage_periods` retained (≥1)
- New plan upsert returns `benefits_disabled_for_company`
- HR workspace `resource_state=unavailable` and `counts=None` (not fake zeros)
- Employee workspace `resource_state=unavailable` and `plans=None` (not “No benefits”)
- `company_modules.benefits` enabled=false
- `notification_source_module_enabled(company, "benefits")` is false after commit
