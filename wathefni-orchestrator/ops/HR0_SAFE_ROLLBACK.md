# HR-0 / HR-0A — Security-preserving rollback

**Status:** Binding for staging and production incident response after HR-0.

## Goal

Recover service availability **without** restoring closed security holes.

## Must NOT restore (normal rollback)

Normal rollback must **never** re-introduce:

1. Company-wide employee visibility for unscoped `manager` operators
2. `legacy_untrusted` shared-token dashboard authority on production/staging-like paths
3. Unauthenticated legacy `ai-recruiter` `/internal/*` routes
4. Candidate CV view/preview/download without audit attempts

## Preferred recovery order

1. **Disable the affected workflow** (feature flag / module / route gate) if a functional regression is isolated.
2. **Keep fail-closed authority and quarantine controls** in place:
   - manager-scope fail-closed
   - legacy dashboard token auth disabled / startup refuse
   - legacy recruiter `/internal` disabled + localhost bind
   - CV audit hooks (fail-open on audit sink errors is intentional for authorized reads)
3. **Revert only the functional wiring** that caused the incident (for example an attendance filter bug), via a targeted fix-forward commit preferred over full artifact restore.
4. **Leave additive schema in place**: `manager_scopes.dashboard_user_id` column and `idx_manager_scopes_user` are safe to retain.

## Staging / production artifact rollback

If `ops/deploy.sh rollback` is used for a production outage:

- Restores the last pre-deploy orchestrator + dashboard snapshot.
- **Before returning traffic to normal**, confirm the restored artifact still includes HR-0 authority controls. If the snapshot predates HR-0, **do not** use this path for HR-0 regressions — fix-forward instead, or restore a post-HR-0 known-good snapshot.
- Re-run:
  - `GET /health` and `GET /ready` → `permission_authority=backend_current_required`
  - shared-token `/dashboard/auth/me` → 401/403
  - manager without scopes → empty employee set
  - `curl` to any legacy `/internal` public path → not reachable / 404

## Exceptional emergency rollback (security impact — explicit)

Use only if a post-HR-0 build is catastrophically unavailable and no post-HR-0 snapshot exists.

| Action | Security impact |
| --- | --- |
| Restore pre-HR-0 orchestrator artifact | **HIGH** — may reopen manager fail-open, legacy_untrusted, unaudited CV |
| Re-enable `WATHEFNI_ALLOW_LEGACY_DASHBOARD_TOKEN_AUTH` outside test harness | **CRITICAL** — forbidden; startup must refuse |
| Re-publish legacy recruiter `/internal` publicly | **CRITICAL** — forbidden |
| Drop `dashboard_user_id` column | **Unnecessary** — do not drop during emergency |

If an exceptional pre-HR-0 restore is unavoidable:

1. Record incident ticket + approver.
2. Immediately re-apply HR-0 authority commits (`e83d483` lineage / successor) as the next change.
3. Keep legacy recruiter quarantined at the network edge even if app code temporarily regresses.
4. Treat the window as a security incident, not a routine rollback.

## Database

- Additive `dashboard_user_id` column/index: **retain**.
- No broad production backfill required for rollback.
- Throwaway HR-0A harness companies (`HR0ASTG`, `HR0AOTH`) may be deleted freely.
