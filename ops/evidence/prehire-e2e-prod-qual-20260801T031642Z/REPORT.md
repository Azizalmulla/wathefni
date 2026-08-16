# Pre-hiring E2E production qualification — REPORT

**Stamp:** `20260801T031642Z`  
**Verdict:** **PASS WITH FINDINGS** (1× P3 product defect; mutation/idempotency paths accepted from prior freeze packs — not re-mutated this run)  
**Host:** `https://api.wathefni.ai` · health local **200** · dashboard chunk `dashboard-CmztGRNg.js`  
**Primary tenant:** `WATHEFNI` owner  
**Mode:** Qualification only — **no redesign / no feature adds / no fixes applied**

Evidence root:  
`/Users/azizalmulla/Desktop/claw/ops/evidence/prehire-e2e-prod-qual-20260801T031642Z`

---

## Executive summary

Live production surfaces for Overview → Assistant were exercised via API + Playwright (EN/AR × desktop/mobile), plus connection/settings probes for Teams/email/ingestion. Happy-path reads and UI navigation **pass**. One low-severity orphan API route returns **500** instead of **404**. Full mutation/idempotency/cancel/rollback authority remains pinned to the Jul 25 lifecycle freeze and Jul 30–31 M365 packs (cited; not re-executed to avoid duplicate Graph/hire noise).

| Suite | Passed | Failed | Total |
|---|---:|---:|---:|
| API live gates | 46 | 1 | 47 |
| UI live gates | 40 | 0 | 40 |
| **Combined** | **86** | **1** | **87** |
| Screenshots | 37 | — | — |

---

## PASS / FAIL per module

| Module | Verdict | Live gates | Notes |
|---|---|---|---|
| Overview | **PASS** | API+UI | mine/company work-queue, next-action, overview calendar |
| Jobs | **PASS** | API+UI | list, open apply linkage, EN/AR, mobile |
| CV/email ingestion | **PASS** | API | mailbox/email/import settings readable; mailbox **feature.enabled=false** on this tenant (observation) |
| Candidates | **PASS** | API+UI | list, profile, follow-up filter, saved views, RTL, mobile |
| Ranking | **PASS** | API+UI | rank by position; missing position neutral |
| Assessments | **FAIL** | API+UI | UI/cohort path PASS; orphan `/assessments/queue` → **500** (P3) |
| Interviews | **PASS** | API+UI | upcoming + tab filters; video module ON |
| Calendar | **PASS** | API+UI | events with start/end; scopes; sync connections present (Google disconnected) |
| Microsoft Teams + outbound email | **PASS** | status + prior EVID | email integrations `ready`; Teams meeting matrix / outbound deny-allow cited |
| Reports | **PASS** | API+UI | EN+AR payloads; UI all viewports |
| Assistant | **PASS** | API+UI | capabilities EN/AR; sessions; UI all viewports |
| Cross-cutting | **PASS** | API+UI | auth fail-closed, foreign company closed, back/forward, RTL |

---

## Full test matrix coverage

Canonical plan: `matrix/MATRIX.md`

| Path class | Coverage this run |
|---|---|
| Happy paths | **Live** API+UI for all listed modules |
| Permissions / tenant isolation | Invalid token; foreign `X-Company-Code`; company calendar scope; prior follow-up tenant pack |
| Duplicate / idempotency | **Cited** Jul 25 freeze (hire/confirm/token) + Teams reschedule same-id; not re-mutated |
| Failure / retry / cancel / rollback | **Cited** Teams cancel, mail deny, lifecycle stale_version; dashboard rollback scripts not in scope |
| EN/AR + RTL | **Live** UI desktop+mobile; Reports/Assistant capabilities AR |
| Desktop / mobile | **Live** 1440×900 and 390×844 |
| Production data contracts | Assessments `tab=reports`; applications cohort filters; calendar start/end; work-queue scopes |

---

## Blockers ranked by severity

| Sev | ID | Module | Finding | Blocks ship? |
|---|---|---|---|---|
| **P3** | `AS02_orphan_route` | Assessments | `GET /dashboard/prehire/assessments/queue` → HTTP 500 plain text; UI uses applications cohort (200) | **No** — hygiene / fail-closed |

### Observations (not failures)

1. Mailbox intake feature `enabled: false` for WATHEFNI while email sending status is `ready` (Wathefni sender).  
2. Google calendar sync connection present but `status: disconnected`.  
3. Public `https://api.wathefni.ai/health` → 404 (edge); host `127.0.0.1:8010/health` → 200.  
4. Fresh Graph Teams create/cancel and outbound mail allow/deny **not** re-run; prior packs ≤3 days old accepted (`verify/PRIOR_EVIDENCE.md`).

Failure artifact: `failures/AS02_orphan_route.json`

---

## Recommended repair waves (do not start until approved)

### Wave A — Assessments orphan route hygiene (P3)
- Map unknown `/dashboard/prehire/assessments/queue` (and similar) to **404 JSON**, not 500.  
- Smoke: non-UI assessment paths fail closed.  
- No UI behavior change expected.

### Wave B — Optional freshness recheck (integrations)
- Re-run `prove-m365-teams-meeting.py` + outbound mail allow/deny if AAP/mail SP changes suspected.  
- Confirm Microsoft calendar connection health in UI settings.

### Wave C — Lifecycle mutation requal (scheduled)
- Re-run synthetic-tenant matrix (`FQ*`) with `dry_run` delivery when freeze age or orchestrator SHA drifts — hire atomicity, confirmation single-use, AI cannot decide.

### Wave D — Ingestion posture (product decision)
- If inbound CV mailbox is required for this tenant: enable mailbox feature and qualify check-now / idempotent re-ingest.  
- Else document intentional disable.

**No post-hiring refinement in these waves.**

---

## Key live proofs

| Proof | Result | Artifact |
|---|---|---|
| Bootstrap modules include pre_hiring, assessments, interviews, video_interviews | PASS | `verify/api-results.json` |
| Applications list + sample profile | PASS | api-results |
| Assessment send cohort via applications | PASS (2 apps) | api corrections |
| Calendar mine/company with `start`/`end` | PASS | api corrections |
| Assessments `tab=reports` URL preserved | PASS | `UI_AS04_tab_reports` |
| EN/AR RTL desktop+mobile all pages | PASS | `verify/ui-results.json` + `screenshots/` |
| Email integrations ready | PASS | `verify/email-integrations.json` |
| Calendar sync connections readable | PASS | `verify/calendar-sync-connections.json` |

---

## What was deliberately not mutated

- No new job publish/close, assessment send/resend/cancel, interview schedule, hire, or offer transitions on the live WATHEFNI tenant.  
- No new Teams OnlineMeeting or outbound Graph send.  
Authority for those paths remains the cited freeze/M365 evidence until Wave B/C.

---

## Final

**Overall: PASS WITH FINDINGS**  
**Modules failed:** Assessments (P3 orphan route only)  
**Next:** approve Wave A (and optionally B–D); do not start post-hire refinement.
