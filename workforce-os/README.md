# WhatsApp Workforce OS

> By **AI Octopus** — Kuwait-first, GCC-ready

WhatsApp-native HR platform powered by OpenClaw. From job posting to compliance tracking — all through WhatsApp.

## Modules

| Module | What It Does | Status |
|---|---|---|
| **Hiring** | Job posting → QR intake → CV screening → interviews → hiring | ✅ Built |
| **Onboarding** | Post-hire doc collection → checklists → Drive upload | 🔧 Template ready |
| **PRO/Compliance** | Document expiry tracking → renewal reminders → compliance alerts | 🔧 Template ready |

## Architecture

- **Runtime:** OpenClaw Gateway (one agent per company, fully isolated)
- **Channel:** WhatsApp (one number per company)
- **Data:** File-based JSON in agent workspace
- **Dashboard:** Google Sheets (per company)
- **Storage:** Google Drive (per company)
- **Scheduling:** OpenClaw Cron (compliance checks, onboarding follow-ups)

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
  --modules "hiring,onboarding,compliance" \
  --country "KW" \
  --sector "General Trading"
```

### What it creates

- Workspace at `~/.openclaw/workspaces/company-almulla/`
- All workspace files (AGENTS.md, IDENTITY.md, SKILL.md, SOUL.md, TOOLS.md, etc.)
- Data directories with company.json, hr-users.json, compliance-rules.json
- Onboarding templates
- OpenClaw agent config snippet
- Cron job configs for compliance and onboarding

### Post-provisioning

1. Create Google Sheet and Drive folder
2. Update Sheet ID and Drive folder ID in workspace files
3. Add agent to `openclaw.json`
4. Pair WhatsApp number
5. Add cron jobs
6. Restart Gateway

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
