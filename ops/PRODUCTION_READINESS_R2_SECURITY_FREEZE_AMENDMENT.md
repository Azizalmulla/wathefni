# Production Readiness R2 — Security Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`
**Phase:** R2 — Security & Secret Hardening
**Date:** 2026-08-12
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Baseline:** `ops/PRODUCTION_READINESS_R1_AUDIT.md` (owner accepted)
**Full pass:** `ops/PRODUCTION_READINESS_R2_SECURITY_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r2-security-20260812T154724Z/`

---

## What freezes with R2

These are now binding contracts. Changing any of them requires a written amendment, not a pull request.

1. **Public link signing keys are dedicated or absent.** No signing path may fall back to another
   credential, a connection string, or a constant in source. `wathefni-orchestrator/security_link_secrets.py`
   is the only source of link key material. Missing or invalid means the capability is unavailable.
2. **The removed dev constants stay banned.** `wathefni-assessment-dev-secret` and
   `wathefni-video-interview-dev-secret` may never verify a token again, in any environment.
3. **One abuse-control primitive.** New public or authentication endpoints use
   `security_rate_limit.py`. A new endpoint does not invent its own throttle, and rate-limit state stays
   durable and shared across workers.
4. **Authentication endpoints do not disclose existence.** Company existence, account existence, and
   "the password alone was wrong" may not be inferable from status code, body, or error code before
   credentials are proven.
5. **Network position is never authentication.** No endpoint may accept a caller because of client host,
   proxy header, or loopback origin. The removed `token unset → localhost accepted` branch does not come back.
   Where an address is used as a rate-limit *dimension*, it is taken from the hop our own edge proxy
   appended, and a forwarding header is believed only from a trusted proxy peer.
6. **Every internal endpoint carries a class.** Class A (tenant-scoped routine) or Class B
   (platform / break-glass), declared in `security_internal_authority.ENDPOINT_CLASSIFICATION`. A new
   internal route without a classification is a defect.
7. **Tenant scope comes from the authenticated principal.** For Class A, caller-supplied `company_code`
   may narrow to what the principal already holds, never widen it, and every query and update carries the
   tenant predicate. A tenant principal is pinned to its own company.
8. **Client-supplied tenant metadata is descriptive only.** `channel == "web_dashboard"` — or any other
   string a caller controls — is not tenant authority. Dashboard-originated actions bind to the
   authenticated session in-process.
9. **Break-glass is disabled by default.** Class B operations require configuration to be enabled, a
   secret distinct from the internal token, operator attribution, a rate-limit budget, and an audit row
   written before the operation runs. An unauditable break-glass operation does not execute.
10. **Destructive operations need more than the shared internal token.** A query parameter such as
    `apply=true` is not authorization.
11. **Tenant selection for inbound mail derives from a routing authority.** A request-body company is
    never sufficient; a body company that contradicts the destination mailbox is refused.
12. **Denial logs stay clean.** Passwords, signing secrets, bearer tokens, and candidate or employee
    content never enter `security_denial_events` or `security_break_glass_events`. Principals are stored
    as digests.

## What does not change

1. Waves 1–6 remain frozen as **domain authority**. R2 reopened no domain model. The only frozen-surface
   edits were the security gates named above.
2. Waves 4–6 remain **not product-surface complete**, exactly as the R1 interpretation amendment states.
   The R5 hybrid decision is untouched and is not implemented here.
3. All Wave 4/6 capability remains global-OFF and company-gated.
4. `PRODUCTION_READINESS_R2_SECURITY_FULL_PASS` is **not** `PRODUCTION_READY` and authorises no rollout.

## Deployment prerequisites

R2 fails closed, which means it has real deployment requirements:

* `WATHEFNI_ASSESSMENT_LINK_SECRET` and `WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET` must be provisioned before
  the public link capabilities work. Production has never had them — it was signing with the dashboard
  token — so this is a required provisioning step, not an optional one.
* **Video-interview links issued under the old fallback stop verifying and must be re-issued.** That is
  the point of the fix; plan the candidate-facing communication.
* `WATHEFNI_INTERNAL_WORKER_TOKEN` must be set for any caller of the worker endpoint. Verified: the
  production transcript worker runs in-process and does not use it today.
* Company-scoped internal tokens (`WATHEFNI_INTERNAL_TENANT_TOKENS`) are optional. Without them, internal
  callers are platform principals that must name a company explicitly on Class A routes.
* JSON-valued environment variables must be quoted in env files.

## Rollback

Rolling back means restoring the previous `app.py` and removing the three `security_*.py` modules and the
`zzzzz-r2-security.conf` drop-in. That reinstates forgeable public links, an unthrottled login surface, a
localhost-open worker endpoint, and cross-tenant audit reads, so it is an incident action rather than a
routine option.

Safer partial controls, in order of preference:

* `WATHEFNI_RATE_LIMIT_OVERRIDES` to loosen a specific policy.
* `WATHEFNI_RATE_LIMIT_DISABLED=1` to suspend throttling only.
* `WATHEFNI_INTERNAL_WORKER_ACCEPT_SHARED=1` to let the platform token drive the worker channel.
* `<VAR>_PREVIOUS` to keep already-issued links alive through a key change.

The new tables (`security_rate_limit_buckets`, `security_denial_events`, `security_break_glass_events`)
are additive and can stay in place across a rollback. History is retained.

## Do not begin automatically

R3 Production Data Safety · R4+ remediation · R5 Wave 4/6 surface work · RP physical device
qualification · RC canary company · broad production rollout.

**STOP for owner review.**
