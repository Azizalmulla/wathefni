# Mobile action authority — staging closure

## Root cause

Mobile advertised candidate/interview actions from raw permission bags and the
lifecycle stage matrix, but registry execution went through
`require_entitlement(_entitlement_context(scope))`.

`_entitlement_context` previously dropped `permission_authority` /
subject markers from `posthire_dashboard_scope`, so `context_permissions()`
fail-closed to `{}` and returned `permission_denied` even when `/me` and
`allowed_actions` advertised the action.

Secondary gaps:

1. Mobile DTOs could advertise `schedule_interview` even though
   `POST /dashboard/mobile/candidates/{id}/decision` only executes
   `shortlist|reject|hire`.
2. Canonical shortlist/reject executors did `set(request.metadata).get(...)`,
   which raises `AttributeError` when lifecycle is enabled — confirm failed
   after prepare succeeded.

## Exact authority function

Shared decision authority:

- `recruiting_lifecycle.authorize_recruiting_action(action, stage, permissions)`
- Advertisement: `mobile_candidate_allowed_actions` →
  `allowed_actions_for_stage` ∩ `MOBILE_EXECUTABLE_CANDIDATE_ACTIONS`
- Permissions source: `app.context_permissions(context)` via
  `_authoritative_permissions` (requires `permission_authority=backend_current`
  + matching subject user/company)
- Registry execution: `require_entitlement(_entitlement_context(scope), …)`
  with markers preserved

## Action matrix (post-fix)

| Action | Permission | Valid stages | Manager-scope | Web | Mobile | Execute | Same authority? |
|--------|------------|--------------|---------------|-----|--------|---------|-----------------|
| shortlist | `candidate.manage` | → shortlisted (e.g. ready_for_review) | N/A recruiting | Yes | Yes | `POST …/candidates/{id}/decision` → `shortlist_candidate` | Yes — `authorize_recruiting_action` |
| reject | `candidate.decide` | non-terminal → rejected | N/A | Yes | Yes | decision → `reject_candidate` | Yes |
| hire | `candidate.decide` | shortlisted / interview → hired | N/A | Yes | Yes | decision → `hire_candidate` | Yes |
| schedule_interview | `interview.manage` | → interview | N/A | Yes | **No** (not advertised) | registry / web | Web matrix only; mobile filtered |
| reschedule | `interview.manage` | interview | N/A | Partial | **No** (`feature_disabled`) | web | Capability gate |
| cancel_interview | `interview.manage` | scheduled/rescheduled | N/A | Yes | **No** | web | Capability gate |
| save notes | `interview.manage` | interview row | N/A | Yes | Yes (`write`) | `POST …/interviews/{id}/notes` | Yes — `require_entitlement` + capability |

Fail-closed preserved. `stale_decision` (confirm) remains distinct from
`permission_denied` / `action_forbidden` / `already_decided` (prepare).

## Tests

Local:

- `python3 smoke-test-mobile-action-authority.py` — 53+ passed
- `python3 smoke-test-hr2a-mobile-data.py`
- `python3 smoke-test-hr1-operator-mobile.py`
- `python3 smoke-test-canonical-recruiting-lifecycle.py` — 77 passed on staging DB
- mobile vitest: `src/api/actions.test.ts`, `lifecycle.test.ts`
- web vitest: `lifecycle-labels.test.ts`

Staging (authenticated native API, not fixture-only):

- `ops/mobile-lifecycle-authority-staging-proof.py` — **36/36**
  (`staging-evidence/canonical-lifecycle/mobile-authority-proof.json`)
- `ops/hr2-staging-verify.py` — **46/46**
  (`staging-evidence/canonical-lifecycle/hr2-authority-verify.log`)

Proof coverage: real mobile login → `/me` → candidate list/detail →
permitted shortlist prepare+confirm → recruiter hire absent/denied →
interview detail without cancel/reschedule → EN/AR label contract →
re-login after logout → `stale_decision` distinct from permission denial.

## Production promotion / rollback

**Do not promote to production yet** until:

1. Full `ops/deploy.sh staging` green artifact is recorded for this exact tree
   (including unrelated leave standalone suite if still gated).
2. Mobile app build that consumes filtered `allowed_actions` is validated on a
   device/simulator against staging (this proof covers authenticated API;
   native UI EN/AR restart was covered at API + label-contract level).

When promoting:

- Deploy via `ops/deploy.sh production` only after staging-green sha matches.
- Rollback: `ops/deploy.sh rollback` to last pre-deploy snapshot.

Rollback risk for this change is low: authority is fail-closed; worst case
over-hides actions rather than advertising non-executable ones.
