# R5H module-off proof

After `sync_catalog_entitlement(..., enabled=False)` on tenant `R5H71CB15`:

- `history_preserved=true`
- Historical campaigns retained (`COUNT(eng_campaigns) >= 1`)
- New campaign returns `engagement_disabled_for_company`
- Workspace `resource_state=unavailable` and `counts=None` (not fake zeros)
- `notification_source_module_enabled(company, "engagement")` is false **after commit**

Existing tenants are not auto-enabled. Kill switch `WATHEFNI_ENGAGEMENT_C5=off` still wins.
