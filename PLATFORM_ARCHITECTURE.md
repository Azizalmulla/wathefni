# Kuwait AI Agent Platform - Architecture

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AGENT OS KUWAIT                                    │
│                     "AI Agents for Every Business"                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Restaurant │     │   Clinic    │     │   Salon     │     │   Garage    │
│   Agent     │     │   Agent     │     │   Agent     │     │   Agent     │
│  +965 111   │     │  +965 222   │     │  +965 333   │     │  +965 444   │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │                   │
       └───────────────────┴───────────────────┴───────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │      YOUR PLATFORM          │
                    │   (Multi-Tenant OpenClaw)   │
                    │                             │
                    │  • Agent Routing            │
                    │  • Knowledge Bases          │
                    │  • Billing & Usage          │
                    │  • Admin Dashboard          │
                    └──────────────┬──────────────┘
                                   │
       ┌───────────────────────────┼───────────────────────────┐
       │                           │                           │
┌──────▼──────┐          ┌─────────▼─────────┐       ┌────────▼────────┐
│  WhatsApp   │          │     Telegram      │       │   Voice/SMS     │
│  Business   │          │       Bot         │       │    (Future)     │
└─────────────┘          └───────────────────┘       └─────────────────┘
```

---

## Platform Components

### 1. Infrastructure Layer (Cloud)

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLOUD (DigitalOcean/AWS)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │   OpenClaw   │  │   Database   │  │   File Storage       │   │
│  │   Gateway    │  │  (Postgres)  │  │   (S3/Spaces)        │   │
│  │   Server     │  │              │  │                      │   │
│  │              │  │ • Clients    │  │ • Menus (PDF/images) │   │
│  │ • Multi-agent│  │ • Agents     │  │ • Voice notes        │   │
│  │ • Routing    │  │ • Sessions   │  │ • Media              │   │
│  │ • Channels   │  │ • Analytics  │  │                      │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │    Redis     │  │   Nginx      │  │   Monitoring         │   │
│  │   (Cache)    │  │  (Reverse    │  │   (Logs/Alerts)      │   │
│  │              │  │   Proxy)     │  │                      │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

Estimated cost: $50-150/month for first 50 clients
```

### 2. Business Portal (Web App)

```
┌─────────────────────────────────────────────────────────────────┐
│                    BUSINESS PORTAL                               │
│                  portal.agentos.kw                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  For Business Owners (Your Clients):                             │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  📊 Dashboard                                                ││
│  │  • Messages today: 47                                        ││
│  │  • Orders received: 12                                       ││
│  │  • Appointments booked: 8                                    ││
│  │  • Customer satisfaction: 94%                                ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  📝 Knowledge Base                                           ││
│  │  • Upload menu (PDF/Excel)                                   ││
│  │  • Edit services & prices                                    ││
│  │  • Set business hours                                        ││
│  │  • Add FAQs                                                  ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  💬 Conversations                                            ││
│  │  • View all customer chats                                   ││
│  │  • Take over from AI when needed                             ││
│  │  • Flag/train on mistakes                                    ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  ⚙️ Settings                                                 ││
│  │  • Agent personality                                         ││
│  │  • Working hours (when to respond)                           ││
│  │  • Language (Arabic/English/Both)                            ││
│  │  • Escalation rules                                          ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3. Admin Dashboard (For You)

```
┌─────────────────────────────────────────────────────────────────┐
│                    ADMIN DASHBOARD                               │
│                  admin.agentos.kw                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  📈 Overview                                                 ││
│  │  • Active clients: 23                                        ││
│  │  • Total messages: 12,450                                    ││
│  │  • Revenue: 2,300 KWD/month                                  ││
│  │  • API costs: 180 KWD/month                                  ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  🏢 Clients                                                  ││
│  │  ┌──────────────┬──────────┬──────────┬──────────┬────────┐ ││
│  │  │ Business     │ Type     │ Messages │ Status   │ MRR    │ ││
│  │  ├──────────────┼──────────┼──────────┼──────────┼────────┤ ││
│  │  │ مطعم الديرة  │ Restaurant│ 2,340   │ Active   │ 100 KD │ ││
│  │  │ عيادة الصحة  │ Clinic   │ 890     │ Active   │ 150 KD │ ││
│  │  │ صالون نور    │ Salon    │ 1,205   │ Active   │ 75 KD  │ ││
│  │  └──────────────┴──────────┴──────────┴──────────┴────────┘ ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  🔧 System                                                   ││
│  │  • OpenClaw status: Running                                  ││
│  │  • WhatsApp connections: 23/50                               ││
│  │  • API usage: 2.3M tokens today                              ││
│  │  • Errors: 0                                                 ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4. Onboarding Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    ONBOARDING FLOW                               │
└─────────────────────────────────────────────────────────────────┘

Business Owner Journey:

Step 1: Sign Up
┌─────────────────────────────────────┐
│  agentos.kw                         │
│                                     │
│  "AI Agent for Your Business"       │
│                                     │
│  [Restaurant] [Clinic] [Salon]      │
│  [Garage] [Other]                   │
│                                     │
│  Business Name: ________________    │
│  Phone: ________________            │
│  Email: ________________            │
│                                     │
│  [Start Free Trial - 14 Days]       │
└─────────────────────────────────────┘
              │
              ▼
Step 2: Connect WhatsApp
┌─────────────────────────────────────┐
│  Scan this QR with WhatsApp         │
│                                     │
│       ┌─────────────────┐           │
│       │  █▀▀▀▀▀▀▀▀▀▀█   │           │
│       │  █ QR CODE  █   │           │
│       │  █▀▀▀▀▀▀▀▀▀▀█   │           │
│       └─────────────────┘           │
│                                     │
│  Use a dedicated business number    │
│  (not your personal WhatsApp)       │
└─────────────────────────────────────┘
              │
              ▼
Step 3: Upload Knowledge
┌─────────────────────────────────────┐
│  Teach your AI about your business  │
│                                     │
│  [📄 Upload Menu PDF]               │
│  [📊 Upload Excel Price List]       │
│  [✏️ Type it manually]              │
│                                     │
│  Business Hours:                    │
│  [9:00 AM] to [11:00 PM]            │
│                                     │
│  Languages:                         │
│  [x] Arabic  [x] English            │
└─────────────────────────────────────┘
              │
              ▼
Step 4: Test & Go Live
┌─────────────────────────────────────┐
│  Test your agent                    │
│                                     │
│  Send a message to +965 XXXX XXXX   │
│  Try: "What's on the menu?"         │
│                                     │
│  ✅ Agent responded correctly       │
│                                     │
│  [Go Live]                          │
└─────────────────────────────────────┘
```

---

## Tech Stack

### Backend
| Component | Technology | Why |
|-----------|------------|-----|
| Core Agent | OpenClaw | Multi-agent, multi-channel |
| API Server | Node.js/Express or Python/FastAPI | REST API for portal |
| Database | PostgreSQL | Clients, sessions, analytics |
| Cache | Redis | Session state, rate limiting |
| Queue | BullMQ or Celery | Async tasks |

### Frontend
| Component | Technology | Why |
|-----------|------------|-----|
| Business Portal | Next.js + Tailwind | Fast, modern, Arabic RTL support |
| Admin Dashboard | Next.js + Tailwind | Same stack, shared components |
| Landing Page | Next.js | SEO, marketing |

### Infrastructure
| Component | Technology | Cost |
|-----------|------------|------|
| Cloud | DigitalOcean | $50-100/mo |
| Domain | agentos.kw | ~20 KD/year |
| SSL | Let's Encrypt | Free |
| Email | Resend or Mailgun | $20/mo |
| Payments | Tap Payments | 2.5% + 0.100 KD per txn |

---

## Data Model

```sql
-- Core tables

CREATE TABLE businesses (
    id UUID PRIMARY KEY,
    name VARCHAR(255),
    name_ar VARCHAR(255),
    type VARCHAR(50),  -- restaurant, clinic, salon, etc.
    phone VARCHAR(20),
    email VARCHAR(255),
    whatsapp_number VARCHAR(20),
    agent_id VARCHAR(100),  -- OpenClaw agent ID
    plan VARCHAR(50),  -- trial, starter, pro
    status VARCHAR(50),  -- active, paused, churned
    created_at TIMESTAMP,
    trial_ends_at TIMESTAMP
);

CREATE TABLE knowledge_items (
    id UUID PRIMARY KEY,
    business_id UUID REFERENCES businesses(id),
    type VARCHAR(50),  -- menu_item, service, faq, hours
    name VARCHAR(255),
    name_ar VARCHAR(255),
    description TEXT,
    description_ar TEXT,
    price DECIMAL(10,3),
    category VARCHAR(100),
    active BOOLEAN DEFAULT true
);

CREATE TABLE conversations (
    id UUID PRIMARY KEY,
    business_id UUID REFERENCES businesses(id),
    customer_phone VARCHAR(20),
    started_at TIMESTAMP,
    last_message_at TIMESTAMP,
    message_count INT,
    status VARCHAR(50)  -- active, resolved, escalated
);

CREATE TABLE messages (
    id UUID PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id),
    direction VARCHAR(10),  -- inbound, outbound
    content TEXT,
    timestamp TIMESTAMP,
    tokens_used INT
);

CREATE TABLE analytics_daily (
    id UUID PRIMARY KEY,
    business_id UUID REFERENCES businesses(id),
    date DATE,
    messages_in INT,
    messages_out INT,
    conversations INT,
    orders INT,
    bookings INT,
    tokens_used INT
);
```

---

## Pricing Model

| Plan | Price | Includes |
|------|-------|----------|
| **Trial** | Free (14 days) | 500 messages |
| **Starter** | 50 KWD/month | 2,000 messages, basic analytics |
| **Pro** | 100 KWD/month | 10,000 messages, full analytics, priority support |
| **Enterprise** | 200+ KWD/month | Unlimited, custom integrations, SLA |

**Your margins:**
- API cost: ~0.01-0.02 KWD per message (Claude)
- At 100 KWD/month with 10k messages = 100-200 KWD API cost
- Net margin: ~50-70% after hosting

---

## Development Phases

### Phase 1: MVP (4-6 weeks)
- [ ] Cloud server setup (OpenClaw + Postgres)
- [ ] Multi-agent routing working
- [ ] Simple business portal (upload menu, view chats)
- [ ] WhatsApp connection per client
- [ ] One vertical: Restaurant

### Phase 2: Growth (4-6 weeks)
- [ ] Admin dashboard
- [ ] Billing integration (Tap)
- [ ] Analytics
- [ ] More verticals: Clinic, Salon

### Phase 3: Scale (ongoing)
- [ ] Self-service onboarding
- [ ] Arabic NLP improvements
- [ ] Voice/call support
- [ ] Integrations (POS, calendars)

---

## Competitive Moat

1. **Local presence** — You're in Kuwait, understand the market
2. **Arabic-first** — Optimized for Kuwaiti dialect
3. **Vertical expertise** — Deep templates for restaurant/clinic/salon
4. **Network effects** — Agents can refer customers between businesses
5. **Data advantage** — Learn what works for Kuwait SMBs

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| WhatsApp blocks number | Use Business API, follow ToS |
| API costs spike | Usage limits, tiered pricing |
| Competition | Move fast, build relationships |
| Technical failures | Monitoring, redundancy, fallback to human |

---

## First Steps

1. **Get a VPS** — DigitalOcean droplet ($24/mo)
2. **Deploy OpenClaw** — Docker on the server
3. **Build basic portal** — Next.js, deploy on Vercel
4. **Onboard 1 pilot** — Restaurant you know personally
5. **Iterate** — Fix what breaks, add what's needed
