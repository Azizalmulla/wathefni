# PRODUCTION_READINESS_R2_SECURITY_FULL_PASS

**Status:** QUALIFIED / frozen for owner review
**Stamp:** `PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`
**Phase:** R2 — Security & Secret Hardening (remediation, scoped)
**Date:** 2026-08-12
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Baseline:** `ops/PRODUCTION_READINESS_R1_AUDIT.md` (owner accepted)
**Qualify:** `ops/qualify-production-readiness-r2-security.sh`
**Freeze:** `ops/PRODUCTION_READINESS_R2_SECURITY_FREEZE_AMENDMENT.md`
**Evidence:** `ops/evidence/production-readiness-r2-security-20260812T154724Z/`

**Scope:** exactly the R1 security blocker set — P0-2, P0-3, P0-4, P0-5, P1-22.
No unrelated R3+ finding was fixed. No frozen Wave 1–6 domain authority was reopened.

---

## 1. Result

| Gate | Result |
|---|---|
| Local unit contracts (no DB) | **84 passed, 0 failed** |
| Staging database negative paths, two isolated tenants | **69 passed, 0 failed** |
| Live deployed staging service over HTTP | **16 passed, 0 failed** |
| Waves 1–6 unit freezes + authority contracts + internal-auth lockdown | **green** |
| Open R2 blockers | **none** |

All five named blockers are closed and re-proven against a running system, not only asserted in source.

## 2. What changed

### P0-2 — public link signing secrets now fail closed

`wathefni-orchestrator/security_link_secrets.py` (new) is the only source of link signing keys.

* The fallback chain is gone. `assessment_link_secret()` and `video_interview_link_secret()` read
  one dedicated variable each and raise `LinkSecretUnavailable` otherwise. They no longer fall back to
  `WATHEFNI_DASHBOARD_TOKEN`, `AI_OCTOPUS_DASHBOARD_TOKEN`, `DASHBOARD_TOKEN`, `WATHEFNI_DATABASE_URL`,
  or the two constants that were committed to this repository.
* Those two constants are on a permanent deny list, so a link minted under the old fallback cannot
  verify even if someone sets the constant deliberately. Connection strings and any value that matches
  another live credential are rejected the same way.
* Minimum length 32 with a character-diversity floor.
* Verification is constant-time, compares against every configured key without early exit, and binds the
  token to its subject with a constant-time comparison rather than `!=`.
* Rotation contract without a key-management system: `<VAR>_PREVIOUS` accepts comma-separated retired
  keys that verify but never sign. Retired keys face identical validation.
* `GET /ready` now reports `link_signing` and `public_link_capabilities_available`, so a missing secret
  is a visible readiness degradation instead of a silent downgrade to a guessable key.
* Minting a public video-interview link with no secret returns 503 `link_signing_unavailable`; the
  capability becomes unavailable rather than forgeable.

### P0-3 — dashboard and Setup Console login throttling

* `POST /dashboard/auth/login` and `POST /dashboard/superadmin/setup/auth/login` are throttled on both
  network source and normalized account identity.
* The dashboard login was reordered. It used to call `require_active_company()` before checking the
  password, which turned it into a tenant oracle, and it returned a distinct 403 `account_inactive` for
  a real-but-inactive email. Credentials are now proven first; company lifecycle and account status are
  only disclosed after authentication succeeds. Unknown company, unknown email, and wrong password
  return one identical 401.
* The Setup Console login collapsed `not_platform_admin` into the same 401 as a bad token, so the
  endpoint can no longer be used to discover which operator phones exist.
* A successful sign-in clears that identity's counters, so a legitimate user who mistyped is not punished.

### P0-4 — internal worker channel

* The `token unset → localhost accepted` branch is removed entirely. Network position is not
  authentication, and a proxy that does not preserve the client address turned that branch into an open
  endpoint.
* `WATHEFNI_INTERNAL_WORKER_TOKEN` is a dedicated secret. The broad platform token is accepted only if a
  deployment explicitly sets `WATHEFNI_INTERNAL_WORKER_ACCEPT_SHARED=1`; the default is no.
* Missing secret fails closed. Comparison is timing-safe. Denials are audited.
* Verified: the production transcript worker (`wathefni-video-interview-worker.service`) runs
  `video-interview-worker.py` in-process and does not call this endpoint, so closing it breaks no
  existing operation.

### P0-5 — internal endpoint classification, tenant scope, break-glass

`wathefni-orchestrator/security_internal_authority.py` (new) declares every endpoint in the R1 P0-5 set
as exactly one of two classes; there is no ambiguous middle ground.

Two internal principals now exist:

* **tenant** — `WATHEFNI_INTERNAL_TENANT_TOKENS` = `{"COMPANYCODE": "<token>"}`. Scope is pinned to that
  company and cannot be widened by any parameter.
* **platform** — the existing `WATHEFNI_INTERNAL_TOKEN`. Still required everywhere, but no longer
  sufficient for a global read or any destructive operation.

Specific fixes:

* The three `/orchestrator/audit/*` reads were completely unscoped and returned `hr_turns.raw_text` —
  raw conversation content — for every tenant at once. All three now require a company and carry the
  tenant predicate in SQL.
* Break-glass operations require: enabled by configuration (off by default), a break-glass secret that is
  distinct from the internal token, operator attribution via `X-Operator-Id`, a rate-limit budget, and an
  audit row written *before* the operation runs. If the audit write fails, the operation is refused.
* `apply=true` on the quarantine sweep is no longer reachable by knowing the shared internal token. A
  query parameter is not authorization.

### P0-5 — `web_dashboard` tenant trust

`request_company_code()` trusted `metadata.company_code` whenever `metadata.channel == "web_dashboard"`,
so any holder of the internal token could act as any tenant over HTTP.

Dashboard-originated turns are built in-process from an authenticated dashboard session. They now carry a
per-process authority marker that never leaves the process, and `/orchestrator/whatsapp-turn` strips any
claimed marker at the HTTP boundary. Client-supplied tenant metadata is descriptive only.

### P0-5 — email intake routing

`POST /orchestrator/posthire/documents/email-intake` took its tenant from the request body. It now derives
the tenant from an authenticated routing source — a tenant principal, or the destination mailbox the
message was delivered to (`company_operational_mailboxes`, then `mailbox_connections`). A body
`company_code` that contradicts the routing authority is refused (`intake_routing_conflict`); a body
company with no routing evidence at all is refused (`intake_routing_unresolved`).

### P1-22 — calendar guest-token throttling

Both `/calendar/guest/{token}/state` and `/calendar/guest/{token}/action` consume the shared primitive.
Guest-token semantics are unchanged: an unknown token is still 404, a revoked token is still 410.

### Abuse-control primitive

`wathefni-orchestrator/security_rate_limit.py` (new) is one durable, Postgres-backed limiter so future
public endpoints do not each invent throttling. It supports a route/policy key, principal and IP
dimensions, window, limit, lock, retry metadata (`Retry-After` plus `retry_after_seconds`), telemetry
hooks, and per-policy tuning through `WATHEFNI_RATE_LIMIT_OVERRIDES` without a code change. Counters live
in the database, so additional uvicorn workers cannot bypass them. Only the named routes call it;
internal high-volume application APIs are untouched.

On limiter-store failure the protected routes fail closed, which costs nothing because each of them
already needs the same database to do its work. `WATHEFNI_RATE_LIMIT_FAIL_OPEN=1` exists as an incident
control.

### Security logging

Denied attempts land in `security_denial_events` with route, policy, denial class, timestamp, a truncated
SHA-256 principal digest, and the tenant when it is already authenticated. Credential-shaped keys are
redacted before anything is written. Break-glass use lands in `security_break_glass_events` with operator
attribution. This is deliberately a denial log, not the R8 observability project.

## 3. Endpoint classification matrix

| Route | Class | Company scope | Destructive | Why |
|---|---|---|---|---|
| `/orchestrator/audit/turns` | A — tenant-scoped | required | no | Reads `hr_turns.raw_text` (conversation content). Must never span tenants. |
| `/orchestrator/audit/pending-actions` | A — tenant-scoped | required | no | Reads pending actions for one company's operators. |
| `/orchestrator/audit/action-results` | A — tenant-scoped | required | no | Reads executed action results for one company. |
| `/orchestrator/debug/intake-jobs/{job_id}/replay` | A — tenant-scoped | required | no | Replays one dead-letter job belonging to one company. |
| `/orchestrator/debug/intake-operations` | A — tenant-scoped | required | no | Intake operations summary; the per-company view is the routine use. |
| `/orchestrator/debug/intake-documents/{document_id}/download` | A — tenant-scoped | required | no | Returns quarantined document bytes (candidate PII) for one company. |
| `/orchestrator/debug/intake-documents/{document_id}/signed-download` | A — tenant-scoped | required | no | Mints a short-lived download capability for one company's document. |
| `/orchestrator/posthire/documents/email-intake` | A — tenant-scoped | required | no | Writes employee documents. Tenant derives from the destination mailbox. |
| `/orchestrator/debug/intake-outage-replay` | B — break-glass | global (Class A when a company is named) | no | Platform-wide requeue across every tenant during an outage. |
| `/orchestrator/debug/intake-quarantine/sweep` | B — break-glass | global | **yes** (`apply=true`) | Deletes orphaned quarantine storage across tenants. |
| `/orchestrator/debug/intake-worker/run` | B — break-glass | global | no | Drains the shared ingress queue for all tenants. |

`/orchestrator/debug/prompt-context` and `/orchestrator/debug/llm-usage` remain on the platform internal
token and return no tenant business data; they are recorded as safe debt in §8 rather than reclassified.

## 4. Tenant-scope matrix

| Surface | Tenant source before R2 | Tenant source after R2 | Proof |
|---|---|---|---|
| `hr_turns` audit read | none — global | authenticated principal; SQL predicate `company_code=%s` | tenant A cannot read tenant B turns (403) |
| `pending_actions` audit read | none — global | authenticated principal; SQL predicate | tenant A cannot read tenant B pending actions (403) |
| `action_results` audit read | none — global | authenticated principal; SQL predicate | tenant A cannot read tenant B action results (403) |
| Intake operations / documents / replay | caller-supplied query parameter | authenticated principal, pinned for tenant tokens | tenant A cannot read, mint, or replay for tenant B (403) |
| Email intake | request-body `company_code` | tenant principal, else destination mailbox identity | conflicting body company refused; unresolvable routing refused |
| Dashboard-originated turns | `metadata.company_code` + `channel` string | in-process session authority marker | guessed marker does not select a tenant |
| Platform principal, any Class A route | implicit "all tenants" | must name one company; audited | unscoped read returns 400 `company_scope_required` |

## 5. Rate-limit policy matrix

| Policy | Mode | Limit per identity | Limit per source | Window | Lock | Applied to |
|---|---|---|---|---|---|---|
| `dashboard_login` | failures | 8 | 32 | 15 min | 15 min | `POST /dashboard/auth/login` |
| `setup_operator_login` | failures | 5 | 20 | 15 min | 30 min | `POST /dashboard/superadmin/setup/auth/login` |
| `calendar_guest_token` | requests | 40 | 160 | 5 min | 10 min | `/calendar/guest/{token}/state` and `/action` |
| `internal_break_glass` | requests | 10 | 40 | 10 min | 10 min | Class B platform administration |

Network sources get a wider allowance than a single account so a shared office NAT does not lock out on
one user's typos. Every limit is overridable per policy through `WATHEFNI_RATE_LIMIT_OVERRIDES`.

The source dimension is only as good as the address it reads. The edge proxy (Caddy, on loopback)
*appends* the real peer to any `X-Forwarded-For` the caller sent, so the first element of that header is
caller-controlled and the last is ours. The limiter therefore consults the header only when the direct
peer is a trusted proxy — loopback by default, configurable through `WATHEFNI_TRUSTED_PROXY_HOSTS` — and
then takes the final hop. A caller that reaches the process directly cannot describe its own source at
all. Without this, one attacker could have rotated a header value to spend a fresh per-source budget on
every request; the per-identity budget would still have held, but the per-source budget would have been
decorative.

## 6. Negative-path results

Executed against isolated staging. Two synthetic tenants were created for the cross-tenant tests and
removed afterwards. No production data was used.

**Live deployed staging service (`smoke-test` over HTTP against the restarted process) — 16/16**

| Proof | Result |
|---|---|
| `/ready` reports link signing available and exposes no secret material | pass |
| Link forged with the removed video-interview dev constant | 403 |
| Worker endpoint, no token, from 127.0.0.1 | 403 |
| Worker endpoint, wrong token | 403 |
| Worker endpoint, shared platform token | 403 |
| Worker endpoint, dedicated worker token | accepted |
| Unknown internal token on an audit route | 401 |
| Platform token, unscoped audit read | 400 `company_scope_required` |
| Platform token, explicit company | 200, that company only |
| Tenant token requesting another tenant | 403 `tenant_scope_violation` |
| Tenant token reading itself | 200 |
| `sweep?apply=true` with only the internal token | 403 `break_glass_disabled` |
| Break-glass disabled by default in a real deployment | confirmed |
| Dashboard login brute force | 429 with `Retry-After` |
| Calendar guest-token flood | 429 |

**Staging database, real route handlers, two isolated tenants — 69/69**, including:

* old assessment dev secret cannot forge a token; old video-interview dev secret cannot forge a token
* the database URL cannot serve as a signing key
* a missing production signing secret fails closed (503) and degrades `/ready`
* a valid dedicated signing secret works; rotation keeps issued links alive; removing the retired key kills them
* dashboard and Setup brute-force limits trigger; unknown company, unknown email, and wrong password are
  indistinguishable in status and body; the lockout response names neither the company nor the email
* legitimate credentials still sign in and clear the counter
* calendar guest-token throttle triggers and still returns 404 for an unknown token
* tenant A cannot retrieve tenant B turns, pending actions, action results, or intake artifacts
* a caller-supplied dashboard `company_code` cannot override session tenant, with or without a guessed
  authority marker
* debug / replay / sweep escalation denied; destructive `apply=true` requires the stronger authority,
  operator attribution, and a distinct secret
* unauthorized attempts are audit-visible, and the audit contains none of the password, operator token,
  platform token, tenant token, worker token, break-glass token, signing secrets, or the account email

The staging suite was executed twice back to back, inside the 30-minute lockout window of the first run,
and returned 69/69 both times. Because the limiter is durable rather than per-process, each run takes its
own synthetic source address and operator identity; a suite that reused them would have inherited the
previous run's lockout, which is the correct product behaviour and a defective test.

**Local unit contracts — 84/84**, covering the secret validation matrix, rotation, classification
completeness, principal resolution, break-glass credential separation, policy shape, redaction, and the
spoof-resistance of the network-source dimension.

## 7. Regressions

| Suite | Result |
|---|---|
| Wave 6 product acceptance (C8) unit | 47 passed, 0 failed |
| Wave 6 C1–C7 unit freezes | 27 / 35 / 36 / 33 / 33 / 39 / 40 passed, 0 failed |
| Wave 5 / 4 / 3 / 2 / 1 product acceptance unit | 50 / 48 / 42 / 47 / 28 passed, 0 failed |
| `test_interaction_authority_contracts` | OK (3 tests) |
| `smoke-test-internal-auth.py` (staging DB) | 10 passed, 0 failed |

## 8. Genuine blockers and safe debt

**Open R2 blockers: none.**

Safe debt, recorded rather than hidden:

1. **Deployment prerequisite, not a defect.** Production currently sets no dedicated link-signing secret,
   which means production has been signing public links with `WATHEFNI_DASHBOARD_TOKEN` — the R1 P0-2
   finding, confirmed live. When R2 ships, `WATHEFNI_ASSESSMENT_LINK_SECRET` and
   `WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET` must be provisioned or the public link capabilities become
   unavailable and `/ready` says so. **Any outstanding video-interview link issued under the old fallback
   stops working and must be re-issued.** That is the intended security outcome, and it needs an
   operational note in the rollout, not a code change.
2. **`/orchestrator/debug/prompt-context` and `/orchestrator/debug/llm-usage`** still take the platform
   internal token with no tenant. They expose prompt configuration and aggregate LLM usage counts, not
   tenant business records. Classified as platform diagnostics; revisit in R8 observability.
3. **Setup operator credentials remain an environment JSON map** (`WATHEFNI_SETUP_OPERATOR_CREDENTIALS`).
   R2 throttled and de-enumerated that login but did not move operator identity into a real credential
   store. Out of R2 scope.
4. **`smoke-test-browser-assessment.py` fails at its DB-token stage on staging** with `KeyError: 'attempt'`.
   This is pre-existing and unrelated: the identical failure reproduces against the pre-R2 production
   `app.py` (baseline captured in evidence). The test's HMAC-token assertions, which R2 touches, pass. The
   stale portion of that test belongs to an R3+ cleanup.
5. **Staging tree drift, surfaced not caused.** Restarting the staging service revealed that
   `/opt/wathefni/staging/orchestrator` was missing eight modules its own files import, so the running
   staging process had been serving stale code. The modules were restored from the production tree and
   the service now starts cleanly. Staging deploy integrity belongs to R7 infrastructure.
6. **The rate-limit store shares the application database.** Adequate for the current single-node
   topology and strictly better than the per-process dictionary it replaces, but a future multi-node
   deployment should revisit whether counters belong in a dedicated store.
7. **Operational note:** JSON-valued environment variables such as `WATHEFNI_INTERNAL_TENANT_TOKENS` must
   be quoted in env files. Unquoted braces and commas are mangled by shell brace expansion when the file
   is sourced, which silently degrades a tenant token to "unrecognised" and yields 401.

## 9. Configuration introduced

| Variable | Purpose | Default |
|---|---|---|
| `WATHEFNI_ASSESSMENT_LINK_SECRET` | Assessment link signing (required for the capability) | unset → capability unavailable |
| `WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET` | Video-interview link signing (required) | unset → capability unavailable |
| `..._PREVIOUS` | Comma-separated retired keys, verify only | unset |
| `WATHEFNI_INTERNAL_WORKER_TOKEN` | Dedicated worker channel secret | unset → endpoint closed |
| `WATHEFNI_INTERNAL_WORKER_ACCEPT_SHARED` | Opt in to the shared token for the worker channel | off |
| `WATHEFNI_INTERNAL_TENANT_TOKENS` | `{"COMPANY": "<token>"}` company-scoped internal principals | unset |
| `WATHEFNI_BREAK_GLASS_TOKEN` | Break-glass secret, must differ from the internal token | unset |
| `WATHEFNI_BREAK_GLASS_ENABLED` | Enables Class B operations | **off** |
| `WATHEFNI_TRUSTED_PROXY_HOSTS` | Peers whose `X-Forwarded-For` may be believed | loopback only |
| `WATHEFNI_RATE_LIMIT_OVERRIDES` | Per-policy tuning | unset |
| `WATHEFNI_RATE_LIMIT_FAIL_OPEN` | Incident control | off (fail closed) |
| `WATHEFNI_RATE_LIMIT_DISABLED` | Emergency kill switch | off |

## 10. Stop

R2 is complete and frozen. **STOP for owner review before R3 Production Data Safety.**

`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS` is not `PRODUCTION_READY` and does not authorise rollout.
Wave 4/6 remain global-OFF and company-gated; the R5 hybrid surface decision is untouched. R3 does not
start automatically.
