# Platform-Wide AI Assistant Architecture Audit

**Mode:** research + architecture only — **no** code, deploy, live tool registration, or company-data exposure to a new AI path  
**Date:** 2026-08-03  
**Constrained by:** Employees 360 · Onboarding · Attendance · Leave · Shifts · Payroll · Analytics · Compliance · Action Inbox · Setup Console Wave A freezes  
**Product rule:** The assistant may explain, summarize, investigate, and **prepare** actions. Frozen modules remain systems of record and action. It must never bypass permissions, SOD, approvals, legal holds, money authority, rollout gates, or module freezes.

---

## Verdict in one line

Keep **one** platform assistant spine (the existing tool-call orchestrator + `action_registry` + capability catalog). Extend it with a **module registration contract**, not per-module assistants. First implementation wave = **spine contract + kill switches + grounding/audit envelope** on WATHEFNI HR dashboard — **not** new mutation power, **not** AI inside frozen product UIs, **not** Payroll money / Attendance ingest / broad rollout / mobile apps.

---

## 1. Current AI / assistant implementation truth

### What is live today

| Surface | Reality |
|---|---|
| **Dashboard Assistant** (`AdminAIPage`, nav `ai`) | Live Pre-Hiring-centric Wathefni Assistant |
| **HR WhatsApp** | Same tool-call path (`handle_toolcall_whatsapp_turn`) |
| **Spine** | `tool_call_orchestrator.py` → OpenAI Responses / `gpt-5.6-terra` → `action_registry.py` |
| **Capability truth** | `assistant_capability_catalog.py` (per-turn AVAILABLE / denied / unconfigured) |
| **Privacy** | `assistant_privacy.py` scrubs civil ID / IBAN / raw CV before model context |
| **Confirmation** | Backend `requires_confirmation` + pending confirmation resume (LLM cannot self-approve) |
| **Non-HR WhatsApp** | Mostly deterministic handlers (+ selective LLM); not the HR assistant product |
| **CV OCR / embeddings** | Mistral OCR + Voyage for **ranking / documents** — not chat RAG |

### Post-hire tools already in the registry (module-gated)

Leave, attendance, shifts, onboarding, compliance, payroll **reads**/approvals/export, `workforce_analytics` — offered only when module ON + actor permitted. These are **tools on the platform assistant**, not “AI inside” Analytics / Compliance / Payroll product pages.

### Explicitly dark / disabled

| Item | Gate |
|---|---|
| `list_onboarding_status`, `list_compliance_documents` | `WATHEFNI_ASSISTANT_HR_READS` (default off) |
| Candidate Knowledge live tools | Code exists; `register_live_tools()` **not wired** |
| WhatsApp HSM templates | `WATHEFNI_OUTBOUND_TEMPLATES` off |
| Legacy regex inference | Off (admin chat expects toolcall) |
| Ranking recalc via assistant | Default `replay_only` |

### Honesty: `ai: false` on product surfaces

Setup Wave A · Analytics Wave 1 · Compliance Wave 1 · Action Inbox Wave 1 · Payroll external adapter — all assert **no AI inside those products**. That ban stays. Platform assistant ≠ embedding an LLM into those pages.

### Absent (important)

- No Anthropic path
- No conversation embeddings / chat RAG
- No dedicated employee/manager mobile assistant
- No AI in Setup Console / Action Inbox / Analytics / Compliance **UIs**
- No master `WATHEFNI_ASSISTANT_KILL` (today: soft-stop via missing key, modules, allowlists)
- No Employees 360 / Unified Action Inbox / Setup Console **capability groups** in the catalog yet
- No citation / evidence envelope as a first-class assistant contract (tools return data; grounding is prompt policy, not structured citations)

### Architecture already correct (do not fork)

```
Actor (HR dashboard | HR WhatsApp | future mobile shell)
        ↓
tool_call_orchestrator  (locale, privacy, confirmation, budgets)
        ↓
capability_catalog  (enabled modules + permissions + providers)
        ↓
action_registry.execute  (entitlement · confirm · SOD · freezes)
        ↓
Frozen module SoA APIs  (systems of record / action)
```

**Do not** invent a second assistant per module. Modules register into this spine.

---

## 2. Platform threat model

| Threat | Why it matters | Required control |
|---|---|---|
| **Cross-tenant leak** | Multi-company future; workspace + DB | Fail-closed `company_code` / ContextVar; never trust LLM-supplied tenant |
| **Permission escalation via prompt** | Model asks for forbidden tools | Registry filters tools; executors re-check `require_entitlement` |
| **Freeze / allowlist bypass** | “Just approve leave for everyone” | Same env gates as UI (`SYNTHETIC_ONLY`, allowlists, CAPTURE_INGEST) |
| **SOD collapse** | Approve + export same turn | Existing payroll SOD codes; assistant must not combine conflicting tools for same actor |
| **Money authority hallucination** | “Pay salaries / send WPS” | Honesty + no money tools; refuse with plain language |
| **Ingest / device punch invent** | Fake attendance authority | CAPTURE_INGEST stays off; no punch-create tools for devices |
| **Sensitive data exfiltration** | Civil ID, IBAN, CV body → model/logs | Privacy projection; redacted audit; no raw secrets in prompts |
| **Legal hold violation** | Delete / merge / broadcast held person | Reuse privacy hold gates; refuse mutate/export paths |
| **Silent mutation** | Model “confirms” itself | Backend confirmation tokens; human must affirm |
| **Stale / fabricated facts** | Invented counts or names | Grounded tool results only; cite source + as_of; refuse when blocked |
| **Channel spoof** | WhatsApp vs dashboard identity | Scope from authenticated actor, not message text |
| **Runaway cost / loops** | Tool loops / long sessions | Existing turn budgets; add master kill + rate limits |
| **Incident blast radius** | Bad tool or model regression | Kill switch, company allowlist, tool class kill, audit replay |

**Non-goals of the assistant:** becoming money authority, device ingest authority, government filing authority, or a second write path that skips module SoA.

---

## 3. Tenant / module / permission capability model

### Layers (fail-closed, ordered)

1. **Tenant** — `company_code` on every read/write; workspace + DB environment binding  
2. **Module entitlement** — `company_modules` + `require_entitlement`  
3. **Role / permission** — owner · hr_admin · hr_manager · manager · payroll_operator · employee · platform admin  
4. **Manager scope** — `manager_scope_allows_employee` (empty/unconfigured = deny for scoped acts)  
5. **Wave gates** — `*_SYNTHETIC_ONLY`, `*_COMPANIES`, named phone allowlists  
6. **Honesty freezes** — money off, ingest off, read-only composers  
7. **Assistant offerability** — capability catalog state: AVAILABLE · ENABLED_NOT_CONFIGURED · DENIED · UNSUPPORTED · MISSING_DATA  

### Capability matrix (assistant posture)

| Module | Read via assistant | Prepare / draft | Mutate via assistant | Notes |
|---|---|---|---|---|
| **Employees 360** | Future: scoped reads | Summarize profile / gaps | Only through E360 APIs + freezes | Not a catalog group yet |
| **Onboarding** | Flag-gated today | Status summary | Confirm start/mark/cancel | SoA = Onboarding |
| **Attendance** | List/read when entitled | Exception explain | Confirm absent/correct; **never** device ingest | CAPTURE_INGEST=off |
| **Leave** | List/read | Draft decision summary | Confirm approve/reject; allowlist + self-ban | SoA = Leave |
| **Shifts** | List/read | Schedule explain | Confirm mutate; HR allowlist; manager allowlist empty | SoA = Shifts L0 |
| **Payroll** | Hours/exceptions read | Explain external posture | Confirm policy/timesheet; **no money** | Money authority external |
| **Analytics** | `workforce_analytics` tool only | Attention-style summary | **Never** | Product UI stays `ai:false` |
| **Compliance** | Flag-gated docs list | Expiry summary | Reminder confirm only; no filing | Never `government_verified` |
| **Action Inbox** | Future: compose read | Rank / explain next actions | **Never** (deep-link only) | Product stays compose-only |
| **Setup Console** | Operator-only readiness explain | Point to blockers | **Never** from HR assistant | Platform admin surface |
| **Pre-Hiring** | Core live | Rank / draft comms | Confirm mutations | Existing strength |

**Platform admin / Setup operator** is a different actor class from HR. Do not blend Setup mutations into the HR assistant channel.

---

## 4. Read vs mutation boundaries

### Read (default-safe class)

- Explain enabled-module posture and why something is blocked  
- Summarize tool-returned facts with **source + time**  
- Investigate (multi-tool) within actor scope  
- Prepare an action package: who / what / why / deep link / confirmation payload  

### Mutation (always backend-gated)

| Rule | Detail |
|---|---|
| Registry only | No parallel “assistant write API” |
| Human confirmation | All sensitive `requires_confirmation=True` tools |
| Same gates as UI | Entitlement, allowlist, SYNTHETIC_ONLY, SOD, legal hold |
| Approve ≠ apply | Especially Attendance / Leave dual-control |
| No money rails | No WPS, bank file, remittance, payable posting |
| No ingest rails | No device punch create / CAPTURE_INGEST flip |
| No freeze reopen | Assistant cannot enable modules past env freezes |

### Prepare ≠ execute

“Prepare action” means: structured draft + deep link into the frozen module UI/API + optional confirmation token **awaiting human**. Execution remains the module’s system of action after confirmation (or user completes in UI).

---

## 5. Module registration contract (one spine)

Every enabled module that wants assistant awareness registers **declarations**, not a private LLM stack.

### Contract shape (logical)

```
ModuleAssistantContract
  module_key              # e.g. leave, attendance, action_inbox
  version
  honesty                 # money_authority, ingest, read_only, ai_in_product_ui=false…
  tools[]                 # ActionSpec names owned by this module
  read_capabilities[]     # catalog keys + EN/AR labels + empty chips
  mutation_capabilities[] # always confirmation + gate refs
  deep_links              # page / route templates for blockers & actions
  fallbacks               # missing | stale | blocked | unsupported copy EN/AR
  citation_kinds[]        # record ids, as_of, evidence states allowed
  kill_class              # soft-kill flag name for this module’s tools
```

### Registration rules

1. **Single registry** — `action_registry.register` remains SoT for executable tools.  
2. **Catalog derives from registry + module honesty** — do not hardcode contradictory offerability.  
3. **Product UI `ai:false` modules** may still expose **read tools** to the platform assistant; they must not embed a chat LLM in their own page.  
4. **Composers** (Action Inbox, Analytics attention, Compliance findings, Setup readiness) register as **read/prepare + deep-link only**.  
5. **No per-module prompt forks** — one system policy; modules contribute capability text blocks and fallback strings only.

### Ownership

| Layer | Owner |
|---|---|
| Spine (orchestrator, privacy, confirm, memory, kill) | Platform Assistant |
| Tool executors + SoA mutations | Frozen module teams |
| Catalog labels / chips / fallbacks | Module + Platform (bilingual) |
| Freezes / env gates | Ops freezes (unchanged by assistant waves) |

---

## 6. Grounding and citation approach

### Principle

The model may only assert facts present in **tool results** or **explicit capability_authority**. If unsupported → say so. No inventing headcount, balances, or government status.

### Citation envelope (target)

Every assistant answer that uses data should carry machine-readable evidence:

| Field | Purpose |
|---|---|
| `citations[]` | `{kind, id, module, label_en, label_ar, as_of, deep_link?}` |
| `data_freshness` | `as_of` timezone Asia/Kuwait |
| `authority_state` | live · synthetic · preview_non_authoritative · blocked · missing |
| `confidence` | grounded · partial · unavailable |

UI/WhatsApp render short footnotes or “View in Leave” links — not raw SQL.

### Sensitive data

- Scrub before model: civil ID, IBAN, bank, raw CV, secrets (`assistant_privacy`)  
- Prefer opaque employee keys + display names in scope  
- Unmask paths stay in ESS / module UIs with their own allowlists  
- Logs store redacted tool I/O; full payloads only in restricted audit sinks if required

---

## 7. Audit / event model

Reuse existing sinks; add an assistant-specific event class without mutating SoA schemas.

| Event | When |
|---|---|
| `assistant.turn_started` | Channel, actor, company, locale |
| `assistant.capability_snapshot` | Offerability hash (debug) |
| `assistant.tool_invoked` | Tool, args digest, deny/allow reason |
| `assistant.confirmation_issued` | Token id, tool, subject refs |
| `assistant.confirmation_accepted/rejected` | Human outcome |
| `assistant.mutation_delegated` | Module SoA call result id |
| `assistant.fallback` | missing / stale / blocked / unsupported |
| `assistant.kill_engaged` | Which switch |
| `assistant.privacy_scrub` | Counts of redactions (not values) |

Correlate with `record_admin_audit` / module audits when a mutation commits. Assistant events are **not** a substitute for module SoA audit.

---

## 8. Conversation memory boundaries

| Store | Scope | TTL / limit | Rule |
|---|---|---|---|
| `memory_snapshots` toolcall dialog | Turn / short session | ~20m; ~10 msgs | No cross-company; no raw secrets |
| `dashboard_chat_*` | Dashboard session | Product retention | Same tenant + actor |
| WhatsApp thread | Phone + company | Provider/thread policy | HR vs non-HR paths stay separate |
| Vector chat memory | — | — | **Out of scope** for first waves |
| CV / CK embeddings | Ranking / dark CK | Separate product | Not default chat RAG |

**Memory must not** become a permission cache that outlives entitlement changes — recompute capability catalog every turn.

---

## 9. EN / AR / Kuwaiti Arabic

### Current truth

- Locale from **current message script** or metadata `locale=ar` — not from profile name  
- Empty-state chips already bilingual in capability catalog  
- Not yet a dedicated **Kuwaiti dialect** style guide in the spine

### Target policy (simple)

| Mode | Behavior |
|---|---|
| EN | Clear Gulf HR English; Kuwait context (Civil ID, PAM, Asia/Kuwait) |
| AR | Modern Standard Arabic for formal HR + **Kuwaiti-friendly** phrasing for WhatsApp/chat (avoid stiff MSA-only where product already uses Gulf AR) |
| Numbers / dates | Prefer Kuwait-local formatting; times in Asia/Kuwait |
| Legal / money | Never claim payment or government filing in either language |

Module fallbacks register EN + AR strings in the contract (as Analytics/Leave already do in product copy).

---

## 10. Surfaces: WhatsApp, dashboard, future mobile

| Surface | Role | First waves |
|---|---|---|
| **HR Dashboard Assistant** | Primary control surface | Wave 1 spine |
| **HR WhatsApp** | Same spine, shorter replies, confirm via chat | Wave 1 parity tests; no new powers |
| **Employee / manager WhatsApp** | Deterministic SoA handlers today | Do **not** merge into HR toolcall without a separate actor model |
| **Future mobile** | Thin client of same spine | **NO-GO** this program until dashboard/WhatsApp contract is frozen |
| **Setup Console** | Operator readiness | Explain-only via operator channel later; not HR chat |
| **Module product pages** | SoA UIs | Stay `ai:false` where frozen; deep-link targets only |

---

## 11. Fallback when data is missing, stale, blocked, unsupported

| Condition | Assistant behavior |
|---|---|
| **Missing** | Say what’s missing; next action + deep link; no guess |
| **Stale** | Show `as_of`; offer refresh tool; refuse decisions on stale dual-control without path |
| **Blocked** (permission / allowlist / SYNTHETIC_ONLY / hold) | Plain-language deny; name the class of gate without leaking internals to employees |
| **Unsupported** (money, ingest, government file, AI-in-product) | Hard refuse; point to honest posture |
| **Module off** | “Not purchased / not enabled” via capability_authority |
| **Enabled not configured** | Setup required + Setup/Launch Readiness deep link for operators |

---

## 12. Observability, kill switches, incident handling

### Required kill switches (target)

| Switch | Effect |
|---|---|
| `WATHEFNI_ASSISTANT_KILL` | Master: no LLM turns (all channels) |
| `WATHEFNI_ASSISTANT_MUTATIONS` | Reads/explain only; block confirm-execute |
| Per-module `kill_class` | Disable that module’s tools |
| Existing module freezes | Unchanged hard authority |
| Missing API key | Soft fail (already) |

### Observability

- Turn latency, tool error rate, confirmation abandon rate  
- Deny reasons histogram (permission / freeze / missing)  
- Privacy scrub counts  
- Cost / token budget per company  

### Incident playbook (logical)

1. Engage master kill or mutations kill  
2. Freeze implicated tool class  
3. Pull assistant events + module SoA audits for affected turn ids  
4. Rollback code drop-in if a deploy caused it (same pattern as other waves)  
5. Do **not** “fix” by widening allowlists or turning on money/ingest  

---

## 13. Target architecture (long-term, simple)

```
                    ┌─────────────────────────────┐
                    │  Surfaces (dash / WA / later │
                    │  mobile) — thin clients      │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  Platform Assistant Spine    │
                    │  locale · privacy · memory   │
                    │  confirm · kill · audit      │
                    │  grounding envelope          │
                    └──────────────┬──────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
     Capability Catalog    action_registry      Honesty / freezes
     (offerability)        (execute only)       (env + module)
              │                    │
              └──────────┬─────────┘
                         ▼
              Frozen module systems of action
              E360 · Onboarding · Attendance · Leave
              Shifts · Payroll · (composers deep-link only)
```

**One brain. Many registered modules. Zero shadow write paths.**

---

## 14. Rollout strategy

| Phase | Scope | Verdict posture |
|---|---|---|
| **This audit** | Architecture only | **GO** as research |
| **Wave 1 — Spine Contract** | Kill switches, registration contract, citation envelope, audit events, EN/AR policy, catalog gaps for Inbox/E360/Setup as **read/prepare declarations** — WATHEFNI HR dashboard; mutations kill default or unchanged confirmation | Staging then prod synthetic |
| **Wave 2 — Safe reads widen** | Carefully enable dark HR reads (`ASSISTANT_HR_READS`) under allowlists; Action Inbox compose-read; Analytics attention via existing tool | Still no money/ingest |
| **Wave 3 — Prepare-action UX** | Confirmation cards + deep links polished EN/AR; WhatsApp parity | Still SoA executes |
| **Later** | Manager-scoped assistant; employee assistant; mobile shell | Separate owner waves |
| **Never without freeze change** | Payroll money, Attendance ingest, AI inside Analytics/Compliance/Inbox/Setup UIs, broad external tenants | **NO-GO** |

No broad rollout. Company allowlist remains WATHEFNI until a multi-tenant wave exists.

---

## 15. Exact first implementation wave

### Name

**Platform Assistant Wave 1 — Spine Contract (WATHEFNI, HR dashboard-first)**

### In scope

1. Document + implement **module registration contract** against existing registry (no parallel frameworks)  
2. Master **kill** + **mutations** kill switches  
3. **Grounding/citation envelope** on assistant responses (tool-backed)  
4. **Assistant audit events** (turn / tool / confirm / fallback / kill)  
5. Catalog declarations for **Action Inbox · Employees 360 · Setup readiness** as read/prepare/deep-link only (no new SoA mutations)  
6. Unified fallback copy EN/AR for missing/stale/blocked/unsupported  
7. Kuwaiti Arabic style notes in system policy (no dialect model fork)  
8. Staging qualify + prod synthetic canary; rollback; sibling freezes green  

### Out of scope (hard)

- Registering Candidate Knowledge live tools  
- Payroll money authority / bank / WPS  
- Attendance CAPTURE_INGEST / device punch tools  
- Embedding LLM into Analytics / Compliance / Action Inbox / Setup product pages  
- iOS / Android  
- External tenants / broad rollout  
- Frozen-module schema or authority changes  
- Chat RAG / new vector memory  
- Turning on `WATHEFNI_ASSISTANT_HR_READS` for all (optional later wave)  

### Exit criteria (Wave 1)

- Kill switch proven (turns stop)  
- Mutations kill proven (reads ok, confirms blocked)  
- Citations present on sample grounded answers  
- No freeze regressions; CAPTURE_INGEST remains off; money honesty unchanged  
- Residual 0; no new external tenant  

### Wave 1 gate name (proposed)

`STAGING_PLATFORM_ASSISTANT_WAVE1_SPINE_GO` → later `PROD_SYNTHETIC_PLATFORM_ASSISTANT_WAVE1_SPINE_GO`

---

## 16. Risks and unresolved questions

### Risks

| Risk | Mitigation |
|---|---|
| Registry already large; contract becomes paperwork | Generate catalog from registry metadata; keep declarations thin |
| HR WhatsApp + dashboard drift | Same spine tests both channels |
| “Prepare” confused with execute | UX copy + mutations kill during early canaries |
| Model invents Kuwait labor law | Refuse legal advice; cite Compliance findings tools only |
| Expanding post-hire tools reopens freezes politically | Wave 1 adds **no** new mutation executors |
| Privacy scrub gaps on new tools | Contract requires privacy classification per tool |

### Unresolved questions (owner decisions)

1. **Should Action Inbox become the default “what needs me?” entry** for the assistant, or remain a separate page the assistant only deep-links?  
2. **Manager assistant:** same spine with scope, or delay until manager allowlists exist for Shifts? (Today Shifts manager allowlist is empty.)  
3. **Kuwaiti Arabic:** product-copy review by native speaker vs model-only style instructions?  
4. **Retention** of dashboard chat + assistant events under Kuwait data policy?  
5. **Employee-facing assistant:** ever, or keep employees on deterministic WhatsApp/app only?  
6. **CK tools:** wire later under dark allowlist, or keep ranking-only forever for chat?  
7. **Setup explain:** allow platform-admin assistant channel, or keep Setup Console UI-only?  

---

## 17. Explicit NO-GO (this audit)

| Item | Verdict |
|---|---|
| Code / deploy / live tool registration from this audit | **NO-GO** |
| Exposing company data to a new AI path | **NO-GO** |
| Payroll money authority | **NO-GO** |
| Attendance ingest on | **NO-GO** |
| Broad rollout / external tenants | **NO-GO** |
| iOS / Android assistant | **NO-GO** |
| Frozen-module contract changes | **NO-GO** |
| Separate assistant logic inside every module | **NO-GO** (rejected architecture) |
| Starting Platform Assistant Wave 1 implementation | **Not started** (await owner GO) |

---

## 18. Bottom line

| Question | Answer |
|---|---|
| Current truth? | One live Pre-Hire-centric toolcall assistant; post-hire tools exist but gated; composers/honesty ban AI-in-product |
| Right long-term shape? | **One spine**, module registration contract, SoA stays in frozen modules |
| First wave? | **Spine Contract** — kill, citations, audit, catalog gaps, EN/AR — no new mutation power |
| Start coding now? | **No** — this document is research only |

**Architecture audit: GO**  
**Implementation: NO-GO until an owner-authorized Platform Assistant Wave 1**
