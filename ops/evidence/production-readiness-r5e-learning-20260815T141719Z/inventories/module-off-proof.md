# R5E module-off proof

After historical assignment / completion / certificate, Learning was disabled via `sync_catalog_entitlement(enabled=False)`.

| Check | Result |
|---|---|
| Assignments retained | `ld_assignments` count ≥ 1 |
| New catalog work blocked | `learning_disabled_for_company` |
| Workspace state | `resource_state=unavailable`, `counts=None` (not fake zeros) |
| `company_modules.learning` | `enabled=false` |
| New notifications | `notification_source_module_enabled(company, "learning")` is false after commit |

Surfaces hide new Learning work. History remains reconstructable. No second inbox is created while disabled.
