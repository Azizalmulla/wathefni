# Phase 8B — Production-dark deployment evidence

**Date:** 2026-07-12  
**Scope:** Deploy approved Phase 7E-R2 artifact to production while employee-app access remains dark.  
**Recommendation:** **production-dark green**

Phase 8B does **not** authorize company-module enablement, global employee-app enablement, pilot selection, or employee invitation. Those remain Phase 8C+.

## 1. Deployed commits and artifact hash

Accepted source commits present and deployed:

- `0c2ac61` — provider-aware document storage compensation
- `4a19250` — rejected-upload audit
- `cf77df8` — R2 verifier/timer evidence and ops wiring
- `d6b755f` — Phase 7E closure + Phase 8A plan docs

Exact verified artifact hash:

- `544d69b750f1ca9487eb7c867f8ae324f62395ef4440378057b95365d07d68c2`

Pre-deploy snapshot / rollback path:

- `/opt/wathefni/backups/phase8b/predeploy-20260712T111524Z`
- also recorded in `/opt/wathefni/backups/.last-predeploy`
- contains `orchestrator.tgz` and `dashboard-public.tgz`
- rollback command path verified: `ops/deploy.sh rollback`

## 2. Health before and after

| Check | Result |
|-------|--------|
| Health before | `200` |
| Health after | `200` |
| Orchestrator active after | `active` |

## 3. Migration result

- `ensure_schema(force=True)` → `prod schema ok`
- `document_storage_operations` created (`to_regclass` returns table)
- pinned dependency: `puremagic==2.2.0` present

## 4. Production reconciliation service/timer

| Unit | State |
|------|--------|
| `wathefni-document-storage-reconcile.timer` | **active and enabled** |
| `wathefni-document-storage-reconcile.service` | installed; one-shot exercised |

Before deploy: timer not-found / inactive.  
After deploy: timer installed, enabled, and active.

## 5. Reconciliation one-shot

- `Result=success`
- `ExecMainStatus=0`
- worker output: `{"ok": true, "processed": 0, "pruned": 0, "results": []}`

## 6. Storage operation counts

- total: `0`
- pending (`prepared`/`stored`/`deleting`/`compensation_pending`): `0`
- `manual_review`: `0`

## 7–8. Employee-app routes remain dark

Live production process (`127.0.0.1:8010`):

- `GET /app/me` → `503` `employee_app_disabled`
- `POST /app/auth/activate` → `503` `employee_app_disabled`

No company has `employee_app` enabled (`enabled_employee_app_count=0`).

## 9. Dashboard / bootstrap unchanged

Dashboard public aggregate hash before/after:

- before: `d9a95374392413b67d418c85b2637a6b7bb2786a8bdea86fce27718cca5a22ca`
- after:  `d9a95374392413b67d418c85b2637a6b7bb2786a8bdea86fce27718cca5a22ca`

Public edge checks:

- `/dashboard/auth/me` → JSON `401` (not SPA HTML)
- `/dashboard/setup/readiness` → JSON `401`
- `/dashboard/__routing_probe_should_404__` → JSON `404`
- `/dashboard` shell contains `#root`

## 10. Shared routing / Phase 7D unchanged

- `company_channel_accounts` remains disabled
- company outbound resolve returns shared default with `reason=flag_off`, `runtime_routing_changed=False`
- shared dry-run send uses `account_id=default` and does **not** include `channel_route`

## 11. Protected flags unchanged

Before and after restart:

- `WATHEFNI_EMPLOYEE_APP=off`
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`
- `WATHEFNI_ONBOARDING_SEED=off`

## 12. No tenant / invite / session / document fixtures

- enabled `employee_app` modules: none
- `employee_app_invites`: `0`
- `employee_sessions`: `0`
- phase fixture companies (`P7E%` / `PROPOSED%`): `0`
- no activation messages sent
- no production onboarding checklist rows created for a pilot
- no pilot tenant created or selected

## 13. Rollback command/path verified

- snapshot present at `/opt/wathefni/backups/phase8b/predeploy-20260712T111524Z`
- `orchestrator.tgz` and `dashboard-public.tgz` present
- `/opt/wathefni/backups/.last-predeploy` points at that snapshot
- `ops/deploy.sh rollback` path exists and is the approved restore command
- rollback was **not** executed because production-dark verification passed

## 14. Recommendation

**production-dark green**

Stop here. Do **not** proceed to:

- company `employee_app` module enablement
- global `WATHEFNI_EMPLOYEE_APP=on`
- pilot company selection/activation
- employee invitations
- one-employee canary

Those require a separate Phase 8C approval.
