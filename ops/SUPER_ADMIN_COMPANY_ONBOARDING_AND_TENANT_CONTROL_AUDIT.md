# Super Admin Company Onboarding and Tenant Control — Current-State Audit

**Audit date:** 2026-07-27  
**Scope:** repository implementation plus read-only production posture  
**Production changes made:** none  
**External tenants enabled:** none

## Executive verdict

### Decision

**GO for a controlled implementation of a canonical tenant control plane.**

**NO-GO for onboarding an external company with the current Setup Console as if it were a complete or safe control plane.**

The current system has useful foundations: a real company registry, tenant-scoped dashboard sessions, a canonical twelve-module catalog, server-side entitlement checks on many interactive APIs, fixed roles, per-company settings, audited setup mutations, reversible company disable/archive, and multiple tenant-isolation harnesses. The existing Setup Console is therefore a valid bootstrap tool, not a mock.

It is not yet the requested operating model:

- there is no distinction between purchased, selected, configured, tested, ready, and live;
- module configuration is a single destructive replacement of enabled keys;
- there is no draft/publish, impact preview, versioned configuration, or rollback;
- integration and technical readiness are mostly global environment or SSH concerns;
- disabling a module does not universally stop its workers, queued jobs, webhooks, timers, or notifications;
- company pause revokes interactive credentials but does not provide a complete processing and delivery suspension boundary;
- roles are fixed and not module-assignable custom roles;
- legal entity, structure, policies, retention, quotas, imports, and most provider setup are outside the Super Admin flow;
- production contains a live legacy `interviews` entitlement that is not in the canonical catalog. Saving modules through the current console can disable it;
- the checked-out `app.py` imports `apply_legacy_module_implications`, but the checked-out `module_catalog.py` does not define it. The checkout cannot import the application unchanged and is behind the deployed interview-boundary posture;
- production has twelve orphan `company_settings` records, proving lifecycle cleanup and referential integrity are incomplete.

The requested control center should be implemented before normal HR UI redesign and before enabling any external tenant.

## Audit method and evidence standard

This audit inspected:

- backend source and schema DDL in `wathefni-orchestrator/app.py`;
- canonical product metadata in `wathefni-orchestrator/module_catalog.py`;
- setup normalization in `wathefni-orchestrator/company_setup.py`;
- the React Setup Console in `apps/wathefni-dashboard/src/setup-console/`;
- HR web navigation and entitlement presentation in `apps/wathefni-dashboard/src/App.tsx` and `src/lib/moduleWorkspace.ts`;
- HR and employee mobile entitlement consumers;
- communication, intake, delivery, interview, identity, offer, and indexing services;
- worker entrypoints and systemd definitions;
- tenant, entitlement, and database-isolation smoke harnesses;
- legacy provisioning in `workforce-os/scripts/provision-company.sh`;
- read-only production health, flags, company/module rows, integrity counts, services, and timers.

“Works end to end” below means a backend authority, persisted state, protected API, and active product path exist. It does not mean every combination has been proven against a real second production tenant. Production currently contains only `WATHEFNI`.

## Read-only production snapshot

Observed on 2026-07-27 without mutation:

- `/health`: HTTP 200.
- Companies: one — `WATHEFNI`, status `active`, country `KW`.
- External tenants: zero.
- Dashboard users: 4.
- Company channel accounts: 0.
- Company branches/teams: 0/0.
- `company_settings`: 13 rows, of which **12 have no matching `companies` row**.
- Setup audit rows (`action_results.action_type LIKE 'setup_%'`): 1.
- Dashboard sessions: 49 unexpired active rows and 7 expired rows still marked active.
- Production Setup Console and V2 UI: ON.
- Workspace bootstrap: ON.
- Company-owned WhatsApp account routing: OFF.
- Employee App: OFF.
- Inbound email: ON.
- Shared outbound layer: ON.
- approved outbound WhatsApp templates: OFF.
- leave balances: ON, observe-only.
- unified intake authority tenant allowlist: `WATHEFNI`.
- verified-job-binding enforcement tenant allowlist: `WATHEFNI`.
- mailbox sync, Google Calendar, Microsoft 365, and Teams tenant setup were not enabled in the inspected runtime posture.

Enabled `WATHEFNI` module rows:

`analytics`, `assessments`, `attendance`, `compliance`, `employment_offers`,
`interviews`, `leave`, `onboarding`, `payroll`, `pre_hiring`, `shifts`,
`video_interviews`.

`interviews` is not one of the twelve canonical catalog keys. This is a production-significant compatibility row, not harmless residue.

The live service proves that deployed production contains a newer or patched
module-catalog boundary than this checkout. In the audited checkout,
`app.py` imports and calls `apply_legacy_module_implications`, while
`module_catalog.py` contains neither that function nor the referenced
`LEGACY_IMPLIED_MODULES`. This is release drift and an application-import blocker
for the repository state; it must be reconciled before any deployment or module
mutation.

Active production timers include inbound intake, inbound operations monitoring,
Talent Pool auto-classification, delivery sweep, offer lifecycle, document
storage reconciliation, post-hire scan, shift reminders, leave accrual, backup,
and uptime. Candidate Knowledge and video-interview workers are enabled services.

## 1. Current company creation, update, pause, and offboarding

### Current authoritative records

| Concern | Current authority | What it stores | Gap |
|---|---|---|---|
| Company identity | `companies` | code, display name, country, lifecycle status/reason/timestamps, JSON metadata | no legal name, registration identity, branding, language, or owner relation |
| Regional settings | `company_settings.settings` | timezone, currency, notification preset, channel-policy acknowledgement, legacy free-form settings | untyped JSON; orphan rows exist; no version or publish state |
| Modules | `company_modules` | module key, enabled boolean, source, free-form settings | enabled conflates contract, configuration, and runtime state |
| Users | `dashboard_users` | tenant, email, phone, fixed role, account status | no canonical custom role assignment |
| Sessions/invites | `dashboard_user_sessions`, `dashboard_user_invites` | tenant-bound credentials and lifecycle | no Super Admin session inventory/cleanup page |
| HR WhatsApp identity | `dashboard_whatsapp_identities` | user/tenant/phone binding | distinct from company sender, correctly |
| Structure | `company_branches`, `company_teams`, `employee_org_assignments`, `manager_scopes` | branch/team and manager scope | absent from Setup Console wizard |
| Legal entity | `legal_entities` and event tables created by `kuwait_first_client_foundation.py` | registered names, CR/licence/PAM fields, currency, status | backend foundation is not wired to Setup Console or normal company creation |

### What the Setup Console can do

UI route:

- `/setup-console`, hidden unless `WATHEFNI_SETUP_CONSOLE_ENABLED`.
- V2 serves the React build when available; `app.py` retains a legacy embedded HTML console.

APIs:

- `GET /dashboard/superadmin/setup/companies`
- `POST /dashboard/superadmin/setup/companies`
- `GET /dashboard/superadmin/setup/companies/{company_code}`
- `PATCH .../{company_code}/profile`
- `PATCH .../{company_code}/modules`
- `PATCH .../{company_code}/settings`
- `PATCH .../{company_code}/lifecycle`
- `POST .../{company_code}/owner`
- `POST .../{company_code}/whatsapp-link`
- `PUT/DELETE .../{company_code}/channel-account`

Operator access is fail-closed behind:

- a per-phone bearer token in `WATHEFNI_SETUP_OPERATOR_CREDENTIALS`;
- an allowlisted phone in `WATHEFNI_PLATFORM_ADMINS`;
- both values supplied to the browser manually and held in `sessionStorage`.

Creation currently captures:

- immutable-style company code;
- display name;
- country;
- timezone;
- currency.

It does not capture:

- registered/legal names or government identifiers;
- brand name, logo, colors, domains, or templates;
- default language or supported languages;
- sector, addresses, legal entities, branches, departments, cost centers;
- data region, retention class, quotas, support plan, billing/contract dates;
- an initial administrator set beyond one Owner invite;
- purchased products or contract evidence.

### Lifecycle behavior

Current company states are only:

- `active`
- `disabled`
- `archived`

Disable/archive:

- requires a reason;
- revokes active dashboard sessions;
- revokes operator-mobile sessions;
- supersedes pending dashboard invites;
- invalidates Employee App credentials;
- preserves data and module rows;
- can be reversed by reactivation;
- protects `WATHEFNI` from disable/archive through this endpoint.

This is a useful access-control boundary, but not a complete tenant pause:

- active intake addresses are not disabled;
- Postmark can still durably accept and process tenant email under the global flag;
- pending `employee_messages` can still be retried by `run_delivery_sweep`;
- video transcription work can continue;
- Candidate Knowledge jobs use separate global/tenant allowlists;
- mailbox scheduled sync is driven by connection state and a global flag;
- provider webhooks and scheduled scans do not share one universal active-company gate;
- no queue drain/cancel policy or activation epoch prevents old work from executing after pause.

“Archive” is reversible access blocking, not offboarding. There is no tenant-wide
export package, retention countdown, legal-hold-aware deletion plan, provider
revocation workflow, secret destruction, storage purge manifest, or final
offboarding certificate.

## 2. Complete module and capability inventory

### Canonical product modules

Source: `wathefni-orchestrator/module_catalog.py`.

| Canonical module | Current business capabilities | Hard dependencies | Current runtime notes |
|---|---|---|---|
| `pre_hiring` | Jobs, applications, one Candidates area, CV intake/import, screening, ranking, collaboration, communication, reports | none | large umbrella entitlement; many sub-capabilities cannot be sold or disabled independently |
| `assessments` | assessment invites, attempts, reports, norms, Product 2 authoring | `pre_hiring` | authoring publish is grant-only; separate platform/config readiness is not modeled |
| `video_interviews` | asynchronous video interviews, questions, uploads, transcription | `pre_hiring` | worker can continue pending transcription after entitlement removal |
| `employment_offers` | draft, approve, send, accept/decline/withdraw, hire handoff | `pre_hiring` | surfaced inside candidate flow, not a clear setup/readiness area |
| `onboarding` | employee onboarding checklists, reminders, employee-app tasks | none | stronger with compliance, but no enforced dependency |
| `compliance` | employee documents, expiry/review/reminders | none | country rules and document requirements are not configured in Setup Console |
| `attendance` | records, corrections, history, import, absence scanning | none | import has a separate platform flag |
| `shifts` | schedules, cancellation/reschedule, availability, swaps, reminders | none | default timezone/reminder settings are seeded on first enable only |
| `leave` | requests, decisions, conflicts, policy/balances/ledger | none | policy enforcement is intentionally observe-only |
| `payroll` | hours, timesheets, policy, preview, export | none | currency required; Attendance/Leave are only recommendations |
| `analytics` | workforce analytics/reports | none | data quality depends on producing modules but no readiness dependency |
| `employee_app` | employee authentication, inbox/push and selected employee surfaces | none | tenant selection plus global `WATHEFNI_EMPLOYEE_APP`; payroll has no V1 employee-app surface |

### Pre-hiring capabilities inside the umbrella

These are implemented capabilities, but most are not first-class purchasable or
configurable entitlements:

| Area | Evidence and authority | Current configurability |
|---|---|---|
| Candidates | `/dashboard/prehire/applications`; unified candidate tables/components; person identity and governed profile services | one `pre_hiring` gate; Candidate Knowledge and Talent Pool must remain backend authorities under the single HR-facing Candidates area |
| Jobs/applications | position/job APIs and `prehire_jobs.py`; application lifecycle tables | job create/edit/publish/close permissions exist; no company application-form builder |
| CV intake | WhatsApp, Postmark, manual upload, mailbox/import, `cv_version`/intake authorities | production authority is WATHEFNI-allowlisted; not tenant-setup driven |
| Ranking | rank and evidence policy endpoints; Candidate Knowledge/index evidence | per-position evidence policy exists; no tenant-wide setup policy |
| Screening | position questions and candidate send/answer flows | job-level data; no company default template/versioning UI |
| Assessments | separate canonical entitlement | company assessment catalog/requiredness is not part of onboarding |
| Interviews | scheduled interview lifecycle plus async video | scheduled interview actions depend on non-canonical `interviews`; async video uses `video_interviews` |
| Notes/tasks/tags | application collaboration routes and tables | internal-only notes are enforced by action descriptions; no note categories, candidate visibility model, mention policy, or attachment policy setup |
| Communication | candidate email/WhatsApp, assessment/interview/offer messages | transport largely global; no tenant channel matrix |
| Offers/hire | `offer_routes.py`, `offer_lifecycle.py`, hire transition | separate entitlement but no setup workflow |
| Privacy/identity | duplicates, merges/reversal, legal holds, export/privacy requests | permissions exist; retention/deletion defaults are not configured during onboarding |
| Reports/export | pre-hire reports and CSV export | under `pre_hiring` and `report.export`, not an independently contracted capability |
| Intake Operations | unified intake attention and operations page | additionally hidden by feature/tenant flags, not canonical entitlement state |

### Post-hire and shared capabilities

- **Employees / Employee 360** is a shared people surface, not a separate catalog
  entitlement. It appears when any people module is enabled.
- **Documents** span onboarding, compliance, employee profile, upload/storage,
  reconciliation, and audit. They are not one independently modeled product.
- **Alerts & Delivery** is a shared workspace page when pre-hire or post-hire is relevant.
- **Activity/Audit** is a workspace capability controlled by `audit.read`.
- **Team, settings, organisation structure, authentication, and audit** are
  workspace capabilities rather than purchased modules.
- **HR mobile/operator mobile** is an additional client surface with backend
  permissions, but no canonical tenant lifecycle/readiness record.
- **Employee mobile app** is represented by `employee_app`, with module-derived
  surfaces.
- **Wathefni Assistant/tool calling** filters advertised tools by module and
  permission and rechecks before execution.

### Hidden, legacy, or non-canonical capabilities

1. **`interviews` entitlement split**
   - `ACTION_REQUIRED_MODULES` maps scheduled interview actions to `interviews`.
   - `module_catalog.py` contains `video_interviews`, not `interviews`.
   - production has both rows.
   - the checkout also lacks `apply_legacy_module_implications` even though
     `app.py` imports it; production is therefore ahead of this checkout.
   - the Setup Console only sends canonical keys and then disables every enabled
     row not in the submitted list.
   - **Impact:** pressing “Save modules” can disable scheduled interview actions
     while the UI still shows Interviews under `pre_hiring`.

2. **Legacy workspace provisioning**
   - `workforce-os/scripts/provision-company.sh` creates filesystem workspaces,
     renders `company.json` and HR user files, builds OpenClaw agent/binding
     snippets, instructs an operator to create Google resources, pair WhatsApp,
     add cron jobs, and restart the gateway.
   - it uses an older module vocabulary and is not the canonical Setup Console.
   - runtime startup still supports `company.json` as a seed/fallback source.

3. **Embedded Setup Console**
   - `app.py` still contains `SETUP_CONSOLE_HTML` beside the React V2 console.
   - this is compatibility code and increases drift risk.

4. **Mailbox provider declaration versus implementation**
   - backend constants list Gmail, Microsoft 365, and IMAP.
   - the user-facing feature status and connect API expose Gmail only.
   - M365/IMAP are foundations, not supported end-to-end provider choices.

5. **Legal entity foundation**
   - `kuwait_first_client_foundation.py` creates legal entity, applicability,
     identity, and document metadata tables.
   - there is no Setup Console route for legal entity creation/configuration.

6. **`ai-recruiter/` service**
   - contains separate company/application/position models and webhook routing.
   - it is not the canonical production tenant-control authority used by the
     Setup Console. It must not become a second entitlement source.

## 3. Entitlement, isolation, and dependency behavior

### What works

- `company_modules` becomes authoritative as soon as a company has any registry row.
- `require_entitlement` validates company, active actor, known role, module, and
  backend-current permission subject.
- permission context must bind the subject user and company to the actor and
  current company.
- many direct HTTP routes depend on module-specific contexts.
- HR navigation derives from `enabled_modules`.
- AI tools are filtered before model exposure and rechecked before execution.
- public async-video links check the `video_interviews` entitlement.
- the Setup Console rejects missing hard dependencies server-side.
- disabling Employee App invalidates its sessions/invites.
- tenant-scoped queries and collision harnesses cover candidates and post-hire records.

### Current dependency model

Hard dependencies:

- Assessments → Pre-Hiring
- Video Interviews → Pre-Hiring
- Employment Offers → Pre-Hiring

Soft recommendations:

- onboarding/compliance/Employee App;
- shifts/attendance;
- leave/payroll;
- payroll with attendance and leave;
- analytics with producing operational modules.

The React console auto-adds hard dependencies and removes dependents. The backend
also rejects invalid combinations. This is correct for functional dependencies.

The model is incomplete:

- technical requirements are not represented as dependencies;
- provider, worker, storage, migration, secret, webhook, and health prerequisites
  are not attached to a module;
- soft dependencies have no consequence or readiness explanation;
- a dependency is auto-enabled without distinguishing “included technical
  capability” from “unpurchased business product”;
- disabling a module does not preview affected routes, jobs, notifications, data,
  integrations, or employee-app surfaces;
- no dependency version exists, so catalog changes can reinterpret old tenants.

### Isolation limitations

- No PostgreSQL row-level security policies were found. Isolation relies on
  application query predicates and validated runtime database identity.
- Many tables use `company_code` without a foreign key to `companies`.
- Production’s twelve orphan `company_settings` rows demonstrate the consequence.
- production has only one tenant, so real production cross-tenant behavior is
  not empirically proven.
- staging harnesses deliberately create two colliding tenants and are valuable,
  but they do not cover every table, worker, webhook, export, storage key, and
  integration.
- global WhatsApp suppression by phone is intentionally cross-tenant.
- provider credentials and platform feature flags are often global, not
  tenant-owned.
- legacy helpers frequently default a missing company to `WATHEFNI`; authenticated
  routes have stronger context, but new/background call sites can misuse these helpers.

## 4. Roles and permissions

### Implemented fixed roles

| Requested concept | Current role | Notes |
|---|---|---|
| Company owner | `owner` | broad pre/post-hire, settings, users, audit |
| HR administrator | `hr_manager`; aliases also collapse several admin names to `owner` | no separate constrained HR admin template |
| Recruiter | `recruiter` | recruiting operations; no publish/close or final candidate decision |
| Hiring manager | `hiring_manager` | read/collaboration, interviews, offer approval, some post-hire reads |
| Interviewer | none | feedback participation exists, but no company role |
| Employee manager | `manager` | post-hire operations, requires manager scope |
| Payroll user | none | payroll scopes are bundled into fixed roles/grants |
| Viewer | `viewer` | read-only across entitled modules |
| Custom role | none | not supported |

Permissions are server-defined in `ROLE_PERMISSIONS` in `app.py`. They include:

- jobs create/edit/publish/close;
- candidate manage/decide/import;
- interview and assessment management;
- offer read/manage/approve/send/withdraw/response;
- candidate notes/tasks/tags/identity/privacy/merge/legal hold;
- post-hire read/manage/decision/export scopes;
- users/settings/audit/report scopes.

Additional `dashboard_user_permission_grants` are tenant/user scoped, but they are
not a general custom-role system. Employee permissions, offer hire override, and
assessment publish are deliberately grant-only. There is no deny override, role
version, module assignment, separation-of-duties template, expiry workflow for
ordinary grants, or Super Admin role designer.

Tenant scoping is materially implemented:

- users are unique by `(company_code, email)`;
- sessions carry `company_code`;
- grant lookup requires `(company_code, user_id)`;
- manager scopes carry `company_code`;
- dashboard context rejects requested-company mismatch;
- entitlement context rejects subject-company mismatch.

Module scoping is only partially expressed in roles. Permission keys identify
business actions, but roles themselves are global templates. The effective rule
is “tenant entitlement AND role/grant permission” on protected paths. There is no
stored proof that a custom role applies only to selected modules because custom
roles do not exist.

## 5. Pre-hiring configuration audit

| Configuration | Current state | Missing onboarding control |
|---|---|---|
| Jobs | create/edit/publish/pause/close/reopen APIs and permissions | company defaults, approval chain, templates, required fields |
| Application form | core fields embedded in position/application flows | form builder, localization, consent text, custom/required fields |
| Lifecycle | canonical stages and controlled transitions exist | tenant stage editor, allowed-transition policy, SLA/escalation |
| Notes | versioned internal notes, tasks, tags, ownership | categories, mention rules, attachments, visibility classes, retention |
| Internal/candidate visibility | notes are treated as internal; candidate communication separate | canonical field-level visibility metadata |
| Talent Pool/no-job | held `needs_role`/import states; communication denied until live application | tenant choice for acceptance, auto-admit/held, expiry and review SLA |
| CV intake | unified channel authorities, scanning, extraction, identity, versioning | Super Admin channel enablement and readiness per tenant |
| Duplicate person | suggestions, review, merge/reverse permissions | threshold/policy, auto-action prohibition, reviewer assignment |
| Duplicate application | idempotency and channel-specific prevention | tenant policy and explainable conflict resolution |
| Ranking | evidence and recalculation paths | ranking policy defaults, AI provider/readiness, permitted evidence |
| Screening | job questions and send/receive | reusable templates, scoring/requiredness/expiry |
| Assessments | product and authoring flows | company catalog selection, norm policy, publish approval |
| Interviews | scheduling/feedback/video flows | provider choice, interviewer role, calendar defaults, interview kits |
| Communication | email/WhatsApp flows and held-record guard | channel matrix, template ownership, consent, quiet hours |
| Shortlist/reject/hire | explicit permissions and verified-binding gate | company approval chain and delegation |
| Offers | versioned lifecycle and grant-only override | compensation bands, approval matrix, signatures/templates |
| Candidate profile | unified Candidates components and governed identity | configurable sections, custom fields, field visibility |
| CV retention/versioning | version authorities and inbound retention policy code | tenant retention schedule, legal hold interaction, deletion UI |

Candidate Knowledge and Talent Pool should remain implementation authorities.
They should not be sold or navigated as separate HR products. The normal
HR-facing product remains **Candidates**, with status, source, job relationship,
held reason, profile, CV versions, and governed actions in one area.

## 6. Communication channels and provider audit

### Provider-state gap

The requested state vocabulary does not exist as one model. Current code uses
different enums:

- WhatsApp account: `pending_verification`, `active`, `disabled`;
- mailbox: `disconnected`, `connected`, `needs_reconnect`, `disabled`, `error`;
- intake address: active/inactive-style status;
- email provider availability: inferred from environment variables;
- calendar: configured/not configured;
- push: inferred from global credential plus Employee App effectiveness.

The control plane needs one normalized integration lifecycle:

`not_selected → selected → setup_required → connected → verified → testing →
live`, with side states `degraded`, `disconnected`, `blocked`, and `uninstalling`.

### WhatsApp Business

Current:

- company account registry exists in `company_channel_accounts`;
- only `octopus` is accepted by Setup Console normalization;
- provider account ID is globally unique;
- inbound account can map to company;
- outbound route checks company, audience, active/verified status, feature flag,
  and whether the provider account exists in local Octopus config;
- candidate and employee audiences are separate;
- company sender is correctly distinct from individual HR identity;
- disable retains the row but clears verification;
- global phone suppressions exist.

Gaps:

- provider credentials are not created/stored/rotated by the console;
- account IDs must already exist in local OpenClaw/Octopus configuration;
- `verification_reference` is operator-entered evidence, not a provider API proof;
- no test connection, test send, test receive, webhook challenge, health timeline,
  credential rotation, template registration, or provider-side uninstall;
- company account feature is OFF in production;
- disabling a module/company does not universally cancel queued delivery;
- approved template names are separately configured and globally gated.

### Inbound email

Current:

- Postmark webhook has a shared secret and durable ACK boundary;
- `intake_addresses` maps recipient to company and optional job;
- attachment scan/extraction and intake jobs are durable;
- HR settings APIs can create/delete intake addresses;
- global kill switch and WATHEFNI unified-authority allowlist exist;
- retries, quarantine, operations monitor, and worker/timer exist.

Gaps:

- Setup Console does not own intake addresses;
- no tenant provider ownership verification;
- one global provider/webhook configuration;
- company/module pause is not checked before durable receipt/processing;
- no per-tenant inbound quota, domain verification, or end-to-end test in the
  company setup lifecycle.

### Connected mailbox / Google Workspace

Current:

- `mailbox_connections` is tenant scoped;
- encrypted credentials are in `mailbox_credentials`;
- encryption keys come from environment and support key lists for rotation;
- Gmail OAuth uses readonly scope;
- signed OAuth state binds company and mailbox;
- list labels, auto-import setting, manual “check now,” sync status, reconnect
  state, and disconnect exist;
- raw secrets/errors are not returned to UI.

Gaps:

- only Gmail is user-facing; OAuth, labels, and dry-run inspection are implemented;
- live mailbox import is intentionally rejected with
  `durable_scan_and_identity_authority_required`; the currently safe usable path
  is OAuth/inspection/dry-run rather than authoritative live import;
- OAuth client and encryption keys are global environment configuration;
- no Super Admin setup/readiness surface;
- no provider token revocation on delete was found;
- no scheduled mailbox service was observed in the production timer list;
- disabling Pre-Hiring after connection does not itself turn off `sync_enabled`;
- “test receive” is effectively a sync, not a controlled readiness suite.

### Outbound email

Current:

- Postmark and Gmail transport implementations;
- active provider selected by global environment;
- Postmark falls back to Gmail when unavailable;
- delivery/bounce/complaint webhook records events;
- employee delivery ladder can fall back to email.

Gaps:

- provider choice, sender identity, domain verification, credentials, templates,
  and limits are not tenant scoped;
- no Super Admin test send, DNS readiness, bounce health, rotation, or uninstall;
- fallback can use a platform-global sender that was not explicitly purchased or
  approved for a tenant.

### Calendar, meetings, Microsoft, SMS, push

- Google Calendar/Meet support exists through global `gog` configuration and a
  platform flag; it is not a tenant OAuth integration record.
- Teams is represented as a manual meeting-link type, not a Microsoft Teams
  integration.
- Outlook/Microsoft 365 is declared as a mailbox provider foundation but is not
  exposed as a supported connected provider.
- SMS appears in communication vocabulary but no live SMS provider/control plane
  was found.
- Expo push uses global provider credentials plus Employee App effectiveness;
  there is no tenant push integration setup.

These must be displayed as **not supported**, **future**, or **setup required**,
never as connected choices.

## 7. Policies and company customization

Implemented tenant data:

- free-form company settings;
- notification preset (`frontline`, `office`, `conservative`);
- module-specific JSON settings;
- shifts timezone/reminder defaults;
- leave policies, policy presets, holidays, ledger, balances;
- payroll policy and events;
- message templates with optional company code;
- onboarding/compliance data and document metadata;
- legal entities and employment applicability foundation;
- branch/team/manager scopes;
- candidate ranking evidence policy;
- import settings;
- identity/privacy/legal-hold records.

Missing or fragmented:

- no canonical policy catalog with schema/version/owner;
- no setup flow for working days, holidays, leave law pack, or legal review;
- no workflow/approval-chain designer;
- no notification matrix by event/audience/channel;
- no company language and fallback-locale policy;
- no document requirement set by employee type/location;
- no tenant-wide retention, deletion, legal-hold, and export policy;
- no general custom field registry;
- no brand/template center;
- no quota/limit model;
- no policy draft, effective date, approval, test, or rollback;
- no explicit “what changes for existing records?” migration behavior.

## 8. Technical readiness

### Current strengths

- runtime database identity is validated and immutable;
- staging and production identity mismatch fails startup;
- `/health` and sanitized `/ready` exist;
- backups and restore runbooks exist;
- durable inbound email has quarantine, idempotency, retries, and monitoring;
- workers call runtime identity checks;
- Candidate Knowledge has master/worker/tenant allowlists;
- unified intake and verified binding have tenant allowlists;
- document storage reconciliation and offer lifecycle timers exist;
- entitlement and tenant smoke harnesses exist;
- sensitive mailbox credentials are encrypted at rest;
- module removal invalidates Employee App credentials.

### Current readiness failure

A module can be marked “effective” when:

`company_modules.enabled = true` and any catalog master flag is available.

For eleven of twelve canonical modules there is no master flag. “Effective” does
not prove:

- schema/migration compatibility;
- required policy rows;
- storage buckets/directories and encryption keys;
- provider credentials;
- worker/timer deployment;
- webhook routing and health;
- OCR/AI availability;
- indexing readiness;
- import mapping;
- monitoring/alerting;
- rate-limit/quota configuration;
- backup coverage;
- rollback drill;
- test transaction.

The Setup Console V2 company readiness checks only profile, at least one module,
an Owner, channel-policy acknowledgement, and selected WhatsApp account
verification. A company can therefore be “Ready” while a purchased module is not
operational.

### Worker/timer enforcement findings

| Path | Current gate | Disable/pause concern |
|---|---|---|
| Leave accrual | global leave flag plus per-company Leave entitlement | good module check; active-company state should also be required |
| Candidate Knowledge worker | global master, worker flag, tenant allowlist | not driven by canonical Pre-Hiring state |
| Video transcription worker | pending response selection | no entitlement/active-company recheck before processing |
| Delivery sweep | pending `employee_messages` | no company lifecycle or originating-module recheck before send |
| Mailbox sync | global flag plus connection status/sync flag | no canonical module/active-company execution gate |
| Postmark durable intake | global flag plus active intake address | no canonical module/active-company gate |
| Shift/onboarding/compliance scans | module-specific call paths and global timers | no single universal activation epoch or pause contract |

The core rule is therefore not yet universally enforced outside interactive APIs.

### Schema and migration posture

Most schema is created/altered by a large `ensure_schema` block and service-level
`ensure_*_schema` functions. There is no repository migration chain with an
explicit tenant-control schema version and reversible migration history. This
works for additive bootstrap but is insufficient for a publish/rollback control
plane.

## 9. What works, what is UI-only, and what is manual

### Works end to end today

- create/select a company record;
- update display profile, country, timezone, currency;
- select canonical modules with hard-dependency validation;
- create an Owner invite and accept dashboard authentication;
- manage fixed-role team users in the normal HR workspace;
- link HR user WhatsApp identity;
- tenant-bound dashboard sessions and server-side permissions;
- navigation filtering from enabled modules;
- many direct-route/API entitlement checks;
- reversible company disable/archive with credential invalidation;
- company-scoped activity/audit view;
- WATHEFNI pre-hiring, post-hire, unified intake, and verified-binding production paths;
- Gmail mailbox connector foundation when globally enabled/configured;
- durable Postmark intake and candidate/employee delivery authorities.

### Appears configurable but is not a complete live control

- **Save modules:** changes entitlement rows immediately; it does not configure,
  test, or activate each module and can remove hidden legacy entitlements.
- **Ready:** shallow company provisioning check, not module readiness.
- **WhatsApp verified:** based on entered reference plus pre-existing provider
  config, not live provider ownership/health proof.
- **Channel policy reviewed:** acknowledgement only; it does not configure channels.
- **Platform available/effective:** mostly means no master flag exists, not that
  technical prerequisites passed.
- **Microsoft 365/IMAP provider constants:** not user-facing supported connectors.
- **Teams:** manual link type, not a connected integration.
- **Leave balances:** enabled but intentionally not legal enforcement.
- **Employee App selection:** not live while global master flag is OFF.

### Requires SQL, SSH, env files, or developer/operator help

- platform-admin allowlist and Setup Console operator credentials;
- platform feature flags and tenant allowlists;
- OpenClaw/Octopus provider accounts and secrets;
- outbound email provider and sender credentials;
- inbound Postmark secrets/domain/webhook;
- mailbox encryption and Gmail OAuth client;
- Google Calendar/Meet credentials;
- Expo push credentials;
- OCR/AI/Candidate Knowledge provider keys and allowlists;
- approved WhatsApp templates;
- worker/timer/service installation and monitoring;
- legacy per-company workspace/agent/binding setup;
- Google Sheet/Drive creation in the legacy provisioner;
- branch/team seeding when not using the normal org APIs;
- legal entity creation;
- holiday/leave policy setup;
- custom permission grants;
- production canaries, backups, and rollback.

## 10. Security, isolation, and safety findings

### Critical / P0 before external tenant activation

1. **Checkout/deployment module-catalog drift**
   - the current checkout cannot import `app.py` because
     `apply_legacy_module_implications` is missing;
   - restore the production-green catalog implementation and prove artifact
     parity before deploying.

2. **Module save can disable live scheduled Interviews**
   - reconcile `interviews` versus `video_interviews`;
   - block current production module writes until compatibility is preserved.

3. **No universal execution-time tenant capability gate**
   - queued delivery, intake, mailbox, indexing, transcription, timers, and
     webhooks must recheck active company, published module state, capability,
     integration state, and activation epoch immediately before side effects.

4. **Company disable is not a complete suspension**
   - it blocks access but does not guarantee stop-processing/stop-notifying.

### High / P1

4. Purchased and live states do not exist; binary enablement can expose
   unconfigured functionality.
5. No database RLS; application filters remain the primary isolation boundary.
6. Numerous `company_code` fields lack referential integrity; twelve production
   orphan settings rows exist.
7. Provider credentials and platform flags are global/manual, so tenant
   ownership and isolation cannot be proven from control-plane state.
8. Setup audits are not uniformly transactional: `record_admin_audit` is
   intentionally best-effort/fail-open.
9. No draft/publish/impact/rollback; module changes mutate production state immediately.
10. No custom roles or module-scoped role assignment.

### Medium / P2

11. Expired session rows remain marked active; authentication checks expiry, but
    operational cleanup and visibility are weak.
12. Legacy and V2 setup UIs coexist.
13. Legacy workspace files remain a seed/fallback authority.
14. No unified integration state vocabulary or health history.
15. No tenant-wide export/offboarding workflow.
16. No quota and rate-limit policy per tenant.
17. No second production tenant has proven the complete isolation matrix.

## 11. Recommended canonical entitlement and configuration model

### Principle

Never use one boolean for commercial entitlement, configuration, activation,
runtime health, and access.

### Canonical records

1. **`tenants`**
   - company identity, lifecycle, default locale/timezone/currency, data region;
   - immutable tenant ID separate from editable code/display name.

2. **`tenant_legal_entities` and `tenant_org_units`**
   - legal entities, branches, departments, teams, cost centers;
   - adopt the existing legal/branch/team records rather than duplicate them.

3. **`product_catalog` and `capability_catalog`**
   - business modules, sub-capabilities, versions, dependencies, UI surfaces,
     APIs, workers, notifications, and technical prerequisites.

4. **`tenant_contract_entitlements`**
   - what was purchased, quantity/limits, effective dates, commercial source,
     approved-by evidence;
   - only commercial modules appear here.

5. **`tenant_module_instances`**
   - desired state, published configuration version, operational state,
     activation epoch, paused reason, health state;
   - references a contract entitlement.

6. **`tenant_capability_grants`**
   - explicit sub-capabilities for routes, workers, channels, and surfaces;
   - generated from the module instance but individually auditable.

7. **`tenant_configuration_versions`**
   - draft/published/superseded JSON validated against versioned schemas;
   - author, reviewer, timestamps, diff, impact plan, rollback target.

8. **`tenant_integrations` and `tenant_integration_credentials`**
   - provider, audience, connection state, scopes, ownership proof, secret
     reference, health, test results, rotation/revocation timestamps;
   - secrets in a dedicated secret manager/encrypted vault, never in audit JSON.

9. **`tenant_roles`, `tenant_role_permissions`, `tenant_user_roles`**
   - system templates plus tenant custom roles;
   - module/capability scope, optional org scope, deny rules, expiry.

10. **`tenant_readiness_checks` and `tenant_activation_events`**
    - deterministic check catalog and immutable results;
    - controlled activation, canary scope, monitoring window, rollback.

11. **`tenant_health_events` and `tenant_audit_events`**
    - append-only, actor/source, before/after hashes, correlation ID;
    - setup mutations fail if mandatory audit/outbox persistence fails.

12. **`tenant_work_items`**
    - setup required, degraded, blocked, reconnect, expiring credential, failed test.

### Effective authorization

A request or background job is allowed only when all are true:

1. tenant lifecycle is `active`;
2. contract entitlement is current;
3. module published state is `live`;
4. capability is granted;
5. dependency and integration prerequisites are satisfied;
6. actor holds the tenant/module/org-scoped permission, where an actor exists;
7. the work item’s activation epoch matches the current module epoch;
8. kill switches and runtime health allow the operation.

Navigation, direct APIs, workers, timers, webhooks, queues, AI tools, storage,
exports, and notifications must call the same decision service.

Technical dependencies may be auto-included without being displayed as a
purchased business module. A commercial dependency must never be silently
enabled; it must block publishing and explain what must be purchased or changed.

## 12. Desired onboarding and module lifecycle

### Company lifecycle

`draft → setup → testing → ready → active → suspended/offboarding → archived`

Suspension must atomically:

- reject interactive sessions and new inbound work;
- stop provider routing;
- prevent queue claims with a new activation epoch;
- suppress outbound communication;
- preserve data;
- expose a preview of in-flight work and explicit cancel/drain choices.

### Module lifecycle

Use the requested states with separate dimensions:

| Display state | Meaning |
|---|---|
| Not purchased | no commercial entitlement; hidden from tenant UI/APIs |
| Purchased | contract exists, setup not started |
| Setup required | required decisions/integrations/policies missing |
| Configured | valid draft/published config exists |
| Testing | automated/manual qualification running |
| Ready | every mandatory readiness check passed |
| Live | activated for the tenant and enforced everywhere |
| Paused | intentionally unavailable; queued side effects blocked |
| Degraded | live but health/SLA impaired; safe operations defined |
| Blocked | cannot progress because of dependency/security/compliance failure |

Do not derive these from one column. Store commercial, desired, readiness,
activation, and health states separately and compute the display state.

### Desired setup sequence

Company created  
→ commercial modules recorded  
→ dependencies resolved  
→ owner/admins added  
→ legal/profile/org configured  
→ module policies configured  
→ integrations connected and verified  
→ data imported and validated  
→ automated tests run  
→ impact/readiness reviewed  
→ controlled activation published  
→ monitoring window  
→ normal operation  
→ pause/disable/offboard.

## 13. Recommended Super Admin information architecture

### Company setup wizard

1. **Company**
   - display/legal identity, country, timezone, currency, languages, branding.
2. **Purchase**
   - contract modules, limits, dates; show capabilities without exposing hidden
     technical products.
3. **Structure**
   - legal entities, branches, departments, teams, owner and administrators.
4. **Modules**
   - decisions and dependencies for each purchased module.
5. **Roles**
   - role templates, custom roles, module/org scope, separation of duties.
6. **Policies**
   - lifecycle, approvals, notifications, documents, retention, holidays, fields.
7. **Integrations**
   - provider selection, connect, verify, scopes, send/receive tests.
8. **Data**
   - imports, mapping, validation, duplicate policy, reconciliation.
9. **Readiness**
   - automated checks grouped by module, with owner and remediation.
10. **Review and activate**
    - exact diff, impact, missing dependencies, canary, rollback, publish approval.

The wizard saves drafts. It never makes a module live merely because a checkbox
was selected.

### Permanent company control page

**Overview**
- purchase/configured/live/degraded/blocked summary;
- lifecycle, owners, activation history, action queue.

**Modules**
- commercial state, setup progress, dependencies, version, readiness, live state;
- safe pause/resume with impact preview.

**Integrations**
- normalized state, scopes, tenant ownership, last tests, health, rotation,
  reconnect and uninstall.

**Roles and permissions**
- users, role templates/custom roles, module/org scope, risky grants, sessions.

**Policies**
- workflow, approvals, notifications, holidays, documents, retention, legal
  hold, fields, branding, quotas.

**Data and imports**
- sources, mappings, batches, errors, reconciliation, exports, storage.

**Readiness**
- all mandatory checks, evidence, expiry, blockers, test/retest.

**Health**
- webhooks, providers, workers, queues, timers, OCR/AI, index, rates, backups.

**Audit history**
- draft/publish diffs, actor, time, reason, approvals, tests, rollback.

Every page must answer:

- what was purchased;
- what is selected/configured/live;
- what is broken or blocked;
- what requires action;
- what dependency is missing;
- what will happen if the draft is published.

## 14. Migration plan preserving WATHEFNI

1. **Snapshot current truth**
   - capture WATHEFNI company, modules including legacy `interviews`, settings,
     users/grants, flags, allowlists, integrations, services, timers, and checks.
   - classify orphan settings; do not delete them in the control-plane migration.

2. **Introduce new tables dark**
   - seed catalog/capability versions;
   - import current WATHEFNI entitlements as contract + module instances;
   - represent `interviews` as an explicit compatibility capability;
   - leave all current reads authoritative.

3. **Shadow decision service**
   - compare old versus new authorization for navigation, APIs, tools, workers,
     webhooks, queue claims, and sends;
   - alert on divergence; do not deny WATHEFNI.

4. **Dual-write configuration**
   - current Setup Console mutations write legacy and versioned draft/publish
     records transactionally;
   - require audit/outbox success;
   - retain old flags/allowlists as kill switches.

5. **Read cutover by boundary**
   - interactive routes first;
   - navigation and mobile;
   - workers/timers/queues;
   - webhooks and integrations;
   - notifications last, with canaries.

6. **WATHEFNI freeze and proof**
   - prove no behavior change for every current module and channel;
   - prove pause blocks processing and delivery;
   - prove rollback to legacy reads;
   - keep external tenants unavailable.

7. **External tenant canary**
   - only after complete readiness, isolation matrix, backup/restore, export,
     suspension, provider uninstall, and offboarding tests pass.

## 15. Compact implementation plan — four waves

### Wave 1 — Canonical control-plane foundation

- restore checkout/deployed artifact parity and reconcile the module catalog,
  especially `interviews` and legacy implications;
- add product/capability catalog and dependency types;
- add contract entitlements, module instances, versioned drafts, audit/outbox;
- import WATHEFNI in read-only/shadow mode;
- add referential-integrity and orphan-reporting plan;
- make the existing Setup Console read the richer model without changing live behavior.

Exit: old/new decision parity for WATHEFNI; current module save cannot remove hidden capabilities.

### Wave 2 — Universal enforcement and lifecycle safety

- one authorization/readiness decision for UI, API, mobile, AI tools, workers,
  timers, webhooks, queues, storage, exports, and notifications;
- activation epochs and safe pause;
- module-specific state machine and impact preview;
- custom roles with module/org scope;
- transactional mandatory audit.

Exit: disable/pause provably prevents access, processing, and notifications.

### Wave 3 — Configuration, integrations, and readiness

- versioned module policy schemas;
- pre-hire decisions, fields, workflows, notes, duplicates, retention;
- legal/org/holiday/document/payroll configuration;
- normalized integration records, encrypted secret references, connect/test/
  verify/reconnect/rotate/uninstall;
- automated technical readiness and health.

Exit: WATHEFNI can be reconstructed from the console without SQL/env/SSH for
tenant-level choices; platform infrastructure secrets remain platform operations.

### Wave 4 — Activation, migration, and external-tenant qualification

- setup wizard and permanent control page;
- data import/reconciliation;
- activation canary, monitoring, rollback;
- tenant-wide export/offboarding;
- two-tenant isolation suite across every table and async path;
- owner-authorized external tenant canary.

Exit: first external tenant can be onboarded, operated, paused, and offboarded
without developer help and without exposing unpurchased capabilities.

## 16. Final GO/NO-GO

### GO

Proceed with the four-wave implementation above, dark and production-preserving,
starting with catalog reconciliation and the canonical state model.

### NO-GO

Do not:

- deploy the current checkout until the missing module-catalog implementation is restored and production parity is proven;
- use the current module-save action on WATHEFNI until `interviews` compatibility is fixed;
- treat “Ready” or “Effective” as proof a module can go live;
- enable an external tenant;
- expose Microsoft 365, Teams, IMAP, SMS, or provider choices that are not end-to-end;
- rely on UI hiding without the universal execution-time capability gate;
- call company disable/offboard complete while queued processing and delivery can continue.

## Evidence index

Primary source paths:

- `wathefni-orchestrator/app.py`
- `wathefni-orchestrator/module_catalog.py`
- `wathefni-orchestrator/company_setup.py`
- `wathefni-orchestrator/tool_call_orchestrator.py`
- `wathefni-orchestrator/action_registry.py`
- `wathefni-orchestrator/outbound_delivery.py`
- `wathefni-orchestrator/durable_email_ingress.py`
- `wathefni-orchestrator/inbound_cv_channel_cutover.py`
- `wathefni-orchestrator/candidate_communication_authority.py`
- `wathefni-orchestrator/candidate_knowledge_index_worker.py`
- `wathefni-orchestrator/interview_service.py`
- `wathefni-orchestrator/interview_lifecycle.py`
- `wathefni-orchestrator/offer_routes.py`
- `wathefni-orchestrator/offer_lifecycle.py`
- `wathefni-orchestrator/kuwait_first_client_foundation.py`
- `wathefni-orchestrator/runtime_environment.py`
- `wathefni-orchestrator/inbound_retention_policy.py`
- `apps/wathefni-dashboard/src/setup-console/SetupConsoleApp.tsx`
- `apps/wathefni-dashboard/src/setup-console/api.ts`
- `apps/wathefni-dashboard/src/setup-console/moduleGuidance.ts`
- `apps/wathefni-dashboard/src/App.tsx`
- `apps/wathefni-dashboard/src/lib/moduleWorkspace.ts`
- `apps/wathefni-dashboard/src/posthire/PostHire.tsx`
- `apps/wathefni-hr-mobile/src/auth/access.ts`
- `apps/wathefni-hr-mobile/src/features/operations/routes.tsx`
- `apps/wathefni-employee-mobile/src/features/home/HomeView.tsx`
- `workforce-os/scripts/provision-company.sh`
- `workforce-os/templates/data/company.json.tmpl`

Isolation and operational evidence:

- `wathefni-orchestrator/smoke-test-entitlement-hardening.py`
- `wathefni-orchestrator/smoke-test-tenant-isolation-harness.py`
- `wathefni-orchestrator/smoke-test-tenant-read-hardening.py`
- `wathefni-orchestrator/smoke-test-manager-read-isolation.py`
- `wathefni-orchestrator/smoke-test-module-catalog.py`
- `wathefni-orchestrator/smoke-test-setup-console.py`
- `wathefni-orchestrator/smoke-test-settings-durability.py`
- `wathefni-orchestrator/ops/HR2_DATABASE_ISOLATION_INCIDENT.md`
- `WATHEFNI_FIRST_COMPANY_CHECKLIST.md`
- `wathefni-orchestrator/ops/DEPLOY_RUNBOOK.md`
- `wathefni-orchestrator/ops/RESTORE_RUNBOOK.md`

Core current tables:

- company/access: `companies`, `company_settings`, `company_modules`,
  `dashboard_users`, `dashboard_user_sessions`, `dashboard_user_invites`,
  `dashboard_user_permission_grants`, `dashboard_whatsapp_identities`;
- structure/legal: `company_branches`, `company_teams`,
  `employee_org_assignments`, `manager_scopes`, `manager_scope_members`,
  `legal_entities`, `legal_entity_events`;
- communications: `company_channel_accounts`, `message_template_map`,
  `employee_messages`, `hr_tasks`, `outbound_delivery_events`,
  `mailbox_connections`, `mailbox_credentials`, `intake_addresses`,
  `inbound_messages`;
- pre-hire: `positions`, `applications`, collaboration/identity/privacy tables,
  intake submissions/documents/jobs, CV version/binding tables, assessment,
  interview, offer, ranking, and Candidate Knowledge tables;
- post-hire: `employees`, onboarding/compliance/document tables,
  `attendance_records`, `shift_assignments`, `leave_requests`,
  `leave_policies`, `public_holidays`, `leave_ledger`, `leave_balances`,
  `payroll_timesheets`, `payroll_policies`, `payroll_exports`;
- audit: `action_results` plus domain event/audit tables.

No production mutation, external tenant enablement, post-hiring change, mobile
change, or normal HR UI redesign was performed for this audit.
