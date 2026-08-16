# Wave D Phase 6 — Inbound intake production qualification & GA readiness

**Stamp:** `20260801T160950Z`  
**Mode:** Production qualification only — **no code deploy**, **no external-tenant enablement**, **no post-hiring**.  
**Host:** `root@76.13.63.68`  
**Dashboard:** `https://api.wathefni.ai/dashboard/`  

Local evidence: `ops/evidence/waveD-phase6-inbound-ga-qualification-20260801T160950Z/`  
Remote evidence: `/opt/wathefni/production-evidence/waveD-phase6-ga/20260801T160950Z/`

---

## Final GA recommendation: **limited canary**

| Decision | Result |
|---|---|
| **Overall Wave D inbound GA** | **limited canary** |
| WATHEFNI forwarding product (core) | **GO** for continued WATHEFNI-only canary |
| External-tenant enablement | **NO-GO** |
| Premium Gmail/M365 connector GA | **NO-GO** (remain dark; sync off) |
| Post-hiring | **not started** |

External tenants were **not** enabled in this phase (`WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI`).

---

## Capability PASS/FAIL

| Capability | Result | Notes |
|---|---|---|
| Forwarding intake create/list/disable | **PASS** | General alias `needs_role` |
| General + job-specific aliases | **PASS** | Job alias `role_bound` → `OCCTST_044035` |
| Held Intake review + assign/admit | **PASS** | Single admit → `ready_for_review` |
| Held Intake bulk admit | **PASS** | Bulk assign `promoted=1` |
| Quotas + soft warn | **PASS** | Soft warn + `waiting_quota` never reject |
| Burst overrides | **PASS** | Raises caps; TTL expiry |
| Kill switch | **PASS** | `waiting_budget` / `tenant_kill_switch` |
| ClamAV/OCR outage + replay | **PASS** | dead_letter → `pending` |
| Retention | **PASS** | Dry-run OK; `WATHEFNI_INTAKE_RETENTION_EXECUTE=off` |
| Gmail connector (scopes + durable + idempotent) | **PASS** | `gmail.readonly`; `live_durable`; duplicate=1 |
| Microsoft 365 connector (scopes + dedicated app) | **PASS** | `Mail.Read`/`User.Read`/`offline_access`; mailbox app unset by design |
| Pause / reconnect / revoke / disconnect | **PASS** | pause skip; revoke → `needs_reconnect`; disconnect gone |
| Duplicate / idempotent | **PASS** | Forwarding + Gmail sync |
| Tenant isolation | **PASS** | ACMECORP fail-closed |
| Environment isolation | **PASS** | Postmark staging header `401`; prod pin `200` |
| Concurrency | **PASS** | 4 parallel durable receives |
| EN/AR + RTL UI markers | **PASS** | Live Settings/Candidates/connector strings |
| Ops monitoring / support levers | **PASS** | Worker + ops-monitor timers; usage API; kill switch |
| Onboarding / setup clarity | **PASS** | Forwarding default + connector optional steps EN/AR |
| Privacy / retention readiness | **PASS** | Execute off; Fernet secrets; quarantine active |
| Commercial packaging | **PASS** | Forwarding default; connectors premium/dark |
| Durable→Held synthetic materialization | **FAIL** (medium) | See blockers |

Matrix score: **41 PASS / 1 FAIL** (`verify/prod-d6-ga-matrix.json`).  
The single FAIL is an explicit assessment finding, not a regression of Held admit UX.

---

## Full evidence matrix (case IDs)

Source: `verify/prod-d6-ga-matrix.json`

| Case | Result |
|---|---|
| `health_200` | PASS |
| `commercial_packaging_forwarding_vs_premium` | PASS |
| `external_tenants_remain_disabled` | PASS |
| `forwarding_general_alias` | PASS |
| `job_specific_alias` | PASS |
| `forwarding_list_includes_created` | PASS |
| `forwarding_ingress_durable` | PASS |
| `duplicate_idempotent_forwarding` | PASS |
| `concurrency_burst_durable` | PASS |
| `quota_soft_warning` | PASS |
| `quota_over_limit_waiting_quota` | PASS |
| `burst_override_raises_caps` | PASS |
| `burst_override_expires` | PASS |
| `kill_switch_waiting_budget` | PASS |
| `held_intake_review_visible` | PASS |
| `held_intake_assign_admit` | PASS |
| `held_intake_bulk_admit` | PASS |
| `clamav_ocr_outage_replay` | PASS |
| `retention_dry_run_execute_off` | PASS |
| `gmail_readonly_scope` | PASS |
| `m365_mail_read_scopes` | PASS |
| `m365_dedicated_app_separate` | PASS |
| `mailbox_sync_disabled_by_default` | PASS |
| `gmail_connector_durable_path` | PASS |
| `configured_folder_only` | PASS |
| `gmail_connector_idempotent` | PASS |
| `incremental_cursor_persisted` | PASS |
| `connector_pause` | PASS |
| `connector_revoke_needs_reconnect` | PASS |
| `connector_disconnect` | PASS |
| `connector_off_fail_closed` | PASS |
| `tenant_scoped_encrypted_secrets` | PASS |
| `tenant_isolation_fail_closed` | PASS |
| `environment_isolation_postmark` | PASS |
| `environment_binding_production` | PASS |
| `ops_monitoring_support_ready` | PASS |
| `ui_en_ar_rtl_markers` | PASS |
| `onboarding_setup_clarity` | PASS |
| `privacy_retention_readiness` | PASS |
| `operational_rollback_levers` | PASS |
| `prior_wave_rollback_scripts_present` | PASS |
| `durable_to_held_materialization_synthetic` | **FAIL** |

Screenshots (EN/AR desktop/mobile from live D4/D5 bundles): `screenshots/`

---

## Blockers ranked by severity

1. **MEDIUM — durable → Held application materialization (synthetic)**  
   Synthetic durable Postmark receives completed worker jobs without creating Held Intake applications in the D6 wait window. Held review/admit/bulk were re-proved via `register_imported_cv` (`email_inbound`) into the same Held queue (and prior D4 prod admit PASS remains supporting).  
   → Blocks **external-tenant GA** and “full unattended durable→held” claims.  
   → Does **not** block WATHEFNI forwarding limited canary.

2. **LOW — M365 mailbox OAuth app unset**  
   Dedicated `WATHEFNI_M365_MAILBOX_*` not configured; Mail.Send app remains separate. Expected for dark premium posture.

3. **LOW — inbound metrics depth**  
   Ops monitor timer + usage API exist; no dedicated alert pack for `dead_letter` / `waiting_budget` called out for multi-tenant support.

No **critical** production blocker found for continuing WATHEFNI-only forwarding.

---

## Assessment notes

### Operational monitoring & support
- `wathefni-inbound-intake-worker.timer` and `wathefni-inbound-ops-monitor.timer` active  
- Usage / never-reject visibility via inbound usage API  
- Kill switch, pause, disable address, disconnect connector available as brakes  
- Prior D3/D4/D5 `ROLLBACK.sh` scripts present on disk

### Onboarding / setup clarity
- Forwarding is default product copy and feature payload  
- Connector UI marked optional/premium with EN/AR setup steps  
- Sync remains off

### Privacy / retention
- Retention execute **off**  
- Dry-run cleanup works after policy activate  
- Mailbox secrets Fernet-encrypted, tenant-scoped

### Commercial packaging
- **Core:** company email → Wathefni intake alias (general / job-specific)  
- **Premium (dark):** Gmail/M365 read-only connectors into the same durable pipeline  
- Do not sell or enable external connectors until blocker #1 is closed and a mailbox app is registered

---

## Cleanup proof

`cleanup/cleanup-final.json`

- All `wave_d6_ga_proof*` intake addresses **disabled**
- Active continuous WATHEFNI intakes: **1** (pre-existing Postmark default)
- D6 mailbox connections: **0**
- Kill switch **off**; mailbox sync **off**; enterprise plan restored to **internal**
- External tenants still disabled
- Health final: **orch=200**, **dash=200**

---

## Enablement posture (unchanged)

```
WATHEFNI_INBOUND_EMAIL=on
WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI
WATHEFNI_MAILBOX_SYNC=off
WATHEFNI_INTAKE_RETENTION_EXECUTE=off
WATHEFNI_POSTMARK_INBOUND_ENV=production
WATHEFNI_POSTMARK_INBOUND_ENV_PIN=production
```

---

## What this phase did / did not do

| Done | Not done |
|---|---|
| Full synthetic-tenant E2E matrix on production (WATHEFNI) | External tenant enablement |
| GA readiness decision + blockers | Premium connector GA |
| Cleanup + operational rollback lever proof | New production code deploy |
| | Post-hiring |

**Post-hiring was not started.**
