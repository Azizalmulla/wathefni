# Wathefni — Engineering Handoff

> Single source of truth for a developer/AI joining this project cold. Read this top-to-bottom before touching code or production. Last updated: 2026-06-09.

---

## 1. What we're building

**Wathefni** is a **calm, premium HR operating system** for serious private enterprises in **Kuwait / GCC**. The guiding philosophy is **architecture-first**: we ship deliberate, well-scoped increments, dark-launch sensitive changes behind flags, and never break existing behavior. The product spans the full employee lifecycle:

- **Pre-hiring**: candidate import, CV parsing, interviews, assessments.
- **Post-hiring** (current focus): onboarding, compliance, employees / Employee 360, shifts, attendance, leave, payroll, analytics.
- **Channels**: WhatsApp (employee/candidate conversations), an HR **dashboard** (web), email (Postmark), and an LLM **Assistant** that can run actions.

Tone for any user-facing copy and UI: calm, premium, trustworthy. Kuwait/GCC legal defaults are treated as **configurable presets requiring legal review**, never hardcoded enforcement.

---

## 2. Repository layout

Repo root: `/Users/azizalmulla/Desktop/claw` (git repo, current branch: **`authority-cutover`**).

| Path | What it is |
|---|---|
| `wathefni-orchestrator/` | **The backend.** FastAPI monolith. |
| `wathefni-orchestrator/app.py` | The main app — a very large single file (~41k+ lines) holding routes, DB helpers, business logic, schema. Most work happens here. |
| `wathefni-orchestrator/tool_call_orchestrator.py` | LLM tool-call orchestration: permissions (`TOOL_PERMISSION_MAP`), module gating, confirmation flow. |
| `wathefni-orchestrator/action_registry.py` | Central `ActionSpec` definitions for LLM tools + native dashboard actions (`requires_confirmation`, `required_fields`, `module`, `sensitive`). |
| `wathefni-orchestrator/outbound_delivery.py` | Shared outbound delivery layer (employee messaging: channel ladder, criticality/sensitivity). |
| `wathefni-orchestrator/*-worker.py` | Background workers: `delivery-sweep-worker.py`, `video-interview-worker.py`, `leave-accrual-worker.py`. |
| `wathefni-orchestrator/smoke-test-*.py` | Standalone smoke tests (one concern each). Run on staging against the staging DB. |
| `wathefni-orchestrator/ops/` | Deploy/runbooks/systemd units/backups. **`deploy.sh` is the entry point.** |
| `apps/wathefni-dashboard/` | **The frontend.** Vite + React + TypeScript. |
| `apps/wathefni-dashboard/src/posthire/PostHire.tsx` | The post-hire dashboard UI (onboarding, compliance, employees, shifts, attendance, leave, payroll, analytics). Large composite file. |
| `apps/wathefni-dashboard/src/lib/api.ts` | Dashboard API client. |
| `apps/wathefni-dashboard/src/types.ts` | Dashboard TypeScript types. |
| `ai-recruiter/` | Separate FastAPI service (recruiter flows). Not the focus of recent post-hire work. |
| `delivery/` | A separate "Riders" delivery product (octopus-channel, riders-tools). **Currently showing as deleted in git status — unrelated to Wathefni HR work; do not get distracted by it.** |

> Note on git hygiene: the working tree is messy. Many `wathefni-orchestrator/smoke-test-*.py`, `ops/*`, and the recent **document-upload** changes are **uncommitted/untracked**. Deploys do **not** depend on git (they rsync the working tree), so "deployed" ≠ "committed". See §9.

---

## 3. How it runs (production topology)

- **VPS**: `root@76.13.63.68` (set `WATHEFNI_VPS_HOST` to override).
- **Public edge**: `https://api.wathefni.ai`, fronted by **Caddy** (TLS + reverse proxy). Dashboard SPA served at `/dashboard`; backend API routes are proxied (must return JSON, never the SPA shell — the deploy guard enforces this).
- **Production orchestrator**: `/opt/wathefni/orchestrator` (systemd: `wathefni-orchestrator.service`).
- **Staging orchestrator**: `/opt/wathefni/staging/orchestrator` (port `:8011`, `wathefni-orchestrator-staging.service`).
- **DB**: PostgreSQL (`psycopg2`). Connection via `app.db_connect()`, which loads env (e.g. `WATHEFNI_POSTGRES_ENV`). Prod and staging have separate DBs.
- **Email**: **Postmark** (migrated off Google/`gog`). This is the live outbound email provider.
- **Workers / timers**: `wathefni-leave-accrual.timer` (active) drives leave accrual; `wathefni-backup.timer` drives backups; delivery-sweep + video-interview workers as configured.
- **Backups**: `backup-wathefni daily` (DB dump + files + encrypted secrets, retention applied). Pre-deploy snapshots under `/opt/wathefni/backups/predeploy-*`.

Systemd env / feature flags are set via **drop-in files**: `/etc/systemd/system/wathefni-orchestrator.service.d/*.conf`. After editing: `systemctl daemon-reload && systemctl restart wathefni-orchestrator.service`.

---

## 4. Deployment workflow (READ BEFORE DEPLOYING)

The only deploy tool is `wathefni-orchestrator/ops/deploy.sh`. No CI, no containers. Run it from the operator machine (it drives the VPS over ssh/rsync).

```bash
cd wathefni-orchestrator

ops/deploy.sh staging      # build dashboard + deploy to staging (:8011) + run FULL staging smoke suite,
                           #   then record the deployed app.py sha256 as "staging-green"
ops/deploy.sh production   # promote to prod — REFUSES unless the exact app.py about to ship
                           #   already passed on staging (sha256 in /opt/wathefni/staging/last-green.sha256)
ops/deploy.sh rollback     # restore the most recent pre-deploy production snapshot
```

**The golden path for any backend change:**
1. Edit code locally. `python3 -m py_compile app.py` (and any changed module).
2. For dashboard changes: `cd apps/wathefni-dashboard && npm run build` (must be clean, no TS errors).
3. `ops/deploy.sh staging` → confirm **`ALL STAGING SMOKE CHECKS PASSED`** and that a **staging-green** sha256 is recorded.
4. `ops/deploy.sh production` → it backs up, snapshots, syncs code+dist, migrates schema, restarts, runs the **public-route guard** (real edge through Caddy/TLS), confirms `prod_health=200`.
5. Verify flag state on the running process if relevant (see §5 verification command).

**Code files deploy.sh ships** (`CODE_FILES`): `app.py tool_call_orchestrator.py action_registry.py outbound_delivery.py delivery-sweep-worker.py video-interview-worker.py leave-accrual-worker.py`, plus all `smoke-test-*.py`, `integrity-scan.py`, and `ops/`.

**Smoke suite**: `ops/staging-smoke.sh` runs every `smoke-test-*.py` against the staging DB with `WATHEFNI_DELIVERY_MODE=dry_run`. Add new smokes there.

**Public-route guard**: probes `/dashboard/auth/me`, `/dashboard/prehire/summary`, etc. unauthenticated — they must return **JSON 4xx** (proves the request reached the backend, not Caddy's static SPA handler). A bogus route must JSON-404. This catches the failure class that once blanked the production dashboard.

---

## 5. Feature flags & CURRENT PRODUCTION STATE

All flags accept on/off-style values (the truthy set is `_OUTBOUND_ON_VALUES`, e.g. `on`, `1`, `true`). Default OFF unless set. **Confirmed live production state (2026-06-09):**

| Flag | Prod value | Meaning |
|---|---|---|
| `WATHEFNI_OUTBOUND_LAYER` | **on** | Shared outbound delivery layer active. |
| `WATHEFNI_OUTBOUND_FLOWS` | **leave_decision,onboarding,compliance,shift** | Which flows route through the outbound layer. *(Recently expanded from just `leave_decision` — currently **mid-soak**, watch it.)* |
| `WATHEFNI_OUTBOUND_TEMPLATES` | **off** | WhatsApp out-of-session templates (Octopus/360dialog). Off until approved template names are ready. |
| `WATHEFNI_LEAVE_BALANCES` | **on** | P1 leave balances — **observe-only / read-only**. Does NOT enforce or block approvals. |
| `WATHEFNI_ONBOARDING_HR_MUTATE` | **off** | HR-driven onboarding mutations from dashboard (start/restart, mark/waive item). Code live, controls hidden. |
| `WATHEFNI_DOC_UPLOAD` | **off** | HR document upload from dashboard. **Code just deployed to prod, flag OFF (inert).** |
| `WATHEFNI_ORG_HIERARCHY` | **off** | Org hierarchy (branches/teams/manager scope) features. Backend exists; no admin UI yet. |

**Verify live flags on the running prod process:**
```bash
ssh root@76.13.63.68 'tr "\0" "\n" < /proc/$(systemctl show -p MainPID --value wathefni-orchestrator.service)/environ | grep -i WATHEFNI_'
```

**Flag helpers in `app.py`**: `onboarding_hr_mutate_enabled()`, `leave_balances_enabled()`, `doc_upload_enabled()`. Pattern: `(os.environ.get("FLAG") or "").strip().lower() in _OUTBOUND_ON_VALUES`.

---

## 6. Working principles / guardrails (DO NOT VIOLATE)

These have been applied consistently and the user expects them:

- **Architecture-first, plan-then-code.** For any non-trivial feature, present a short implementation plan (files touched, endpoints, UI, permissions, tests, rollout, risks) and get approval **before** writing code.
- **Dark-launch sensitive/mutating features behind a flag, default OFF in production.** Deploy the code first (no behavior change), then enable via a controlled **canary** (one internal/test employee), verify, then decide keep/revert.
- **Observe-only before enforcement.** E.g. leave balances log consumption but never block approvals. Balance/secondary logic failing must **never** break the primary action.
- **Additive over destructive.** New endpoints/UI; don't change existing ingestion or reads unless required. Rollback should be "flag off".
- **Tenant scoping is mandatory.** Everything is scoped by `company_code`. Resolvers fail closed when company can't be resolved (never cross tenants).
- **Manager scoping on reads AND mutations.** Managers only see their scope (branches/teams/direct reports) via `viewer_phone` (`context.get("hr_phone")`). Helpers: `manager_scope_context`, `employee_scope_sql`, `manager_scope_allows_employee`, `manager_scope_employee_keys`.
- **RBAC via `require_entitlement(context, module, permission)`.** Reads need `*.read`; mutations need `*.manage`.
- **No raw sensitive data in logs.** Audit via `record_admin_audit(...)` with metadata only.
- **Every feature ships with a dedicated smoke test** wired into `ops/staging-smoke.sh`, including RBAC deny paths, tenant isolation, and validation. Smokes must guard `import app` behind `try/except ModuleNotFoundError` so they SKIP cleanly where `psycopg2` is absent (local dev).
- **Strict staging→prod**: local compile/build → staging smoke green → record green hash → prod deploy (gated on hash) → public-route guard → health check.

---

## 7. What's been built (post-hire), and status

All of the following are **in production** unless noted.

### Shared Outbound Delivery Layer (`outbound_delivery.py`)
Resilient employee comms with a channel ladder and criticality/sensitivity config. Writes `employee_messages` + `outbound_delivery_events`; creates `hr_tasks` only when expected; email fallback via Postmark. Live for `leave_decision`; recently expanded to also cover `onboarding`, `compliance`, `shift` (**mid-soak — monitor `employee_messages` by flow/status and open `hr_tasks`**). Templates flow (`WATHEFNI_OUTBOUND_TEMPLATES`) still off.

### Trust fixes (committed `dccd541`)
Leave permission bug (B1), payroll hours/minutes display (B2), attendance correction UI (B3), payroll generate/preview/policy surfacing (B4).

### Onboarding dashboard upgrade (committed `93b70e7`)
Per-employee onboarding progress, checklists (pending/received/completed), "what HR should do next". HR mutations `start_onboarding` and `onboarding_mark_item` exist behind `WATHEFNI_ONBOARDING_HR_MUTATE` (OFF; canary-tested clean in prod earlier, then reverted to OFF).

### Leave balances P1 (committed `7c6ee9a`) — observe-only
- Tables: `leave_policy_presets`, `leave_policies`, `public_holidays`, `leave_ledger`, `leave_balances`.
- Kuwait private-sector **preset** seeded with `legal_reviewed=false`, `enforced=false`. Annual default 30 paid working days/yr; tiered sick (tiers configurable, pending legal review); monthly accrual displayed as annual; Fri–Sat weekend default; public holidays excluded from chargeable days; no negative/advance leave.
- `leave-accrual-worker.py` + `wathefni-leave-accrual.{service,timer}` post accrual entries.
- `approve_leave_request` / `cancel_leave_request` call `observe_leave_consumption(...)` (observe-only; never blocks).
- Balances surfaced in `dashboard_posthire_leave` and Employee 360. UI shows balance chips + a **"not enforced"** banner. `WATHEFNI_LEAVE_BALANCES=on`.
- Do **not** enforce, block approvals, change payroll, or build a policy/holiday editor (that's P2).

### Employee Document Hub + Manager-scoped reads (committed `1fd471b`)
- **Document Hub**: secure view/download of employee documents from `file_registry` across Onboarding checklist, Compliance rows, and Employee 360. No raw storage URLs; local files proxied, external (Drive) returns an access link; tenant-scoped; RBAC-gated; path-traversal guarded; audit-logged. Key helpers: `employee_documents_for`, `employee_document_index`, `resolve_employee_document_file`, `employee_document_local_path`, `_document_hub_read_context`. Endpoints: `GET /dashboard/posthire/employees/{employee_key}/documents`, `GET /dashboard/posthire/documents/{file_id}`.
- **Manager-scoped reads**: all post-hire list/detail endpoints now pass `viewer_phone=context.get("hr_phone")` so managers can't see company-wide lists. `manager_scope_employee_keys()` filters lists; detail views 404 out-of-scope.

### HR document upload (JUST SHIPPED — code in prod, flag OFF, UNCOMMITTED)
See §8.

### Org hierarchy
Backend complete (branches/teams/manager scope, `org_key`, `upsert_org_*`, `set_employee_org_assignment`, `upsert_manager_scope`). **No admin UI yet** — deliberately deferred by the user. `WATHEFNI_ORG_HIERARCHY=off`.

---

## 8. Most recent work: HR document upload (current, not yet committed)

**Goal**: complete the Document Hub loop so HR can attach/replace an employee's onboarding document from the dashboard (e.g. HR receives a civil ID by email, or a scan was bad).

**Backend (`app.py`)** — all additive:
- `doc_upload_enabled()` flag helper (`WATHEFNI_DOC_UPLOAD`, default OFF).
- `POST /dashboard/posthire/employees/{employee_key}/documents` (multipart `UploadFile` + `item_id` form field). Enforcement order: `require_entitlement(..., "onboarding", "onboarding.manage")` → flag → employee exists → manager scope (`manager_scope_allows_employee`) → item required → extension allowlist (`_DOC_UPLOAD_EXTENSIONS`) → non-empty → 15 MiB cap (`_DOC_UPLOAD_MAX_BYTES`). Then it **reuses the exact WhatsApp ingestion bundle** so a dashboard upload is indistinguishable from an employee submission: `store_onboarding_document` → (UPDATE `onboarding_items`) → `record_employee_document_receipt(..., extraction={})` → `recompute_employee_onboarding_counts`. `extraction={}` deliberately skips the synchronous vision/OCR step (kept fast, no LLM dependency; expiry stays a compliance-review concern). Audits `document_uploaded` (metadata only); returns the new `file_id`.
- `doc_upload_enabled` added to the onboarding-detail payload.

**Frontend**: `uploadEmployeeDocument()` in `api.ts` (FormData, no Content-Type), `DocumentUploadButton` + Upload/Replace controls beside onboarding checklist items in `PostHire.tsx` (gated on `onboarding.manage` + flag), `doc_upload_enabled?` added to `OnboardingDetailResponse` type. Build clean.

**Test**: `smoke-test-document-upload.py` (drives the real async endpoint via a constructed `UploadFile`): flag gate (OFF→403), extension/empty/oversize rejection, out-of-scope manager 404, unknown-employee 404, happy path (writes `file_registry`, links `item_id`, flips item to received, downloadable via hub resolver), replace. Wired into `ops/staging-smoke.sh`. **19/19 passing; full staging suite green twice (idempotent).**

**Deploy state**:
- Staging: green. Recorded **staging-green `app.py` sha256 = `9fbf2b4e3a33886edcb72921b7cc21d94601e96d91d64b11eab4069b7160dc91`**.
- Production: **deployed with `WATHEFNI_DOC_UPLOAD` OFF (verified inert)** — endpoint returns 403, buttons hidden, zero behavior change.
- **Git: NOT committed.** Uncommitted/untracked for this feature: `wathefni-orchestrator/app.py` (M), `wathefni-orchestrator/ops/staging-smoke.sh` (M), `wathefni-orchestrator/smoke-test-document-upload.py` (??), `apps/wathefni-dashboard/src/{lib/api.ts,posthire/PostHire.tsx,types.ts}` (M).

**To enable** (when ready): add a drop-in `/etc/systemd/system/wathefni-orchestrator.service.d/doc-upload.conf` with `Environment=WATHEFNI_DOC_UPLOAD=on`, `daemon-reload`, restart, then run a single-employee canary, verify, decide keep/revert.

---

## 9. Git / commit reality

- Branch: `authority-cutover`.
- Recent relevant commits: `1fd471b` (document hub + manager reads), `7c6ee9a` (leave balances P1), `8621bd6` (dup Refresh fix), `93b70e7` (onboarding upgrade), `dccd541` (trust fixes), `5f69525` (outbound layer).
- The working tree also contains a large set of **unrelated** changes from other efforts: `delivery/*` deletions (the Riders product), `ai-recruiter/*` modifications, and untracked `English/`, `Kuwaiti/`, `NBK_ASSESSMENT_SYSTEM.md`, plus many untracked orchestrator smoke tests/ops files. **When committing, scope tightly to the feature at hand** — the user insists commits include only the relevant files, never the unrelated churn.
- Only commit when explicitly asked.

---

## 10. Backlog / deferred (explicitly NOT started, by user direction)

- **Document upload — promote/enable**: code is in prod (flag OFF) and uncommitted. Pending: commit (scoped), then enable via canary when the user decides.
- **Document upload — extend surfaces**: add upload to Compliance rows + Employee 360 (first pass was onboarding-checklist-only).
- **Org Hierarchy admin UI**: backend done; UI deferred.
- **Outbound templates** (`WATHEFNI_OUTBOUND_TEMPLATES`): needs approved Octopus/360dialog template names.
- **New outbound flows** (missed-check-in nudge, payroll-ready notification): only after the shared layer soaks cleanly.
- **Leave balances P2**: enforcement, policy editor, holiday editor, sick-tier legal review. Keep observe-only until then.

---

## 11. Immediate next actions (where we left off)

The outbound flows (onboarding/compliance/shift) are **mid-soak** and document-upload code is in prod with the flag OFF. The open decision the user was choosing between:
1. Run the document-upload **production canary** (one test employee → verify → keep/revert flag).
2. **Commit** the document-upload work (scoped to this feature) before anything else.
3. Leave both **soaking**; revisit later.
4. Build the **Compliance + Employee 360** upload surfaces next (staging).

Confirm with the user which to do; don't assume.

---

## 12. Quick reference — common commands

```bash
# Deploy
cd wathefni-orchestrator && ops/deploy.sh staging
cd wathefni-orchestrator && ops/deploy.sh production
cd wathefni-orchestrator && ops/deploy.sh rollback

# Compile / build
python3 -m py_compile wathefni-orchestrator/app.py
cd apps/wathefni-dashboard && npm run build

# Inspect live prod flags
ssh root@76.13.63.68 'tr "\0" "\n" < /proc/$(systemctl show -p MainPID --value wathefni-orchestrator.service)/environ | grep -i WATHEFNI_'

# Service health
ssh root@76.13.63.68 'systemctl is-active wathefni-orchestrator.service; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/health'

# Run a single smoke on staging (example)
ssh root@76.13.63.68 'cd /opt/wathefni/staging/orchestrator && WATHEFNI_DELIVERY_MODE=dry_run /opt/wathefni/orchestrator/.venv/bin/python smoke-test-document-upload.py'
```

> Reminder: do file operations with the editor's read/edit tools, search with ripgrep/Grep, and reserve the shell for git/ssh/deploy/build. `app.py` is huge — search it (don't read end-to-end).
