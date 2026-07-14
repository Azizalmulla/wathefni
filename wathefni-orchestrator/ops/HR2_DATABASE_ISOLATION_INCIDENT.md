# HR-2 Candidate Database-Isolation Incident Closure

Status: staging remediated and regression-green; live production unchanged.

## Impact conclusion

`no production connection occurred`

This conclusion is specific to the failed HR-2 staging candidate-decision attempts
on 2026-07-14. It does not mean the old wrapper was safe; it means the latent
environment-selection flaw did not select or connect to production during this
incident.

Masked read-only production evidence captured at
`2026-07-14T05:30:55.057032+00:00`:

- production database fingerprint: `b1f1a54885f2`;
- production DSN fingerprint: `4e23b26e4747`;
- HR-2 company/fixture markers in `companies`: `0`;
- candidate records: `0`;
- application records: `0`;
- employee records: `0`;
- onboarding records: `0`;
- candidate/action audit records: `0`;
- outbound delivery/notification records: `0`;
- employee invite records: `0`;
- `dashboard_operator_mobile_confirmations` did not exist in production because
  HR-2 was not deployed there.

The production service had been running since `2026-07-12T18:33:43Z`; the HR-2
requests appear only in the localhost staging service journal. Production and
staging app artifacts had different hashes, and production had no HR-2 schema.

## Exact affected path

The potentially unsafe path was:

1. `POST /dashboard/mobile/candidates/{app_key}/decision`;
2. `operator_mobile_data.confirm_mobile_action`;
3. `action_registry.run_dashboard_registry_action`;
4. shortlist/reject: `_status_mutation_executor` →
   `app.update_application_status`;
5. hire: `_hire_candidate_executor` → `app.update_application_status` →
   `app.transition_hire`;
6. `app.run_workspace_tool`;
7. external workspace tools:
   `tools/db/update_state.py` and `tools/db/posthire_state.py`.

Candidate shortlist and reject use `update_state.py update-application`. Hire
uses the same status updater followed by
`posthire_state.py transition-hire`, which can create an employee plus
onboarding/compliance rows and workspace mirrors.

## Root cause

Before remediation, `run_workspace_tool` inherited the parent process
environment implicitly. The external tools independently declared
`/root/.openclaw/secrets/postgres.env` as their default and loaded that file with
`os.environ.setdefault`. Correct database selection therefore depended on an
inherited `WATHEFNI_DATABASE_URL` already being present. There was no explicit
application-environment value, no database marker, no startup identity
validation, and no pool/worker readiness identity.

That is an environment-fallback and deployment-configuration flaw. It was not
caused by cached configuration, a cross-process connection singleton, or a
database pool switching after initialization. The in-process pool was global,
but it was bound once to whichever unvalidated URL happened to win at startup.

The original incident description overstated the first failure. The first
failing evidence was `application not found`, but the staging journal proves the
failed app keys were:

- `hr2-candidate-app` at `04:47:23Z` and `04:48:02Z`;
- `965500292001-HR2MOB-APPLICATION` at `04:49:19Z`,
  `04:51:23Z`, and `04:52:50Z`.

The seeded canonical application key ended in `HR2_DESIGN`. Adding explicit
environment propagation at `04:51:05Z` did not make the malformed
`...-APPLICATION` request succeed. The first successful canonical request was
`965500292001-HR2MOB-HR2_DESIGN` at `04:54:41Z`. Therefore the observed
`application not found` was caused by the fixture key mismatch, while source
inspection during that failure exposed the separate latent environment flaw.

## Why no production connection occurred

The pre-remediation staging import loaded
`/root/.openclaw/secrets/postgres.staging.env` into `os.environ`. A child created
with the old `subprocess.run(..., env=None)` inherited that URL. The external
tool's production-default file used `setdefault`, so it could not replace the
inherited staging value.

A masked reproduction against the deployed staging configuration returned:

- parent process DSN fingerprint: `9d8eb32ea1c2`;
- inherited child DSN fingerprint: `9d8eb32ea1c2`;
- external-tool `setdefault` selected fingerprint: `9d8eb32ea1c2`;
- staging env-file fingerprint: `9d8eb32ea1c2`;
- production env-file fingerprint: `4e23b26e4747`;
- all selected staging: `true`.

Production read-only searches found no HR-2 company, phone, app-key, marker,
candidate, employee, audit, notification, or invite row. Because the selected
DSN remained staging before the tool attempted its application lookup, the
failed execution did not connect to or read production.

## Why earlier tests missed the flaw

- HR-0A and HR-1 staging suites did not execute candidate registry mutations.
- The initial HR-2A local smoke used source/contract checks and no real child
  process or database.
- The original HR-2 staging verifier covered shortlist only and initially used
  noncanonical fixture app keys.
- No test asserted application environment, configured database name, live
  database marker, worker identity, or child-process environment equality.
- Reject and hire—including employee provisioning—were not part of the first
  staging matrix.

## Durable isolation contract

`runtime_environment.py` now resolves one immutable process binding:

- `WATHEFNI_ENV` is required and restricted to a known environment;
- `WATHEFNI_POSTGRES_ENV` is required; there is no production env-file default;
- the env file must contain a database URL;
- a conflicting ambient database URL is rejected;
- expected host, port, logical database name, and marker are required;
- staging refuses the production logical database before connection;
- production refuses the staging logical database before connection;
- the first direct read-only identity check compares `current_database()`, the
  database environment row, and the configured marker;
- the application pool is created only from the validated immutable URL;
- the unvalidated direct-connect pool fallback was removed;
- there is no runtime/test reset hook for the live binding;
- missing table, missing row, wrong environment, wrong logical database, or
  wrong marker fails startup;
- workspace children always receive the validated env-file values and identity;
- staging candidate status/hire tools receive `--no-sheet-sync`;
- API startup and all four worker entrypoints run the same assertion.

The marker is operator-provisioned by
`ops/provision-environment-identity.py`. Application startup never creates or
updates it, so a wrong database cannot be silently blessed.

`/ready` now exposes only:

- application environment;
- database environment;
- marker fingerprint;
- logical database fingerprint;
- host fingerprint;
- match result.

No credentials, username, raw host, raw database name, or connection string is
returned.

## Cross-system audit

### Candidate mutations

Inspected mobile confirmation, action registry, dashboard candidate actions,
`update_application_status`, `transition_hire`, `run_workspace_tool`, and the
deployed `update_state.py`/`posthire_state.py` copies. Fixed mandatory validated
child environment propagation, explicit `--env` on all three callers, and
staging sheet-sync suppression.

### Leave decisions

Mobile and dashboard leave decisions execute through `app.db_connect` and the
post-hire registry. They are covered by the central validated pool. Outbound
leave delivery records are written to the same validated database; staging
delivery remains `dry_run`.

### Onboarding and document reviews

Dashboard/API routes, document storage reconciliation, and onboarding mutations
use `app.db_connect`. The document reconciliation worker now validates identity
before work. External Drive/`gog` configuration is not a database connection;
it remains a separate credential boundary and was not invoked by candidate
closure tests.

### Attendance corrections and shift actions

Attendance import/correction and shift/reminder paths use the central
`app.db_connect` boundary. Internal scheduled endpoints execute in the already
validated API process.

### Employee status and hire provisioning

Normal employee status paths use the validated pool. Candidate hire's external
post-hire tool now receives the validated child environment. Real staging proof
created the synthetic employee only in staging and then removed it.

One staging-only malformed employee (`WATHEFNI-`, empty phone, synthetic
`Hessa HR2`) was created by an intermediate verifier fixture that omitted phone
and company from application JSON. It was removed together with its exact
workspace mirror, and cleanup now detects that exact historical residue. It was
never present in production.

### Notification delivery

Outbound event state uses the validated pool. Staging systemd configuration
retains `WATHEFNI_DELIVERY_MODE=dry_run`; the full staging smoke proved no real
email/WhatsApp send. Candidate shortlist/reject/hire emitted zero outbound
events, and staging hire reported sheet sync `attempted=false`.

### Workers and scheduled jobs

Delivery sweep, document reconciliation, leave accrual, and video interview
workers explicitly validate before entering their loops. API-hosted scheduled
jobs use the validated API process. Production worker templates declare the
production identity, but were not installed or restarted in this closure.

### Legacy AI Recruiter

`ai-recruiter/` remains quarantined, is not called by Wathefni HR, has no
deployed service/timer in this stack, and its internal routes are off by default.
Its independent `app/database.py` still has an import-time global SQLAlchemy
engine and localhost/default DSN behavior. That is a required remediation before
any future dequarantine, but it is not an HR-2 runtime path and was intentionally
not modified while unrelated uncommitted work exists there.

## Regression evidence

Local:

- runtime environment contract: `23/0`;
- HR-2A mobile adapter contract: `33/0`;
- HR-1 source contract: `84/0`;
- legacy recruiter quarantine: `9/0`;
- dashboard tests: `30/30`.

Real staging:

- complete staging smoke suite: passed;
- staging-green artifact: `44ac7971b266fd43bc798dd542bc776ffaaa274bc22a16f166a7c4ff69d1e6bd`;
- HR-2 verifier: `46/0`;
- HR-1 regression: `70/0`;
- shortlist, reject, and hire completed through the registry in staging;
- hire provisioned a staging employee and cleanup removed it;
- candidate audit rows were present in staging during proof;
- candidate outbound events: `0`;
- candidate hire external sheet sync: `attempted=false`;
- staging process with production env file: refused before connection;
- production-mode process with staging env file: refused before connection;
- missing configured marker: refused;
- real staging connection with marker hidden from `search_path`: refused;
- mismatched marker in worker process: refused before work;
- `/ready` environment match: `true`.

Post-cleanup read-only production counts remained zero for every HR-2 marker
category. Staging harness rows were removed.

## Security-preserving rollback

If candidate mutations regress:

1. disable or route-block the mobile candidate decision endpoints;
2. keep mobile candidate read/CV audit paths available if healthy;
3. keep `runtime_environment.py`, the database marker, startup assertion,
   validated pool, worker checks, and readiness fields active;
4. keep staging delivery `dry_run` and nonproduction sheet sync suppressed;
5. do not restore the old ambient `run_workspace_tool` behavior;
6. do not remove the marker to make startup pass;
7. redeploy the last staging-green functional code only after porting the
   environment guard onto it.

Live production was not changed. Its marker and drop-in remain a future,
separately approved deployment prerequisite; code deployed there without that
provisioning will fail closed rather than fall back.
