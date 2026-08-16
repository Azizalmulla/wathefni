# Employees 360 Wave 3C — Lifecycle production-safety checklist (local/staging)

**Stamp:** `20260801T204413Z`  
**Evidence:** `ops/evidence/employees360-wave3c-lifecycle-safety-local-20260801T204413Z/`  
**Mode:** Implementation + staging qualification  
**Production deploy:** **NOT DONE**

Implements Wave 3B P0-1…P0-10 on Wave 3 PASS baseline. Builds on Wave 2 authority.

---

## Verdict

**PASS** (local/staging)

| Gate | Result |
|---|---|
| P0-1 Company lifecycle policy config | PASS |
| P0-2 Mandatory impact ack + snapshot hash | PASS |
| P0-3 cancel_scheduled vs reinstate | PASS |
| P0-4 Access revoke at configured time (not approval) | PASS |
| P0-5 Staging scheduler (idempotent, retry, audit, lag) | PASS |
| P0-6 Same-employee_key true rehire | PASS |
| P0-7 Settlement packet inputs only (no amounts) | PASS |
| P0-8 Explicit audited downstream actions (reversible) | PASS |
| P0-9 Counsel checklist gate | PASS |
| P0-10 Staging requalification + rollback | PASS |
| Wave 3 unit/smoke remain green | PASS (22 + 51) |
| Wave 3C unit/smoke | PASS (10 + 40) |
| Production | **Not deployed** |
| Wave 4 / redesign / pre-hire / Wave D | Untouched |

---

## Exact implementation

| Component | Path |
|---|---|
| Wave 3C module | `wathefni-orchestrator/employee_lifecycle_wave3c.py` |
| Scheduler worker | `wathefni-orchestrator/lifecycle-effective-worker.py` |
| Staging systemd | `ops/wathefni-lifecycle-effective-staging.{service,timer}` |
| Dashboard APIs | Wave 3 routes upgraded in `app.py` (+ policy, counsel, downstream) |
| Schema version | `employees360-wave3c-lifecycle-safety-v1` |

### Product defaults enforced

- Timezone: `Asia/Kuwait`
- Effective termination: calendar date at 00:00 Kuwait (scheduler)
- App revoke: end of last working day (`23:59:59` Asia/Kuwait)
- SMB: warn-first + mandatory impact acknowledgment
- No self-approval (`allow_self_approval` CHECK false)
- No EOSB / pay-in-lieu calculations
- No automatic legal decisions

### Same-key rehire

When phone identity matches hub phone: new `employment_id` + `assignment_id`, remap authority map, keep hub `employee_key`. Prior employment remains `terminated`; its `legacy_employee_key` is released so uniqueness holds.

---

## Policy schema

Table `employee_lifecycle_company_policies` (per company):

- `tier` small|medium|enterprise  
- `timezone` (default Asia/Kuwait)  
- `notice_hint_monthly_days` / `notice_hint_other_days` (hints only)  
- `revoke_mode` end_of_last_working_day|start_of_effective_date|immediate_on_summary  
- `downstream_mode` warn_first|…  
- `require_impact_ack`, `require_counsel_gate`, `rehire_same_employee_key`  
- `scheduler_cadence`, `lag_alert_seconds`  
- `allow_self_approval` forced false  

Related: counsel reviews, settlement packets, downstream actions, scheduler runs, request impact-ack columns, employment access_revoke_* columns.

DDL: `schema/wave3c-lifecycle-safety-schema.sql`

---

## Scheduler / service design

```
wathefni-lifecycle-effective-staging.timer (hourly, Persistent)
  → wathefni-lifecycle-effective-staging.service (oneshot)
      → lifecycle-effective-worker.py
          → run_lifecycle_scheduler(company)
              1) execute_due_scheduled_terminations (idempotent)
              2) stamp events with run_id
              3) revoke_due_app_access
              4) compute lag; alert if lag_seconds >= policy threshold
              5) journal employee_lifecycle_scheduler_runs
```

Failed tick records `status=failed`; next tick retries without duplicate terminations (rows already `terminated` are skipped).

Staging timer **enabled**. Production timer **not installed**.

---

## Staging evidence

| Artifact | Result |
|---|---|
| `verify/unit.log` | 10/10 |
| `verify/staging-smoke.log` | Wave3C 40/40 + Wave3 51/51 |
| `verify/staging-ops.txt` | timer enabled; prod module absent |
| Proved | future term via scheduler; failed run retry; access active then revoked; cancel-before-effective same employment; reinstate same employment no silent session restore; same-key rehire; settlement inputs only; downstream approve+reverse; rollback |

---

## Unresolved counsel questions

Still require human counsel (system only records checklist answers; does not decide law):

1. KW notice floors for Wathefni contract types  
2. UI notice-suggestion representation risk  
3. Confirm no pay-in-lieu math in Employees 360  
4. EOSB / leave encashment ownership in Payroll  
5. Summary dismissal evidence standard  
6. Reinstate continuity vs broken service  
7. Job-search day tracking  
8. Document retention / legal hold  
9. Cross-border notice regime  
10. Auto-decline leave / auto-cancel shifts practice  

Gate: `employee_lifecycle_counsel_reviews` + `WATHEFNI_LIFECYCLE_COUNSEL_GATE` (staging signed for synthetic proofs).

---

## Production deployment checklist (future — not executed)

1. Counsel answers reviewed/signed for production checklist version  
2. Copy wave3c module + worker + app routes to prod orchestrator  
3. Install **production** timer only after staging soak  
4. Flags: `WATHEFNI_EMPLOYEE_LIFECYCLE_V3=on` + companies=`WATHEFNI` only  
5. Keep `WATHEFNI_LIFECYCLE_COUNSEL_GATE=on`  
6. Canary: synthetic then one dual-control real case  
7. Monitor scheduler lag alerts  
8. Rollback plan: flag off + `rollback_lifecycle_wave3c` scoped keys  
9. Do **not** enable Wave 4 / UI redesign in this deploy  

---

## Explicit non-goals honored

- No production deploy of lifecycle feature paths beyond staging timer install  
- No Wave 4  
- No Employees 360 redesign  
- No frozen pre-hiring / Wave D changes  
