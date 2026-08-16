# HR-0A Closure — Staging Gate

**Status:** `staging-green, authority-remediated, ready for HR-1 design and backend implementation`

**Date:** 2026-07-14  
**Branch:** `authority-cutover`  
**Accepted HR-0 commits on staging lineage:** `32903fd`, `34fd632`, `e83d483`, `a6fd2ab` (+ follow-ups `a20b086`, `42c0253`, and HR-0A runtime fixes below)

**Not started:** Wathefni HR frontend · HR-1 operator mobile auth UI · Employee App Expo workstream (unchanged, independent)

---

## 1. Staging deployment commit/hash and service health

| Item | Value |
| --- | --- |
| Staging service | `wathefni-orchestrator-staging.service` = **active** |
| Bind | `127.0.0.1:8011` (localhost only) |
| Staging `app.py` sha256 | `11e0f2f139dbeae108a7a912dc910db72d2d2d51c50705c52509b22cbfdc0c58` |
| staging-green artifact | `ffeb6eab503b7711e894af017a085ae8591548b958b8ed531ab6126e7894d91f` (`/opt/wathefni/staging/last-green.sha256`) |
| `/health` | `permission_authority=backend_current_required`, `legacy_dashboard_token_auth=false`, `legacy_untrusted_auth_usable=false` |
| `/ready` | `trusted_authority_enforced=true` |
| Full staging smoke | **ALL STAGING SMOKE CHECKS PASSED** |
| HR-0A verifier | **61 passed, 0 failed** (`/tmp/hr0a-staging-verify-report.json`) |

### HR-0A runtime fixes applied during the gate (kept fail-closed)

- Propagate `permission_authority` / subject fields through `posthire_dashboard_scope`, WhatsApp `_base_memory_scope`, and `_entitlement_context` so registry actions honor backend-current grants.
- Treat FastAPI `Query(None)` objects as unset in `normalize_attendance_status_filter`.
- Pass `dashboard_user_id` + `actor_role` into `dashboard_compliance_payload` (HTTP route + helper).
- Staging smoke harnesses updated for backend-current contexts (no shared-token authority).

---

## 2. DB-backed smoke results

- Controlled staging deploy path used (`ops/deploy.sh` lineage + rsync of orchestrator/smokes/ops).
- Minted backend-current operator session for HTTP checks; shared dashboard token → **401** on `/dashboard/auth/me`.
- Full `/opt/wathefni/orchestrator/ops/staging-smoke.sh` green after harness + authority-propagation fixes.
- Throwaway harness companies cleaned by their smokes (`HR0ASTG`, `MGRREADTESTCO`, `DOCUPLOADTESTCO`, etc.).

---

## 3. Manager-scope precedence proof

**Contract (do not merge sets):**

1. Stable `dashboard_user_id` — exclusive when present  
2. Transitional phone fallback — only when user ID is absent (phone-only rows: null/empty `dashboard_user_id`)  
3. Conflict / malformed binding → fail closed with deterministic `configuration_error`  
   (`manager_scope_binding_conflict` / `manager_scope_binding_missing` / `manager_scope_unconfigured` / `manager_scope_empty`)

**Proven on staging (HR-0A verifier + manager read-isolation smoke):**

- Manager with no phone and no `dashboard_user_id` → fail closed  
- Manager with no assignments → zero employee records  
- Explicit user-ID scopes → only assigned branch/team/employees  
- Transitional phone scopes work only where no user-ID binding exists  
- `dashboard_user_id` takes precedence over phone; sets are never merged  
- Conflicting user-ID and phone bindings → fail closed  
- Removed assignments take effect on the next request  
- Cross-company scope rows never grant access  
- Client-supplied phone/company/role/employee key/scope cannot alter authority  
- Owner/HR remain permission-based and do not inherit manager restrictions when unscoped  
- `employees.read`, `employees.manage`, `employees.status.approve` remain grant-only  

---

## 4. Schema / backfill inventory

| Check | Result |
| --- | --- |
| `manager_scopes.dashboard_user_id` | exists |
| Partial index `idx_manager_scopes_user` | exists |
| Migration | `ADD COLUMN IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` (idempotent) |
| Existing rows | readable |
| Conflicting phone↔user bindings | **0** |
| Broad production backfill | **not performed** |

**Current staging counts (active rows):**

- user-ID-bound: **12**  
- phone-only transitional: **234**  
- active total: **246**  

**Proposed backfill (future, not this slice):** match active phone-only rows to `dashboard_users` by `(company_code + digits(phone))` where a single active manager/owner user exists; leave ambiguous rows phone-only until reviewed.

---

## 5. Trusted-authority runtime evidence

**Masked staging configuration (selected):**

- `WATHEFNI_EMPLOYEE_APP=off`
- `WATHEFNI_DELIVERY_MODE=dry_run`
- `WATHEFNI_ONBOARDING_SEED=off`
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`
- `WATHEFNI_OUTBOUND_TEMPLATES=off`
- `WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env`
- No `WATHEFNI_ALLOW_LEGACY_DASHBOARD_TOKEN_AUTH` in staging unit env

**Proofs:**

- Production-like config cannot enter `legacy_untrusted`
- Startup refuses unsafe legacy shared-token config
- Health/ready advertise backend-current trusted authority
- Forged company / phone / role / permissions / manager-scope claims rejected
- Shared client tokens cannot establish operator context
- Normal email/password operator sessions work
- Session revocation takes effect on the next request

---

## 6. Legacy AI Recruiter external-exposure evidence

| Check | Before/after evidence |
| --- | --- |
| Public reverse-proxy `/internal/*` | `https://api.wathefni.ai/internal/companies` → **404 text/plain** (not legacy recruiter) |
| Caddy routes for ai-recruiter/`/internal` | **none** matched under `/etc/caddy` |
| Staging/prod orchestrator bind | `127.0.0.1:8011` / `127.0.0.1:8010` only |
| Postgres | localhost only |
| Docker ai-recruiter | **no containers** |
| systemd recruiter units | **none** |
| Default-disabled `/internal` | returns `404 legacy_internal_disabled` when service present and flag off |
| Token | server-side only; absent from commits/browser bundles/this report |
| Dashboard AI Recruiter module | unaffected (capability-gated inside Wathefni dashboard) |
| Orchestrator dependency on legacy service | **none** |

Prefer complete retirement: no active public dependency found.

---

## 7. Candidate CV audit (masked)

Audit actions: `candidate_cv_view` / `candidate_cv_preview` / `candidate_cv_download` via `record_admin_audit`.

**Policy:** audit sink failure is **fail-open** for authorized CV access (documented on `record_admin_audit`). Access is not broken if the sink errors.

**Sample masked staging rows (HR-0A harness):**

```json
[
  {
    "action_type": "candidate_cv_download",
    "status": "failed",
    "actor_user_id": "58ff***3077",
    "company_code": "HR0ASTG",
    "target": "hr0a-app-HR0ASTG",
    "outcome": "unavailable",
    "created_at": "2026-07-14T03:31:49+00:00",
    "has_token_leak": false
  },
  {
    "action_type": "candidate_cv_preview",
    "status": "failed",
    "actor_user_id": "58ff***3077",
    "company_code": "HR0ASTG",
    "target": "hr0a-app-HR0ASTG",
    "outcome": "unavailable",
    "created_at": "2026-07-14T03:31:49+00:00",
    "has_token_leak": false
  }
]
```

Fields present: operator/user ID, company, candidate/application target, action, outcome, timestamp.  
Not logged: document contents, bearer tokens, signed URLs, local paths, sensitive query params.

Also proven: permission denied + cross-company/not-found paths audited without sensitive leaks.

---

## 8. Attendance status-filter runtime results

**Allowed:** `absent`, `completed`, `late`, `pending`, `present`  

**Invalid contract:** HTTP **400** `{ "error": "invalid_attendance_status", "allowed": [...], "received": "..." }`  

Proven: every allowed status, invalid rejection, pagination, date+status combo, company isolation, manager-scope isolation, no-filter returns authorized page, filter cannot widen scope.

---

## 9. Safe rollback document

Binding doc: [`ops/HR0_SAFE_ROLLBACK.md`](HR0_SAFE_ROLLBACK.md)

Normal rollback must **not** restore:

- company-wide access for unscoped managers  
- `legacy_untrusted` authority  
- unauthenticated legacy recruiter routes  
- unaudited candidate CV access  

Prefer disable workflow / fix-forward / keep fail-closed controls / leave additive schema column+index in place. Exceptional pre-HR-0 restore is marked as a security incident path only.

---

## 10. Zero Employee App and production-business-state change proof

| Surface | Proof |
| --- | --- |
| Staging Employee App | `WATHEFNI_EMPLOYEE_APP=off` |
| Production Employee App | `WATHEFNI_EMPLOYEE_APP=off` |
| Production deploy | **not run** in this gate |
| Production DB backfill | **not run** |
| New mobile / production-facing features | **not enabled** |
| Employee App Expo migration | independent; not blocked or modified by this gate |

---

## Closure

HR-0A is **green**.

`staging-green, authority-remediated, ready for HR-1 design and backend implementation`

HR-1 remains **backend-only** (operator mobile auth + `/dashboard/mobile/me` capability contract). No Wathefni HR frontend until HR-1 is reviewed.
