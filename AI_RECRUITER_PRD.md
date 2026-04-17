# AI Recruiter — Product Requirements Document (PRD)

> **Product:** AI Recruiter by AI Octopus
> **Version:** v2.0 (Updated — reflects actual built system)
> **Date:** February 21, 2026
> **Team:** Aziz Al Mulla + AI (Windsurf/Cascade)

---

## 1. What Is AI Recruiter?

A WhatsApp-native hiring platform for Kuwait. Companies post jobs, candidates apply by scanning a QR code and chatting with an AI on WhatsApp. The AI reads their CV, screens them, and stores everything in a searchable filesystem. HR managers query the AI in natural language — no portal, no login, no laptop needed.

**Deployed on the client's own server. Data never leaves their building.**

**One sentence:** "Scan. Send CV. Get screened. All on WhatsApp. All on your server."

---

## 2. Who Is It For?

### Primary Customers (who pays)
- **Staffing/recruitment agencies** — hire for multiple companies, high volume
- **Direct companies** — restaurants, retail, logistics, call centers, telecoms, banks
- **HR departments** — any company that hires 10+ people/year

### End Users (who interacts)
- **Candidates** — job seekers in Kuwait (mostly blue/white collar)
- **HR managers** — review candidates, shortlist, schedule interviews
- **Company admins** — manage positions, view reports, manage billing

---

## 3. How It Works

### Candidate Flow
```
1. Candidate sees QR code (on job post, career fair, social media, website)
2. Scans QR → WhatsApp opens with pre-filled message: "APPLY-COMPANYX-MARKETING"
3. AI greets candidate, confirms the role they're applying for
4. AI asks candidate to send their CV (PDF, image, or Word doc)
5. AI extracts: name, phone, email, education, experience, skills, languages, certifications
6. AI asks Kuwait-specific screening questions:
   - Visa/residency status (valid work permit? transferable?)
   - Expected salary (in KD)
   - Arabic/English fluency
   - Availability (when can you start?)
   - Role-specific questions from the job description
7. AI confirms application is complete
8. AI asks: "Would you like to be considered for similar roles at other companies?" (consent for Phase 2)
9. Candidate data saved to database under that company + position
```

### HR Manager Flow (all via WhatsApp)
```
1. HR manager is registered as an authorized user for their company
2. HR texts the AI on WhatsApp (same number, AI detects they're HR not a candidate)
3. AI responds to natural language queries:
   - "How many applied today?" → count + summary
   - "Show me Python devs" → list of matching candidates with key info
   - "Tell me about Ahmed" → full candidate profile + AI summary
   - "Shortlist Ahmed" → updates status, confirms
   - "Reject Omar" → updates status, sends polite rejection to candidate
   - "Schedule interview with Ahmed tomorrow 2pm" → sends candidate a WhatsApp message
   - "Export all candidates" → sends CSV file via WhatsApp
   - "Compare top 3 for marketing role" → side-by-side summary
4. Everything happens inside WhatsApp — no portal, no login, no laptop needed
5. AI distinguishes HR users from candidates by their registered phone number
```

### Company Admin Flow (WhatsApp + onboarding call)
```
1. AI Octopus team onboards company (call/meeting — sets up account in backend)
2. Admin texts AI to manage positions:
   - "Add new position: Marketing Manager, 800-1200 KD, full-time"
   - AI asks follow-up questions (requirements, screening questions, etc.)
   - AI generates QR code and sends it via WhatsApp
3. Admin can also text: "Show my active positions", "Close the driver role", etc.
4. QR codes sent as images — admin prints them or shares digitally
```

---

## 4. WhatsApp Strategy

### Standard Tier
- **One shared AI Octopus WhatsApp Business number**
- All companies share this number
- Routing by QR code prefix: `wa.me/965XXXXXXXX?text=APPLY-{COMPANY_CODE}-{POSITION_CODE}`
- Candidate experience feels personalized (AI mentions company name and role)
- WhatsApp profile: "AI Recruiter by AI Octopus"

### Premium Tier (build later, sell when demanded)
- **Dedicated WhatsApp Business number per company**
- Company's own branding on WhatsApp profile
- Still runs on AI Octopus infrastructure
- Higher price point

### WhatsApp Cloud API
- Use Meta's official WhatsApp Cloud API (not personal WhatsApp linking)
- Free tier: 1,000 service conversations/month
- Business tier: ~$0.02-0.05 per conversation after free tier
- Requires Meta Business verification (one-time for AI Octopus)
- Supports: text, images, documents, buttons, list messages, templates

---

## 5. Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| **AI Agent Platform** | OpenClaw | Local-first, open-source, WhatsApp-native, filesystem tools built-in |
| **LLM** | Claude Sonnet 4.6 (Anthropic) | Best Arabic + English, strong instruction following |
| **WhatsApp (dev/demo)** | OpenClaw personal WhatsApp plugin | Works now, no Meta approval needed |
| **WhatsApp (production)** | Meta WhatsApp Business Cloud API | Official, scalable — same OpenClaw agent, swap connection |
| **Storage** | Filesystem (JSON files) | Source of truth — simple, auditable, no DB to manage |
| **HR Dashboard** | Google Sheets (via gog) | HR already knows how to use it, real-time, shareable |
| **CV Storage** | Google Drive (via gog) | Organized per candidate, shareable links |
| **Calendar / Email** | Google Calendar + Gmail (via gog) | Interview scheduling, candidate emails |
| **CV Parsing** | nano-pdf (OpenClaw skill) | Reads PDF CVs directly in the agent |
| **Auth** | hr-users.json (phone number allowlist) | HR users identified by registered phone number |
| **Deployment** | On-prem on client's server | Data sovereignty, works for banks/government |
| **Remote Management** | Tailscale | Secure remote access, no public ports |

### Google Auth Strategy (Now vs Enterprise)
- **Now (testing):** Use Google OAuth via `gog` with the founder/admin account for Drive, Sheets, Gmail, and Calendar.
- **Known limitation:** OAuth can occasionally require re-consent, which is acceptable for internal testing but not ideal for unattended enterprise operations.
- **Enterprise target (first private client onward):** Migrate to **Google Workspace + Service Account + Domain-Wide Delegation (DWD)** for non-interactive auth.

#### Enterprise Cutover Checklist
1. Confirm client has Google Workspace admin access and a dedicated recruiter mailbox (e.g., `recruiter-bot@company.com`).
2. Create a service account in the client's GCP project.
3. Enable Domain-Wide Delegation and grant only required scopes (Drive, Sheets, Gmail, Calendar).
4. Store service account credentials securely on the client server (no personal OAuth dependency).
5. Run smoke tests: CV upload to Drive, Sheet append/update, Gmail send/read, Calendar event creation.
6. Disable personal OAuth for that production tenant after successful validation.

**Decision rule:** Any production tenant requiring 24/7 reliability should use service-account mode.

---

## 6. Data Storage (Filesystem)

No database. Everything is JSON files on the client's server.

```
workspace/data/
├── companies/
│   └── {COMPANY_CODE}/
│       ├── company.json          ← name, sector, contact
│       ├── hr-users.json         ← allowlisted HR phone numbers
│       └── positions/
│           └── {POSITION_CODE}.json  ← title, requirements, screening questions, salary
└── candidates/
    └── {PHONE}/
        ├── profile.json          ← name, email, education, experience, skills, languages,
        │                            nationality, visa, salary, ai_summary, cv_drive_url
        ├── cv.txt                ← raw extracted CV text
        └── applications/
            ├── {COMPANY}-{POSITION}.json  ← status, applied_at, screening_answers, notes
            └── assessments/
                └── {COMPANY}-{POSITION}.json  ← cognitive%, SJT%, skills%, overall%, passed
```

### Google Sheet (HR Dashboard)
One sheet per company. Columns A–R:
`A=Name, B=Phone, C=Email, D=Skills, E=Exp Years, F=Education, G=Visa, H=Salary KD, I=Availability, J=Languages, K=Status, L=Applied Date, M=AI Summary, N=Notes, O=Cognitive%, P=SJT%, Q=Skills%, R=Overall%`

### Phase 2 — Network Layer
```
data/network/
└── {PHONE}/
    ├── anonymous_profile.json    ← skills, exp, salary — no PII
    └── consent.json              ← opted-in sectors, expiry date
```

---

## 7. How the Agent Works

No API endpoints — OpenClaw handles all routing and logic via IDENTITY.md.

| Trigger | Action |
|---------|--------|
| Candidate sends `APPLY-{COMPANY}-{POSITION}` | Agent starts candidate flow |
| Candidate sends PDF | nano-pdf reads it, agent extracts structured data |
| Candidate sends voice note | Agent transcribes + extracts |
| Candidate completes screening | Writes profile.json + application JSON, appends to Google Sheet, uploads CV to Drive |
| HR sends natural language query | Agent reads filesystem, returns results |
| HR says "shortlist Ahmed" | Updates application JSON + Google Sheet status |
| HR says "schedule interview" | Sends Gmail invite + Google Calendar event with Meet link + WhatsApp to candidate |
| HR says "run assessment" | Sends questions one-by-one, scores, saves results, updates Sheet columns O-R |
| Cron job (every 30min) | Checks Gmail for candidate replies to interview invites |

---

## 8. AI / LLM Usage

**Model:** Claude Sonnet 4.6 (Anthropic) — single model for everything.

| Task | How |
|------|-----|
| CV parsing | Agent reads PDF via nano-pdf, extracts structured JSON |
| Candidate screening | Conversational — questions one at a time, Arabic + English |
| HR natural language queries | Agent reads filesystem, interprets query, returns results |
| Assessment scoring | Sends questions, scores per rubric, saves results |
| AI summary | 2-3 sentence candidate summary saved to profile.json |

### Estimated LLM Cost Per Candidate
```
CV parsing + screening:  ~$0.05-0.10
HR queries (avg 5/mo):   ~$0.05
──────────────────────────────────
Total:                   ~$0.10-0.15 per candidate
At 100 candidates/month: ~$10-15/month in LLM costs
```

---

## 9. Pricing Model

| Component | Price |
|-----------|-------|
| Setup (deploy on-prem, configure, customize) | $3,000 – $8,000 one-time |
| Monthly managed service | $1,500 – $4,000/mo |
| Per-hire placement fee (optional) | $500 – $1,000 per hire |

### By Segment
| Segment | Setup | Monthly |
|---------|-------|---------|
| HR/staffing agencies | $3K | $2-3K/mo |
| Large corporates | $5K | $3-5K/mo |
| Banks & telecoms | $8K | $4-8K/mo |
| Government | $10-15K | $3-5K/mo |
| Universities | $3K | $1.5-2K/mo |

---

## 10. Security & Privacy

### Data Protection
- **On-prem** — candidate data lives on the client's own server, never on AI Octopus infrastructure
- **RBAC** — HR users identified by phone number (hr-users.json). Candidates cannot access HR functions.
- **Prompt injection protection** — IDENTITY.md has strict rules preventing identity spoofing, system prompt disclosure, and file manipulation
- **No raw errors exposed** — agent never shows internal errors or file paths to users

### Candidate Consent
- Agent identifies itself as an AI at the start of every conversation
- CV data shared only with the company they applied to
- Network opt-in (Phase 2) always optional and explicitly asked
- Phase 2 requires legal review before implementation

### Remote Management
- AI Octopus accesses client servers via Tailscale only — no public ports, no SSH exposed to internet

---

## 11. What's Built (Current State)

### Done ✅
- [x] WhatsApp integration (personal number via OpenClaw plugin)
- [x] QR code routing via APPLY-{COMPANY}-{POSITION} codes
- [x] CV upload via WhatsApp (PDF → nano-pdf, voice → transcribe, text → extract)
- [x] AI CV parsing — extracts name, email, education, experience, skills, languages, certifications
- [x] AI screening conversation (role-specific questions)
- [x] Candidate filesystem database (JSON files)
- [x] Google Drive CV upload (automatic, silent)
- [x] Google Sheets HR dashboard (auto-populated on application)
- [x] HR natural language queries via WhatsApp
- [x] Status management (shortlist, reject, hire)
- [x] Interview scheduling (Gmail + Google Calendar with Meet link + WhatsApp to candidate)
- [x] Email monitoring cron job (checks candidate replies every 30min)
- [x] Skills assessment system (cognitive, SJT, skills — scored and saved)
- [x] Arabic (Kuwaiti dialect) + English support
- [x] RBAC — candidate vs HR routing by phone number
- [x] Security hardening — prompt injection, identity spoofing, system prompt protection
- [x] On-prem deployment model

### Next (Phase 2)
- [ ] Candidate network opt-in question at end of screening
- [ ] Anonymous profile storage in data/network/
- [ ] Cross-company candidate search for HR
- [ ] Legal review for network data sharing
- [ ] Switch to WhatsApp Business Cloud API (production)
- [ ] Web dashboard (only if clients request it)

---

## 12. Project Structure (Actual)

```
~/.openclaw/
├── openclaw.json                        ← global config (model: claude-sonnet-4-6, bootstrapMaxChars: 50000)
├── agents/
│   └── recruiter/
│       └── agent/
│           └── models.json              ← agent model config
└── workspaces/
    └── recruiter/
        ├── IDENTITY.md                  ← agent brain — all rules, flows, security
        ├── data/
        │   ├── companies/
        │   │   └── {CODE}/
        │   │       ├── company.json
        │   │       ├── hr-users.json
        │   │       └── positions/
        │   └── candidates/
        │       └── {PHONE}/
        │           ├── profile.json
        │           ├── cv.txt
        │           └── applications/
        └── scripts/
            └── generate_cv.py           ← generates PDF CV from profile.json
```

**To onboard a new company:** copy template, customize `company.json`, `hr-users.json`, and positions. ~30 minutes per client.

---

## 13. Roadmap

### Phase 1 — Done ✅ (Private AI Recruiter)
Core product is built and working. See Section 11 for full feature list.

### Phase 2 — Next (Candidate Network Bridge)
1. Add opt-in question at end of candidate screening flow
2. Store `network_opt_in` + consent in profile.json
3. Create `data/network/` folder with anonymous profiles
4. Add HR command: "search network for Python devs"
5. Build contact-request flow (company requests → candidate approves via WhatsApp)
6. Legal review for cross-company data sharing
7. Switch WhatsApp connection to Business Cloud API for production
8. For first enterprise client, migrate Google integrations from OAuth to Workspace service-account (DWD) mode

### Phase 3 — Future (Optional)
- Web dashboard (only if multiple clients request it)
- Video interview integration
- ATS system integrations
- Reference checking automation

---

## 14. Go-To-Market (Kuwait)

### First 3 Clients (warm leads)
1. **Dad's company** — built-in relationship, proves the product
2. **Staffing agency referral** — ask Rawan/Ahmad for intros
3. **Restaurant chain or retail** — high volume, low-tech HR, obvious pain point

### Sales Pitch (30 seconds)
> "Your candidates scan a QR code on the job post, send their CV on WhatsApp, and our AI screens them instantly. You log in to a dashboard and see ranked candidates ready for interview. No more reading 200 CVs manually."

### Marketing Channels
- **WhatsApp broadcast** (ironic but effective in Kuwait)
- **Instagram/LinkedIn** — demo videos showing the QR → screening flow
- **Career fairs** — set up a booth with QR codes, let people experience it live
- **HR managers WhatsApp groups** (very common in Kuwait)

---

## 15. Success Metrics

| Metric | Target (Month 1) | Target (Month 6) |
|--------|------------------|-------------------|
| Companies onboarded | 3 | 15 |
| Candidates screened | 100 | 2,000 |
| Avg time-to-shortlist | < 24 hours | < 4 hours |
| HR satisfaction | "Would recommend" | NPS > 50 |
| Monthly revenue | $1,500 | $10,000 |
| LLM cost per candidate | < $0.15 | < $0.08 (optimize) |

---

*This document is the blueprint. Everything we build follows this plan.*
