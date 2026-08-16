# R6 safe debt

- **ChannelPolicyCard** remains largely English. R6 added a bilingual delivery/preset card; the full channel-chrome Arabic pass stays R11.
- **Setup information architecture** was not visually redesigned. New cards mount in the existing Classic setup areas (Intelligence after Talent; delivery before channels).
- **`FlexibleValue` boolean dump** in Setup Console still prints generic Enabled/Disabled for unstructured debug fields. Module cards that customers toggle use effective state.
- **`WATHEFNI_ONBOARDING_SEED`** stays Class A infrastructure. Customer auto-start is Setup-owned; synthetic/backfill seed is not a company-admin control.
- **Push** stays a deployment gate. Setup shows availability and never provider secrets.
- **Wave 5 C1 default remains off.** That is a kill switch. Setup shows `unavailable_deployment` until infrastructure turns C1 on. Do not flip the default as a product fix.
- **Existing tenants are not auto-enabled** for Intelligence. Company admin must enable `analytics` in Setup after the deployment gate is open.
- **Company create via Setup API** is the product path. The R6 harness SQL-inserts isolated tenants only so cleanup is scoped; that is not a customer-policy step.
- **Audit** continues to use `record_admin_audit` / `action_results`. No second audit ledger.
- **R1 P1-5** (HR Mobile Tasks `allowedActions` not wired) is R7, not R6.
