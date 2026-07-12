# Phase 8C2-R1D — Fail-closed emergency fallback

Staging-validated operating mode for use **before** any production approval of
the R1A/R1B/R1C authority model. This is **not** a rollback to the previous
fail-open production artifact.

## Non-goals (explicitly forbidden)

- Restoring any helper that treats missing/empty permissions as allow
  (`if not perms: return True` or equivalent).
- Restoring role-only authority for `employees.read`, `employees.manage`, or
  `employees.status.approve`.
- Restoring “missing means owner” session or grant fallbacks.
- Redeploying the pre-R1A production `app.py` hash as an approved recovery
  target.

## Retained invariants

1. Permission resolution remains **fail-closed**.
2. Role fallback for employee scopes remains **removed**.
3. Additive tables remain intact:
   - `dashboard_user_permission_grants`
   - `employee_status_changes`
4. Explicit grant correction remains the only recovery path for access.

## Approved fallback modes

### Mode A — Disable affected mutations (preferred)

Keep the fail-closed authority code deployed. Disable only the mutation surfaces
that would be unsafe without reviewed grants:

1. Keep protected flags off:
   - `WATHEFNI_EMPLOYEE_APP=off`
   - `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`
   - `WATHEFNI_ONBOARDING_SEED=off`
2. Leave `employee_app` company module disabled for non-reviewed companies.
3. Do **not** revoke the schema. Grants and status-change ledger stay available
   for audited correction.
4. Use `ops/dashboard-permission-authority.py` to inventory, grant, or revoke
   exact permissions with actor / reason / review reference.
5. Re-run `permission_authority_preflight` before re-enabling employee mutations.

### Mode B — Keep service up, deny employee writes

If a grant mistake is suspected:

1. Revoke the suspect explicit grants (do not widen role permissions).
2. Confirm open sessions lose the permission immediately
   (`permission_authority=backend_current`).
3. Require normal reauthentication for operators who only held recovery /
   bootstrap sessions.
4. Re-issue the reviewed matrix only after inventory + approval.

### Mode C — Code/service incident without authority regression

If the new mutation path itself is defective:

1. Keep the fail-closed permission helper in place.
2. Disable or gate the defective route/module only.
3. Leave additive tables intact for forensic read and later repair.
4. Ship a forward fix; do **not** restore fail-open permission evaluation.

## Verification checklist

- [ ] Health remains 200 on the affected environment.
- [ ] Protected flags remain `off`.
- [ ] `if not perms:` allow-path is absent from deployed `app.py`.
- [ ] Employee scopes are grant-only and distinct.
- [ ] No active `legacy_hr_phone_bootstrap` recovery sessions remain after cutover.
- [ ] Explicit grant correction works via the audited CLI.
- [ ] Production grants/sessions/flags/modules remain untouched until a separate
      production cutover is approved.

## Production note

R1D proved this fallback posture on **staging only**. Production remains on the
pre-cutover artifact until a separate production approval packages Mode A/B/C
with production-specific inventory, grants, and session revocation evidence.
