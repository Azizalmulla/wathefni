# OctoHR public account-deletion resource

Status: deployed and qualified on 2026-08-19 (Kuwait time).

## Public resource

- Customer URL: `https://octo-hr.com/delete-account`
- API adapter: `POST https://api.octo-hr.com/public/account-deletion/request`
- Canonical authority: `create_employee_account_deletion_request(...)`
- Canonical work item: one open `hr_tasks` row with
  `task_type=account_deletion_request`; both the authenticated mobile request and
  the public web request converge on this writer.

The public resource is a functioning request form, not an informational-only
page. It accepts the employee's company code and registered work email or phone,
requires explicit confirmation, and returns non-enumerating public copy. A valid
account creates the same idempotent HR deletion task used by the mobile app.
Unknown accounts receive indistinguishable public copy and create no task.

## Deletion and retention disclosure

The page explains in English and Arabic that the employer is the data controller
and must verify the request. When approved, application access data such as active
sessions, refresh credentials, push tokens, and trusted-device access is revoked
or deleted. Profile/contact data, uploads, and support material are deleted or
irreversibly anonymized when they are no longer legally required.

Employment contracts and personnel documents, payroll and payslip records,
attendance and leave records, approvals, and security/audit evidence may be
retained. The disclosed Kuwait baseline is at least 365 days after employment
ends, with longer retention only where the employer's published policy, payroll
or tax duties, an investigation, legal hold, or a live claim requires it. Retained
records remain restricted and are deleted or anonymized when the applicable
retention obligation ends.

## Security controls

- Exact browser-origin allowlist: `https://octo-hr.com` and
  `https://www.octo-hr.com`.
- Exact Caddy route only; no broad public API proxy.
- Company and identity predicates remain tenant scoped.
- A public request requires evidence of an existing Employee-app account through
  an invite or session record; it does not activate an account or create a session.
- Duplicate identity matches fail closed.
- Source and hashed company/identity rate limits apply.
- Responses do not reveal whether a company, email, phone, or employee exists.

## Production source reconciliation

Production remains a historically composed application, so the deployment used
the fail-closed patcher
`wathefni-orchestrator/ops/patch-production-public-account-deletion.py` instead
of replacing the production application wholesale. The patcher verifies the
known pre-change application and rate-limit hashes and asserts preservation of
the inbound-intake, signed-download, quarantine, intake-worker, app-link,
review-access, frozen-module parity, permission-reconciliation, and Leave
projection markers before emitting the composed source.

| Production change | Git authority | Preserved proof |
| --- | --- | --- |
| Public deletion request body, CORS adapter, and canonical writer | `wathefni-orchestrator/app.py` | Production application SHA-256 `729a3cbe09074762222a83ceef094607d054f9579c258570fd0e95bf7ca0e43e` |
| Public deletion rate policy | `wathefni-orchestrator/security_rate_limit.py` | Production rate-limit SHA-256 `b642a373b2761c23d919063eb3076cc93b81506b711645daa8177f6a07e123dd` |
| Exact public reverse-proxy route | `ops/caddy/api.wathefni.ai.Caddyfile` | Production Caddy SHA-256 `4e02d7d937469b25affe880d1b335466b8e964fb1e6c57967ac173ddd5fea26c` |
| Public EN/AR form and disclosure | `apps/octohr-public/delete-account.html`, `delete-account.js`, and `styles.css` | Canonical URL returns HTTP 200 with the restrictive CSP |

Rollback backup:
`/opt/wathefni/rollback/public-account-deletion-20260818T204800Z`.

## Live qualification

- `/health`: HTTP 200.
- `/ready`: HTTP 200; no pending migrations/drift, failed jobs, or recent
  delivery errors.
- Approved-origin preflight: HTTP 204.
- Missing confirmation: HTTP 400 `confirmation_required`.
- Disallowed origin: HTTP 403 `origin_not_allowed`.
- Synthetic valid request created canonical task
  `3da94314-81f5-42be-ac7a-d769847920d1` for the synthetic
  `OCTOHR-STORE-REVIEW` tenant with `status=open` and `channel=public_web`.
- Repeating the same request returned HTTP 200 and left exactly one open task.

The synthetic open task is intentionally retained as end-to-end qualification
evidence. It does not itself delete, revoke, or mutate the reviewer identity;
completion still requires the normal HR resolution workflow.
