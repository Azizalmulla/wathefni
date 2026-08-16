# Security threat model — Attendance connectors (Wave 2A)

## Assets

- Attendance punch events (integrity, availability)
- Employee identifiers / badge numbers
- Connector credentials (BioTime tokens, AppSecrets, SFTP keys)
- Device serial allowlists
- **Not assets of Wathefni:** biometric templates/images (must never enter)

## Actors

External attacker · malicious insider at customer site · compromised agent host · malicious vendor middleware admin · cross-tenant tenant · supply-chain connector update

## Key threats & controls

| ID | Threat | Likelihood | Impact | Control |
|---|---|---|---|---|
| T1 | Biometric image/template ingested | M | Critical (privacy/legal) | Hard deny-list; parser unit tests; no Finger/Photo APIs |
| T2 | Forged ADMS punches | M | High (payroll fraud) | SN allowlist; shared secret; mTLS; rate limit |
| T3 | Cross-tenant event injection | L | Critical | company-scoped creds; server-side company binding |
| T4 | Credential theft from agent | M | High | OS keychain/TPM; rotate; least privilege read-only |
| T5 | Replay of old events | M | Medium | Idempotent source_event_id; optional watermark |
| T6 | CSV injection / path traversal | M | Medium | Strict schema; size caps; no executable parses |
| T7 | Clock skew / TZ abuse | M | Medium | Quarantine large deltas; preserve original offset |
| T8 | Silent mapping to wrong employee | M | High | Quarantine unmapped; dual-control map changes |
| T9 | Middleware write-back alters devices | L | High | Wave 2B read-only; no employee push to devices |
| T10 | Compromised connector update | L | High | Signed artifacts; pinned majors |

## Privacy boundary statement

Wathefni receives **attendance event data and device identifiers only**.

Ecosystems requiring explicit biometric exposure controls:

1. **ZK ADMS** — may push photos/biodata → terminate with ATTLOG-only parser  
2. **Hikvision alertStream** — may include `pictureURL` / face snapshots → strip  
3. **Suprema G-SDK** — Finger.GetImage / template set APIs exist → **do not call**; prefer BioStar TA punch logs  

If a customer insists on a path that cannot strip biometrics reliably → **refuse connector enablement**.
