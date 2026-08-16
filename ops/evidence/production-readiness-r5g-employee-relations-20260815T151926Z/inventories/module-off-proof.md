# R5G module-off proof

After disable on `R5G7A4629`:

- Historical cases retained (`G historical cases retained`)
- New intake blocked
- HR workspace `resource_state=unavailable` and `counts=None` (not fake zeros)
- `company_modules.employee_relations` enabled=false
- New ER notifications suppressed after commit (`notification_source_module_enabled` false)
- History remains controlled; cases are not leaked through generic HR surfaces
