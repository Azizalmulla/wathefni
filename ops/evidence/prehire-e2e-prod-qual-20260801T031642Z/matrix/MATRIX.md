# Pre-hiring E2E production qualification — full test matrix

**Stamp:** `20260801T031642Z`  
**Mode:** Production live qualification — **no product redesign / no feature adds**  
**Host:** `https://api.wathefni.ai` · dashboard chunk `dashboard-CmztGRNg.js`  
**Tenant under test (primary):** `WATHEFNI` owner session  
**Delivery:** prefer read-only + dry_run; mutations only when idempotent/safe and logged

Legend: `P` planned · `PASS` · `FAIL` · `BLOCKED` · `SKIP` (unsafe/unavailable) · `EVID` prior evidence accepted with freshness note

---

## Cross-cutting

| ID | Case | Happy | Perm/tenant | Dup/idem | Fail/retry/cancel/rollback | EN/AR RTL | Desk/mob | Contract |
|---|---|---|---|---|---|---|---|---|
| X01 | Health 200 + dashboard HTML refs live chunk | P | — | — | — | — | — | P |
| X02 | Bootstrap + enabled_modules + access permissions | P | P | — | — | — | — | P |
| X03 | Cross-company token cannot read WATHEFNI apps (isolation) | — | P | — | P | — | — | P |
| X04 | Missing auth → 401/403 closed | — | P | — | P | — | — | — |
| X05 | Locale EN↔AR persists; RTL on AR | P | — | — | — | P | P | — |
| X06 | Smoothness: sticky page / skeletons (cite deploy) | EVID | — | — | — | P | P | P |

---

## Overview

| ID | Case | Paths |
|---|---|---|
| OV01 | Summary loads (counts, recent, role_priority) | happy, contract |
| OV02 | Work-queue scope `mine` | happy, contract |
| OV03 | Work-queue scope `company` (owner) | happy, perm |
| OV04 | Scope persist `wathefni_work_queue_scope` — no Company→My flicker | contract, desk |
| OV05 | Cohort CTAs deep-link Candidates/Assessments with durable URL keys | contract |
| OV06 | Next-action endpoint | happy |
| OV07 | Overview calendar mine panel | happy |
| OV08 | Recruiter without company scope cannot elevate | perm |
| OV09 | AR overview RTL | EN/AR, mobile |

---

## Jobs

| ID | Case | Paths |
|---|---|---|
| JB01 | Positions list + status tiles/summary | happy, contract |
| JB02 | Filter status/department/location | happy |
| JB03 | Position detail / application_link / apply code present for open | happy, contract |
| JB04 | Create draft (dry or skip if unsafe) | happy / SKIP |
| JB05 | Publish/pause/close transitions authority | fail/idem note |
| JB06 | Duplicate create same code rejected | dup |
| JB07 | Role without jobs.create cannot mutate | perm |
| JB08 | EN/AR jobs page | locale |
| JB09 | Mobile jobs list | mobile |

---

## CV / email ingestion

| ID | Case | Paths |
|---|---|---|
| IN01 | Mailbox connections status readable | happy, contract |
| IN02 | Import settings / intake list | happy |
| IN03 | Import batches recent | happy |
| IN04 | Email sending settings (outbound policy surface) | happy, contract |
| IN05 | Held/notify / intake review surface if present | happy |
| IN06 | Idempotent re-ingest same message (contract / prior EVID) | dup, EVID |
| IN07 | Failure path: bad mailbox / disconnected | fail |
| IN08 | Tenant isolation on import APIs | perm |

---

## Candidates

| ID | Case | Paths |
|---|---|---|
| CA01 | Unified applications list loads | happy |
| CA02 | Feature flags: unified + classification | contract |
| CA03 | URL durable filters round-trip (q,status,view,position,follow_up,…) | contract |
| CA04 | Follow-up clear drops context keys | contract |
| CA05 | Saved views list / select replace (not merge) | contract |
| CA06 | Profile + person profile for sample app | happy |
| CA07 | Stage toolbar buckets | contract |
| CA08 | Skeleton not empty-flash (smoothness EVID + live) | contract |
| CA09 | Cross-tenant app_key denied | perm |
| CA10 | Duplicate notify/assessment blocked or idempotent | dup |
| CA11 | AR RTL candidates + mobile sheet | locale, mobile |
| CA12 | Filter drawer/sheet Wave4 | happy, desk/mob |

---

## Ranking

| ID | Case | Paths |
|---|---|---|
| RK01 | Rank for open position loads | happy |
| RK02 | Top-N from rankable pool only | contract |
| RK03 | Ranking does not mutate lifecycle | contract |
| RK04 | Recalculate idempotent / audit | dup |
| RK05 | Missing position → empty/neutral not crash | fail |
| RK06 | No jobs.create/candidates.read role scoping | perm |
| RK07 | EN/AR ranking | locale |

---

## Assessments

| ID | Case | Paths |
|---|---|---|
| AS01 | Config loads; module enabled | happy |
| AS02 | Queue cohorts: send/pending/in_progress/resend/failed | contract |
| AS03 | Attempts list + needs_review + reports tabs | contract |
| AS04 | Surface tabs not overwritten by cohort URL write | contract |
| AS05 | Report payload for completed attempt | happy |
| AS06 | Resend / cancel paths (safe/dry) | fail/retry/cancel |
| AS07 | Module-off tenant blocks send (EVID Jul25 or live if available) | perm, EVID |
| AS08 | Duplicate send invitation | dup |
| AS09 | AR assessments RTL | locale |

---

## Interviews

| ID | Case | Paths |
|---|---|---|
| IV01 | Interviews list tabs upcoming/needs_feedback/video/completed | happy, contract |
| IV02 | Video tab gated by `video_interviews` module | perm, contract |
| IV03 | Schedule path authority (dry or EVID) | happy, EVID |
| IV04 | Reschedule same id / no duplicate event | dup, EVID |
| IV05 | Cancel interview | cancel, EVID |
| IV06 | Feedback / notes surfaces | happy |
| IV07 | EN/AR interviews | locale |

---

## Calendar

| ID | Case | Paths |
|---|---|---|
| CL01 | Events `scope=mine` | happy |
| CL02 | Team scopes list; unauthorized hidden | perm |
| CL03 | Company scope requires `calendar.company` | perm |
| CL04 | Sync connections (microsoft/google) status | contract |
| CL05 | Mobile day view — no week→day snap | contract, mobile |
| CL06 | Create/cancel dry or EVID | fail/cancel, EVID |
| CL07 | Conflicts / free-busy if exposed | happy |
| CL08 | AR calendar | locale |

---

## Microsoft Teams + outbound email

| ID | Case | Paths |
|---|---|---|
| TM01 | Teams meeting joinUrl live (recheck or EVID freshness) | happy |
| TM02 | Calendar event linked + Asia/Kuwait | contract |
| TM03 | Outside AAP denied | perm |
| TM04 | Invitation email Sent Items | happy |
| TM05 | Reschedule same id; cancel 204 | dup, cancel |
| ML01 | Outbound evidence mailbox allow | happy |
| ML02 | Outside-scope send 403 | perm |
| ML03 | Dashboard email settings reflect provider | contract |
| ML04 | Assistant/calendar Teams wiring present | contract |

---

## Reports

| ID | Case | Paths |
|---|---|---|
| RP01 | Reports payload locale=en | happy |
| RP02 | Reports payload locale=ar | locale |
| RP03 | Skeleton not empty-flash | contract |
| RP04 | Export type endpoints (if any) audit-only | happy / fail |
| RP05 | Disabled-module wording absent when OFF (EVID) | perm, EVID |
| RP06 | Mobile reports | mobile |

---

## Assistant

| ID | Case | Paths |
|---|---|---|
| AI01 | Capabilities empty_state EN | happy |
| AI02 | Capabilities empty_state AR | locale |
| AI03 | Chat sessions list | happy |
| AI04 | Proposal requires human confirm (no silent decision) | perm, contract |
| AI05 | Tools respect module entitlements | perm |
| AI06 | Teams/calendar tool wiring | contract, EVID |
| AI07 | Empty chrome no spinner flash on revisit | contract |
| AI08 | Mobile assistant | mobile |

---

## Execution order

1. Cross-cutting health/bootstrap/auth  
2. API read matrix per module  
3. UI EN desktop → AR desktop → EN mobile → AR mobile screenshots  
4. Contract spot-checks (URL, cohorts, scopes)  
5. Teams/mail freshness (status + cite or re-prove)  
6. Permission/isolation probes  
7. Compile failures/ + PASS/FAIL + repair waves  

**No fixes until matrix complete.**
