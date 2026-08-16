# Attendance Wave 2A — Kuwait Device Ecosystem & Connector Architecture

**Stamp:** `20260802T024341Z`  
**Mode:** Research only — no production connector code, no deploy, no real clocking, no QR/GPS/kiosk, frozen modules untouched.  
**Depends on:** Wave 1 / 1B / 1C immutable punch authority (`source` + `source_event_id` idempotency).

## Executive recommendation

| Decision | Choice |
|---|---|
| Long-term architecture | Vendor-neutral **canonical punch contract** → Attendance Authority; multiple adapters behind capability negotiation |
| First connector (Wave 2B) | **ZKTeco BioTime / ZKBio Time middleware REST transaction pull** |
| Why first | Highest Kuwait attendance-device share; documented third-party API; event-only payloads; common on-prem private-cloud pattern; no biometric templates required |
| On-prem agent | Required for BioTime/HikCentral/BioStar LAN installs that cannot expose vendor middleware to the internet |
| Direct ADMS/PUSH to Wathefni cloud | Defer (Wave 2C+) — powerful but higher protocol + biometric-exfiltration risk |
| Controlled capture readiness | Still **NO-GO** until synthetic connector canary + mapping remediation |

---

## 1. Kuwait market / device matrix

Confidence legend: **H** = official docs + Kuwait public presence; **M** = strong regional/integrator evidence; **L** = inferred / needs supplier interview.

| Ecosystem | Common Kuwait devices / software | Typical deploy | Direct terminal API | Push vs pull | Cloud API | Local SDK | Middleware API / DB | Webhook / event | Offline / replay | Stable event IDs | TZ / event semantics | Emp↔device ID mapping | License | LAN / firewall | On-prem Wathefni agent? | Cred model | Lock-in | Conf |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **ZKTeco + BioTime / ZKBio Time** | Push-capable terminals (Green Label / ProFace / SpeedFace class); BioTime 8/9.x | Device → BioTime private cloud → HR | Partial (proprietary ADMS/PUSH; not preferred) | Device **push** to BioTime; Wathefni **pull** BioTime API | BioTime is usually customer-hosted “private cloud”; not Wathefni SaaS | Windows-centric BioTime; ADMS libs unofficial | **REST** `/iclock/api/transactions/` + personnel APIs; optional sync DB tables | BioTime→HR is pull; device→BioTime push | Device stores logs; BioTime retains transactions; pull by time window | Transaction `id` + `terminal_sn`+`punch_time`+`emp_code` composite | Device local time; `punch_state` coded (0/1/…); map to in/out | `emp_code` ↔ Wathefni employee_key | BioTime **API license mod** often required (`IsNotOpenAPI` gate) | BioTime LAN/VPN; devices outbound to BioTime | **Yes** (poll BioTime or terminate ADMS locally) | Admin user/token or Basic; rotate via BioTime users | Medium (software) / High if ADMS only | **H** |
| **ZK ADMS / PUSH direct** | Same terminals with Cloud/ADMS server URL | Device → HTTP `/iclock/*` | Yes (protocol) | Device **push** | Can point at cloud URL | Unofficial OSS ADMS servers | N/A (raw protocol) | Device-initiated HTTP | Device retries offline buffer | ATTLOG line fields; SN+uid+time(+status) | Device clock; status codes | Device User ID | Firmware feature; no BioTime license | Outbound HTTPS from site | Optional agent as ADMS terminator | Serial allowlist + shared stamp/token | High protocol lock-in; fragile | **H** (protocol) / **M** (Kuwait use) |
| **Hikvision + ISAPI** | MinMoe / face T&A terminals; DS-K1T* | Direct device or via HikCentral | **ISAPI** REST Digest | Pull AcsEvent search; optional alertStream / HTTP host push | Hik-Connect OpenAPI (cloud) separate from on-prem | Device SDK / ISAPI; Windows-heavy legacy SDK | HikCentral Artemis OpenAPI (AppKey/HMAC) | Event subscription + HTTP notification | Device event buffer; page search | `time`+`employeeNoString`+`doorNo`+device; platform event IDs vary | ISO timestamps; `attendanceStatus` / major-minor codes | `employeeNo` string | HikCentral OpenAPI license/module; device firmware | Device TCP 80/443 on LAN; agent VPN | **Yes** for LAN ISAPI / HikCentral | Digest user or AppKey/AppSecret | Medium–High (security stack) | **H** |
| **HikCentral Professional** | Multi-device AC + T&A | Central on-prem | Via platform, not each device | Platform push subscribe + search | On-prem OpenAPI; Hik-Connect for SMB cloud | Docs in install folder | Artemis OpenAPI; optional DB bridge (vendor docs) | Subscribe by event type | Platform retention | Prefer platform event id | Centralized TZ config | Person ID sync from HR | Partner OpenAPI enablement | OpenAPI host inside customer DC | **Yes** | AppKey/AppSecret HMAC | High platform lock-in | **H** |
| **Suprema + BioStar 2** | BioStation / FaceStation / XPass | BioStar 2 server | G-SDK / Device SDK (direct) or BioStar API | API **pull** (~3–10s lag); **WebSocket** for near-real-time | BioStar typically on-prem; mobile API needs license | G-SDK gRPC multi-language; Device SDK Windows heritage | BioStar New API + **TA API** `/tna/punch_logs/modified` | WebSocket events (not classic webhook) | Device + BioStar DB | Punch log `id`; device_datetime | ISO-8601; punch type enums (IN/OUT/BREAK_*) | BioStar `user_id` | BioStar + TA modules | BioStar ports (incl. TA ~3002); TLS | **Yes** | Session cookie / bs-session-id | Medium–High | **H** |
| **Anviz + CrossChex** | Anviz terminals; CrossChex Cloud / on-prem | Cloud popular for SMB | Limited; prefer cloud | Cloud **webhook push** + API **pull** | **CrossChex Cloud API** | Windows CrossChex SDK | Cloud API key/secret | **Webhooks** supported | Cloud retention + device buffer | Cloud record ids + workno+time | ISO timestamps; checktype codes | `workno` / employee object | Cloud subscription | Outbound to Anviz cloud | Agent only if on-prem CrossChex | API key/secret + token | Medium | **H** (API) / **M** (KW share) |
| **IBA (KCS Kuwait)** | Integrates Morpho/IDEMIA, ZKTeco, Suprema, Virdi, Lenel, TrustOne, CivinTec, others | Local T&A platform feeding HR/payroll | Via IBA, not Wathefni↔device | Usually IBA owns device sync; export/API to HR | Customer on-prem/web | Proprietary | **Partner API / DB / file** (must confirm per deal) | Unknown publicly | IBA DB is system of record for many sites | Unknown — ask KCS | Kuwait/GCC shift semantics (8/12/24/48h) | IBA employee id | Commercial IBA license | Customer DC | **Yes** if IBA stays LAN-only | Per-customer | High (local platform) | **H** (existence) / **L** (API details) |
| **USB / CSV / XLSX / SFTP** | Any brand + integrator export | Nightly file drop | N/A | Batch pull | N/A | N/A | File schema per site | N/A | Manual re-upload | Hash of row + file etag | Often naive local timestamps | Badge / emp code columns | None | SFTP inbound or agent watch folder | Agent or SFTP gateway | SFTP keys | Low tech lock-in / high ops cost | **H** |
| **Enterprise AC → HR** (LenelS2, Honeywell, Bosch) | Door events reused as attendance | SI-managed | Vendor APIs | Pull/subscribe | Varies | Vendor SDKs | Often middleware or SQL views | Sometimes | Platform logs | Platform event ids | Door grant ≠ T&A direction | Badge ↔ person | Expensive | Strict LAN | **Yes** | Vendor IAM | High | **M** |

### Kuwait presence notes (public)

- **KCS / IBA:** Local bilingual T&A platform; integrates multi-vendor biometrics; sales `sales@kcs.com.kw`, +965 9722… ([kcs.com.kw/iba-time-and-attendance](https://www.kcs.com.kw/iba-time-and-attendance/)).
- **ZKTeco:** Marketed by regional/Kuwait distributors and integrators (e.g. AIMS / MS Solution listings; UltraTech installs ZKTeco + Suprema).
- **Suprema:** Ideal Information Co. publicly states official agent status in Kuwait; ScreenCheck ME regional; UltraTech installs.
- **Hikvision:** Common in CCTV+AC stacks; Al-Nisf / Okaz / UltraTech appear in public distributor/integrator materials (confirm current authorized status in outreach).
- **Pattern:** SME attendance → ZKTeco+BioTime or Anviz; enterprise security → Hikvision/HikCentral or Suprema/BioStar; some corporates → IBA as HR-facing T&A regardless of reader brand.

---

## 2. Integration-method comparison

| Method | Latency | Ops burden | Privacy risk | Idempotency quality | Kuwait fit | Wathefni priority |
|---|---|---|---|---|---|---|
| Vendor middleware REST pull (BioTime / HikCentral / BioStar TA) | Minutes (poll) | Low–medium | Low if event-only fields | High (vendor ids) | Best for managed fleets | **P0** |
| Signed webhook / HTTP event receive | Seconds | Medium (ingress + verify) | Low–medium (must strip images) | Medium–high | Anviz cloud; Hik HTTP host | **P1** |
| On-prem agent (LAN poll + outbound queue) | Minutes | Medium (agent fleet) | Controllable | High | Required for air-gapped BioTime/HikCentral | **P0** (infra) |
| Direct ADMS/PUSH terminator | Seconds | High (protocol) | **High** (photos/templates possible) | Medium | Useful for multi-site without BioTime | **P2** |
| SQL/DB polling | Minutes | High (schema drift) | Medium | Variable | Legacy SI sites | **P3** last resort |
| CSV/XLSX/SFTP | Hours–day | High | Low | Weak without strict keys | Ubiquitous fallback | **P1** fallback |
| Direct G-SDK / Device SDK | Seconds | High | **High** (template APIs exist) | Medium | Suprema-heavy campuses | **P2** gated |

---

## 3. Recommended priority order

1. **Canonical punch contract + connector framework** (shared with all adapters)  
2. **ZKTeco BioTime transaction pull connector** (+ on-prem agent packaging)  
3. **CSV/SFTP fallback adapter** (same contract; covers USB exports)  
4. **Hikvision HikCentral OpenAPI / ISAPI AcsEvent** (event-only allowlist)  
5. **Anviz CrossChex Cloud webhook + pull**  
6. **Suprema BioStar TA API / WebSocket**  
7. **IBA partner adapter** (after KCS technical disclosure)  
8. **ZK ADMS direct** (only with hard biometric payload deny-list)  
9. **SQL polling** only when no API exists

### Exact first connector to build (Wave 2B)

**Name:** `wathefni-connector-biotime`  
**Mode:** Pull `GET /iclock/api/transactions/` with time cursor + optional `terminal_sn` filter  
**Auth:** Token or Basic per site license  
**Normalize:** BioTime `punch_state` → `in|out|break_*|unknown`  
**Idempotency:** `source=biotime`, `source_event_id=biotime:{transaction_id}` (fallback hash of sn+emp_code+punch_time+punch_state)  
**Deploy:** Customer LAN agent → signed outbound to Wathefni ingest  
**Privacy:** Never request / store bio templates; ignore photo fields if present  
**Synthetic canary only** until mapping + authority gates pass

---

## 4. Target connector architecture

```
[Device fleet]
    │  push / local protocol
    ▼
[Vendor middleware | ADMS terminator | File drop | Cloud vendor]
    │
    ▼
[Wathefni Connector Adapter]  ← capability negotiation
    │  sanitize (strip biometrics)
    │  map device_user_id → employee_key
    │  mint source_event_id
    ▼
[Canonical Punch Envelope] ──► [Attendance Authority ingest_punch]
    │                              (Wave 1 immutable store)
    ▼
[Connector Observability]  health / last_sync / lag / error / version
```

### Adapter kinds

| Adapter | Role |
|---|---|
| `cloud_api` | Vendor SaaS pull (Anviz, Hik-Connect) |
| `middleware_api` | BioTime / HikCentral / BioStar |
| `onprem_agent` | Runs in customer network; outbound-only preferred |
| `signed_webhook` | Ingress with HMAC/mTLS; replay window |
| `sql_poll` | Read-only views; quarantine schema drift |
| `file_sftp` | CSV/XLSX parsers with column maps |

### Capability negotiation (examples)

`supports_push`, `supports_pull`, `supports_webhook`, `event_id_stable`, `direction_native`, `offline_replay`, `biometric_payload_risk`, `max_lag_sla_s`, `tz_source` (`device|middleware|utc`)

### Health / ops

Per connector instance: `last_success_at`, `lag_seconds`, `events_in_window`, `error_rate`, `auth_expiry`, `agent_version`, `quarantine_count`.

### Credentials & tenancy

- Per-company connector credentials in sealed secret store  
- No shared BioTime admin across tenants  
- Rotation runbook + dual-credential overlap window  
- Agent identity = company-scoped mTLS or signed JWT short-lived

### Offline / retry / replay

- Agent durable queue (disk) before upload  
- At-least-once delivery; authority dedupe on `(company, source, source_event_id)`  
- Cursor checkpoint in connector state (not in punch store)

### Mapping remediation

- Unmapped `device_user_id` → quarantine queue (not silent drop)  
- HR maps to employee_key; never auto-create real employees from device  
- Device registry: serial/SN ↔ site ↔ company

### Versioning

- Semver connectors; capability document per version  
- Agent auto-update channel with signed artifacts; pin major in production

---

## 5. Generic connector contract (canonical punch)

Aligns with Wave 1 `ingest_punch`:

```json
{
  "company_code": "WATHEFNI",
  "source": "biotime",
  "source_event_id": "biotime:123456",
  "device_id": "SN-ABCDEF",
  "device_user_id": "1001",
  "employee_key": "WATHEFNI-…",
  "punched_at": "2026-08-02T09:01:22+03:00",
  "direction": "in",
  "verify_method": "fingerprint|face|card|pin|mobile|unknown",
  "connector_id": "biotime-wathefni-01",
  "connector_version": "0.1.0",
  "raw_ref": { "vendor_fields_allowlisted": true }
}
```

**Hard privacy rules**

- Forbidden in Wathefni: fingerprint images, face images, templates, `pictureURL` blobs, ADMS biodata payloads  
- Allowed: event time, direction/status codes, device id, person/device user id, verify *type* enum  
- Ecosystems where exposure cannot be reliably prevented without careful allowlists: **ZK ADMS direct**, **Suprema G-SDK Finger APIs**, **Hikvision alert payloads with face snapshots** — require deny-by-default parsers

---

## 6. On-prem agent architecture

- Single Go/Python agent binary per site (or per BioTime host)  
- Outbound HTTPS only to Wathefni (no inbound unless webhook mode)  
- Modules: poller | webhook forwarder | file watcher | state DB (sqlite) | secrets | health heartbeat  
- Kuwait default TZ `Asia/Kuwait`; never rewrite punched_at except documented clock-skew quarantine  
- Runs beside BioTime/HikCentral; service account least privilege (read transactions only)

---

## 7. Security threat model (summary)

| Threat | Mitigation |
|---|---|
| Biometric exfiltration into Wathefni | Deny-list fields; contract tests; no template APIs |
| Forged punches via open ADMS URL | Device SN allowlist, mutual auth, per-site tokens |
| Credential theft on agent host | OS secret store / TPM where available; short-lived tokens |
| Cross-tenant bleed | company_code scoping on every ingest; separate connectors |
| Replay / duplicate storms | Idempotent `source_event_id`; rate limits |
| Malicious CSV | Schema allowlist; size caps; no macros |
| Middleware admin overreach | Read-only API users; no employee write from Wathefni in Wave 2B |
| Clock skew | Quarantine if |device_tz_delta| > threshold |

Full matrix: `architecture/threat-model.md`.

---

## 8. Supplier / partner shortlist (outreach)

| Partner | Why | Contact path (public) | Ask |
|---|---|---|---|
| **Kuwait Computer Services (KCS) — IBA** | Local T&A platform; multi-vendor device hub | sales@kcs.com.kw / +965 97221371… | API/DB export; HRMS partnership; frequency of live sync vs file |
| **Ideal Information Co.** | Public Suprema agent in Kuwait | LinkedIn / company channels | BioStar TA API availability; reseller partnership |
| **UltraTech Kuwait** | Multi-brand installer (ZK/Suprema/HID/Paxton) | utechkw.com | Most-installed models; BioTime vs file export norms |
| **AIMS / MS Solution (ZKTeco listings)** | ZKTeco distribution claims | mssolution.me | BioTime versions sold; API license packaging |
| **Stebilex** | Regional biometrics (IDEMIA/VIRDI/Suprema) | stebilex.com | Enterprise AC→attendance patterns |
| **Hikvision authorized KW distributors** (Al-Nisf / Okaz — verify) | HikCentral footprint | Official Hikvision partner finder | OpenAPI enablement; T&A event fields without face image |
| **ZKTeco ME / BioTime product** | Vendor API license clarity | zkteco.me BioTime docs | Confirm API mod SKU for Kuwait |

Interview status: **desk research complete; live supplier interviews pending** (questionnaire in `outreach/`).

---

## 9. Wave 2B implementation plan

1. Freeze canonical punch schema + privacy deny-list tests  
2. Implement BioTime pull adapter against staging BioTime or recorded fixtures  
3. Implement on-prem agent skeleton (heartbeat, cursor, queue, mTLS)  
4. Mapping UI/API for device_user_id quarantine (synthetic only)  
5. Synthetic end-to-end: BioTime fixture → authority punches → projection  
6. Observability dashboards (lag/errors)  
7. CSV/SFTP adapter sharing contract  
8. Partner outreach results → adjust priority (IBA / Hikvision)  
9. Security review of parsers (no biometric fields)  
10. **Do not** enable real clocking or expand beyond synthetic allowlist

Exit criteria for 2B: synthetic BioTime canary PASS; privacy tests PASS; freezes green; real import still off.

---

## 10. Remaining unknowns & resolution

| Unknown | How to resolve |
|---|---|
| Exact BioTime versions dominant in Kuwait (8 vs 9.x) | Distributor SKU survey |
| Whether API license is sold by default with BioTime | Ask ZK distributors + quote API mod |
| IBA integration surface (REST vs SQL vs file) | KCS technical workshop NDA |
| Share of pure USB/CSV sites vs live BioTime | UltraTech / AIMS install base interview |
| Hikvision T&A events with/without face image by default | Lab device + OpenAPI field audit |
| Customer willingness to run Wathefni agent | Pilot offer with outbound-only agent |
| ADMS used without BioTime in KW | Ask installers; treat as secondary |

---

## Sources

See `sources/SOURCE_INDEX.md`. Key official docs:

- ZKBio Time API product + 9.0 API User Manual (transactions, token auth)  
- Hikvision 3rd-party integration / T&A integrate solution (ISAPI AcsEvent, HikCentral OpenAPI, alertStream)  
- Suprema BioStar 2 API / TA API / WebSocket / G-SDK  
- Anviz CrossChex Cloud API + webhooks  
- KCS IBA product page + company profile (vendor list)

## Non-goals confirmed

No deploy · no real clocking · no device import enablement · no QR/GPS/kiosk · no Attendance UI redesign · no frozen-module changes · no production connector code in this wave.
