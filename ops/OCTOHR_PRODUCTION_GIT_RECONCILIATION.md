# OctoHR production ↔ Git reconciliation

Date: 2026-08-18

Branch: `authority-cutover`

Scope: narrow production-parity closure; no domain-model rewrite and no wholesale replacement of production `app.py`.

## Reconciliation authority

The production VPS runs a historically composed `app.py`. Its pre-reconciliation SHA-256 is
`4912189f246eac19fea4b1c5e72ef32d3f90a534f95036fa44a48e6f8eb53b69`; its module-catalog SHA-256 is
`d2d5b7f3096f405efb3997777647bb57982fb65b1746a8c508185f7ad59bfabd`.

`wathefni-orchestrator/ops/patch-production-octohr-parity.py` is the Git authority for the narrow
compatibility artifact. It refuses any different production base hash, refuses a source missing any
accepted hotfix marker, parses the result, and is idempotent. The expected generated hashes are:

- patched `app.py`: `e497590c645ce635be9014ada247209fe855b66fb7a6d0cad5b9b64a906a2e3f`
- patched `module_catalog.py`: `31bca651721d4f908e7dfabd1e47e870670632075ec10b284a391db9049be75a`

## Production hotfix preservation record

| Production correctness behavior | Git equivalent / authority | Reconciliation result |
|---|---|---|
| Intake operations | Existing tracked intake implementation in `wathefni-orchestrator/app.py`; required marker in the compatibility patcher | Preserved; patch fails closed if absent |
| Intake document download | Existing tracked intake implementation in `wathefni-orchestrator/app.py`; required marker in the compatibility patcher | Preserved; patch fails closed if absent |
| Intake signed download | Existing tracked intake implementation in `wathefni-orchestrator/app.py`; required marker in the compatibility patcher | Preserved; patch fails closed if absent |
| Quarantine sweep | Existing tracked intake implementation in `wathefni-orchestrator/app.py`; required marker in the compatibility patcher | Preserved; patch fails closed if absent |
| Intake worker | Existing tracked intake implementation in `wathefni-orchestrator/app.py`; required marker in the compatibility patcher | Preserved; patch fails closed if absent |
| Production app-link mounting | `wathefni-orchestrator/app_links.py` plus the tracked mount in `wathefni-orchestrator/app.py`; both mount markers required by the patcher | Preserved; production `app_links.py` was byte-identical to Git |
| Existing isolated store-review route registration | `wathefni-orchestrator/store_review_access.py` and tracked registration in Git | Preserved; patcher verifies registration and does not create a second authority |

The inspection found no additional production-only route authority. The production composite is now
reproducible from its recorded base hash plus the tracked patcher; important code is therefore no longer
an undocumented VPS-only source of truth.

## Five frozen route groups

The compatibility patch adds only Employee feature definitions, frozen HTTP adapter registration, and
module-catalog entries for Performance, Talent, Learning, Benefits, and Engagement. The exact 30-file
dependency closure is tracked in
`wathefni-orchestrator/ops/octohr-production-parity-files.txt`. Each adapter continues to call the
already-frozen authority and the normal role + module + company-scoped guards.

The initial production gates are tenant-scoped to `OCTOHR-STORE-REVIEW` in
`ops/systemd/octohr-production-parity.conf`. Existing `WATHEFNI` Payroll canary allowlists and synthetic
markers are explicitly retained while the synthetic review tenant is appended.

## Routing and review access

`ops/caddy/api.wathefni.ai.Caddyfile` explicitly proxies only the three already-implemented routes:

- `/auth/store-review-availability`
- `/app/auth/store-review-login`
- `/dashboard/mobile/auth/store-review-login`

The application kill switch, fixed-identity validation, review-tenant pinning, generic failure behavior,
audit logging, and normal session/authorization authorities remain unchanged.

## Review data and Payslips

`wathefni-orchestrator/ops/provision-octohr-store-review.py` now has an owner-marker-guarded reconciliation
mode. It does not rotate persistent reviewer credentials. Documents use the canonical file authority.
Payslips use the frozen Payroll Wave 1 contract authority, Wave 2A external adapter, and Wave 3 generation
and employee-release authority; no frontend fallback or invented payroll response is introduced.

## Difference classification

| Difference class | Allowed production-only state |
|---|---|
| Deployment configuration | systemd drop-in installation path, Caddy active config, tenant-scoped kill-switch values |
| Secret | Postmark token, database/session secrets, store-review credential hashes and owner credentials |
| Generated/runtime state | database records, file storage, logs, job state, caches, bytecode, backups, evidence |
| Unexplained code drift | Target: **0** after deployment verification |

## Qualification status

- Preserved hotfix markers: 7/7
- Frozen surface regressions: Performance 56/56, Talent 62/62, Learning 78/78, Benefits 92/92, Engagement 97/97
- Store-review access regression: 15/15
- App-link regression: 20/20
- Production deployment and live parity proof: pending the narrow deployment
- Postmark live EN + AR delivery: pending secure Server API token availability

This record must be updated with the deployed hashes and live production proofs before final store builds.
