# Super Admin Tenant Control — Wave 2 Universal Enforcement

**Date:** 2026-07-27  
**Scope:** Universal enforcement and lifecycle safety only  
**Environment:** Production (`WATHEFNI` only)  
**Evidence run:** `20260727T102939Z` (`/tmp/wave2-tenant-control-20260727T102939Z/evidence.json`)

## Verdict

**GO for Wave 3.**

Wave 2 delivered a shared canonical decision boundary, activation epochs, safe
company/module lifecycle controls, additive roles foundation, orphan-write
prevention, and bounded WATHEFNI canaries — all without enabling external
tenants, without redesigning the normal HR UI, and without globally replacing
legacy entitlement authority.

Canonical authority remains **shadow-first**. Authoritative deny is enabled only
for explicitly allowlisted canary capabilities/surfaces, then cleared.

---

## Non-negotiables preserved

| Constraint | Result |
|---|---|
| No external tenants | Met — `companies` still exactly `WATHEFNI` |
| No normal HR UI redesign | Met — nav reacts via `enabled_modules` filtering only |
| Legacy entitlement reads retained | Met — `company_modules` / `require_entitlement` remain default authority |
| Global authoritative replacement | Hard-off |
| WATHEFNI accidental suspension | Blocked without explicit canary token |
| Unified inbound CV + verified-binding ENFORCE | Healthy; ENFORCE still WATHEFNI-only |
| Health | `200` before and after restart |
| 12 orphan settings | Retained unchanged |

---

## 1. Decision contract

**Code:** `wathefni-orchestrator/tenant_control_decision.py`

### Inputs evaluated

- tenant lifecycle
- contract entitlement / capability grant
- published module dimensions (`purchased` … `blocked`)
- dependency readiness (catalog-backed)
- integration readiness (optional input)
- actor permission ok (optional input)
- activation epoch (queued vs live)
- kill switches
- runtime health

### Structured result

```text
allow / deny
reason_code
tenant
module
capability
configuration_version
activation_epoch
remediation
audit_correlation_id
mode = shadow | authoritative | bypass | legacy
legacy_allow
parity
detail
```

### Authority posture

| Mode | Behavior |
|---|---|
| `shadow` (default) | Canonical decision computed and audited; effective allow follows legacy |
| `authoritative` | Only when `tc_canary_authority` matches tenant/module/capability/surface |
| `bypass` | Decision kill switch off → Wave 1 / legacy behavior |
| Global authoritative | Forced `False` even if env asks for it |

### Kill switches

| Flag | Role |
|---|---|
| `WATHEFNI_TENANT_CONTROL_PLANE` | Master |
| `WATHEFNI_TENANT_CONTROL_DECISION` | Decision service |
| `WATHEFNI_TENANT_CONTROL_LIFECYCLE_ENFORCE` | Lifecycle denials |
| `WATHEFNI_TENANT_CONTROL_EPOCH_ENFORCE` | Epoch mismatch denials |
| `WATHEFNI_TENANT_CONTROL_CANARY_AUTHORITY` | Allow canary-only authority |
| `WATHEFNI_TENANT_CONTROL_AUTHORITATIVE` | Ignored / hard-false globally |
| `WATHEFNI_TENANT_CONTROL_ALLOW_WATHEFNI_SUSPEND` | Explicit token required to suspend WATHEFNI |

---

## 2. Exact surface coverage

| Surface | Hook | Wave 2 behavior |
|---|---|---|
| HR navigation | `effective_company_modules` | Filters authoritatively denied modules from bootstrap `enabled_modules` |
| Module checks | `company_has_module` | Shadow observe; canary authoritative deny |
| Direct routes / APIs | `require_entitlement` | Shadow observe; canary authoritative deny |
| Company session gate | `require_active_company` | Observes control-plane lifecycle |
| AI tool execution | `tool_call_orchestrator._require_tool_entitlements` | Observe/enforce `ai_tools` |
| AI tool advertisement | inherits `company_has_module` for gated modules | Hidden when canary-denied |
| HR / employee mobile | via `company_has_module` / lifecycle context | Shadow + canary path |
| Outbound notifications | `outbound_delivery.deliver_to_employee` | Observe/enforce `outbound_notifications` |
| Queue claims / workers | `tenant_control_queue_gate` | Epoch + lifecycle + module pause |
| Intake | `allow_intake` | Tenant lifecycle gate |
| Webhooks | `allow_webhook` | Tenant lifecycle gate |
| Timers / reminders | via module automation + decision helpers | Ready for per-row gate (see gaps) |
| Exports | via API entitlement path | Covered when module-gated |
| Candidate indexing / video transcription / delivery sweep | queue gate helpers available; CK + video workers active | Delivery-sweep unit inactive (pre-existing) |

No background path should rely only on entitlement at enqueue time: queued work
must carry/compare `activation_epoch` through `tenant_control_queue_gate`.

---

## 3. Lifecycle state model

### Company lifecycle

`draft → setup/provisioning → testing → ready → active → paused/suspended → offboarding → archived`

Suspending a tenant (control-plane) atomically records:

- epoch bump
- mandatory audit + outbox (fail closed)
- effects flags: reject intake/webhooks, block queue claims, suppress outbound,
  stop timers/workers for that tenant, preserve data
- optional session revoke callback hook

**WATHEFNI protection:** suspension/offboarding/archive raises
`wathefni_suspension_blocked_without_explicit_canary_token` unless the env token
matches.

**Synthetic canary tenant:** `__TC_WAVE2_CANARY__` exists only in `tc_tenants`
(`synthetic=true`, `externally_usable=false`). No `companies` row. Not externally
usable.

### Module dimensions (not one boolean)

`purchased`, `desired`, `configured`, `tested`, `ready`, `live`, `paused`,
`degraded`, `blocked` + `instance_state` + `activation_epoch`

Pause preview covers UI, APIs, mobile, workers, timers, queues, webhooks,
integrations, notifications, and dependent capabilities.

---

## 4. Activation epoch design

| Scope | Storage |
|---|---|
| Tenant epoch | `tc_tenants.activation_epoch` + `tc_activation_epochs` |
| Module epoch | `tc_tenant_module_instances.activation_epoch` + `tc_activation_epochs` |

Rules:

1. Pause / resume / lifecycle transitions bump epoch.
2. Queued work should store the epoch at creation (`stamp_activation_epoch`).
3. Before side effects, workers call `allow_queue_claim` / `allow_worker_side_effect`.
4. Mismatch → deny + `tc_blocked_work` (`disposition=hold|reject`).

Canary C proof:

| Field | Value |
|---|---|
| Enqueued epoch | 3 |
| Live epoch after pause/resume | 5 |
| Stale allow | `false` (`activation_epoch_mismatch`) |
| Fresh allow | `true` |

---

## 5. Roles / permission parity

**Code:** `tenant_control_roles.py`  
**Tables:** `tc_role_templates`, `tc_tenant_roles`, `tc_role_grants`,
`tc_permission_parity_runs`

Additive only — fixed HR roles remain authoritative for live auth.

| Result | Value |
|---|---|
| Templates seeded | owner, hr_admin, recruiter, hiring_manager, viewer |
| Custom roles | supported (module/capability/org scopes, deny rules, expiry, SoD warnings) |
| WATHEFNI parity | **PASS** (`checked=3`, `mismatches=[]`) |

---

## 6. Mandatory audit / outbox

Control-plane lifecycle and module pause/resume mutations call
`_audit_fail_closed`:

- require both `tc_audit_events` and `tc_outbox_events` rows
- raise `control_plane_audit_outbox_persistence_failed` otherwise

Recorded fields include actor, tenant, before/after, reason, impact, affected
capabilities, configuration/activation epoch, rollback target, correlation ID.

Decision observations persist to `tc_decision_audit` when shadow audit is on.

---

## 7. Integrity work

| Item | Result |
|---|---|
| Prevent new orphan `company_settings` | `set_company_setting` now requires a `companies` row |
| Existing 12 orphans | Retained; re-classified; monitoring row written |
| Other orphan probes | modules/users/positions/applications/employees = 0 |
| Deletes | None |

Orphan codes (unchanged): ASST*, RANK*, OFFER1XO, TENANTREADTESTA/B, ZZSEED*.

---

## 8. Canary results

### A — Pause non-critical capability (`analytics`)

| Check | Result |
|---|---|
| Impact preview | UI/APIs/mobile/workers/notifications identified |
| Navigation allow | deny |
| API allow | deny |
| AI tool allow | deny |
| Queue claim allow | deny |
| Notification allow | deny |
| Restore | allow restored; analytics `live=true`, `paused=false` |
| Legacy `company_modules` | unchanged (still 12 enabled) |

### B — Synthetic tenant suspend (`__TC_WAVE2_CANARY__`)

| Check | Result |
|---|---|
| `companies` row | absent |
| `externally_usable` | false |
| Sessions / navigation | deny (`tenant_lifecycle_suspended`) |
| Intake | deny |
| Queue claims | deny |
| Delivery | deny |
| WATHEFNI suspend without token | blocked |
| Restore | allow |

### C — Activation epoch

Stale epoch N work denied after pause/resume advanced live epoch; fresh epoch
allowed.

### D — Existing WATHEFNI modules

| Check | Result |
|---|---|
| False denials | none |
| `interviews` enabled | true |
| Interview rows | present (scheduled/completed posture unchanged by canary) |
| Verified-binding ENFORCE | WATHEFNI only |
| Unified inbound flags | on / tenants=`WATHEFNI` |
| Health | 200 |
| Workers | orchestrator + video-interview + CK index active |

---

## 9. Blocked-work evidence

Sample from `tc_blocked_work`:

| work_kind | reason_code | disposition |
|---|---|---|
| canary_queue | module_paused | hold |
| canary_stale_epoch | module_paused | hold |
| epoch_canary | activation_epoch_mismatch | hold |
| intake:email | tenant_lifecycle_suspended | reject |
| synthetic_queue | tenant_lifecycle_suspended | hold |

---

## 10. Rollback proof

| Switch | Proven |
|---|---|
| Plane off | yes |
| Decision off → mode `bypass` | yes |
| Lifecycle enforce off | yes |
| Epoch enforce off | yes |
| Global authoritative forced false | yes |
| Wave 1 authoritative false | yes |
| Canary authority cleared after proofs | yes (`enabled=0` for WATHEFNI) |
| Health after restore | 200 |

Rollback path to Wave 1 behavior: set
`WATHEFNI_TENANT_CONTROL_DECISION=off` (or plane off). Legacy
`company_modules` / `require_entitlement` continue unchanged.

Production backup before Wave 2 patch:

`/opt/wathefni/var/wave2-backups/20260727T102850Z`

---

## 11. Schema additions (Wave 2)

**Schema version:** `tenant-control-schema-v2`

Additive tables/columns:

- tenant/module activation epochs + `tc_activation_epochs`
- module dimension columns on `tc_tenant_module_instances`
- `tc_blocked_work`
- `tc_role_templates` / `tc_tenant_roles` / `tc_role_grants`
- `tc_canary_authority`
- `tc_decision_audit`
- `tc_orphan_monitoring`
- `tc_permission_parity_runs`

Wave 1 tables retained.

---

## 12. Code artifacts

| Path | Role |
|---|---|
| `tenant_control_decision.py` | Canonical decision contract |
| `tenant_control_lifecycle.py` | Company/module lifecycle + epochs + canary authority |
| `tenant_control_roles.py` | Additive roles + parity |
| `tenant_control_surfaces.py` | Observe/enforce adapter |
| `tenant_control_queue_gate.py` | Worker/intake/webhook gates |
| `tenant_control_wave2_schema.py` | Additive schema |
| `app.py` | Nav/API/module/settings/lifecycle hooks |
| `tool_call_orchestrator.py` | AI tool gate |
| `outbound_delivery.py` | Notification gate |
| `ops/wave2-tenant-control-universal-enforcement.py` | Canary proof runner |
| `ops/patch-wave2-app-tenant-control.py` | Production app patch helper |
| `smoke-test-tenant-control-wave2.py` | Unit smokes |

---

## 13. Remaining gaps (for Wave 3+)

1. **Not every worker claim loop is hard-wired yet** — shared queue gate exists
   and was proven in canaries; video/assessment/email/CK/delivery loops still
   need line-by-line stamping of `activation_epoch` on enqueue + claim-time
   checks in production paths.
2. **`wathefni-delivery-sweep-worker` was inactive** during proof (pre-existing
   unit state). Outbound path is still gated via `deliver_to_employee`.
3. **Reminder/timer HTTP entrypoints** remain multi-tenant scanners; deepen
   per-row lifecycle/epoch checks beyond module automation flags.
4. **Custom roles are additive only** — live auth still uses fixed HR roles.
5. **Integration readiness** is an input to the decision contract but provider
   connect/test/verify remains Wave 3 configuration work.
6. **Global authoritative mode** must stay off until multi-tenant isolation and
   full worker coverage are proven.

---

## 14. Final GO / NO-GO for Wave 3

### GO

Proceed to Wave 3 (configuration, integrations, and readiness) on top of this
enforcement foundation.

### NO-GO

Do not:

- enable an external tenant;
- turn on global canonical authority;
- suspend WATHEFNI without the explicit canary token;
- treat shadow observations as proof every worker already stamps epochs;
- delete the 12 orphan `company_settings` rows;
- redesign normal HR UI as part of Wave 3 kickoff.

Wave 2 universal enforcement is complete. Stop.
