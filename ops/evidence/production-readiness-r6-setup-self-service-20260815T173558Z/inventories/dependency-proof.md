# R6 dependency proof

Hard dependencies (Setup + domain enable):

| Module | Requires | Invalid enable | After dependency |
|---|---|---|---|
| Compensation Planning | Company-enabled Job Architecture | `ja_must_be_enabled` / HTTP **409** `dependency_unmet` | Enable JA, then enable Comp **explicitly** |
| Workforce Planning | Company-enabled Job Architecture | Same governed failure | Enable JA, then enable WFP **explicitly** |

Proved on staging tenants `R6AF1BAF5` / `R6BF1BAF5`:

- Comp without JA → `ok=false`, `error=ja_must_be_enabled`
- Comp after JA → `ok=true`
- WFP on tenant B without JA → governed failure
- HTTP Comp without JA on tenant B → **409**

JA is **not** auto-enabled when Comp/WFP is requested. No unrelated commercial module is silently turned on.

Setup GET for Comp/WFP annotates `runtime_gate` with `ja_must_be_enabled` when JA is deployment-available but not company-enabled, so the card shows **Requires a dependency** rather than **Enabled**.
