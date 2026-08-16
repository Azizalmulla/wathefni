# Super Admin Tenant Control — Wave 3 Configuration, Integrations & Readiness

**Date:** 2026-07-27  
**Scope:** Tenant configuration, integration control plane, automated readiness, async epoch coverage  
**Environment:** Production (`WATHEFNI` only)  
**Evidence run:** `20260727T110053Z` (`/tmp/wave3-tenant-control-20260727T110053Z/evidence.json`)  
**Deploy backup:** `/opt/wathefni/var/wave3-backups/20260727T105947Z`

## Verdict

**GO for Wave 4.**

Wave 3 delivered versioned schema-validated tenant configuration, an honest
integration control plane (supported vs unsupported), automated readiness that
refuses “selected ⇒ ready”, Super Admin setup APIs compatible with the existing
Setup Console, WATHEFNI reconstruction proof (completeness 1.0), and line-level
activation-epoch stamping/gating across the production async paths listed below.

External tenants were not enabled. Normal HR UI was not redesigned. Global
canonical authority remains **hard-off**. WATHEFNI live behavior was preserved
aside from additive control-plane records and shadow/canary-gated worker checks.

---

## Non-negotiables preserved

| Constraint | Result |
|---|---|
| No external tenants | Met — `companies` count = **1** (`WATHEFNI`) |
| No normal HR UI redesign | Met — APIs under Super Admin setup only |
| Global canonical authority | Hard-off (`global_authoritative=false`) |
| Wave 1 authoritative | Off |
| Orphan settings | **12** unchanged |
| Verified-binding ENFORCE | WATHEFNI-only posture retained |
| Unified inbound CV | Not altered by this wave |
| Health | **200** before and after deploy/restart |
| Canary authority after proofs | Cleared (`enabled=0`) |

---

## 1. Configuration schemas

**Code:** `tenant_control_config.py`  
**Tables:** `tc_config_schemas`, `tc_config_documents`  
**Schema version:** `tenant-control-schema-v3` / `tenant-config-schemas-v1`

### Domains

| Domain | Purpose |
|---|---|
| `company_profile` | Display name, country, timezone, currency, languages, branding |
| `org_structure` | Legal entities, branches, departments, teams, cost centers |
| `module_policies` | Per-module live/policy knobs |
| `notification_policies` | Preset, channels, quiet hours |
| `retention_policies` | CV retention, deletion, export, legal hold |
| `quotas` | Operational limits |
| `custom_fields` | Candidate/employee fields + required fields |
| `document_requirements` | Required documents catalog |
| `workflows` | Approval chains |
| `prehire` | Full pre-hiring tenant setup (see §2) |
| `posthire` | Post-hire module foundations (see §3) |

### Lifecycle supported

`draft` → `validated` → `in_review` / `approved` → `published`  
Also: `scheduled`, `rolled_back`, `superseded`, `rejected`

| Capability | Implementation |
|---|---|
| Draft | `create_draft` + idempotency key |
| Validation | Schema required-keys/types + secret-key scan |
| Review/publish | `publish_document` with version bump |
| Effective date | `effective_from` |
| Rollback | `rollback_domain` republishes target version snapshot |
| Before/after diff | `before_json` / `after_json` / `diff_json` |
| Migration impact | `migration_impact` JSON on publish |
| Ownership / approvals | `owned_by`, `approved_by` |
| Audit / outbox | Fail-closed via lifecycle audit helper |

**Secrets rule:** Forbidden secret key names in config JSON are rejected at
validate time. Secrets belong only in `tc_secret_refs` (locator + fingerprint).

---

## 2. Pre-hiring configuration

Domain `prehire` requires:

- Candidates area (single HR product; `split_products` rejected)
- Jobs / application forms
- Lifecycle stages / transitions
- Notes (categories, mentions, attachments, visibility)
- Duplicate person / application policy
- General CV / no-job intake policy
- Held vs admitted behavior
- CV retention / versioning
- Ranking defaults + evidence policy
- Screening templates
- Assessments
- Scheduled interviews + video interviews
- Communication policy
- Shortlist / reject / offer / hire approvals
- Candidate custom fields
- Backend capabilities object with **HR-visible CK/Talent Pool forbidden**

WATHEFNI seeded posture keeps Candidate Knowledge and Talent Pool as
**backend-only** under one Candidates area.

---

## 3. Post-hire configuration foundations

Domain `posthire` configures tenant-level choices for existing modules without
redesigning their UIs:

`onboarding`, `compliance`, `attendance`, `shifts`, `leave`, `payroll`,
`analytics`, `employee_app` (platform flag honest / currently off).

---

## 4. Supported versus unsupported provider matrix

**Code:** `tenant_control_integrations.py`

| Provider key | Channel | Tier | Selectable | WATHEFNI seed state |
|---|---|---|---|---|
| `octopus_whatsapp` | whatsapp_business | platform_global | yes | live |
| `postmark_inbound` | inbound_email | supported | yes | live |
| `postmark_outbound` | outbound_email | supported | yes | live |
| `gmail_gog` | gmail_mailbox | partial | yes | setup_required |
| `google_calendar` | calendar_meet | partial | yes | setup_required |
| `microsoft_365` | outlook | **unsupported** | **no** | not_selected |
| `microsoft_teams` | teams | **unsupported** | **no** | not_selected |
| `imap` | imap_mailbox | **unsupported** | **no** | not_selected |
| `sms` | sms | **future** | **no** | not_selected |
| `push` | push_notifications | partial | yes | setup_required |
| `mistral_ocr` | ocr_ai | platform_global | yes | live |
| `candidate_indexing` | candidate_knowledge_index | supported | yes | live |

### Integration lifecycle states

`not_selected` → `selected` → `setup_required` → `connected` → `verified` →
`testing` → `live` → (`degraded` | `disconnected` | `blocked` | `uninstalling`)

### Honest ownership rules

- Unsupported/future providers cannot be selected or marked ready.
- Manually entered `provider_account_ref` alone cannot reach `verified` / `live`.
- Secret refs store **locator + fingerprint only** — never secret material.
- Integration tests always report `account_ref_verified_ownership=false`.

### Modeled for supported/partial/platform_global

Tenant ownership, provider account ref, secret ref, scopes, connect/verify,
test send/receive, webhook test, health, reconnect, secret rotation fields,
revocation/uninstall states, kill switch, degrade → block side effects → restore.

---

## 5. Readiness catalog

**Code:** `tenant_control_readiness.py`  
**Tables:** `tc_readiness_catalog`, `tc_readiness_results`

Checks include (where applicable):

| check_key | Severity |
|---|---|
| `contract_entitlement` | blocker |
| `published_configuration` | blocker |
| `dependency_graph` | blocker |
| `roles_permissions` | warning |
| `schema_ready` | blocker |
| `activation_epoch_ready` | blocker |
| `queue_gate_ready` | blocker |
| `worker_coverage` | warning |
| `integration_supported` | blocker/warn |
| `provider_credentials` | blocker/warn |
| `interviews_compatibility` | blocker |
| `verified_binding_posture` | warning |
| `employee_app_flag` | info |
| `unsupported_provider_not_ready` | blocker |
| `monitoring_backup` | warning |

Each result records: `pass|fail|warning|blocked`, evidence, timestamp, expiry,
owner, remediation, retest action.

**Selected ≠ Ready:** canary forced a missing published domain → `ready=false`;
after remediation/retest against published `prehire` → pass.

---

## 6. Exact worker coverage

| Path | Epoch stamp | Claim/side-effect gate |
|---|---|---|
| `durable_email_ingress.enqueue_job` | yes | n/a (stamp on create) |
| `durable_email_ingress.claim_next_job` | yes | yes |
| `inbound_cv_adapters.adapt_manual_import` | yes | yes |
| `inbound_cv_adapters.adapt_whatsapp_unsolicited` | yes | yes |
| `candidate_knowledge_index_worker` | yes | yes |
| `process_pending_video_interview_transcripts` | yes | yes |
| `assessment_ai_service.process_queued_run` | yes | yes |
| `outbound_delivery.run_delivery_sweep` | yes | yes |
| `outbound_delivery.deliver_to_employee` | (metadata) | yes + integration kill switch |
| `run_mailbox_sync` | yes | yes |
| `run_onboarding_reminder_scan` | yes | yes |
| `run_compliance_scan` | yes | yes |
| `run_shift_reminder_scan` | yes | yes |
| `run_leave_accrual_sweep` | yes | yes |
| `candidate_identity.export_person_package` | yes | yes |
| `candidate_identity.enqueue_document_privacy_job` | yes | stamp on enqueue |
| `offer_lifecycle` | n/a | API-driven; no dedicated expire worker found |

Stale-epoch proof (canary E): analytics pause/resume advanced epoch `5 → 7`;
stale work denied authoritatively (`activation_epoch_mismatch`); fresh epoch
allowed.

### Delivery-sweep classification

| Fact | Value |
|---|---|
| Incorrect Wave 2 name | `wathefni-delivery-sweep-worker.service` **does not exist** |
| Real unit | `wathefni-delivery-sweep.service` + `.timer` |
| Timer | **active / enabled** |
| Service | **fails every run** |
| Root cause | Missing `WATHEFNI_APPLICATION_ENVIRONMENT` in unit env → `application_environment_missing_or_invalid` |
| Classification | **Required, misconfigured** |
| Wave 3 action | **Not silently enabled or fixed** |
| Outbound path still gated | `deliver_to_employee` + sweep code path when process starts successfully |

---

## 7. Setup and integration APIs

Registered under `/dashboard/superadmin/setup/` (existing Super Admin auth):

| Method | Path |
|---|---|
| GET | `/providers` |
| GET | `/companies/{code}/config/{domain}` |
| POST | `/companies/{code}/config/drafts` |
| POST | `/companies/{code}/config/drafts/{id}/validate` |
| POST | `/companies/{code}/config/publish` |
| POST | `/companies/{code}/config/rollback` |
| GET/POST | `/companies/{code}/integrations` |
| POST | `/companies/{code}/integrations/test` |
| POST | `/companies/{code}/integrations/{provider}/pause` |
| POST | `/companies/{code}/integrations/{provider}/reconnect` |
| GET/POST | `/companies/{code}/readiness` (+ `/run`) |
| GET | `/companies/{code}/reconstruction` |

Existing Setup Console remains compatible. No redesigned wizard in this wave.

Production route registration confirmed: **23** related hits including all Wave 3
Super Admin endpoints above.

---

## 8. WATHEFNI reconstruction proof

Using only control-plane records/APIs (`build_reconstruction`):

| Area | Represented |
|---|---|
| Modules / capabilities | yes (`tc_tenant_module_instances` + grants) |
| Interviews compatibility | yes (`cap.interviews_compatibility`) |
| Roles | yes (seeded role count) |
| Unified inbound CV posture | via published `prehire` + technical flags |
| Verified-binding enforcement | flags in reconstruction snapshot |
| Channels / integrations | 12 provider rows with honest tiers |
| Workers | delivery-sweep classification included |
| Policies | 11 published config domains |
| Technical flags / allowlists | captured from env |
| Integration limitations | unsupported remain `not_selected` / unselectable |

**Result after seed:** `ok=true`, `gaps=[]`, `completeness_score=1.0`  
Live behavior was not cut over to these configs as runtime authority.

---

## 9. Bounded canary results

Evidence: `/tmp/wave3-tenant-control-20260727T110053Z/evidence.json`  
Local copy: `ops/evidence/wave3-tenant-control/evidence.json`

| Canary | Result |
|---|---|
| A — draft → validate → publish → rollback | **PASS** (v1→v2 canary→rollback v3 restores `Wathefni`) |
| B — supported integration test (`postmark_inbound` health) | **PASS** |
| C — unsupported provider unavailable (`microsoft_365` select) | **PASS** (`provider_not_selectable`) |
| D — readiness fail missing prerequisite + retest | **PASS** (forced fail then retest pass) |
| E — stale-epoch real worker path denied | **PASS** (`activation_epoch_mismatch`, authoritative) |
| F — integration degraded → blocked side effect → restore | **PASS** |
| G — no false denial on existing WATHEFNI modules | **PASS** (12 modules) |
| Health 200 / workers healthy (orchestrator) | **PASS** |
| Overall script | **`ok: true`, `failures: []`** |

---

## 10. Safety

| Proof | Result |
|---|---|
| Mandatory audit on config publish | yes (`config_published` + diff) |
| No secrets in recent audit JSON | yes (`secret_leaks_in_recent_audit=[]`) |
| Tenant-scoped integration ownership | yes (`company_code` + `tenant_id`) |
| No cross-tenant access surface added | yes (company-scoped APIs; single company) |
| Rollback | config rollback canary + kill-switch restore |
| Kill switches | plane/decision/epoch env switches retained |
| No external tenant | companies=1 |
| Global canonical authority hard-off | proven |

---

## 11. Remaining manual / platform-operations dependencies

| Item | Notes |
|---|---|
| `wathefni-delivery-sweep.service` env fix | Platform ops must add `WATHEFNI_APPLICATION_ENVIRONMENT=production` (and related binding vars) deliberately — not auto-fixed here |
| Partial providers | Gmail live import still blocked pending durable scan/identity authority; Calendar/Meet not full self-serve; Push depends on employee app flag |
| Assessment AI worker | Still refuses production by design |
| Config runtime authority | Published configs are control-plane truth for reconstruction/readiness; runtime still largely legacy settings/modules |
| Setup Console wizard redesign | Deferred to later wave |
| External tenant onboarding | Explicitly out of scope until later wave |

---

## 12. Rollback proof

| Path | How |
|---|---|
| Code rollback | Restore `/opt/wathefni/var/wave3-backups/20260727T105947Z/pre/*` and restart orchestrator |
| Config rollback | `POST .../config/rollback` (proven canary A) |
| Integration kill / restore | pause → kill_switch blocks outbound; reconnect clears |
| Decision bypass | `WATHEFNI_TENANT_CONTROL_DECISION=off` → Wave 2/legacy shadow/bypass |
| Plane off | `WATHEFNI_TENANT_CONTROL_PLANE=off` |
| Global authority | Remains forced false even if env requests it |

---

## 13. Code artifacts

| Path | Role |
|---|---|
| `tenant_control_wave3_schema.py` | v3 additive schema |
| `tenant_control_config.py` | Versioned config framework + WATHEFNI defaults |
| `tenant_control_integrations.py` | Provider matrix + lifecycle + secret refs |
| `tenant_control_readiness.py` | Catalog + evaluation |
| `tenant_control_wave3_routes.py` | Super Admin APIs + reconstruction |
| `tenant_control_queue_gate.py` | Epoch stamp / load / gate_or_skip |
| `ops/wave3-tenant-control-configuration-integrations-readiness.py` | Production canaries |

Worker/intake patches: `app.py`, `durable_email_ingress.py`,
`inbound_cv_adapters.py`, `outbound_delivery.py`,
`candidate_knowledge_index_worker.py`, `assessment_ai_service.py`,
`candidate_identity.py`.

---

## 14. Final GO/NO-GO for Wave 4

**GO for Wave 4.**

Wave 3 closes the configuration/integration/readiness control-plane gap and the
Wave 2 async wiring gap for the listed production paths, without enabling
external tenants, without pretending unsupported providers are ready, and
without switching global canonical authority on.

Recommended Wave 4 focus (out of scope here): onboarding wizard UX, runtime
cutover from legacy settings to published config authority, deliberate
delivery-sweep unit env repair, and any remaining partial-provider completion
gates — only after explicit acceptance.
