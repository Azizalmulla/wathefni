# Kuwait AI Recruiter — Go-To-Market Strategy

> **Updated:** February 21, 2026
> **Product:** AI Recruiter (lead product). On-prem deployment per client.

---

## Company Structure

### Recommended: WLL (Limited Liability Company)

| Aspect | Details |
|--------|---------|
| **Structure** | شركة ذات مسؤولية محدودة |
| **Ownership** | 51% Kuwaiti partner / 49% you |
| **Minimum Capital** | 1,000 KWD |
| **Timeline** | ~3 months |
| **Tax (2026)** | 15% Business Profits Tax |

**Partner strategy:** Silent partner — provides the 51% legal requirement, takes a fixed fee or small profit share, you keep operational control via side agreement.

### Registration Steps
1. Name reservation — MOCI
2. Prepare AOA, MOA, partner agreements
3. Deposit 1,000 KWD capital in bank
4. Get commercial trade license
5. CITRA registration (for messaging/tech activities)

---

## Technical Architecture

### Per-Client Deployment (On-Prem)

Each client gets OpenClaw installed on **their own server**. We manage it remotely via Tailscale.

```
Client's Server
├── OpenClaw Gateway (running 24/7)
├── Agent: recruiter-{COMPANY_CODE}
│   ├── IDENTITY.md          ← customized per company
│   └── workspace/
│       ├── data/companies/{CODE}/
│       │   ├── company.json
│       │   ├── hr-users.json
│       │   └── positions/   ← job descriptions
│       └── data/candidates/
│           └── +96597.../
│               ├── profile.json
│               ├── cv.txt
│               └── applications/
```

**Remote access:** Tailscale — no public ports, no VPN complexity, fully auditable.

### OpenClaw Capabilities Used

| Feature | Usage |
|---------|-------|
| WhatsApp plugin | Candidate & HR communication |
| Filesystem tools | JSON-based candidate database |
| gog (Google tools) | Sheets dashboard, Drive CV storage, Calendar interviews, Gmail |
| nano-pdf | CV parsing |
| Cron jobs | Email monitoring, reminders |
| RBAC (hr-users.json) | Candidate vs HR routing |

### Phase 2 — Network Layer (After 3+ Clients)

```
AI Octopus Controlled (shared, read-only for agents)
└── data/network/
    └── +96597.../
        ├── anonymous_profile.json   ← skills, exp, salary — no PII
        └── consent.json             ← opted-in sectors, expiry
```

Each client's agent can search this layer when HR asks for candidates. Companies never access it directly — AI Octopus is the neutral middle layer.

---

## Business Model

### Per Client Pricing

| Component | Price |
|-----------|-------|
| Setup (deploy, configure, customize) | $3,000 – $8,000 one-time |
| Monthly managed service | $1,500 – $4,000/mo |
| Per-hire placement fee (optional) | $500 – $1,000 per hire |

### Revenue Projections

**Year 1 (3 clients):**
| Stream | Revenue |
|--------|---------|
| Setup fees (3 × $5K avg) | $15K |
| Retainers (3 × $2.5K/mo × 8mo) | $60K |
| Placement fees | $10K |
| **Total** | **~$85K** |

**Year 2 (8 clients + network):**
| Stream | Revenue |
|--------|---------|
| Setup fees (8 × $5K) | $40K |
| Retainers (8 × $3K/mo × 12mo) | $288K |
| Network placement fees | $50K |
| **Total** | **~$378K** |

> One bank or government contract ($50K-$200K setup) changes everything.

---

## Target Clients

| Segment | Why | Pricing |
|---------|-----|---------|
| HR/staffing agencies | Hiring IS their business, fast decision | $2-3K/mo |
| Banks & telecoms | High volume, strict data rules, on-prem required | $4-8K/mo |
| Government | Civil service recruitment, Arabic-first | $5-15K setup + retainer |
| Large corporates | 100+ hires/year, overwhelmed HR teams | $3-5K/mo |
| Universities | Career fairs, student placement | $1.5-2K/mo |

**Start with HR agencies** — fastest sales cycle, most motivated buyer, best word-of-mouth.

---

## Go-To-Market — Next 90 Days

### Month 1
- [ ] Register the company (WLL — identify Kuwaiti partner)
- [ ] Film the demo video (script is written, product works)
- [ ] Close first pilot client using existing AI Octopus relationships

### Month 2
- [ ] Deploy first client on-prem
- [ ] Document case study with real numbers (candidates processed, time saved)
- [ ] Pitch 3 more companies using the case study

### Month 3
- [ ] Close 2nd and 3rd paying clients
- [ ] Start retainer contracts
- [ ] Begin legal review for Phase 2 candidate network

---

## Competitive Moats

| Moat | Why It Matters |
|------|----------------|
| **On-prem deployment** | Banks and government can't use cloud-only solutions. We're the only option. |
| **Arabic-first** | Kuwaiti dialect, bilingual. Most AI tools are English-only. |
| **WhatsApp-native** | No app download. Candidates already live on WhatsApp. |
| **First-mover** | Nobody is doing this in Kuwait yet. |
| **Candidate network (Phase 2)** | Defensible data moat — can't replicate without the clients, and we have the clients. |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Long enterprise sales cycles | Start with HR agencies — 2-4 week decisions |
| Client IT blocking on-prem install | Tailscale + Docker = clean, auditable, no public ports |
| LLM hallucinations | Strict IDENTITY.md rules, file-based state |
| Candidate data privacy (Phase 2) | Legal review before building. On-prem = client owns Phase 1 data. |
| Competition arrives | Move fast, lock in clients, build the network first |

---

## The Pitch

> **"AI Recruiter by AI Octopus. Your candidates apply on WhatsApp in 2 minutes. Your AI screens them instantly. Everything runs on your own server — your data never leaves your building. HR manages everything from their phone."**

*Updated: February 21, 2026*
