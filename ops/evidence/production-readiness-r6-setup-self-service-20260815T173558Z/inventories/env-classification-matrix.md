# R6 environment classification matrix

Classes:

- **A** — legitimate infrastructure / deployment gate → env stays
- **B** — customer policy → Setup
- **C** — obsolete / dead → not authoritative

| Key | Class | Owns | Setup honesty |
|---|---|---|---|
| `WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1` | A | Intelligence kill switch (default off) | `unavailable_deployment` when off |
| `WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES` | A | Staged Intelligence allowlist; empty admits after R6 | Explicit list still blocks OTHER |
| `WATHEFNI_ANALYTICS_KILL` | A | Immediate Intelligence kill | Never Enabled while on |
| `WATHEFNI_*_C#` / `WATHEFNI_*_COMPANIES` | A | Wave 4/6 kill switches and staged allowlists | Empty admits when customer_enableable |
| `WATHEFNI_EMPLOYEE_APP` | A | Employee App master kill | Company module remains customer entitlement |
| `WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST` | A | Employee-key rollout | Not company policy |
| `WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST` | A | Staged fail-closed | Not company policy |
| `WATHEFNI_PUSH_NOTIFICATIONS` | A | Push provider deployment | Delivery card shows availability only |
| `EXPO_ACCESS_TOKEN` / `WATHEFNI_PUSH_PROVIDER` | A | Provider secrets | Never exposed in Setup |
| `WATHEFNI_ONBOARDING_SEED` | A | Synthetic / backfill seed | Customer auto-start is Setup-owned |
| `WATHEFNI_ONBOARDING_HR_MUTATE` | A | Dashboard onboarding mutate kill | Empty company allowlist already admits when on |
| `onboarding.auto_start_on_hire` | B | Hire → onboarding auto-start | Canonical company_settings |
| `notification_preset` | B | Customer notification preset | Setup delivery card |
| Channel policy / accounts | B | Customer delivery channels | Existing channel cards; secrets stay integrations |
| `leave_policies` + leave overlay | B | Customer leave policy | `leave_policies` canonical |
| Attendance ops / Wave 2 ingest | B | Customer attendance concerns | One store per concern |
| Legacy HTML `notification_preset` (~app.py:42600) | C | Display leftover | Not authoritative |

`secrets_never_moved_to_setup=true`.
