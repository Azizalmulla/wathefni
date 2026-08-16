# Wave 2B implementation plan — BioTime first connector

## Scope

- Build `biotime` middleware pull adapter + on-prem agent skeleton
- Wire to Attendance Authority synthetic path only
- Add CSV/SFTP fallback sharing the same contract
- No real clocking enablement; import/QR/GPS/kiosk remain off

## Work packages

| ID | Work | Exit |
|---|---|---|
| 2B-1 | Canonical envelope types + privacy deny-list tests | Tests fail closed on biometric fields |
| 2B-2 | BioTime client (token/basic) + transaction pagination/cursor | Fixture tests PASS |
| 2B-3 | Direction + timezone mapping table (configurable) | Documented defaults for KW |
| 2B-4 | On-prem agent: poller, sqlite outbox, heartbeat, mTLS upload | Agent canary on staging LAN |
| 2B-5 | Mapping quarantine API (device_user_id → employee_key) | Unmapped never auto-binds reals |
| 2B-6 | Observability: lag, last_sync, errors, version | Metrics exported |
| 2B-7 | CSV/SFTP adapter | Same envelope; hash idempotency |
| 2B-8 | Synthetic end-to-end canary → authority punches | PASS; cleanup; freezes green |
| 2B-9 | Security review of parsers | Sign-off |
| 2B-10 | Incorporate supplier interview results | Priority delta doc |

## Explicit non-goals for 2B

- Production ADMS terminator
- Hikvision/Suprema/Anviz/IBA production adapters (spike OK)
- Enabling `WATHEFNI_ATTENDANCE_IMPORT`
- Expanding synthetic allowlist to real employees
- Attendance UI redesign

## Suggested sequencing (calendar)

Week 1: 2B-1..2B-3  
Week 2: 2B-4..2B-6  
Week 3: 2B-7..2B-8 + outreach  
Week 4: 2B-9..2B-10 + Wave 2B evidence pack
