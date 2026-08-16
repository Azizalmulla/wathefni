# Employees 360 Wave 6 — Final UX & workflow refinement

**Stamp:** `20260801T231034Z`  
**Evidence:** `ops/evidence/employees360-wave6-ux-20260801T231034Z/`  
**Scope:** Local implementation + **staging** prove  
**Production deploy:** **NOT DONE**  
**Real lifecycle / ESS rollout / Wave 7 / pre-hire / Wave D:** **UNTOUCHED**

---

## Verdict: **PASS**

| Gate | Result |
|---|---|
| Local dashboard build | **PASS** |
| Unit tests (chrome + nav) | **13/13 PASS** |
| Staging Wave 3–5 API smoke (auth) | **PASS** (remediation/org/lifecycle/ESS) |
| Staging dashboard dist sync | **PASS** (Workforce nav visible) |
| EN/AR + desktop/mobile screenshots | **PASS** (captured) |
| RTL (`main[dir=rtl]` in AR) | **PASS** |
| Production orchestrator unchanged for Wave 6 routes | **PASS** (`employee-lifecycle/remediation` absent on prod) |
| Authority bypass in UI | **PASS** (API-only; approve ≠ apply; bank masked) |

---

## Implemented UX changes
1. **Employees directory** — quiet board table, cream identity rows, status column, deep-link `?employee=`.
2. **Employee profile** — status reason/reference via `ConfirmDialog` (no `window.prompt` for status); Wave 4 assignment history; masked ESS bank panel.
3. **Workforce hub** (`?page=workforce`) — Organization · Lifecycle · Remediation · Migration · Requests with section rail, blocked reasons, conflict banner, confirmations for commit/rollback/apply.
4. **EN/AR labels** for Workforce nav + subtitles; hub `dir` follows locale.

## Shared components
**Reused:** `Card`, `PageIntro`, `StatusPill`, `SearchInput`, `Button`, `Badge`, `ConfirmDialog`, pre-hire tokens.  
**New:** `MaskedField`, `ApprovalStrip`, `ConflictBanner`, `RecordEpoch`, `BlockedReason`, `WorkflowEmpty`, `WorkforceSectionRail`, `QuietStat`.

## Staging proof
| Check | Result |
|---|---|
| Remediation queue | `count=10` |
| Org units | `4` |
| Migration batches list | `0` (empty OK) |
| Lifecycle pending | `0` (empty OK; lifecycle enabled on staging for UX) |
| ESS policy | `enabled=true` |
| Screenshots | `screenshots/en-desktop|ar-desktop|en-mobile|ar-mobile/` |

Thin **read-only** staging endpoints added (not on production):
- `GET /dashboard/posthire/employee-lifecycle/remediation`
- `GET /dashboard/posthire/employee-org/migration-batches`

Staging also received `employee_policy_packs_wave3h.py` sync so remediation list works, plus lifecycle V3 env for pending queue visibility. **Production app.py was not updated with these routes.**

## Tests
- `src/posthire/employees360/chrome.test.tsx`
- `src/lib/moduleWorkspace.test.ts` (includes `workforce` nav page)

## Remaining risks
1. Some profile document flows still use `window.prompt` (activation handoff / doc reject) — not Wave 6 primary paths.
2. Staging lifecycle was enabled for UX prove; keep synthetic-only; do not lift for real employees.
3. Employee-facing mobile ESS app not redesigned (`EMPLOYEE_APP` remains off).
4. Remediation UI is read-only by design — classification still dual-control backend.
5. Screenshot probe reads `documentElement.lang` inconsistently; `main[dir=rtl]` is the shell source of truth (verified).

## Explicit non-goals (honored)
No production deploy · no real-employee onboarding/classification · no real lifecycle/ESS rollout · no Wave 7 · no pre-hiring/Wave D changes.
