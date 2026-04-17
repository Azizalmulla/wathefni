# WhatsApp Workforce OS — Product Requirements Document

> **By AI Octopus** | Kuwait-first, GCC-ready
> WhatsApp-native HR platform: from job posting to compliance tracking

---

## 1. Product Vision

**One WhatsApp number per company. One AI assistant that handles everything from hiring to compliance.**

Companies in Kuwait and the GCC deal with:
- Hiring (job posts, screening, interviews) — occasional
- Onboarding (document collection, checklists) — per hire
- PRO/Compliance (residency renewals, civil ID expiry, work permits) — **every single day**

We combine all three into a single WhatsApp-native platform that companies interact with the same way they chat with a colleague.

### Positioning

```
WhatsApp Workforce OS
├── Module 1: Hiring          ← demos well, gets clients in the door
├── Module 2: Onboarding      ← natural extension after hire
└── Module 3: PRO/Compliance  ← recurring pain = recurring revenue
```

### Selling Model

- **Not a rigid SaaS** — we acquire a company and build what they need
- **Modular** — companies can buy any combination of modules
- **Private** — each company gets their own WhatsApp number, their own AI agent, their own isolated data
- **Per-company customization** — when we onboard a client, we configure their specific workflows, documents, compliance rules, and screening questions

---

## 2. Architecture

### Core Stack

| Layer | Technology |
|---|---|
| **Agent Runtime** | OpenClaw Gateway (self-hosted) |
| **AI Model** | Anthropic Claude Sonnet 4.6 (configurable per company) |
| **Chat Channel** | WhatsApp via Baileys (one number per company) |
| **Data Storage** | File-based JSON in agent workspace |
| **HR Dashboard** | Google Sheets (one sheet per company) |
| **Document Storage** | Google Drive (one folder per company) |
| **Calendar** | Google Calendar + Meet |
| **Email** | Gmail via `gog` CLI |
| **Scheduling** | OpenClaw Cron (compliance checks, reminders) |
| **Memory** | OpenClaw vector memory (OpenAI embeddings, hybrid search) |

### Multi-Tenant Isolation

Each company is a fully isolated OpenClaw agent:

```
~/.openclaw/
├── openclaw.json                          ← master config (all agents + bindings)
├── workspaces/
│   ├── company-almulla/                   ← Al Mulla Group workspace
│   │   ├── AGENTS.md
│   │   ├── IDENTITY.md
│   │   ├── SKILL.md
│   │   ├── SOUL.md
│   │   ├── TOOLS.md
│   │   ├── USER.md
│   │   ├── MEMORY.md
│   │   ├── HEARTBEAT.md
│   │   ├── data/
│   │   │   ├── companies/ALMULLA/
│   │   │   ├── candidates/
│   │   │   └── employees/                 ← Module 2+3
│   │   └── memory/
│   ├── company-zain/                      ← Zain Kuwait workspace
│   │   └── ... (same structure)
│   └── company-aioctopus/                 ← AI Octopus (demo/internal)
│       └── ... (current recruiter)
├── agents/
│   ├── almulla-hr/                        ← agent state + sessions
│   ├── zain-hr/
│   └── aioctopus-hr/
```

**Isolation guarantees:**
- Separate WhatsApp number per company
- Separate workspace (files, data, memory)
- Separate session store (conversation history)
- Separate Google Sheet, Drive folder, Calendar
- No data leakage between companies — enforced by OpenClaw agent boundaries

### Agent Binding (in openclaw.json)

```json
{
  "agents": {
    "list": [
      {
        "id": "almulla-hr",
        "name": "Al Mulla HR",
        "workspace": "~/.openclaw/workspaces/company-almulla",
        "model": { "primary": "anthropic/claude-sonnet-4-6" }
      },
      {
        "id": "zain-hr",
        "name": "Zain HR",
        "workspace": "~/.openclaw/workspaces/company-zain",
        "model": { "primary": "anthropic/claude-sonnet-4-6" }
      }
    ]
  },
  "bindings": [
    {
      "match": { "channel": "whatsapp", "accountId": "almulla-wa" },
      "agentId": "almulla-hr"
    },
    {
      "match": { "channel": "whatsapp", "accountId": "zain-wa" },
      "agentId": "zain-hr"
    }
  ]
}
```

---

## 3. Module 1: Hiring (Pre-Hire)

> **Status: BUILT** — live and working in current AI Octopus recruiter

### Capabilities

| Feature | Description |
|---|---|
| **Job Creation** | HR creates positions via WhatsApp chat |
| **QR Code Intake** | Auto-generated QR codes + apply links for each position |
| **CV Collection** | PDF, image, voice note, or typed text — extracted + structured |
| **Screening** | Position-specific + Kuwait default questions, prefilled from CV |
| **Interview Scheduling** | Google Calendar + Meet link + WhatsApp notification + email invite |
| **HR Dashboard** | Google Sheets with all candidates, statuses, scores |
| **Assessment** | Cognitive, SJT, Skills assessments — HR-triggered, scored, synced |
| **Candidate Management** | Search, filter, rank, shortlist, reject, offer, hire |
| **Bulk Messaging** | Broadcast to filtered candidate groups with HR approval |
| **CV Export** | Generate PDF from candidate profile |
| **Email Monitoring** | Check for candidate replies to interview invites |

### Candidate Flow

```
QR Scan / Apply Link
    ↓
APPLY-{COMPANY}-{POSITION}
    ↓
Greet → Ask for CV
    ↓
Extract CV → Write files → Upload to Drive
    ↓
Gate: Drive upload OK?
    ↓
Screening Questions (prefilled from CV where possible)
    ↓
Save to JSON + Google Sheet
    ↓
"Application complete! Good luck! 🤞"
```

### HR Flow

```
WhatsApp message from HR phone
    ↓
Route check: phone in hr-users.json?
    ↓
Intent classification → Execute
    ↓
Search / Filter / Shortlist / Reject / Interview / Hire / Assess
    ↓
Sync: JSON files + Google Sheet
```

### Data Model (Existing)

```
data/
├── companies/{COMPANY_CODE}/
│   ├── company.json
│   ├── hr-users.json
│   ├── positions/{POSITION_CODE}.json
│   └── sync-queue/{APP_KEY}.json
├── candidates/{PHONE}/
│   ├── profile.json
│   ├── cv.txt
│   ├── applications/{COMPANY}-{POSITION}.json
│   └── assessments/{COMPANY}-{POSITION}.json
```

---

## 4. Module 2: Onboarding (Post-Hire)

> **Status: TO BUILD**

### Trigger

When HR says **"hire Ahmed"** or **"onboard Ahmed"**:
1. Application status changes to `hired`
2. Candidate record transitions to employee record
3. Bot immediately starts onboarding flow with the new employee via WhatsApp

### Capabilities

| Feature | Description |
|---|---|
| **Hire Transition** | Candidate → Employee with one HR command |
| **Document Collection** | Request passport, civil ID, photos, bank details, medical via WhatsApp |
| **Onboarding Checklist** | Per-position template with tracked completion |
| **Document Verification** | Basic checks (expiry date, photo quality) |
| **Drive Upload** | All docs uploaded to company's Drive folder |
| **Reminder Sequences** | Auto-remind employee for missing documents |
| **HR Dashboard Update** | Onboarding status tracked in Google Sheet |
| **Completion Notification** | HR notified when onboarding is complete |

### Onboarding Flow

```
HR: "Hire Ahmed for PYDEV"
    ↓
Update application status → hired
Create employee record
    ↓
Bot → Ahmed (WhatsApp):
  "Congratulations! 🎉 Welcome to {Company}!
   To complete your onboarding, I'll need a few documents.
   Let's start — please send a photo of your Civil ID (front and back)."
    ↓
Collect documents one by one:
  1. Civil ID (front + back)
  2. Passport (photo page)
  3. Personal photo
  4. Bank account details (IBAN)
  5. Medical fitness certificate (if required)
  6. Educational certificates (if required)
    ↓
Each doc: receive → upload to Drive → mark complete → next
    ↓
Missing docs: auto-remind after 24h, 48h, 72h
    ↓
All complete → notify HR
  "Ahmed's onboarding is complete! ✅ All documents collected."
```

### Onboarding Data Model

```
data/
├── companies/{COMPANY_CODE}/
│   ├── employees/{PHONE}/
│   │   ├── employee.json              ← core employee record
│   │   ├── onboarding.json            ← checklist + completion state
│   │   └── documents/
│   │       ├── civil-id.json          ← metadata: number, expiry, file_url, status
│   │       ├── passport.json          ← metadata: number, expiry, nationality, file_url
│   │       ├── photo.json             ← metadata: file_url, status
│   │       ├── bank.json              ← metadata: bank_name, iban, status
│   │       └── medical.json           ← metadata: date, result, file_url, status
│   └── onboarding-templates/
│       ├── default.json               ← default onboarding checklist
│       └── {POSITION_CODE}.json       ← position-specific overrides
```

### employee.json Schema

```json
{
  "phone": "+96597485758",
  "name": "Ahmed Ali",
  "email": "ahmed@example.com",
  "company_code": "AIOCTOPUS",
  "position_code": "PYDEV",
  "position_title": "Python Developer",
  "department": "",
  "hired_date": "2026-04-06",
  "start_date": "",
  "status": "onboarding",
  "source_application": "+96597485758-AIOCTOPUS-PYDEV",
  "onboarding_complete": false,
  "profile_data": { },
  "notes": ""
}
```

### onboarding.json Schema

```json
{
  "template": "default",
  "started_at": "2026-04-06",
  "completed_at": null,
  "status": "in_progress",
  "items": [
    {
      "id": "civil_id",
      "label": "Civil ID (front + back)",
      "label_ar": "البطاقة المدنية (أمام وخلف)",
      "type": "document",
      "required": true,
      "status": "pending",
      "collected_at": null,
      "file_url": null,
      "reminder_count": 0,
      "last_reminder_at": null
    },
    {
      "id": "passport",
      "label": "Passport (photo page)",
      "label_ar": "جواز السفر (صفحة الصورة)",
      "type": "document",
      "required": true,
      "status": "pending"
    },
    {
      "id": "personal_photo",
      "label": "Personal photo",
      "label_ar": "صورة شخصية",
      "type": "photo",
      "required": true,
      "status": "pending"
    },
    {
      "id": "bank_details",
      "label": "Bank account (IBAN)",
      "label_ar": "حساب البنك (IBAN)",
      "type": "text",
      "required": true,
      "status": "pending"
    },
    {
      "id": "medical",
      "label": "Medical fitness certificate",
      "label_ar": "شهادة اللياقة الطبية",
      "type": "document",
      "required": false,
      "status": "pending"
    }
  ]
}
```

---

## 5. Module 3: PRO / Compliance Operations

> **Status: TO BUILD**

### What Is PRO?

PRO (Public Relations Officer) in Kuwait/GCC handles all government-facing employee paperwork: residency permits, work permits, civil ID renewals, medical certificates, PACI appointments, MOI visits. Every company with expat employees needs this — and it's almost always tracked in messy spreadsheets.

### Capabilities

| Feature | Description |
|---|---|
| **Document Expiry Tracking** | Civil ID, residency, work permit, passport, medical — with expiry dates |
| **Escalating Reminders** | 90d → 60d → 30d → 15d → 7d → overdue alerts to HR |
| **Employee Doc Requests** | Auto-ask employees for renewal documents via WhatsApp |
| **Appointment Scheduling** | PACI, MOI, medical — create calendar events + remind |
| **Missing Docs Chasing** | Auto-follow-up with employees for missing paperwork |
| **Compliance Dashboard** | Google Sheet tab with all employees + document statuses + expiry dates |
| **Status Collection** | Ask employees for renewal updates ("Did you get your new residency?") |
| **Offboarding** | Collect company property, final docs, close employee record |
| **Bulk Compliance Report** | "Show me all expiring documents this month" |

### Compliance Flow

```
Daily Cron Job (OpenClaw Cron, 8:00 AM)
    ↓
Read all employees/{PHONE}/documents/*.json
    ↓
Check expiry dates against compliance rules
    ↓
For each expiring document:
  - 90 days: log only (internal tracking)
  - 60 days: notify HR via WhatsApp
  - 30 days: notify HR + request docs from employee
  - 15 days: escalate to HR with urgency
  - 7 days:  URGENT alert to HR
  - Overdue: CRITICAL alert to HR daily until resolved
    ↓
Track reminder history in compliance.json
```

### HR PRO Commands

```
"Show expiring documents"        → List all docs expiring in next 30/60/90 days
"Who needs renewal?"             → Filter employees with upcoming expirations
"Ahmed's residency renewed"      → Update document with new expiry date
"Schedule PACI for Ahmed"        → Create calendar event + notify Ahmed
"Request civil ID from Ahmed"    → Ask Ahmed via WhatsApp to send updated civil ID
"Offboard Ahmed"                 → Start offboarding checklist
"Compliance report"              → Full report of all employee document statuses
"Add employee"                   → Manually add an employee (not from hiring flow)
```

### Compliance Data Model

```
data/
├── companies/{COMPANY_CODE}/
│   ├── employees/{PHONE}/
│   │   ├── documents/
│   │   │   ├── civil-id.json
│   │   │   │   {
│   │   │   │     "type": "civil_id",
│   │   │   │     "number": "123456789012",
│   │   │   │     "issue_date": "2024-01-15",
│   │   │   │     "expiry_date": "2029-01-15",
│   │   │   │     "file_url": "https://drive.google.com/...",
│   │   │   │     "file_drive_id": "1abc...",
│   │   │   │     "status": "valid",
│   │   │   │     "last_verified": "2026-04-01",
│   │   │   │     "renewal_status": null,
│   │   │   │     "notes": ""
│   │   │   │   }
│   │   │   │
│   │   │   ├── residency.json
│   │   │   │   {
│   │   │   │     "type": "residency",
│   │   │   │     "permit_number": "26/123456",
│   │   │   │     "article": "18",
│   │   │   │     "sponsor": "Al Mulla Group",
│   │   │   │     "issue_date": "2025-06-01",
│   │   │   │     "expiry_date": "2026-06-01",
│   │   │   │     "file_url": null,
│   │   │   │     "status": "valid",
│   │   │   │     "renewal_status": null,
│   │   │   │     "fine_per_day_kd": 2,
│   │   │   │     "notes": ""
│   │   │   │   }
│   │   │   │
│   │   │   ├── work-permit.json
│   │   │   ├── passport.json
│   │   │   └── medical.json
│   │   │
│   │   └── compliance.json
│   │       {
│   │         "last_checked": "2026-04-06",
│   │         "overall_status": "compliant",
│   │         "reminders_sent": [
│   │           {
│   │             "document": "residency",
│   │             "type": "hr_notify",
│   │             "sent_at": "2026-04-01",
│   │             "days_until_expiry": 61
│   │           }
│   │         ],
│   │         "pending_actions": [],
│   │         "offboarding": null
│   │       }
│   │
│   └── compliance-rules.json
│       {
│         "country": "KW",
│         "reminder_windows_days": [90, 60, 30, 15, 7],
│         "document_types": {
│           "civil_id": {
│             "label": "Civil ID",
│             "label_ar": "البطاقة المدنية",
│             "typical_validity_years": 5,
│             "renewal_lead_days": 30,
│             "authority": "PACI",
│             "required": true
│           },
│           "residency": {
│             "label": "Residency Permit",
│             "label_ar": "الإقامة",
│             "typical_validity_years": 1,
│             "renewal_lead_days": 60,
│             "authority": "MOI",
│             "fine_per_day_kd": 2,
│             "required": true
│           },
│           "work_permit": {
│             "label": "Work Permit",
│             "label_ar": "إذن العمل",
│             "typical_validity_years": 1,
│             "renewal_lead_days": 30,
│             "authority": "MOSAL / PAM",
│             "required": true
│           },
│           "passport": {
│             "label": "Passport",
│             "label_ar": "جواز السفر",
│             "typical_validity_years": 5,
│             "renewal_lead_days": 90,
│             "authority": "Embassy / Home country",
│             "required": true
│           },
│           "medical": {
│             "label": "Medical Certificate",
│             "label_ar": "شهادة اللياقة الطبية",
│             "typical_validity_years": 2,
│             "renewal_lead_days": 30,
│             "authority": "MOH",
│             "required": true
│           }
│         },
│         "escalation_rules": {
│           "90": "log_only",
│           "60": "notify_hr",
│           "30": "notify_hr_and_employee",
│           "15": "urgent_hr",
│           "7": "critical_hr",
│           "0": "overdue_daily"
│         }
│       }
```

---

## 6. Google Sheets Dashboard (Per Company)

Each company gets a Google Sheet with tabs for each module:

### Tab 1: Candidates (Module 1 — Hiring)
| Name | Phone | Email | Skills | Exp | Education | Visa | Salary KD | Availability | Languages | Status | Applied | AI Summary | Notes | Cognitive% | SJT% | Skills% | Overall% | App Key |

### Tab 2: Employees (Module 2+3 — Onboarding + Compliance)
| Name | Phone | Email | Position | Department | Hired Date | Start Date | Onboarding Status | Civil ID Expiry | Residency Expiry | Work Permit Expiry | Passport Expiry | Medical Expiry | Compliance Status | Notes |

### Tab 3: Compliance Alerts (Module 3)
| Employee | Document | Expiry Date | Days Left | Status | Last Reminder | Action Required |

---

## 7. Provisioning — New Company Setup

When we acquire a new company client:

### What the Provisioning Script Does

```bash
./provision-company.sh \
  --company-code "ALMULLA" \
  --company-name "Al Mulla Group" \
  --company-name-ar "مجموعة الملا" \
  --whatsapp-number "+96512345678" \
  --hr-phones "+96599001122,+96599003344" \
  --hr-names "Sara Al Rashid,Mohammed Ali" \
  --google-account "almulla-hr@gmail.com" \
  --modules "hiring,onboarding,compliance" \
  --country "KW"
```

### What It Creates

1. **Workspace** at `~/.openclaw/workspaces/company-almulla/`
   - `AGENTS.md` — generated from template
   - `IDENTITY.md` — generated with company-specific routing, scope, and module flows
   - `SKILL.md` — generated with enabled module behaviors
   - `SOUL.md` — generated with company name and vibe
   - `TOOLS.md` — generated with company-specific paths, sheet IDs, drive folders
   - `USER.md` — generated with primary HR contact info
   - `HEARTBEAT.md` — generated with compliance check schedule (if Module 3 enabled)
   - `MEMORY.md` — initialized with company setup notes
   - `data/companies/{CODE}/company.json`
   - `data/companies/{CODE}/hr-users.json`
   - `data/companies/{CODE}/compliance-rules.json` (if Module 3)
   - `data/companies/{CODE}/onboarding-templates/default.json` (if Module 2)

2. **Google Sheet** — created via `gog` with appropriate tabs for enabled modules

3. **Google Drive folder** — created for company document storage

4. **OpenClaw config update** — adds agent + binding to `openclaw.json`

5. **WhatsApp pairing** — triggers QR pairing for the new number

6. **Cron jobs** — if Module 3, creates daily compliance check cron job

---

## 8. Cron Jobs (Automated Background Tasks)

### Daily Compliance Check (Module 3)

```json
{
  "name": "compliance-check-almulla",
  "schedule": { "kind": "cron", "expr": "0 8 * * *", "tz": "Asia/Kuwait" },
  "sessionTarget": "isolated",
  "agentId": "almulla-hr",
  "payload": {
    "kind": "agentTurn",
    "message": "Run daily compliance check. Read all employee documents, check expiry dates against compliance-rules.json, send reminders per escalation rules. Report summary to HR.",
    "lightContext": false
  },
  "delivery": {
    "mode": "announce",
    "channel": "whatsapp",
    "to": "+96599001122"
  }
}
```

### Onboarding Follow-Up (Module 2)

```json
{
  "name": "onboarding-followup-almulla",
  "schedule": { "kind": "cron", "expr": "0 10 * * *", "tz": "Asia/Kuwait" },
  "sessionTarget": "isolated",
  "agentId": "almulla-hr",
  "payload": {
    "kind": "agentTurn",
    "message": "Check all employees with onboarding status 'in_progress'. For any missing documents not reminded in 24h, send a WhatsApp reminder to the employee. Report summary to HR."
  },
  "delivery": {
    "mode": "announce",
    "channel": "whatsapp",
    "to": "+96599001122"
  }
}
```

---

## 9. Pricing Model (Suggested)

| Tier | Modules | Monthly (KD) | Notes |
|---|---|---|---|
| **Starter** | Hiring only | 50-100 | Job posting + screening + interviews |
| **Growth** | Hiring + Onboarding | 100-200 | + post-hire doc collection |
| **Enterprise** | Full Workforce OS | 200-500 | + PRO compliance tracking |

Add-ons:
- Per additional WhatsApp number: 20-30 KD/mo
- Per additional HR user beyond 3: 10 KD/mo
- Assessment module: 30 KD/mo
- Custom integrations: project-based

**But remember:** we're not selling rigid packages. We customize per client. These are guidelines, not walls.

---

## 10. GCC Expansion Path

Same platform, different compliance config per country:

| Country | Key Documents | Authorities | Config File |
|---|---|---|---|
| **Kuwait** | Civil ID, Residency (Art 18/20), Work Permit | PACI, MOI, MOSAL/PAM, MOH | `KW.json` |
| **Saudi** | Iqama, GOSI, National Address | Muqeem, Qiwa, MOL, GOSI | `SA.json` |
| **UAE** | Emirates ID, Labour Card, Visa | MOHRE, ICP, EHS | `AE.json` |
| **Bahrain** | CPR, Work Permit | LMRA, NPRA | `BH.json` |
| **Qatar** | QID, Work Permit | MOI, MADLSA | `QA.json` |
| **Oman** | Resident Card, Labour Clearance | ROP, MOL | `OM.json` |

When we expand to a new country:
1. Create compliance rules JSON for that country
2. Template workspace generates correct document types + authorities
3. Same bot architecture, same provisioning script, different config

---

## 11. Implementation Phases

### Phase 1: Template System (NOW)
- Extract current recruiter workspace into reusable template
- Parameterize all company-specific values
- Build provisioning script
- Test by re-provisioning AI Octopus from template

### Phase 2: Module 2 — Onboarding
- Hire transition flow (candidate → employee)
- Document collection via WhatsApp
- Onboarding checklist tracking
- Drive upload for employee docs
- Google Sheet "Employees" tab
- Reminder sequences for missing docs

### Phase 3: Module 3 — PRO/Compliance
- Document expiry tracking data model
- Daily compliance cron job
- Escalating reminder system
- HR PRO commands (expiring docs, renewal updates, PACI scheduling)
- Google Sheet "Compliance Alerts" tab
- Employee doc request flow via WhatsApp

### Phase 4: Multi-Company Operations
- Provisioning script hardened + tested
- WhatsApp multi-account pairing flow
- Company management commands
- Monitoring + health checks across agents

---

## 12. File Map (Template → Per-Company)

```
/Users/azizalmulla/Desktop/claw/workforce-os/
├── templates/
│   ├── workspace/
│   │   ├── AGENTS.md.tmpl
│   │   ├── IDENTITY.md.tmpl
│   │   ├── SKILL.md.tmpl
│   │   ├── SOUL.md.tmpl
│   │   ├── TOOLS.md.tmpl
│   │   ├── USER.md.tmpl
│   │   ├── HEARTBEAT.md.tmpl
│   │   └── MEMORY.md.tmpl
│   ├── data/
│   │   ├── company.json.tmpl
│   │   ├── hr-users.json.tmpl
│   │   ├── compliance-rules/
│   │   │   ├── KW.json
│   │   │   ├── SA.json
│   │   │   └── AE.json
│   │   └── onboarding-templates/
│   │       └── default.json
│   └── cron/
│       ├── compliance-check.json.tmpl
│       └── onboarding-followup.json.tmpl
├── scripts/
│   ├── provision-company.sh
│   ├── deprovision-company.sh
│   └── update-company.sh
├── WORKFORCE_OS_PRD.md                    ← this file
└── README.md
```
