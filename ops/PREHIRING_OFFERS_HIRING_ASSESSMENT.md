# Pre-Hiring Offers and Hiring — End-to-End Assessment

**Assessment date:** 2026-07-25 (Kuwait)  
**Mode:** Read-only source, test, configuration, route-guard, schema, and aggregate production-data inspection  
**Implementation/deployment:** None  
**Authoritative source inspected:** `/tmp/wathefni-c3-local`  
**Production host inspected read-only:** `root@76.13.63.68`  
**Frozen authorities left unchanged:** Jobs, Candidates, Ranking, Reports, Assistant, Assessments, and Interviews

## Executive verdict

**Verdict: Offers/Hiring has a strong authority core, but it is not yet enterprise-ready for the complete scope of this assessment. A contained Offers/Hiring remediation is justified before the module is frozen.**

The strengths that should be preserved are:

- formal employment offers are first-class entities, not application stages;
- terms are versioned while draft and the accepted version is pinned;
- creation, approval, send, withdrawal, and manual response use distinct permissions;
- self-approval is denied by default;
- AI cannot mutate offers or use hire override;
- public response tokens are random, stored hashed, version-bound, one-time, and revoked on response or withdrawal;
- an enabled `employment_offers` module requires an accepted offer before hire, except for a grant-only, human-confirmed, reasoned, durably audited override;
- the canonical hire path commits application stage, employee creation/linkage, compliance seeding, onboarding seed when enabled, and hire-operation completion in one PostgreSQL transaction;
- duplicate employee links and concurrent open hire operations have database guards;
- Reports consumes aggregate offer/hire truth without exposing compensation;
- the module depends only on `pre_hiring`; it does not depend on Ranking, Assessments, or Interviews.

The confirmed enterprise blockers are:

1. **Compensation privacy is too broad.** Any role with `prehire.read`, including `viewer`, can retrieve salary, allowances, terms, internal notes, and the offer PDF. There is no offer-read or compensation-read scope.
2. **Expiry is not an offer lifecycle operation.** A due token rejects a response, but the offer remains `sent`, the stale public link still reveals compensation, and the open-offer uniqueness guard prevents a replacement offer.
3. **Send is not recoverable or concurrency-safe across the external message and database.** WhatsApp is called before the offer/token/delivery transaction. A stale or failed database commit can leave a delivered but unusable link, and concurrent calls can message twice.
4. **There is no resend/reissue authority.** A lost or expired link cannot be safely replaced in place. The one response URL returned by send disappears after the dashboard reload, including the documented manual-share fallback.
5. **Public offer HTML interpolates unescaped database fields.** Candidate-controlled or operator-controlled title/name text can execute markup/script in the public candidate page.
6. **Legacy direct hire handlers remain in `app.py` and bypass the accepted-offer gate and atomic `hire_operations` path.** Current registry configuration mitigates the native dashboard path, but the old pending/direct-action graph contains executable `update_application_status(..., "hired")` plus separate `transition_hire(...)` branches.

Material but narrower findings also exist in accepted-offer uniqueness, database immutability/constraints, Arabic document rendering, audit-feed completeness, hire-override confirmation defaults, web confirmation UX, and mobile presentation parity.

This verdict does **not** justify reopening Ranking, Assessments, Interviews, Reports, Assistant, Jobs, or Candidates. The smallest justified work is an Offers/Hiring boundary remediation and the minimum shared-entrypoint delegation needed to eliminate the legacy hire bypass. No changes were made during this assessment.

## Scope and evidence standard

Evidence used:

- frozen orchestrator, dashboard, and HR-mobile source under `/tmp/wathefni-c3-local`;
- exact production SHA-256 fingerprints for the offer, hire, route, mobile, Reports, and shared-entrypoint files;
- read-only production environment-key presence, module policy, schema/index/constraint inspection, table grants, and aggregate integrity SQL;
- unauthenticated production route-guard probes against `127.0.0.1:8010`;
- existing Offer-1 smoke tests and production/staging proof scripts;
- local execution of the two non-mutating Offer-1 smoke suites.

No finding is based on another HR product’s feature set. A missing capability is classified only where it:

- contradicts the explicit authority requested for this assessment;
- creates a demonstrated privacy, legal-terms, delivery, lifecycle, concurrency, or audit failure;
- leaves an advertised state or recovery path unreachable; or
- makes the current UI/API claim materially misleading.

## Production truth snapshot

Read-only production inspection established:

| Evidence | Production observation |
|---|---|
| Health/binding | `/health` returned `200`, `status=ok`, and matched production application/database binding |
| Offer dashboard guards | unauthenticated list/get returned JSON `401 dashboard_auth_failed` |
| Mobile guard | unauthenticated candidate detail returned JSON `401 session_expired` |
| Invalid public token state | JSON `404 invalid_token` |
| Invalid public token page | HTML `404 Offer unavailable` |
| Module state | `employment_offers` enabled for `WATHEFNI` only |
| Module source | `production_controlled_enablement` |
| Self-approval setting | unset; code default is `false` |
| Registry routing | `WATHEFNI_PREHIRE_VIA_REGISTRY=all` |
| Onboarding seed | `WATHEFNI_ONBOARDING_SEED=off` |
| Offer rows | 0 |
| Past-due sent offers | 0 |
| Expired, unused, unrevoked offer tokens | 0 |
| Hired applications without linked employee | 0 |
| Duplicate `(company_code, app_key)` employee links | 0 |
| Offer/hire worker | no offer-expiry or hire-reconciliation service/timer exists |
| Production schema | all six Offer-1 tables, `hire_operations`, applications, and employees present |
| Employee link guard | `employees_company_app_key_uq` present |
| Offer status constraints | no database `CHECK` on offer or delivery status |
| Version immutability | no trigger; runtime role has `UPDATE`, `DELETE`, and `TRUNCATE` on version/event/token/delivery tables |

The clean aggregate state is positive operational evidence. It does not prove missing expiry, resend, compensation, or delivery-recovery controls because production currently has no offer rows.

### Frozen-source-to-production fingerprints

| File | SHA-256 |
|---|---|
| `offer_lifecycle.py` | `efae44a80504d0ea7f5b6ac92a8da5c0482142ead153db35537c99a56fdcf311` |
| `offer_service.py` | `9686a108c1b7ea748a90636a913b78bc6dd416aa8e27dfb8173e27092b8417a7` |
| `offer_routes.py` | `914c5975dc3b5f10bd6eadc4deb29259ad6638321290d4e6cb85cfdefe95e7b8` |
| `hire_operations.py` | `d7a32c0f66579094d61d367e7ad95cee63dfd5aed3221a58f2e50509f3248099` |
| `app.py` | `ba3f4a4a3375bb05b8bd37bf0d4d10b47f24d003596e11d144c1637f6a92a6ef` |
| `action_registry.py` | `04c58c9fdc68d9809bfc3fffa62cdbe2be100b82dcf7efd622129099fbce2631` |
| `tool_call_orchestrator.py` | `a968142adf4343bfed8ea57dd9af6713df103207a5ab0924e879e5f806fbff52` |
| `operator_mobile.py` | `0fa299a11e0fdd2138f38ee4ce928f91ab56b337cfed86a1d43bc9ef36344a45` |
| `operator_mobile_data.py` | `574e9f565c0f50b1f5f893404c0078f9a6a826ee6fbb02fd5290f957ce2621f6` |
| `reports_v1.py` | `d7f52f2a082ff1ad5979e642ce44bf892f3dd41ea3a979f7c92f5b975c147a41` |

The local and production fingerprints matched exactly.

## Architecture and authority map

### Runtime architecture

```text
Dashboard candidate drawer
  → OfferPanel
  → authenticated, tenant-scoped offer routes
  → offer_service
  → employment_offers
       ├─ employment_offer_versions
       ├─ employment_offer_events
       ├─ employment_offer_tokens
       ├─ employment_offer_deliveries
       └─ employment_offer_hire_override_audits

Candidate response
  → /offer/{token}
  → SHA-256 token lookup + version/status/expiry checks
  → accepted | declined

Dashboard / mobile / Assistant hire
  → human confirmation
  → accepted-offer gate or grant-only audited override
  → hire_operations
  → canonical recruiting_lifecycle transition
  → transactional employee create/link
  → compliance seed
  → optional onboarding seed
  → completed hire operation

Reports
  → aggregate employment_offers + canonical lifecycle events
  → no compensation projection
```

### Source ownership

| Concern | Authority |
|---|---|
| Offer states, permissions, tables, labels, hire gate helpers | `wathefni-orchestrator/offer_lifecycle.py` |
| Draft/version/send/respond/token/document/override behavior | `wathefni-orchestrator/offer_service.py` |
| Dashboard and public HTTP routes | `wathefni-orchestrator/offer_routes.py` |
| Atomic hire and employee creation | `wathefni-orchestrator/hire_operations.py` |
| Canonical application stage transition | `wathefni-orchestrator/recruiting_lifecycle.py` |
| Dashboard + Assistant shared registry hire executor | `wathefni-orchestrator/action_registry.py:764-904` |
| Dashboard offer UI | `apps/wathefni-dashboard/src/components/OfferPanel.tsx` |
| Dashboard offer client | `apps/wathefni-dashboard/src/lib/offers-api.ts` |
| Post-hire UI handoff | `apps/wathefni-dashboard/src/hireHandoff.ts` |
| Mobile capability/API adapter | `operator_mobile.py:735-829`; `operator_mobile_data.py:1695-1758,2770-2853` |
| Reports consumer | `reports_v1.py:192-210,480-500,664-704` |

### Canonical tables

1. `employment_offers`
   - current offer state and current-term projection;
   - company/application scope;
   - approval/send/response/withdraw audit fields;
   - source: `offer_lifecycle.py:233-289`.
2. `employment_offer_versions`
   - versioned canonical `terms_json`, bilingual wording, document hash/location/source;
   - primary key `(offer_id, version)`;
   - source: `offer_lifecycle.py:292-309`.
3. `employment_offer_events`
   - lifecycle event history with actor, status change, version, confirmation reference, and payload;
   - source: `offer_lifecycle.py:313-335`.
4. `employment_offer_tokens`
   - hashed one-time response tokens, version binding, expiry, use, and revocation;
   - source: `offer_lifecycle.py:338-357`.
5. `employment_offer_deliveries`
   - offer/version/document-specific channel result;
   - source: `offer_lifecycle.py:361-386`.
6. `employment_offer_hire_override_audits`
   - grant-only exception audit with actor subject, reason, confirmation, source stage, and idempotency;
   - source: `offer_lifecycle.py:391-427`.
7. `hire_operations`
   - durable prepare/execute operation with observed stage/version, actor, confirmation, result, and recovery status;
   - source: `hire_operations.py:16-56`.
8. `employees.app_key`
   - canonical application-to-employee link;
   - production has unique partial index `employees_company_app_key_uq`.

### Status models

**Offer:** `draft`, `pending_approval`, `approved`, `sent`, `accepted`, `declined`, `expired`, `withdrawn` (`offer_lifecycle.py:24-47`).

**Delivery:** `pending`, `sent`, `failed`, `intentionally_skipped` (`offer_lifecycle.py:75`).

**Hire operation:** `prepared`, `processing`, `completed`, `failed`, `manual_review` with a database `CHECK` (`hire_operations.py:19-55`).

**Application:** Offers remain orthogonal. `offered` and `offer_sent` are legacy read aliases normalized to `shortlisted`; they are not formal-offer states (`recruiting_lifecycle.py:62-64`).

## Capability matrix

| Capability | Current result | Authority/evidence | Enterprise gate |
|---|---|---|---|
| Create draft | Implemented | `offer_service.py:163-331` | Pass |
| Draft idempotency | Implemented | company/idempotency unique index + lookup | Pass |
| One open offer per application | Implemented | `employment_offers_open_app_uq` | Pass for open states |
| Edit/version draft | Implemented | optimistic version CAS; inserts next version | Pass in service |
| Immutable sent terms | Service-enforced | edits only when `status='draft'` | Partial: no DB immutability |
| Submit approval | Implemented | `draft → pending_approval` | Pass |
| Separation of duties | Implemented | creator cannot approve unless explicit company policy | Pass |
| Approve/return | Implemented | permission + state CAS | Pass, minor matrix drift |
| Send | Implemented | WhatsApp + delivery/token/event | Fail: partial-write boundary |
| Delivery truth | Partial | success row versioned; failed send raises before offer delivery row | Fail |
| Resend/reissue | Missing | no service, route, UI, or worker | Fail |
| Candidate accept/decline | Implemented | public one-time token and manual HR path | Pass |
| Expiry | Token-only | response rejects due token; offer never becomes `expired` | Fail |
| Withdrawal | Implemented | reason required; unused tokens revoked | Pass |
| Compensation privacy | Missing dedicated scope/redaction | all `prehire.read` callers receive terms/PDF | Fail |
| Secure public preview | Partial | hashed token, but expiry not enforced on preview | Fail |
| Hire gate | Implemented | accepted offer or audited override when module enabled | Pass on canonical path |
| Atomic employee creation | Implemented | lifecycle + employee + seed + operation in one transaction | Pass |
| Duplicate hire guard | Implemented | unique app/employee link and open operation guards | Pass |
| Partial-hire detection | Implemented read-only | `reconcile_hire_operations` reports half-hires | Partial: no active worker |
| Onboarding handoff | Implemented conditionally | employee/compliance always; checklist seed feature-gated | Pass with config caveat |
| Dashboard | Full core offer flow | `OfferPanel.tsx` | Partial UX/localization |
| Mobile backend | Read + approve/return/respond/withdraw | mobile offer endpoint | Pass as stated V1 subset |
| Mobile app UI | Not wired | no offer action use in HR-mobile source | Parity gap, not authority bypass |
| Assistant | Hire only; offer mutation absent | AI mutation rejected; registry hire gated | Pass; no new offer tools justified |
| Reports | Aggregate offer/hire truth | `reports_v1.py` | Pass |
| Arabic | Labels/wording fields exist | generated PDF converts non-ASCII to `?`; panel EN-only | Fail for generated Arabic artifact |
| Ranking/Assessments/Interviews independence | Confirmed | module depends only on `pre_hiring`; no service coupling | Pass |

## Offer, version, and approval authority

### What is sound

- `build_terms_payload` canonically snapshots role, department, currency, salary, allowances, proposed start, probation, expiry, wording, and candidate name (`offer_lifecycle.py:443-471`).
- Create writes version 1 and a SHA-256 document reference in the same database transaction (`offer_service.py:251-330`).
- Draft edit uses expected version and `WHERE ... status='draft' AND current_version=%s`, then inserts a new version row (`offer_service.py:334-505`).
- Sent and terminal offers cannot be edited through the service.
- Acceptance stores `accepted_version=current_version` (`offer_service.py:832-847,933-947`).
- Approval has a distinct `offer.approve` permission and self-approval is denied unless the tenant explicitly sets `offer_allow_self_approval=true` (`offer_service.py:540-547`).
- AI actors are rejected before all offer mutations (`offer_lifecycle.py:551-565`).

### Integrity limitations

- The database has no offer-status `CHECK`, delivery-status `CHECK`, or transition trigger.
- `employment_offer_versions` and `employment_offer_events` are not append-only at the database boundary.
- The production runtime role can update, delete, truncate, and trigger all Offer-1 tables.
- The status matrix advertises `approved → draft`, but `return_to_draft` only accepts `pending_approval` (`offer_lifecycle.py:41`; `offer_service.py:619-620`).
- `requires_approval` exists but is not read by the service; all offers currently require the approval path.
- The open-offer index excludes accepted offers, and `create_draft` checks only `find_open_offer`. A shortlisted/interview application can therefore accumulate multiple accepted offers, creating competing accepted legal terms (`offer_lifecycle.py:272-275`; `offer_service.py:224-231`).

## Delivery and candidate-flow analysis

### Current flow

1. Read approved offer/version.
2. Mint a raw response token and build the public URL.
3. Render localized WhatsApp invitation.
4. Call `send_company_whatsapp_message`.
5. If transport reports failure, raise `offer_delivery_failed`.
6. In a new database transaction, CAS `approved → sent`.
7. Insert token hash, delivery row, and offer event.
8. Return the response URL once; the HTTP route strips `raw_token`.

Evidence: `offer_service.py:630-799`; `offer_routes.py:272-289`.

### Truth and recovery problems

- External delivery precedes the database CAS and token insert (`offer_service.py:668-713` before `715-795`).
- A concurrent loser can send the message and only then fail `status='approved'` CAS.
- A database error after transport success leaves a candidate with a URL whose token hash may not exist.
- A failed external send raises before an `employment_offer_deliveries(status='failed')` row is written, so Offer-1’s own delivery history is incomplete.
- No-transport mode marks `intentionally_skipped` and still sets `sent`, which is defensible only if HR can retrieve the URL for manual sharing.
- The send response contains `respond_url`, but `OfferPanel.run` ignores the returned object and immediately reloads (`OfferPanel.tsx:58-64`).
- Reloaded `offer_public_dto` does not expose the response URL or delivery metadata (`offer_lifecycle.py:897-971`), so the documented manual-share link disappears.
- There is no resend/reissue endpoint or service.
- The raw bearer URL is persisted in delivery metadata (`offer_service.py:767-775`), reducing token secrecy to database/backup confidentiality.

### Candidate response

The mutation path is comparatively strong:

- lookup uses SHA-256 of the raw token;
- token row and offer are locked;
- invalid, revoked, used, expired, wrong-state, and wrong-version tokens fail closed;
- offer response, token use, and event commit together (`offer_service.py:876-960`).

The preview path is weaker:

- `public_offer_preview` does not reject `expires_at < now()`;
- it returns candidate name and salary and sets `can_respond` without checking expiry (`offer_service.py:964-995`);
- the HTML then renders those values and response buttons (`offer_routes.py:359-395`);
- all dynamic HTML fields are interpolated without escaping.

## Hiring and employee-creation authority

### Canonical path

The canonical flow is:

1. `prepare_hire_operation` locks the tenant-scoped application, enforces one open operation, captures observed stage/version, actor, channel, reason, and idempotency (`hire_operations.py:93-183`).
2. Candidate-action confirmation binds the operation reference and observed state (`app.py:52339-52402`).
3. `enforce_hire_gate` requires an accepted offer when `employment_offers` is enabled (`offer_service.py:1034-1128`).
4. A no-offer override requires the grant-only permission, human actor, explicit confirmation, reason, and a durable idempotent audit written before proceeding.
5. `execute_hire_operation` calls canonical `transition_application` with the original expected stage/version and confirmation (`hire_operations.py:306-352`).
6. The transactional side effect creates or links exactly one employee, seeds compliance documents, conditionally seeds onboarding items, records the application hiring projection, and completes the operation (`hire_operations.py:186-301`).
7. Any transactional side-effect failure rolls back the application transition (`recruiting_lifecycle.py:1599-1620`).

This is a credible enterprise transaction boundary.

### Duplicate and concurrency controls

- unique `(company_code, idempotency_key)` for hire operations;
- one open `prepared|processing` operation per company/application;
- `FOR UPDATE` on application and operation rows;
- unique employee link per `(company_code, app_key)`;
- existing employee-key/app-key collision checks;
- completed operation replay returns idempotently;
- lifecycle transition uses expected stage/version and confirmation.

### Recovery limitations

- `reconcile_hire_operations` only reports recoverable operations and hired-without-employee rows; it does not execute recovery and has no production worker (`hire_operations.py:355-387`).
- `prepare_hire_operation` is called before the dashboard’s accepted-offer gate. A rejected hire attempt can leave a prepared operation that blocks a different actor until the original operation is reused or manually handled (`app.py:52361-52383,52553-52588`).
- Hire-override audit commits before hire execution. If the later lifecycle CAS fails, the audit says `to_stage='hired'` but has no completion/outcome field.
- `DashboardHireRequest.confirm` defaults to `True`, weakening the requirement that an override client explicitly opt into confirmation (`app.py:36880-36883,52543-52571`).

### Legacy parallel hire paths

Two legacy graph handlers still execute:

```text
update_application_status(app, "hired")
transition_hire(app)
```

at `app.py:33259-33271` and `app.py:33615-33628`.

Those branches do not call `enforce_hire_gate`, `prepare_hire_operation`, or `execute_hire_operation`. They also split application transition from employee creation. Production’s `WATHEFNI_PREHIRE_VIA_REGISTRY=all` protects the migrated native pre-hire path, and `WATHEFNI_LEGACY_REGEX_INFERENCE_ENABLED` is not enabled, but the capability/pending-action graph remains executable code. This is a real parallel authority, not merely a legacy label.

## Lifecycle and onboarding integration

- Offer status is correctly separate from application lifecycle.
- Formal-offer module enablement changes the hire gate but does not modify Ranking, Assessment, or Interview authority.
- Hiring creates/links the employee and seeds compliance documents in the same transaction.
- Dashboard extracts the new `employee_key` and can hand off to the employee/post-hire surface (`hireHandoff.ts:17-35`).
- Onboarding checklist seeding is intentionally dark-launched. Production currently has `WATHEFNI_ONBOARDING_SEED=off`; therefore a successful hire creates the employee and compliance baseline but does not create onboarding checklist rows (`app.py:385-390`; `hire_operations.py:271-274`).
- This setting is not itself a defect if the owner intentionally keeps onboarding checklist seeding disabled. It must, however, be explicit in qualification: “employee created” and “onboarding checklist started” are not equivalent in current production.

Rollback behavior is strong inside the canonical hire transaction. External employee communication and sheet mirrors are explicitly outside the committed hiring result (`hire_operations.py:1-5`), so they require separate delivery truth rather than rollback of a completed hire.

## Permissions, privacy, tenant isolation, and audit

### Mutation permissions

| Action | Required permission |
|---|---|
| Create/edit/submit | `offer.manage` |
| Approve/return | `offer.approve` |
| Send | `offer.send` |
| Withdraw | `offer.withdraw` |
| Manual response | `offer.record_response` |
| Hire | `candidate.decide` |
| Hire without accepted offer | grant-only `offer.hire_override` |

Role defaults are intentionally separated:

- owner/HR manager: manage, approve, send, withdraw, record response;
- recruiter: manage, send, withdraw; no approval;
- hiring manager: approve only;
- viewer: no offer mutation;
- hire override: never inferred from role defaults.

### Read/privacy defect

The read side does not mirror that separation:

- list/get/document routes call `_require_offers_module`, which requires only `prehire.read` (`offer_routes.py:105-127,163-183,339-357`);
- `viewer` has `prehire.read` (`app.py:6133-6135`);
- the DTO always returns base salary, allowances, terms, wording, candidate phone snapshot, and web internal notes (`offer_lifecycle.py:932-963`);
- the PDF route has no additional offer or compensation scope.

Tenant scoping is otherwise consistent: offer queries include `company_code`, application resolution is tenant-scoped, mobile uses authoritative backend context, and production proofs include cross-tenant denial.

### Audit

Offer lifecycle events and hire-override audits are durable and actor-aware. The main pre-hire audit endpoint, however, reads `action_results` and does not union `employment_offer_events` or override audits. Candidate timeline can surface offer events separately. If `/dashboard/prehire/audit` is presented as the compliance authority, its offer history is incomplete.

## Assistant, Reports, mobile, dashboard, and Arabic parity

### Assistant

- No create/approve/send/withdraw offer tools are registered.
- This is correct: the offer authority explicitly forbids AI mutation.
- Hire remains a sensitive, confirmed action and uses the accepted-offer gate on the registry path.
- AI hire override is stripped and rejected.
- No evidence justifies adding Assistant offer mutations.

### Reports

- Reports reads `employment_offers` for aggregate offer counts and sent/accepted funnel events.
- It reads canonical lifecycle events for hires.
- It does not project compensation.
- Reports is a consumer, not a mutation authority.
- No Reports remediation is justified.

### Mobile

- Backend candidate detail includes an Offer-1 payload.
- Backend supports confirmed approve, return, record accept/decline, and withdraw.
- Create/edit/send are intentionally excluded from mobile V1.
- The HR mobile client does not render or call the offer actions; it only recognizes generic offer timeline events and legacy stage aliases.
- This is a presentation parity gap, not a bypass. No evidence justifies expanding mobile beyond the documented V1 subset; wiring that existing subset is optional unless owner workflow requires it.

### Dashboard

- The full core lifecycle is present in `OfferPanel`.
- Approve, send, record accept/decline, and withdraw execute immediately on click; unlike hire and mobile offer actions, there is no explicit confirmation dialog.
- Uploaded PDF, version-history document download, and hire override exist in backend authority but are not surfaced in the panel.
- Hire override should remain hidden unless the owner intends to operate the grant-only exception. Its API confirmation default must still be corrected.

### Arabic/RTL and accessibility

- Arabic status labels and bilingual wording fields exist.
- Candidate invitation locale uses the candidate message catalog.
- The dashboard panel is hard-coded English and has no locale/RTL handling.
- Inputs rely on placeholders rather than explicit labels.
- The minimal PDF generator converts every non-ASCII character to `?` (`offer_lifecycle.py:504-507`), so a generated Arabic legal document is not faithful even though the terms JSON contains Arabic.
- The public offer page is English-only and does not set locale/direction.

## Failure and idempotency matrix

| Scenario | Current behavior | Correctness |
|---|---|---|
| Duplicate draft, same idempotency key | returns existing offer | Pass |
| Concurrent draft, different keys | partial unique open-offer index rejects one | Pass |
| Stale draft edit | expected-version CAS returns `stale_offer` | Pass |
| Concurrent approval/withdraw | status CAS lets one win | Pass |
| Concurrent send | both may externally message before one DB CAS fails | Fail |
| Provider failure before any send | raises and offer stays approved | Partial; Offer-1 failed delivery row absent |
| Provider success, DB failure | candidate may receive invalid token URL | Fail |
| No transport | marks intentionally skipped and offer sent | Partial; manual URL is not recoverable after reload |
| Lost candidate link | no resend/reissue | Fail |
| Token second use | rejected | Pass |
| Token wrong version | rejected | Pass |
| Token withdrawn | rejected | Pass |
| Token expired response | rejected | Pass |
| Expired-token preview | still exposes salary and may show response buttons | Fail |
| Due sent offer | remains sent/open forever | Fail |
| Replacement after expiry | blocked by open-offer guard until manual withdraw | Fail |
| Multiple accepted offers | allowed because accepted is terminal and excluded from open uniqueness | Fail/ambiguous |
| Hire before acceptance, canonical path | rejected | Pass |
| Hire override without grant/reason/confirm/audit | rejected | Pass, except API confirm default |
| Duplicate hire confirmation | completed operation replays idempotently | Pass |
| Concurrent hire operations | one open operation per app | Pass |
| Employee already linked to another application | rejected | Pass |
| Employee/lifecycle side effect fails | whole canonical hire transaction rolls back | Pass |
| Legacy direct hire handler | stage and employee side effect are separate; no offer gate | Fail |
| Onboarding seed disabled | employee/compliance created, no checklist rows | Explicit config behavior |
| Offer DB status corruption | no status/delivery `CHECK` | Fail at DB integrity layer |
| Version/event mutation by runtime DB role | permitted; no append-only trigger | Fail at legal-audit integrity layer |
| PDF write then DB rollback | orphan file can remain | Low-severity cleanup gap |

## Classified findings

### OH-01 — Compensation and offer documents are readable with generic `prehire.read`

- **Exact evidence:** `offer_routes.py:105-127,163-183,339-357`; `offer_lifecycle.py:932-963`; `app.py:6133-6135`.
- **Concrete risk/failure:** A viewer or any generic pre-hire reader can retrieve salary, allowances, complete terms, internal notes, candidate phone snapshot, and the legal PDF without an offer/compensation read scope.
- **Affected user/workflow:** viewers, hiring managers, recruiters, delegated auditors, offer list/detail/document workflow.
- **Severity:** High.
- **Enterprise-readiness blocker:** Yes.
- **Smallest justified fix:** add one dedicated backend read permission (for example, `offer.read_compensation`) and enforce it consistently on list/get/document/mobile DTOs; return a redacted status-only offer projection to generic pre-hire readers.
- **Consequence if unchanged:** formal compensation is disclosed beyond the mutation roles the permission model otherwise separates.

### OH-02 — Due offers never become `expired`, and stale links retain read access

- **Exact evidence:** `expired` is declared in `offer_lifecycle.py:24-47`; sent remains open in `35-42` and `272-275`; only response checks token expiry at `offer_service.py:905-907`; preview omits expiry at `964-995`; no expiry writer or worker exists.
- **Concrete risk/failure:** Candidate response fails after due date, but HR sees `sent`, a replacement offer is blocked, Reports continues to count sent, and anyone holding the old URL can still read salary.
- **Affected user/workflow:** candidate response, HR follow-up, expiry, replacement offer, Reports funnel, compensation privacy.
- **Severity:** High.
- **Enterprise-readiness blocker:** Yes.
- **Smallest justified fix:** implement an idempotent due-offer transition that CASes `sent → expired`, revokes unused tokens, records an event, and is invoked both lazily on read/respond and by a small worker/sweep; make preview reject or redact expired tokens.
- **Consequence if unchanged:** permanent sent-state dead ends and indefinite stale-link compensation disclosure.

### OH-03 — External send precedes the canonical database claim

- **Exact evidence:** provider call and result handling at `offer_service.py:668-713`; offer CAS/token/delivery/event transaction at `715-795`.
- **Concrete risk/failure:** concurrent sends can message twice; a successful message can contain a token that is never persisted if the later CAS or database transaction fails.
- **Affected user/workflow:** sender, candidate, delivery support, retry/concurrency.
- **Severity:** High.
- **Enterprise-readiness blocker:** Yes.
- **Smallest justified fix:** claim a durable send operation first, persist pending token/delivery/outbox state, let one worker/provider call execute, then mark sent/failed idempotently. Wathefni remains canonical even if provider delivery fails.
- **Consequence if unchanged:** duplicate messages, broken candidate links, and disagreement between provider reality and Offer-1 truth.

### OH-04 — There is no resend/reissue or durable manual-share recovery

- **Exact evidence:** no resend service/route/client exists; send returns `respond_url` at `offer_service.py:796-798`; route retains it at `offer_routes.py:287-289`; `OfferPanel.run` discards the response and reloads at `OfferPanel.tsx:58-64`; reload DTO omits the URL at `offer_lifecycle.py:897-971`.
- **Concrete risk/failure:** a candidate who loses the message, or an intentionally skipped delivery, cannot receive/retrieve a valid link without withdrawing and creating a new offer or manually recording a response.
- **Affected user/workflow:** HR support, candidate resend, no-transport/manual-share path.
- **Severity:** High.
- **Enterprise-readiness blocker:** Yes.
- **Smallest justified fix:** add idempotent resend/reissue for `sent`: revoke the prior unused token, mint one replacement token for the same version, persist a new delivery operation, and expose truthful status. Do not persist the raw URL after send.
- **Consequence if unchanged:** routine delivery recovery requires legal-state workarounds and weakens candidate-response evidence.

### OH-05 — Public offer HTML is vulnerable to unescaped field injection

- **Exact evidence:** direct f-string interpolation of title, candidate name, salary, status, and token into HTML at `offer_routes.py:368-395`; no escaping/template auto-escape.
- **Concrete risk/failure:** a crafted candidate name or position title can inject markup/script into the public candidate page.
- **Affected user/workflow:** candidate opening an offer link; any operator previewing the public page.
- **Severity:** High.
- **Enterprise-readiness blocker:** Yes.
- **Smallest justified fix:** use an auto-escaping template or `html.escape` for every dynamic text/attribute, plus a restrictive CSP.
- **Consequence if unchanged:** script execution in the bearer-link page can alter the decision UI or exfiltrate the token.

### OH-06 — Legacy direct hire branches bypass the Offer-1 gate and atomic hire operation

- **Exact evidence:** `app.py:33259-33271` and `33615-33628` call `update_application_status(..., "hired")` and `transition_hire` directly; canonical authority is `action_registry.py:764-904` plus `hire_operations.py:306-352`.
- **Concrete risk/failure:** if a pending/direct legacy graph branch is reached, a candidate can be hired without an accepted offer and application stage can commit separately from employee setup.
- **Affected user/workflow:** legacy WhatsApp/pending-action paths, maintainers, any future config rollback from registry.
- **Severity:** High.
- **Enterprise-readiness blocker:** Yes until removed, delegated, or proven unreachable with a fail-closed guard.
- **Smallest justified fix:** replace both branch bodies with the canonical gated hire operation or explicitly reject them; add a source/runtime regression proving every `hired` mutation entrypoint reaches `enforce_hire_gate` and `execute_hire_operation`.
- **Consequence if unchanged:** Offer-1 is not the sole hiring authority and a config/path regression can recreate half-hires.

### OH-07 — Multiple accepted offers can exist for one application

- **Exact evidence:** open uniqueness covers only draft/pending/approved/sent (`offer_lifecycle.py:272-275`); `create_draft` rejects only `find_open_offer` (`offer_service.py:224-231`); accepted is terminal and does not change the application stage before hire.
- **Concrete risk/failure:** HR can create and accept another offer for the same still-shortlisted/interview application; hire gate selects the most recently responded accepted offer, leaving competing accepted legal terms.
- **Affected user/workflow:** accepted-offer amendment/replacement, hire confirmation, audit/legal review.
- **Severity:** High.
- **Enterprise-readiness blocker:** Yes for unambiguous accepted terms.
- **Smallest justified fix:** prohibit a new draft while an accepted offer exists unless an explicit, audited supersede/reopen operation invalidates the prior acceptance; enforce the invariant in the database.
- **Consequence if unchanged:** employee creation may be linked to one accepted version while another accepted agreement remains valid in the same authority.

### OH-08 — Offer versions/events are not immutable at the database boundary

- **Exact evidence:** no triggers in `ensure_offer_schema`; production table grants give `wathefni_app` `UPDATE`, `DELETE`, and `TRUNCATE` on versions/events; only primary/FK constraints exist.
- **Concrete risk/failure:** accidental SQL, maintenance code, or a compromised runtime can rewrite or delete the legal terms and lifecycle audit that the product presents as versioned evidence.
- **Affected user/workflow:** compliance, legal-term verification, incident reconstruction.
- **Severity:** Medium–High.
- **Enterprise-readiness blocker:** Yes if these rows are the legal/audit system of record; otherwise conditional on documented external immutability.
- **Smallest justified fix:** database append-only triggers or least-privilege grants for versions/events, with a controlled retention/deletion authority that preserves privacy obligations.
- **Consequence if unchanged:** the service is immutable by convention, not by authority.

### OH-09 — Generated Arabic offer documents are not faithful

- **Exact evidence:** bilingual wording exists at `offer_lifecycle.py:443-471`, but `_simple_pdf` replaces every non-ASCII character with `?` at `504-507`; production proof checked only PDF header and differing hash, not readable Arabic.
- **Concrete risk/failure:** an Arabic offer can store correct terms JSON but present an unreadable/generated legal document.
- **Affected user/workflow:** Arabic-speaking candidate, Arabic HR operator, bilingual legal review.
- **Severity:** High where generated Arabic PDF is used as the agreement; Medium when uploaded PDFs are mandatory.
- **Enterprise-readiness blocker:** Yes for the stated Arabic parity scope.
- **Smallest justified fix:** use a Unicode/Arabic-shaping PDF renderer and embedded font, or prohibit generated Arabic documents and require a validated upload until supported.
- **Consequence if unchanged:** the candidate-facing artifact can materially differ from the recorded Arabic terms.

### OH-10 — Main pre-hire audit view omits offer and override authorities

- **Exact evidence:** Offer events and overrides are stored in dedicated tables (`offer_lifecycle.py:313-428`); `/dashboard/prehire/audit` reads the action-results feed rather than unioning those authorities; candidate timeline has separate offer event mapping.
- **Concrete risk/failure:** an auditor using the main audit UI can miss approval, send, response, withdrawal, and hire-override evidence.
- **Affected user/workflow:** compliance reviewer, owner audit export, incident review.
- **Severity:** Medium.
- **Enterprise-readiness blocker:** Conditional; yes if the main audit view is claimed as complete.
- **Smallest justified fix:** include tenant-scoped offer events and override audits in the audit read model, or label and link the separate Offer audit as the authoritative record.
- **Consequence if unchanged:** compliance evidence is durable but operationally fragmented and easy to overlook.

### OH-11 — Hire-override explicit confirmation defaults on

- **Exact evidence:** `DashboardHireRequest.confirm: bool = True` at `app.py:36880-36883`; endpoint accepts that default at `52543-52571`.
- **Concrete risk/failure:** an API client can omit `confirm` while requesting override; grant and reason are still required, but explicit confirmation is not.
- **Affected user/workflow:** grant-only override API users.
- **Severity:** Medium.
- **Enterprise-readiness blocker:** No by itself.
- **Smallest justified fix:** default `confirm=False` and require literal `true` for override.
- **Consequence if unchanged:** exception-hire confirmation is weaker than the policy and audit text claim.

### OH-12 — Offer dashboard actions lack explicit consequence confirmation

- **Exact evidence:** `OfferPanel.tsx:178-227` calls approve/send/record/withdraw immediately; mobile requires `confirm` at `operator_mobile_data.py:2796-2800`; hire already has a confirmation flow.
- **Concrete risk/failure:** a misclick can approve, send compensation, record a legal response, or withdraw an offer.
- **Affected user/workflow:** dashboard HR operators.
- **Severity:** Medium.
- **Enterprise-readiness blocker:** No.
- **Smallest justified fix:** reuse the existing confirmation dialog with target, version, recipient, and consequence.
- **Consequence if unchanged:** avoidable irreversible state changes and candidate communication incidents.

### OH-13 — Mobile Offer-1 backend exists but the HR app does not present it

- **Exact evidence:** backend capability/action support at `operator_mobile.py:797-810` and `operator_mobile_data.py:1695-1758,2770-2853`; no Offer-1 client/action usage under `apps/wathefni-hr-mobile`; only generic offer timeline text and legacy aliases exist.
- **Concrete risk/failure:** backend advertises mobile offer capability while operators cannot see or execute it in the app; compensation can still be included in the candidate payload.
- **Affected user/workflow:** HR mobile users.
- **Severity:** Low–Medium.
- **Enterprise-readiness blocker:** No, provided mobile is documented as web-handoff for offers.
- **Smallest justified fix:** either wire only the already-approved V1 subset with the corrected read permission, or stop advertising/embedding it and provide a web handoff.
- **Consequence if unchanged:** dead capability and inconsistent cross-surface expectations.

### OH-14 — Offer statuses and delivery statuses lack database constraints

- **Exact evidence:** production constraints contain only PK/FK/unique constraints for Offer-1; `ensure_offer_schema` defines status as free text (`offer_lifecycle.py:233-387`).
- **Concrete risk/failure:** invalid status values can bypass the service matrix and break open-offer uniqueness, allowed actions, Reports, and expiry processing.
- **Affected user/workflow:** all offer lifecycle consumers and operations scripts.
- **Severity:** Medium.
- **Enterprise-readiness blocker:** No alone; part of authority hardening.
- **Smallest justified fix:** add validated `CHECK` constraints after a preflight scan, covering offer, delivery, token purpose, and actor types.
- **Consequence if unchanged:** direct SQL or future code can create states the authority cannot interpret.

### OH-15 — Prepared hire operations and override audits have incomplete outcome recovery

- **Exact evidence:** prepare occurs before offer gate (`app.py:52361-52383` vs `52553-52576`); reconcile is report-only (`hire_operations.py:355-387`); override audit commits before hire and has no completion outcome (`offer_service.py:1102-1242`).
- **Concrete risk/failure:** a rejected/stale hire can leave an open prepared operation or an override audit that appears to target hired even when execution never completes.
- **Affected user/workflow:** retry by another actor, support/reconciliation, compliance review.
- **Severity:** Medium.
- **Enterprise-readiness blocker:** No if canonical happy path remains healthy; must be qualified.
- **Smallest justified fix:** gate before or inside operation preparation, record operation/audit outcome, and add a bounded stale-operation reconciliation policy.
- **Consequence if unchanged:** manual intervention and ambiguous exception-hire evidence after failures.

## Evidence-backed recommendation

**Recommendation: do not freeze Offers/Hiring as production-green yet. Perform one contained Offers/Hiring remediation, then qualify locally and in isolated staging.**

The minimum justified remediation is:

1. add compensation/document read authorization and redacted DTOs;
2. implement canonical due-offer expiry and enforce expiry on preview;
3. introduce a durable, idempotent send/resend operation that claims database authority before provider delivery;
4. stop persisting raw response URLs;
5. escape the public candidate page;
6. eliminate/delegate the two legacy direct hire branches;
7. enforce one unambiguous accepted agreement per application;
8. make legal versions/events append-only and add status constraints;
9. make the Arabic document truthful or require upload for Arabic;
10. correct override confirmation default and add focused audit/recovery states.

Optional enhancements that should be deferred unless the owner requires them:

- Assistant offer drafting or mutation tools;
- mobile create/edit/send;
- general compensation planning, bands, benchmarking, equity, bonus modeling, or e-signature integrations;
- automated negotiation workflows;
- broad redesign of frozen Reports, Ranking, Assessments, Interviews, Jobs, or Candidates.

## Required schema and configuration changes

No schema or configuration was changed during this assessment.

### Smallest proposed schema delta

- offer read/compensation permission registered in backend permission authority;
- durable send/reissue operation or outbox table with:
  - company, offer, version, operation/idempotency key;
  - channel/recipient/document hash;
  - pending/sending/sent/failed/unknown state;
  - provider reference, attempt count, lease/retry fields;
- offer expiry index on `status='sent', expires_at`;
- unique/invariant mechanism preventing multiple active accepted agreements per application unless superseded;
- optional `superseded_by_offer_id` / supersede event if replacement-after-accept is approved;
- offer and delivery status `CHECK` constraints;
- append-only protection for offer versions/events;
- hire-override execution outcome and stale-operation timestamps if implemented in the same patch.

### Proposed configuration

- explicit offer public base URL, rather than relying on assessment/public fallback;
- worker/timer configuration for due-offer expiry and delivery outbox;
- explicit owner decision for `WATHEFNI_ONBOARDING_SEED` after onboarding qualification;
- no change to Ranking, Assessments, Interviews, Reports, Assistant, Jobs, or Candidates configuration.

## Local and staging qualification plan

### Local

1. Run existing:
   - `smoke-test-offer-lifecycle.py`;
   - `smoke-test-offer-hire-override.py`;
   - canonical lifecycle, pre-hire registry parity, Reports, Assistant, Candidates, Assessments, and Interviews frozen regressions.
2. Add focused offer tests for:
   - compensation redaction by role/scope;
   - document permission parity;
   - public preview expiry;
   - HTML escaping/XSS strings;
   - due expiry idempotency;
   - one expiry event and token revocation;
   - replacement offer after expiry;
   - concurrent send produces one provider operation;
   - provider success + process crash recovery;
   - provider failure + retry;
   - resend revokes old token and preserves terms version;
   - no raw token/URL at rest;
   - multiple accepted agreements rejected or explicitly superseded;
   - append-only version/event enforcement;
   - generated Arabic text is readable or generated path is rejected;
   - every hire entrypoint reaches the same gate and hire operation;
   - stale prepared hire operation and failed override outcome reconciliation.
3. Add dashboard tests for:
   - confirmation dialogs;
   - permission-redacted panel;
   - send/resend truth;
   - Arabic/RTL labels and accessible inputs.
4. Add mobile contract tests only for the approved V1 subset or web handoff.

### Isolated staging

Use synthetic applications, phone numbers, actors, and one isolated provider destination. Do not message a real candidate.

Prove:

1. draft create idempotency and concurrent open-offer uniqueness;
2. versioned edit and stale-version rejection;
3. separation of duties and role permissions;
4. compensation hidden from generic viewer and visible only to approved scope;
5. document authorization matches JSON authorization;
6. approve → send creates exactly one durable operation and one candidate message;
7. crash/failure between provider and DB recovers without duplicate or broken link;
8. resend creates one new token, revokes the old one, keeps the same offer/version, and records both attempts truthfully;
9. accept/decline one-time behavior;
10. withdrawal and expiry revoke tokens;
11. due offer becomes `expired`, disappears from open-offer lock, and stale URL no longer reveals compensation;
12. XSS fixture is displayed as text, not executed;
13. only one accepted agreement can govern hire;
14. hire before accept fails;
15. accepted offer → confirmation → hire creates one employee and one completed operation atomically;
16. concurrent duplicate hire creates one employee;
17. forced employee-side failure leaves application not hired and no employee;
18. override requires grant, explicit confirm, reason, human actor, durable audit, and recorded execution outcome;
19. no legacy route can bypass the offer gate;
20. onboarding behavior matches the selected feature configuration;
21. Arabic generated/uploaded document is human-readable and matches canonical terms;
22. Reports counts reflect sent/accepted/expired/hired truth without compensation;
23. Assistant cannot mutate offers or override hire;
24. mobile approved subset or explicit web handoff is truthful;
25. zero synthetic database, file, delivery, token, employee, onboarding, audit, Assistant, and provider residue.

Do not promote until every privacy, delivery, expiry, sole-hire-authority, atomicity, and cleanup gate passes.

## Owner UX checklist

### Dashboard offer flow

- [ ] Open an eligible shortlisted/interview candidate.
- [ ] Confirm salary/allowances/internal notes are absent for a viewer.
- [ ] Confirm an authorized offer operator sees the intended compensation.
- [ ] Create a draft with English and Arabic wording.
- [ ] Edit and verify a new visible version.
- [ ] Submit for approval.
- [ ] Confirm the creator cannot self-approve under default policy.
- [ ] Approve as a separate authorized user.
- [ ] Verify send confirmation names candidate, version, recipient, and consequence.
- [ ] Send once and verify truthful pending/sent/failed state.
- [ ] Verify refresh does not lose recovery controls.
- [ ] Resend and verify the old link is revoked.
- [ ] Accept and decline on separate synthetic offers.
- [ ] Verify a second response is rejected.
- [ ] Withdraw and verify the public link is unavailable.
- [ ] Let an offer expire and verify status becomes `Expired`.
- [ ] Verify the expired URL reveals no candidate compensation.
- [ ] Create a replacement after expiry.
- [ ] Verify a second accepted agreement cannot silently coexist.
- [ ] Download each version only with the compensation-read scope.

### Hiring

- [ ] Attempt hire before acceptance and verify fail-closed.
- [ ] Accept, confirm hire, and verify exactly one employee.
- [ ] Verify candidate stage, employee link, compliance seed, and operation complete together.
- [ ] Retry the same confirmation and verify idempotent result.
- [ ] Attempt concurrent hire and verify no duplicate employee.
- [ ] Force a transactional failure and verify no half-hire.
- [ ] If override is enabled, verify grant-only visibility, explicit confirmation, mandatory reason, and complete audit/outcome.
- [ ] Verify every dashboard, mobile, and Assistant hire path enforces the same gate.

### Arabic, mobile, audit, and Reports

- [ ] Read the generated/uploaded Arabic document; no `?` replacement or broken shaping.
- [ ] Verify Arabic/RTL dashboard/public layout and accessible labels.
- [ ] Verify mobile shows only the approved V1 subset or an explicit web handoff.
- [ ] Verify offer lifecycle and override evidence appears in or is linked from the main audit surface.
- [ ] Verify Reports counts sent, accepted, expired, and hired correctly and never exposes compensation.

## Explicit out-of-scope items

- Any implementation or deployment during this assessment.
- Production mutation, synthetic production fixtures, candidate communication, or provider sends.
- Reopening frozen Jobs, Candidates, Ranking, Reports, Assistant, Assessments, or Interviews behavior.
- Adding interview, assessment, or ranking prerequisites to offers or hiring.
- Letting interview scores, assessment scores, or Ranking output approve an offer or confirm hire.
- Assistant offer approval/send/withdraw/accept/decline/override tools.
- Compensation benchmarking, salary bands, equity, bonus, tax, payroll, or benefits administration beyond recorded offer terms.
- Third-party e-signature, identity verification, or negotiation portals.
- Mobile create/edit/send unless separately approved.
- General onboarding redesign; only the hire handoff contract and current seed configuration are assessed.
- Offers/Hiring production promotion or freeze.
- Starting another module.

## Final assessment state

**Offers/Hiring is assessed but not production-green/frozen for the requested enterprise scope.**

The current production state is clean and the canonical hire transaction is strong. The blockers are contained and evidence-backed: compensation authorization, due-offer expiry, delivery/resend recovery, public-page safety, sole hiring authority, accepted-agreement uniqueness, and Arabic legal-document fidelity.

No code, schema, configuration, staging, production, frozen authority, or provider state was changed. Stop here pending owner direction.
