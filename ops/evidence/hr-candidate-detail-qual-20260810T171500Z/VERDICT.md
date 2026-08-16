# HR Candidate detail — physical-surface qualification

Stamp: `20260810T171500Z`  
Surface: `/hr/candidates/[appKey]` · `CandidateReviewView` + `app/hr/candidates/[appKey].tsx`  
Actor: Aziz owner `96599338566`  
Fixture: import `imp-wathefni-3bda14696342799f-WATHEFNI-IMPORT` (ready_for_review · shortlist/reject)  
Terminal: `imp-wathefni-511c5f998f9f75cd-WATHEFNI-IMPORT` (import_archived · no decide actions)

## Functional verdict: **CONDITIONAL — do not lock yet**

Backend mobile candidate SOD prepare path is sound for canary. The **shipped UI matches Leave’s pre-fix honesty/visual debt** and must not freeze until cream + honesty land (same pattern as Leave).

### Exercised (host, production helpers)

| Check | Result |
| --- | --- |
| Detail for ready_for_review import | stage ready_for_review · actions shortlist/reject + CV · cv `q2.pdf` |
| Ranking score | null · `ai_advisory=true` · evidence empty (honest empty → UI placeholders) |
| Offer key present on payload | `offer` in keys — **UI does not render** |
| Prepare shortlist | needs_confirmation · EN consequence `Move … to the shortlist for IT manager.` |
| Confirm | **not run** on live import (preserve pipeline); prepare-only |
| Terminal archived | decide actions `[]` · CV only |
| `mobile_candidate_rankings` | **0 items** while DB has ready_for_review — Hiring list entry may be empty |
| Priorities `candidate_decisions` | empty at probe time (Hiring section type present) |
| Entry path | Hiring / list / Assistant — **not** Home/Inbox |

### Client / honesty gaps (block lock)

1. **Legacy visual** — `@hr/theme` `Screen`/`WorkspaceHeader` + cream/sage/amber/lilac/sky card stack + plum score ring (not Leave cream `PageScreen`/`HrPushedNav`).
2. **Always `tone="info"` badge** — not stage-driven (hired/rejected look the same).
3. **`#appKey` chrome** — raw id slice (Leave froze this away).
4. **EN-only CV fallback** — `"No CV available"` hard-coded.
5. **EN-only prepare fallback consequences** in view if prepare fails; route passes **raw server consequence** (English) with no Leave-style i18n map.
6. **`already_decided` unwired** — API raises `already_decided` on prepare for terminal stages; route never maps to a decided panel (shows ready + `candidate.noActions` or empty decide).
7. **Offer (and assessment if present) not shown** despite payload keys — honesty gap if Hiring deep-links imply offer context.
8. **`schedule_interview` UI** still gated on allowed_actions (usually absent — dead path OK).
9. **Rankings list empty** — detail-by-key works; queue discovery may fail for imports (investigate before claiming Hiring entry green).

### Not blocking (acceptable under controlled canary)

- Action button labels already use `candidate.*` i18n; confirm sheet action uses `lifecycleActionLabel`.
- SOD prepare→confirm spine + invalidation pattern mirrors Leave (preserve).
- Safe-back via `useHrSafeBack`.

## Exact visual / honesty changes recommended (no workflow expansion)

1. Migrate to cream `PageScreen` + `HrPushedNav`; one cream surface + one attention callout (e.g. not-informed).
2. Status chip tone from canonical stage (success/danger/warning/neutral).
3. Demote/remove `#xxxxxxxx` app_key chrome.
4. Localize CV empty + consequence templates EN/AR (known EN patterns → i18n; unknown passthrough).
5. Wire `already_decided` when stage terminal / no decide actions (or on API `already_decided`).
6. Optionally surface honest offer summary if payload present — or explicitly omit with no fake claim.
7. Diagnose why `mobile_candidate_rankings` returns 0 for ready imports.

## Lock criteria for Candidate

- [ ] Cream migration + hierarchy simplify
- [ ] Stage tone + no raw `#id` chrome
- [ ] Consequence + CV empty EN/AR
- [ ] `already_decided` / terminal non-actionable
- [ ] One physical EN+AR pass
- [ ] Then stamp canary PASS and freeze

Evidence: this folder (`qualify-run*.txt`, `db-find-candidates.txt`, `client-gap-scan.txt`, probes).
