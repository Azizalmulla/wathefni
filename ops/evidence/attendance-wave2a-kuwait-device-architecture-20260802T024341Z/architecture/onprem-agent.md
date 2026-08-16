# On-prem agent architecture (Wave 2A)

## Goals

- Reach BioTime / HikCentral / BioStar / file drops on customer LAN without exposing them to the internet
- Outbound-only to Wathefni by default
- Never transport biometric templates or images

## Components

```
┌─────────────────────────────────────────────┐
│  Wathefni Attendance Agent (site)           │
│  ┌─────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ Pollers │ │ File     │ │ Optional     │  │
│  │ BioTime │ │ watcher  │ │ local webhook│  │
│  │ Hik*    │ │ SFTP dir │ │ terminator   │  │
│  └────┬────┘ └────┬─────┘ └──────┬───────┘  │
│       │           │              │          │
│       └───────────┴──────┬───────┘          │
│                          ▼                  │
│                 Sanitize + Map              │
│                          ▼                  │
│              Durable queue (sqlite)         │
│                          ▼                  │
│         Outbound HTTPS ingest client        │
│         (mTLS / short-lived JWT)            │
│                          ▼                  │
│              Health heartbeat               │
└─────────────────────────────────────────────┘
```

## Networking

| Direction | Required |
|---|---|
| Agent → BioTime/HikCentral/BioStar (LAN) | Yes |
| Agent → Wathefni ingest (internet/VPN) | Yes |
| Internet → Agent | No (unless signed webhook mode explicitly enabled) |
| Devices → Agent ADMS | Optional Phase 2C only |

## State

- `cursors` per poller (last transaction id / timestamp)
- `outbox` punches pending ack
- `mapping_cache` optional (authoritative map still server-side)
- `agent_id`, `company_code`, `version`

## Upgrade strategy

- Signed release artifacts; staged canary per company
- Config schema versioned; refuse unknown majors
- Capability advertisement on heartbeat

## Packaging

- systemd unit / Windows service
- Config: company, connector type, secrets ref, poll interval, deny-list version
- Logs without PII beyond employee/device ids already in HR
