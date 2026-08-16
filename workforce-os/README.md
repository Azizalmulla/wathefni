# WhatsApp Workforce OS

> By **AI Octopus** — Kuwait-first, GCC-ready

WhatsApp-native HR platform powered by OpenClaw. From job posting to compliance tracking — all through WhatsApp.

## Modules

| Module | What It Does | Status |
|---|---|---|
| **Hiring** | Job posting → QR intake → CV screening → interviews → hiring | ✅ Built |
| **Onboarding** | Post-hire doc collection → checklists → Drive upload | ✅ Built |
| **PRO/Compliance** | Document expiry tracking → renewal reminders → compliance alerts | ✅ Built |
| **Shifts** | Schedule shifts → reminders → roster questions → conflict handling | ✅ Built |
| **Attendance** | Check-in/out → late/absence tracking → attendance dashboard | ✅ Built |

## Architecture

- **Runtime:** OpenClaw Gateway (one agent per company, fully isolated)
- **Channel:** WhatsApp (one number per company)
- **Data:** Postgres is source of truth for orchestrator-backed modules; workspace JSON stores company identity/config/templates
- **Dashboard:** Google Sheets (per company)
- **Storage:** Google Drive (per company)
- **Scheduling:** OpenClaw Cron or orchestrator endpoints for compliance, onboarding, shift reminders, and attendance scans

## Multi-Company Deployment Model

Use the same shared product engine for every customer, but isolate each customer at the runtime/config layer.

- **Shared code:** hiring, onboarding, compliance, shifts, attendance, guardrails, Sheets sync, and notification logic.
- **Per-company config:** company identity, HR users, WhatsApp account, enabled modules, Sheets, Drive, compliance rules, and module settings.
- **Per-company runtime:** one OpenClaw agent/workspace per company.
- **Dedicated hosting option:** for enterprise customers, deploy the same codebase on a separate server with separate Postgres, secrets, OpenClaw config, WhatsApp account, Google account, Sheet, and Drive folder.
- **Module entitlements:** enable only the modules a company bought, such as `shifts` only for a restaurant or `onboarding,compliance` for an office.
- **Customization rule:** company-specific behavior belongs in config/templates/settings first. Only add code when the behavior should become reusable product capability.

## Quick Start

### Provision a new company

```bash
./scripts/provision-company.sh \
  --company-code "ALMULLA" \
  --company-name "Al Mulla Group" \
  --company-name-ar "مجموعة الملا" \
  --whatsapp-number "+96512345678" \
  --hr-phones "+96599001122,+96599003344" \
  --hr-names "Sara Al Rashid,Mohammed Ali" \
  --hr-emails "sara@almulla.com,mohammed@almulla.com" \
  --hr-roles "manager,admin" \
  --google-account "almulla-hr@gmail.com" \
  --modules "hiring,onboarding,compliance,shifts,attendance" \
  --country "KW" \
  --sector "General Trading"
```

### What it creates

- Workspace at `~/.openclaw/workspaces/company-almulla/`
- All workspace files (AGENTS.md, IDENTITY.md, SKILL.md, SOUL.md, TOOLS.md, etc.)
- Data directories with company.json, hr-users.json, compliance-rules.json
- Onboarding templates
- OpenClaw agent config snippet
- Cron job configs for compliance, onboarding, shifts, and attendance when enabled

### Post-provisioning

1. Create Google Sheet and Drive folder
2. Update Sheet ID and Drive folder ID in workspace files
3. Add agent to `openclaw.json`
4. Pair WhatsApp number
5. Add module rows/settings in `company_modules` for orchestrator-backed deployments
6. Add cron jobs or orchestrator scheduled jobs for enabled modules
7. Restart Gateway/orchestrator services
8. Run smoke tests for that company before live use

## Enterprise Isolation Checklist

For a customer that wants its own hosting:

1. Provision a company workspace using `scripts/provision-company.sh`.
2. Create a dedicated Postgres database and secrets file.
3. Deploy the orchestrator with that database URL and company workspace path.
4. Create a dedicated OpenClaw agent and WhatsApp account binding.
5. Create customer-owned Google Sheet and Drive folder.
6. Insert enabled module rows into `company_modules`.
7. Run module smoke tests: candidate, onboarding, compliance, shifts, attendance as applicable.
8. Keep company-specific rules in `company.json`, compliance rules, onboarding templates, and module settings.

## File Structure

```
workforce-os/
├── templates/
│   ├── workspace/          ← Workspace file templates (.tmpl)
│   ├── data/               ← Data file templates
│   │   ├── compliance-rules/
│   │   │   └── KW.json     ← Kuwait compliance rules
│   │   └── onboarding-templates/
│   │       └── default.json
│   └── cron/               ← Cron job templates
├── scripts/
│   └── provision-company.sh
├── WORKFORCE_OS_PRD.md     ← Full product requirements
└── README.md               ← This file
```

## GCC Expansion

Add compliance rules for new countries:

```
templates/data/compliance-rules/
├── KW.json   ← Kuwait (done)
├── SA.json   ← Saudi Arabia
├── AE.json   ← UAE
├── BH.json   ← Bahrain
├── QA.json   ← Qatar
└── OM.json   ← Oman
```

Same bot architecture, same provisioning script, different compliance config.
