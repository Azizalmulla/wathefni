# Employee App P1 — Phase 1 (Home, tasks, safe navigation)

Stamp: `20260808T062710Z` · base commit `cf26d59512a22a7634eb4edd28b4425ec1624405` (+ working tree, see `source-sha256.txt`)

Owner review is **not** requested for this phase. Canary rollout stays Aziz/Talal only.
Backend change is deployed to production; the client change is JS-only and OTA-eligible.

## What shipped

1. **Server-owned Home projection: `GET /app/home`.**
   One self-scoped read that aggregates what the owning modules already say — today's
   shift, today's attendance, the 30-day attendance summary, onboarding's own completion
   contract, actionable tasks, and inbox unread. Home no longer issues five module
   requests and re-derives workflow rules from status strings.

   Every module carries its own `disabled | error | ready` state. A module that could not
   be read reports `error` and carries **no value**, so an unavailable read can never
   reach the client as an empty business fact. Each module read runs inside its own
   `SAVEPOINT`, so one failing read cannot abort its siblings — proven with an injected
   SQL error, not a Python exception.

   Home is not a second entitlement registry: module state comes from the same
   `employee_app_feature_contract_for_context` used everywhere else, so `documents` is
   still entitled by `onboarding` OR `compliance` and `payslips` by `payroll`.

2. **Tasks are the owning modules' facts, counted — never re-decided by Home.**
   `onboarding_documents` (onboarding's `next_action.party == employee` + outstanding
   count), `document_renewal` (Documents' own `renewal_required`), `leave_pending`
   (Leave's own pending rows), `payslip_released` (Payroll's released set **intersected
   with** Inbox's unread set — an unread payroll message alone cannot invent a payslip).
   The server emits `kind`, `count`, `severity`; it never emits a client route.

3. **Today's attendance is today's record.** The previous Home showed the newest row in
   the 30-day window as if it were today. The projection selects the row dated with the
   Kuwait business day, and the window summary stays separate.

4. **Shared module reads, one query per fact.** `/app/shifts/today`,
   `/app/shifts/upcoming`, `/app/attendance`, `/app/leave` and `/app/notifications` now
   call the same `_employee_*_rows` helpers the projection uses, so Home and the module
   screens cannot drift apart. Existing response shapes are unchanged.

5. **Strict client route registry.** `APP_ROUTES` in `employeeAppComposition.ts` lists
   every navigable destination once with the entitlement that owns it and the query
   parameters it reads. `resolveRoute` replaces substring path matching, which used to
   admit any path that merely *contained* a known word. Absolute URLs, scheme URLs,
   protocol-relative paths, traversal, undeclared parameters and malformed parameter
   values are all refused. `openableHref` returns the canonical href or `null`, and
   Inbox, Home and push all fall back calmly (Home, or an explained alert) instead of
   pushing a route that dead-ends.

6. **Simplified Home hierarchy.** Today → tasks → caught-up → onboarding progress →
   one entitled-destination list → primary action → Inbox. Onboarding no longer renders
   three competing CTAs (the attention card is gone; the task card is the action and the
   progress card is the progress), and Quick Actions no longer duplicate Documents,
   Leave and Payslips — `homeDestinations` is the single launcher, with Request leave as
   the only distinct primary action and only when the `leave.request` action is granted.

## Gates

Local (this machine), 12/12 PASS:

```
mobile typecheck (tsc --noEmit)                PASS
mobile PIN crypto selftest                     PASS
mobile entitlement composition shapes          PASS  (44 checks)
auth wave 2 phases 1–5 unit suites             PASS  (5 suites)
mobile capability + composition contract       PASS
backend modules compile                        PASS
employee app capability contract               PASS
```

Production orchestrator host, 11/11 PASS:

```
mobile capability + composition contract       PASS
backend modules compile                        PASS
employee app capability contract               PASS
employee app runtime access enforcement        PASS
employee app home projection contract          PASS  (29 checks, new)
employee app access eligibility matrix         PASS
employee app invitation + delivery             PASS
employee payslips P0 release gate              PASS
employee payslips P0.1 official PDF            PASS
employee↔HR sync hardening                     PASS
employee app session/self-scope regression     PASS  (staging EMPAPPTESTCO)
```

New gate `smoke-test-employee-app-home-projection.py` covers the zero / one / two /
four / full-suite entitlement shapes, disabled-module silence, injected read failure
with savepoint isolation, today-vs-window attendance, each task kind and its
disappearance with its module, locale handling, and `caught_up` honesty.

Service health after deploy: `systemctl is-active` active, `/health` 200,
`/app/home` unauthenticated → 401.

## Still open for later phases

- Physical iPhone A–F composition, RTL and slow/failing-module checks (Phase 4 gate).
- `/app/workday` unified Schedule projection (Phase 2).
- Documents current/attention/history hierarchy and Profile structure (Phase 3).

## Frozen and untouched

Setup Console, Auth Wave 2 phases 0–5, employee access policy storage/modes, Migration
& Sync, OCR/onboarding authority, Bank ESS authority and placement, Payroll Authority
seals/release/PDF eligibility. No payment date is invented. `employeeAppComposition.ts`
remains the single frontend composition derivation.

## Rollback

`ROLLBACK.sh` restores the previous `app.py` from
`/opt/wathefni/backups/employee-app-p1-home-20260808T062710Z` and restarts the service.
The client change is JS-only; roll back the OTA to the previous update ID. `/app/home`
simply disappears, and the previous Home client reads the module endpoints it always
read — their contracts were not changed.
