# Canonical punch contract (Wave 2A)

Target ingest for all connectors. Maps 1:1 onto Wave 1 `AttendanceAuthorityService.ingest_punch`.

## Required fields

| Field | Type | Notes |
|---|---|---|
| `company_code` | string | Tenant; allowlist enforced upstream |
| `source` | string | Stable connector family: `biotime`, `hikcentral`, `hik_isapi`, `biostar`, `anviz_cloud`, `csv`, `sftp`, `iba`, `adms` |
| `source_event_id` | string | Globally unique per company+source; never reuse |
| `device_user_id` | string | Vendor employee/badge/user id on device |
| `punched_at` | RFC3339 with offset | Prefer vendor timestamp; default interpret as Asia/Kuwait if naive |
| `direction` | enum | `in` \| `out` \| `break_start` \| `break_end` \| `unknown` |

## Recommended fields

| Field | Type | Notes |
|---|---|---|
| `employee_key` | string | Resolved by mapping service; optional at adapter edge |
| `device_id` | string | Terminal SN / door id |
| `verify_method` | enum | `fingerprint` \| `face` \| `card` \| `pin` \| `mobile` \| `unknown` — type only |
| `connector_id` | string | Instance id |
| `connector_version` | string | Semver |
| `work_date_hint` | date | Optional; authority owns overnight rules |
| `raw_ref` | object | Allowlisted vendor scalars only |

## Forbidden fields (hard fail)

Any of: `fingerprint_image`, `face_image`, `template`, `biometric_template`, `picture`, `pictureURL` (binary), `photo`, `biodata`, base64 image blobs, template hex strings.

## Idempotency

Authority unique key: `(company_code, source, source_event_id)`.

Preferred ids:

- BioTime: `biotime:{transaction.id}`
- HikCentral: `hikcentral:{eventId}`
- Hik ISAPI: `hik_isapi:{deviceId}:{time}:{employeeNo}:{major}:{minor}`
- BioStar TA: `biostar:{punch_log.id}`
- Anviz: `anviz:{record_id}`
- CSV: `csv:{file_sha256}:{row_sha256}`

## Direction mapping notes

| Vendor | Mapping approach |
|---|---|
| BioTime `punch_state` | Configurable table; default 0→in, 1→out; else unknown |
| Hik `attendanceStatus` / major-minor | Map check-in/out; door-open alone → unknown |
| BioStar punch type | Native IN/OUT/BREAK_* |
| CSV | Column map per customer |

## Capability document (per connector version)

```json
{
  "connector": "biotime",
  "version": "0.1.0",
  "supports_pull": true,
  "supports_push": false,
  "supports_webhook": false,
  "event_id_stable": true,
  "direction_native": "partial",
  "offline_replay": true,
  "biometric_payload_risk": "low",
  "requires_onprem_agent": true,
  "max_recommended_poll_s": 60
}
```
