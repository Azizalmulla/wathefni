# Wathefni Full Interaction & Dead-Control Audit

Base audit stamp: `20260805T195406Z`  
Late authority closure stamp: `20260805T220256Z`

## Release decision

Canary qualification passed for confirmed P0/P1 defects. There are no confirmed broken, dead, or permission-mismatched P0/P1 controls in the final matrix. Broad rollout is not implied by this canary stamp.

**Assurance program (20260805T224005Z):** confirmed P0/P1 work is closed; residual 495 unproven + P2 raw-error contracts are tracked under `ops/INTERACTION_ASSURANCE_PROGRAM/` and do not block product development. Releases fail only on confirmed P0/P1 regressions (`run-interaction-assurance-release-gate.py`) or static dead-control inventory failures.

## Coverage

- Static inventory: 1,101 source controls (1,035 dashboard, 66 employee mobile), 0 dead candidates.
- Dashboard browser inventory: 240 production-connected role/locale/viewport pages across owner, HR manager, and restricted viewer; 6,645 visible control instances.
- Final targeted browser qualification: 24 pages, 804 control instances, 24 directly passing outcomes, 780 inventoried/static-correlated outcomes, 0 broken.
- Dashboard mutation probes: 191 item-route probes across three roles; 0 server failures; restricted viewer denial reached where generated fixtures allowed it.
- Employee app API audit: 17/17 controls pass, including repeat-safe notification, leave, push, refresh, and sign-out paths.
- Locale/layout: final shell evidence is LTR for English and RTL for Arabic on desktop and mobile for all dashboard roles.
- Late production role probe: 6/6 attendance read/manage outcomes passed (owner, HR manager, restricted viewer).
- Late employee proof: Talal `/app/me` advertised the Settings deletion and Onboarding upload capabilities; controlled account-deletion replay reused one task.

## Confirmed fixes shipped

1. Candidate classification mutations now enforce `candidate.manage`, return calm errors, and write admin audit events.
2. Restricted viewers no longer render or request candidate-intake management.
3. Dashboard API and payroll/setup surfaces suppress raw machine codes in user-facing feedback.
4. Onboarding and leave icon-only actions now have localized accessible names.
5. Concurrent audit capacity no longer exhausts the production pool (`WATHEFNI_DB_POOL_MAX=32`); final 191-route probe had 0 server failures.
6. Dashboard builds now run the static dead-control inventory and fail when a dead source control is found.
7. Attendance Ops reads now require `attendance.read`; all mutations require `attendance.manage` and write admin audit events.
8. `/orchestrator/whatsapp-turn` now fails closed behind the shared internal token; the Octopus gateway sends the token and the public route remains unavailable.
9. Employee account deletion now matches the advertised capability and reuses an existing open HR task on replay.
10. Onboarding upload/replace/resubmit controls now intersect server item actions with `onboarding.upload_document` before rendering or execution.
11. Leave cancellation and notification-read mutations are repeat-locked; notification failures are visible; Documents and Settings expose back controls.
12. Post-hire employee deep links preserve the employee query after page navigation, and Arabic sidebar/mobile navigation is RTL.

## Residual findings (retained — assurance program)

Confirmed P0/P1 work is **closed**. Residual work is tracked under `ops/INTERACTION_ASSURANCE_PROGRAM/` and does **not** block product development. Releases fail only on confirmed P0/P1 regressions (`ops/full-web-e2e/run-interaction-assurance-release-gate.py`) or static dead-control inventory failures.

### Suite count reconciliation

| Source | Passed | Failed | Total |
|---|---|---|---|
| Earlier `dashboard-full-suite.out` | **410** | 13 | 423 |
| Late `dashboard-broad-suite-late.out` | **415** | 13 | 428 |

Same 13 failure names; +5 passed / +1 file from added coverage. All 13 were test drift (Classic setup, Communications tab, Talent Pool `—`, Migration & Sync, onboarding “complete” copy, compliance landing, interview tiles) and are fixed in-tree — not live product regressions.

### Open tracked residual

- **495 P1 `unproven`** destructive/idempotency/audit properties — progressive proof via disposable IAX fixtures (`interaction_assurance_fixtures.py`, register `ops/INTERACTION_ASSURANCE_PROGRAM/unproven-p1-register.json`). Never against real customer records.
- **~91 P2** raw/unclear mutation error contracts — gradual by module (calendar calm messages started).
- **7** frontend endpoint literals remain static-normalizer candidates.

The full matrix preserves every result:

- `findings/interaction-control-matrix.json`
- `findings/interaction-control-matrix.csv`
- `findings/interaction-control-matrix-summary.json`
- Residual register: `ops/INTERACTION_ASSURANCE_PROGRAM/RESIDUAL_REGISTER.md`

## Production evidence and rollback

- Service: active; health binding reports production application/database match.
- Dashboard `index.html` local/remote SHA-256 match: `e70a36305a6a7420e4bc064dbac1f88ae0c7aadb7cf986933fce16867ed118a7`.
- Employee JS-only canary OTA: group `34a288bc-36c6-40fb-80e3-a38fe5449320`, runtime `0.1.0`, iOS + Android.
- Orchestrator and OpenClaw gateway are active; unauthenticated local WhatsApp ingress returns 401 and the public route returns 404.
- Late rollback backup checksums and local rollback syntax validated; `deploy/ROLLBACK.sh` restores backend/dashboard/gateway and republishes the embedded mobile runtime.
- Late cleanup: 3 temporary dashboard users disabled, 3 dashboard sessions revoked, and 1 Talal audit session revoked (in addition to the base audit cleanup).

