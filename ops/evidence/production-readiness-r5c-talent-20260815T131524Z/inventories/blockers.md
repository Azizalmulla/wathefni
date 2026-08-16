# R5C blockers

**Open R5C blockers: none.**

Resolved during qualification:

1. **Write gate used HR role as a substitute for permission.** Owner + `talent.read` could POST profiles. Fixed: writes require `talent.manage` / `talent.review` / `talent.succession` / `talent.sensitive`.
2. **Notifications were mapped but never emitted.** `_notify` now fires on review start, succession plan create, manager nomination review (actor only — never the nominee), and employee mobility save. R4 `flow=talent` suppression applies.
3. **Wave 4 honesty still claimed Talent hidden.** `setup_console_wave4_policies.honesty_payload()` now records `talent_customer_enableable=true`, matching the R5B Performance carve-out pattern.
4. **Qualify MOBILE_OK matcher required the word `passed`.** Composition prints `PASS employee app composition shapes (65 checks)`. Matcher updated; composition itself was green.
