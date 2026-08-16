# Calendar Wave 1b — UX Closure + Freshness FREEZE

**Status:** FROZEN  
**Stamp:** `20260804T223738Z`  
**Builds on:** Rendering Stability Wave 2 (`20260804T223220Z`) · Calendar Wave 1 audit (`20260804T221643Z`)

## Frozen surface

- Sticky selected event + open drawer across range refresh (snapshot)
- Scroll capture/restore across day/week/month navigation
- Adjacent-range prefetch retained; TanStack abort = latest request wins
- Category colors use shared `wf-accent-*` / `wf-frame` tokens (category ≠ status)
- Clarified EN/AR category labels (`Personal time` / `وقت شخصي`, etc.)
- Manual Calendar CRUD + Interview ownership gates unchanged
- **No** new post-hiring event sources; synthetic preview remains review-only

## Freshness (low-risk)

Visibility-paused `refetchInterval` / soft poll on Overview work queue, Calendar, Candidates, Jobs, Interviews, Assessments, Alerts notifications + HR tasks loader, Needs Attention. Soft-keep content; no WebSockets/SSE; no backend authority changes.

## Hard bans

1. Do not add leave/onboarding/compliance/payroll/shifts calendar emitters without Calendar Wave 2 owner review.
2. Do not weaken interview schedule authority or `calendar.sync` owner-only.
3. Do not reintroduce local hex category fills or opacity-flash refresh chrome.
4. Do not enable focus-refetch that blanks queues.

## Rollback

See production evidence `ROLLBACK.sh` for this stamp.
