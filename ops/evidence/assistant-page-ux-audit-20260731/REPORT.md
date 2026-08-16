# Wathefni Assistant — Deep Product / UX Audit (Pre-UI)

**Date:** 2026-07-31  
**Scope:** Wathefni Assistant page only — **audit; no implement; no deploy**  
**UX / product readiness verdict:** **FAIL** vs calm grounded HR copilot (backend action authority largely **PASS**)  
**Canvas:** `assistant-page-ux-audit.canvas.tsx`

---

## Exact purpose

The Assistant is a **company-scoped HR copilot**: ask in natural language, get grounded answers from real tenant data, and run **backend-authorized** hiring (and enabled post-hire) actions with confirmation. Unit of conversation = one dashboard chat session (`conversation_id`) owned by `(company_code, actor_user_id)`.

It is **not** the system of record for pipeline, ranking, assessments, calendar, or reports. Those desks own their contracts; the Assistant invokes tools that must respect the same registry permissions / visibility.

| Surface | Owns | Does **not** own |
|---|---|---|
| **Assistant** | Natural-language Q&A + tool-mediated actions; session history; confirmation UX | Canonical stage buckets, ranking formulas, assessment cohorts, calendar sync, report metrics |
| **Overview** | Today’s work CTAs / people-first queue | Free-form chat or multi-step workflows |
| **Jobs** | Opening lifecycle + share | Conversational job draft (Assistant can preflight create) |
| **Candidates** | Pipeline list + application authority | Soft chat cards as full profile |
| **Interviews** | Interview queue tabs | Scheduling truth without interview tools |
| **Calendar** | Schedule projections | Chat-driven calendar rewrite |
| **Assessments** | Send / attempts / needs-review | Cohort membership invented in chat |
| **Ranking** | Job-scoped advisory order | Soft-rank as permanent stage |
| **Reports** | Leadership metrics + CSV | Assistant inventing funnel/time-to-hire numbers |

**Product classification today:** hybrid — **controlled action surface** underneath (toolcall + `action_registry`) with a **chat UX** that still behaves partly like a general chatbot (WhatsApp-oriented system prompt, wording-driven nav chips, free-reply from state without re-query).

---

## Current structure

| Block | What exists |
|---|---|
| Header | “Wathefni Assistant” · History · New chat |
| Empty state | Module-gated prompt chips (hiring + post-hire) |
| Transcript | User bubbles · assistant text · candidate cards · confirmation card · nav chips |
| Composer | Textarea + send (Enter) · busy disables send |
| History drawer | Sessions grouped Today/Yesterday/Earlier |
| New-chat modal | Clears view; cancels pending confirmations server-side |

Primary files: `AdminAIPage.tsx`, `App.tsx` (`askDashboardAssistant`, sessions), `api.ts` (`streamDashboardChat`), `tool_call_orchestrator.py`, `action_registry.py`, `assistant_privacy.py`, `assistant_jobs_ux.py`, `assistant_policy.py` (**unwired**), `app.py` chat routes + `dashboard_chat_artifacts`.

---

## What it can do vs explain/suggest

### Can do (mutate / execute via tools)
When the tool is in the actor’s catalog and permissions/modules allow:

- Job create / pause / close / reopen (preflight → confirm)
- Candidate shortlist / hire / reject; workflows & batches (preflight → confirm)
- Send assessment / video interview / notify / interview invite (sensitive → confirm)
- Schedule interview (OCC + confirm)
- Selected post-hire tools when modules entitled (leave approve/reject, attendance corrections, payroll export, etc.)

### Explain / suggest only (read tools or free reply)
- Rankings (typically replay), candidate lists, job inventory/search, status / invite status, overview-ish work questions from tools
- Free-form evaluation grounded in prior `state_summary` / privacy-projected context — **no DB re-query** on step-1 free reply
- Navigation chips (“Open Ranking / Candidates / …”) — UI navigation, not mutations

### Does **not** currently own
- Reports metric authority (`assistant_policy` Reports-vs-Overview helpers exist but are **not wired** into the live turn)
- Inventing candidates/jobs/statuses as durable records (blocked by resolver + enums; free text can still over-claim)

---

## Prompts, quick actions, cards, states, result types

| UI element | Source | Grounding |
|---|---|---|
| Empty chips | `assistantPromptChips` — modules + assessments | Client module list only |
| Jobs → Assistant create | Fixed EN prompt into chat | Preflight create path |
| Candidate cards | Tool outputs → `dashboard_chat_candidate_card` | DB-backed fields; open → `openCandidateByKey` live |
| Confirmation card | `needs_confirmation` tool status | Backend pending_actions |
| Nav chips | Tool results + **message wording heuristics** | Module-gated for Interviews/Assessments tools; wording chips are loose |
| “Show more roles” | `assistant_prompt` nav type | **Broken on FE** — `applyChatNavigation` only handles `page` |
| Streaming dots | Client `isStreaming` | Synthetic SSE after full turn |
| History sessions | `dashboard_chat_sessions` | Tenant + actor scoped |

Conversation states: empty · streaming · answered · confirmation pending/inactive · history open · new-chat confirm · error bubble.

---

## Authority: permissions, tenant, context

| Layer | Reality |
|---|---|
| Route | `prehire.read` to chat |
| Tool catalog | Filtered by module + `TOOL_PERMISSION_MAP` |
| Mutations | `action_registry.execute` + confirmation / OCC where required |
| Page context | `page: lastWorkPage` when on Assistant; `selected_app_key` if profile open |
| Visibility | Tools should use same company scope; chat sessions isolated by company+actor |
| Confirm | Explicit approval text / button → same chat path (`Yes, confirm it`) |
| Audit | `action_results` / turn audit; thin client audit subset — not full `record_admin_audit` per chat tool |
| Destructive | Sensitive tools require confirmation; new chat cancels pending confirmations |

**Grounded:** yes for tool calls. **Not fully grounded:** free replies from history; wording-only nav chips; Reports boundary policy unwired.

---

## Invention / hallucination risk

Mitigations: enum catalogs, `candidate_not_found` / `ambiguous`, privacy scrub + untrusted-data wrapper, Jobs inventory authority, “never invent enum values” in `TOOLCALL_SYSTEM`.

Remaining risks:

1. Free reply without tools can assert status/scores from stale `state_summary`.
2. System prompt still WhatsApp-centric (“speak to HR admin on WhatsApp”) — wrong surface framing.
3. Prompt says evaluations may use `cv_text` while privacy projection denies raw CV — instruction/privacy conflict.
4. Wording chips can open Candidates/Ranking from casual language without a tool result.

---

## Failure & edge handling

| Case | Behavior | Gap |
|---|---|---|
| Missing context | Clarifying question / `needs_candidate_reference` | OK |
| Ambiguous candidate | List matches; do not pick | OK |
| Module off | Tool hidden; Assessments/Interviews chips gated | Post-hire empty chips still advertise modules if enabled list incomplete |
| Permission denial | Tool not visible / entitlement fail | Error copy may be generic |
| Stale data | Post-success `refreshEverything()` | Free-reply path can stay stale; no explicit stale badge |
| Failed tool / stream | Error bubble + notice | No cancel mid-flight; fake streaming |
| Partial results | Batch/workflow preflight messages | No first-class partial UI chrome |
| Open candidate / page | Live keys / `openPage` | Ranking position set when chip includes `position_code` |

---

## Persistence, privacy, injection

- Sessions: `dashboard_chat_sessions` / `messages` — company + actor + channel `dashboard`
- Privacy: `assistant_privacy` allowlist/denylist + injection scrub on candidate evidence
- Injection: CV/notes treated as untrusted when projected; user chat still goes to model as instructions
- Sensitive HR fields (civil id, phone/email in projection denylist) scrubbed from model context — cards may still show phone if present on card payload

---

## Loading / streaming / retry / duplicate

| Topic | Reality |
|---|---|
| Streaming | **Fake:** full turn then token drip (`sleep`) |
| Cancel | No `AbortController`; busy only |
| Retry | Re-send message |
| Duplicate submit | `chatBusy` guard |
| Turn budget | ~90s server cancel |

---

## AR / RTL / mobile / a11y / Profiler

| Topic | Reality | Rank |
|---|---|---|
| AR / RTL | No `locale` / `dir=rtl`; EN chrome; history dates `en-GB` | High |
| Mobile | Fixed height chat; chips wrap; history drawer full-width OK | Medium |
| Raw enums | Cards use `stageLabel`; confirmation/status strings may be backend EN | Medium |
| Long replies | WhatsApp-short policy; dashboard can still dump long text | Medium |
| Scroll | Transcript `overflow-y-auto`; auto-scroll to end | Leave alone (mostly) |
| Focus / Escape | History/new-chat overlays: **no** `useOverlayFocus` / Escape / return focus | High |
| Keyboard | Enter send; Shift+Enter newline | Leave alone |
| React Profiler | **Absent** on send / stream / open card / confirm | High |

---

## Ranked findings

### Critical
1. **Product identity mismatch** — Backend is a controlled HR action surface; UI + `TOOLCALL_SYSTEM` still read as WhatsApp general chatbot. Risks wrong tone, wrong brevity rules, and “chatty” behavior on a cream HR desk.
2. **`assistant_prompt` navigation dead** — “Show more roles” chips use `type: assistant_prompt` but FE only opens `item.page` → silent no-op.
3. **Fake streaming + no cancel** — Long tools block the request; UI pretends to stream; user cannot abort.

### High
4. **Wording-driven nav chips** — Message contains “candidate”/“rank” → Open Candidates/Ranking without tool authority (generic chatbot noise).
5. **Free-reply from stale `state_summary`** — Can invent confidence without re-query; post-answer refresh helps next tool turn only.
6. **`assistant_policy` unwired** — Reports vs Overview boundary and ranking replay policy not on live path → metric questions can confuse Overview with Reports.
7. **No AR/RTL / locale on Assistant** — Rest of recruiting desks localized; Assistant English-only chrome.
8. **Overlays lack Escape / focus restore** — History + new-chat dialogs.
9. **No React Profiler / interaction marks** — Cannot prove send/stream/open/confirm cost.
10. **Local `action_registry.py` truncation risk** — Workspace file appears truncated vs evidence/full registry; treat as integrity risk for local/staging parity (verify production SHA separately).

### Medium
11. Privacy/instruction conflict (`cv_text` in prompt vs privacy denylist).
12. Confirmation button always sends English “Yes, confirm it” (works with Arabic approval regex on backend, but UX is EN).
13. Thin admin-audit for chat tools vs button desks.
14. Candidate cards may surface score/reasons without linking to Ranking contract labels.
15. Empty chips can include post-hire modules without clarifying Assistant ≠ those desks’ authority.

### Leave alone
- Confirmation card pattern for sensitive actions
- Session persistence scoped by company + actor
- Module gates on Assessments/Interviews tool chips
- Candidate card → live `openCandidateByKey`
- New-chat cancels pending confirmations
- Cream panel / transcript / composer composition (structure)
- Enter-to-send composer

---

## Recommended product direction (Wathefni)

**Calm HR copilot** — not a generic chatbot:

1. **One job:** explain what HR should do next and why, using real company data; execute only through backend authority.
2. **Ground every claim** — prefer tool results over free memory; show quiet “based on live records” / empty/error/partial states.
3. **Actions = controlled** — keep registry + confirmation + OCC; make confirmation UI the primary action surface (preview → confirm), not chatty re-asks.
4. **Kill chatbot noise** — remove wording-only nav chips; fix `assistant_prompt` chips; dashboard-specific system prompt (not WhatsApp).
5. **Respect desks** — deep-link to Overview/Jobs/Candidates/… with live filters; never replace Ranking/Reports/Assessments contracts.
6. **Visual** — warm cream, strong black type, restrained color, less is more; preserve current composition; no broad redesign.
7. **AR/RTL + Profiler** before polish — locale, Escape/focus, marks for send / stream-done / open card / confirm.

---

## Exact files

### Dashboard
- `apps/wathefni-dashboard/src/pages/AdminAIPage.tsx`
- `apps/wathefni-dashboard/src/App.tsx` (`askDashboardAssistant`, sessions, nav)
- `apps/wathefni-dashboard/src/lib/api.ts` (`streamDashboardChat`)
- `apps/wathefni-dashboard/src/types.ts` (chat types)
- `apps/wathefni-dashboard/src/pages/lazy.tsx`

### Backend
- `wathefni-orchestrator/tool_call_orchestrator.py` (`TOOLCALL_SYSTEM`, turn loop)
- `wathefni-orchestrator/action_registry.py` (tools — verify full registry on prod)
- `wathefni-orchestrator/assistant_privacy.py`
- `wathefni-orchestrator/assistant_jobs_ux.py`
- `wathefni-orchestrator/assistant_policy.py` (unwired)
- `wathefni-orchestrator/app.py` (`/dashboard/prehire/chat*`, `dashboard_chat_artifacts`)

---

## Current action / tool authority (summary)

```
UI message
  → POST /dashboard/prehire/chat/stream (prehire.read)
  → handle_toolcall_whatsapp_turn
  → visible tools (module + permission)
  → preflight / needs_confirmation / execute via action_registry
  → action_results + pending_actions (OCC on lifecycle)
  → dashboard_chat_artifacts (cards, confirmation, nav)
  → SSE typing → synthetic deltas → done
```

Mutations require registry confirmation where marked SENSITIVE / PREFLIGHT-THEN-CONFIRM. Reads use DB-backed tools. Free replies may skip tools.

---

## PASS / FAIL

| Check | Result |
|---|---|
| Backend mutations gated by permissions + confirmation | **PASS** (registry path) |
| Session tenant + actor isolation | **PASS** |
| Candidate open resolves live authority | **PASS** |
| Module gates for Assessments/Interviews tool chips | **PASS** |
| Grounded calm HR-copilot UX | **FAIL** (WhatsApp chatbot framing + free-reply + wording chips) |
| No dead / misleading action affordances | **FAIL** (`assistant_prompt` nav; wording chips) |
| Real streaming + cancel | **FAIL** |
| Reports/Overview boundary enforced in Assistant | **FAIL** (policy unwired) |
| AR/RTL + overlay a11y | **FAIL** |
| React Profiler evidence | **FAIL** (absent) |
| **Overall (ready for UI polish)** | **FAIL** |

---

## Implementation / deploy

**Not started** (audit only). Do not redesign or implement until the product direction above is approved; then prioritize identity/system-prompt, dead chips, grounding, a11y/RTL, real stream/cancel, Profiler — without broad layout redesign.
