# Wathefni Calendar — C5 Implementation (Platform Integrations + Sync)

**Date:** 2026-07-29 (Asia/Kuwait)  
**Host:** `root@76.13.63.68`  
**Stamp:** `20260729T161956Z`  
**Evidence:** `/opt/wathefni/production-evidence/wathefni-calendar-c5/20260729T161956Z/`  
**Authority:** C0 §4.9 / §7, C1–C4 implementation docs, communication-channel audit  
**Scope:** Platform-level company integrations (Google Workspace + Microsoft 365) · Calendar as first consumer · one-way Wathefni→provider · Meet/Teams creation  
**Preserves:** Waves 1–6, Calendar C1–C4, communication handoff  
**Tenants with `calendar` enabled:** **0**  
**Not in this wave:** SSO, directory, email, files, two-way sync, recurrence, resources, broad tenant launch, full OAuth consent UI

---

## Verdict

**PASS.**

Platform company connections are the credential/consent/account/health/audit authority. Calendar sync is a consumer projection (`calendar_sync_*` linked via `platform_integration_id`). Google Calendar + Meet and Outlook/Graph Calendar + Teams are implemented as one-way dry-run-safe adapters. Future capabilities are registered only. C1–C4 regressions green. Health **200**. Sync timer active with `CALENDAR_SYNC_DRY_RUN=true`.

| Suite | Result |
|---|---|
| `smoke-test-calendar-c5.py` | **62 PASS / 0 FAIL** |
| C4 / C3 / C1 | **38 / 41 / 53** PASS |
| Health after restart | **200** |
| `wathefni-calendar-sync.timer` | **active** (`CALENDAR_SYNC_DRY_RUN=true`) |
| `WATHEFNI_MAILBOX_SECRET_KEY` | Provisioned for company credential encryption |

---

## Architecture

```text
platform_company_integrations
  + credentials (Fernet ciphertext)
  + capabilities / scopes / consent / health / audit
        │
        │  attach_calendar_sync_connection()
        ▼
calendar_sync_connections.platform_integration_id
  + sync policy / outbox / bindings / privacy
        │
        ▼
get_adapter(provider_key)
  ├─ google / google_workspace  → Google Calendar + Meet (gog)
  └─ microsoft / microsoft_365  → Graph Calendar + Teams (isOnlineMeeting)
```

**Rules locked**

- Wathefni Calendar remains source of truth.
- Platform layer owns connection + credential + consent + account + health + audit.
- Calendar must not become a second credential authority for company connections.
- Reserved capabilities (`identity.sso`, `directory.read`, `email.send`, `files.readwrite`) are listed in the registry and **never granted or executed** in C5.
- Implemented capabilities only: `calendar.events`, `meetings.create`.
- Inbound provider edits/deletes remain ignored (`external_delete_policy=ignore`).
- Provider failures never mutate Wathefni event rows.
- Credentials never appear in public list payloads.

---

## Schema

Additive via `calendar_schema.ensure_calendar_schema` → `platform_integrations.ensure_schema`:

| Table | Role |
|---|---|
| `platform_company_integrations` | Company Google Workspace / Microsoft 365 connection |
| `platform_company_integration_credentials` | Encrypted refresh tokens |
| `platform_company_integration_audit` | Connect / disconnect / attach audit |
| `calendar_sync_connections.platform_integration_id` | Link from Calendar sync projection |
| `calendar_sync_*` (prior C5) | Outbox, bindings, sync audit, optional legacy local credentials |

Providers: `google_workspace`, `microsoft_365`.  
Sync provider keys remain: `google`, `microsoft` (Calendar projection).

---

## Files

| File | Role |
|---|---|
| `wathefni-orchestrator/platform_integrations.py` | Shared connection foundation |
| `wathefni-orchestrator/calendar_sync.py` | Sync projection; consumes platform credentials |
| `wathefni-orchestrator/calendar_sync_adapter.py` | Adapter factory (Google + Microsoft) |
| `wathefni-orchestrator/calendar_sync_google.py` | Google Calendar + Meet |
| `wathefni-orchestrator/calendar_sync_microsoft.py` | Graph Calendar + Teams |
| `wathefni-orchestrator/calendar_schema.py` | Ensures platform + sync schema |
| `wathefni-orchestrator/app.py` | Platform + Calendar sync APIs |
| `wathefni-orchestrator/tenant_control_integrations.py` | Catalog: M365 / Google Calendar partial |
| `apps/wathefni-dashboard/src/lib/api.ts` | Platform + sync clients |
| `apps/wathefni-dashboard/src/components/CalendarShell.tsx` | Platform connect UX + sync status |
| `ops/wathefni-calendar-sync.service` / `.timer` | Worker; dry-run default |
| `ops/WATHEFNI_CALENDAR_C5_IMPLEMENTATION.md` | This document |

---

## APIs

| Route | Purpose |
|---|---|
| `GET /dashboard/platform/integrations` | List company integrations + capability registry |
| `POST /dashboard/platform/integrations/connect` | Connect Google Workspace or Microsoft 365; optional Calendar attach |
| `POST /dashboard/platform/integrations/{id}/disconnect` | Disconnect platform + detach Calendar sync |
| `POST /dashboard/calendar/sync/connections/google` | Convenience: platform Google Workspace + Calendar attach |
| `POST /dashboard/calendar/sync/connections/microsoft` | Convenience: platform Microsoft 365 + Calendar attach |
| Existing sync list/update/disconnect/reconnect + event sync status/retry | Unchanged consumer surface |

Entitlement for this wave: `calendar` + `calendar.sync` (Calendar is the only product consumer).

---

## Proofs

| Path | Result |
|---|---|
| Platform connect Google Workspace + Microsoft 365 | PASS (encrypted refresh token; no secret in list) |
| Calendar attach via `platform_integration_id` | PASS |
| Dry-run Google create/update/cancel | PASS (same provider event id) |
| Dry-run Microsoft create/update/cancel + Teams | PASS (same id; meeting_url present) |
| Platform disconnect detaches Calendar sync | PASS |
| Reserved SSO not granted | PASS |
| No cross-tenant platform/sync leak | PASS |
| Worker dry-run default | Kept |

---

## UX

Authorized users with `calendar.sync`:

- Platform integrations panel: connect Google Workspace / Microsoft 365 (account + refresh token), list health/capabilities, disconnect platform
- Calendar sync projections: privacy toggle, disconnect/reconnect, legacy operator ensure
- Event drawer: sync status, retry, external link

Full OAuth consent UI is deferred; connect accepts an authorized refresh token from setup.

---

## Remaining (do not start here)

- Full OAuth consent / redirect UX for Workspace and M365
- Live sync enablement per tenant (selective dry-run off)
- SSO, directory, email, files capabilities
- Two-way sync / conflict UI
- Recurrence product / resources
- Broad Calendar module enablement

**Stop after this C5 platform + Calendar consumer wave.**
