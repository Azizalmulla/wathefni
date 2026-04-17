# AI Octopus — Business Strategy & Plan

> **Updated:** February 21, 2026
> **Focus:** AI Recruiter as the lead product. On-prem deployment. Private-first, network second.

---

## 1. The One Product: AI Recruiter

AI Octopus's lead product is **AI Recruiter** — a WhatsApp-native hiring platform deployed on the client's own infrastructure.

**One sentence:** *"Your candidates apply on WhatsApp. Your AI screens them. Your data never leaves your building."*

### How It Works
1. Company puts a **QR code** on job posts, career fairs, LinkedIn, website
2. Candidate scans → WhatsApp opens with pre-filled apply code
3. AI greets candidate, asks for CV (PDF, voice note, or typed)
4. AI reads CV, extracts all info, asks screening questions
5. Candidate data saved to company's own server — fully isolated
6. HR asks the agent natural language questions: *"Who applied this week?"*, *"Show me Python devs with transferable visa"*
7. Agent searches, ranks, and presents candidates instantly

### Why It Works in Kuwait
- **Zero friction** — no app, no portal, no login. Just WhatsApp. Everyone has it.
- **24/7 intake** — candidates apply at 2am, agent handles it
- **Bilingual** — Arabic (Kuwaiti dialect) + English
- **Career fair killer** — QR code on a banner, 500 students scan in one day, all CVs captured automatically
- **Data sovereignty** — runs on client's own server, not our cloud

---

## 2. Deployment Model: On-Prem First

Every client gets their own isolated deployment on **their own infrastructure**.

We install OpenClaw on their server, configure their agent, and manage it remotely via **Tailscale** — no public ports, no cloud dependency, full security.

### Why On-Prem Wins
- **Banks & government** — regulatory requirement, data cannot leave their network
- **Large corporates** — IT security teams block cloud-only solutions
- **Trust** — "your data never touches our servers" is a killer pitch in Kuwait
- **Premium pricing justified** — on-prem = higher setup fee, higher retainer

### Multi-Company Architecture
Each company = one OpenClaw agent on their own server. All agents share the same codebase and IDENTITY.md template — customized per company (their positions, HR numbers, Google Sheet). Takes ~30 minutes to onboard a new client.

---

## 3. Revenue Model

### Per Client
| Component | Price |
|-----------|-------|
| Setup (deploy, configure, customize) | $3,000 – $8,000 one-time |
| Monthly managed service | $1,500 – $4,000/mo |
| Per-hire placement fee (optional) | $500 – $1,000 per hire |

### Year 1 (Realistic — 3 clients)
| Stream | Revenue |
|--------|---------|
| Setup fees (3 × $5K avg) | $15K |
| Retainers (3 × $2.5K/mo × 8mo) | $60K |
| Placement fees | $10K |
| **Total** | **~$85K** |

### Year 2 (8 clients + network upsell)
| Stream | Revenue |
|--------|---------|
| Setup fees (8 × $5K) | $40K |
| Retainers (8 × $3K/mo × 12mo) | $288K |
| Network placement fees | $50K |
| **Total** | **~$378K** |

> One bank or government contract ($50K-$200K setup) changes everything.

---

## 4. Growth Roadmap

### Phase 1 — Private AI Recruiter (Now)
- Each company gets their own isolated agent on their own server
- Fully private — no data sharing between companies
- Pitch: *"Your AI recruiter. Your server. Your data."*
- **Target first clients:** HR agencies, staffing companies, large corporates, banks

### Phase 2 — Candidate Network Bridge (After 3+ Clients)
Once you have multiple companies on the platform, add an opt-in talent network:

- At end of screening, AI asks: *"Want to be considered for similar roles at other companies?"*
- Opted-in candidates get an anonymous profile in a shared network layer
- Companies search the network — see skills, experience, salary range only (no name/phone/CV)
- Company requests contact → candidate approves via WhatsApp → details revealed only then
- **AI Octopus is the neutral middle layer** — companies never access the network directly

**Revenue:** $1-3K placement fee per network hire, on top of existing retainers.

**Why it works:** Companies already trust you (paying clients). Candidates control their data. No "why would we share?" objection — companies aren't sharing anything, candidates are.

---

## 5. Tech Stack

| Component | Tool |
|-----------|------|
| AI Agent Platform | OpenClaw (local-first, open-source) |
| LLM | Claude Sonnet 4.6 (Anthropic) |
| WhatsApp | OpenClaw WhatsApp plugin (personal) → WhatsApp Business Cloud API (production) |
| Storage | Filesystem (JSON files) — source of truth |
| HR Dashboard | Google Sheets (via gog) |
| CV Storage | Google Drive (via gog) |
| Calendar / Email | Google Calendar + Gmail (via gog) |
| Remote Management | Tailscale |
| Deployment | On-prem on client's server |

---

## 6. Competitive Moats

1. **On-prem deployment** — Cloud-only competitors can't pitch to banks and government. We can.
2. **Arabic-first** — Kuwaiti dialect, bilingual. Most AI tools are English-only.
3. **WhatsApp-native** — No app download. Candidates already live on WhatsApp.
4. **First-mover in Kuwait** — Nobody is doing this here yet.
5. **Candidate network (Phase 2)** — Once built, becomes a defensible data moat. Competitors can't replicate the network without the clients, and you have the clients.
6. **AI Collection (future)** — Dad's company owns a payment gateway. Relevant for other AI Octopus products (restaurants, clinics) — not the recruiter specifically.

---

## 7. Target Clients

| Segment | Why | Pricing |
|---------|-----|---------|
| HR/staffing agencies | Hiring IS their business | $2-3K/mo |
| Banks & telecoms | High volume, strict data rules, on-prem required | $4-8K/mo + large setup |
| Government | Civil service recruitment, Arabic-first | $5-15K setup + retainer |
| Large corporates | 100+ hires/year, overwhelmed HR teams | $3-5K/mo |
| Universities | Career fairs, student placement | $1.5-2K/mo |

---

## 8. Go-To-Market — Next 90 Days

### Month 1
- [ ] Film the demo video (script is ready, product works)
- [ ] Register the company (WLL — need Kuwaiti partner)
- [ ] Close first pilot client (warm lead — use existing AI Octopus relationships)

### Month 2
- [ ] Deploy first client on-prem
- [ ] Document case study with real numbers
- [ ] Pitch 3 more companies using the case study

### Month 3
- [ ] Close 2nd and 3rd paying clients
- [ ] Start retainer contracts
- [ ] Begin legal review for Phase 2 candidate network

---

## 9. Key Risks

| Risk | Mitigation |
|------|------------|
| Long enterprise sales cycles (banks/gov) | Start with HR agencies — faster decisions |
| Client IT blocking on-prem install | Tailscale + Docker makes it clean and auditable |
| LLM hallucinations | Strict IDENTITY.md rules, file-based state (not memory) |
| Candidate data privacy | On-prem = client owns their data. Phase 2 requires legal review. |
| Competition arrives | Move fast, lock in clients, build the network before anyone else |

---

## 10. The Pitch

> **"AI Recruiter by AI Octopus. Your candidates apply on WhatsApp in 2 minutes. Your AI screens them instantly. Everything runs on your own server — your data never leaves your building. HR manages everything from their phone."**
