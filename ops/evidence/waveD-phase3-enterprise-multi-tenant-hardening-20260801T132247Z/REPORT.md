# Wave D Phase 3 — Enterprise-safe multi-tenant inbound hardening

**Stamp:** `20260801T132247Z`  
**Mode:** Local implementation only. **No deploy. No Wave D4. No Gmail/M365 mailbox sync. External tenants remain disabled.**

---

## Verdict: **PASS**

| Gate | Result |
|---|---|
| Generous configurable limits by tenant/plan | **PASS** |
| Soft warnings before hard restriction | **PASS** |
| Burst capacity (admin override) for hiring campaigns | **PASS** |
| Queue legitimate mail (`waiting_quota`) — never reject for volume | **PASS** |
| Admin overrides to raise limits immediately | **PASS** |
| Hard block only malware / clear abuse / extreme platform risk | **PASS** (volume path never rejects; env isolation / 413 body remain platform-risk) |
| Strict tenant isolation + staging/prod Postmark separation | **PASS** |
| ClamAV/OCR outage retry + replay | **PASS** |
| Retention/deletion rules with dry-run + execute proof | **PASS** |
| Usage and health visibility per tenant | **PASS** |
| Global + tenant kill switches (hold, don’t lose mail) | **PASS** |
| Concurrency-safe address create/rotate | **PASS** |
| Audit logs for override / replay / env reject / plan / kill | **PASS** |
| External tenants disabled; no mailbox sync; no D4 | **PASS** |
| Local smoke | **PASS** (23/23) |

**Core rule held:** legitimate candidates are never dropped for volume; over-cap traffic is durable-queued; one tenant’s load cannot resolve into another’s company_code.

---

## Architecture changes

```
company careers@ → forward → tenant Wathefni intake
  → Postmark inbound webhook
      ├─ secret auth
      ├─ X-Wathefni-Inbound-Env / ?env= isolation (staging ≠ production)
      └─ durable_email_ingress
           ├─ recipient → intake_addresses (tenant isolation)
           ├─ enterprise plan + soft warn + burst override
           ├─ over hard cap → status=waiting_quota (queue, ACK durable)
           ├─ tenant kill_switch → waiting_budget (hold, don’t drop)
           ├─ malware / abuse → quarantine / reject paths (unchanged)
           └─ worker: ClamAV/OCR RetryableJobError → retry → dead_letter
                └─ outage replay sweep → pending
```

**New module:** `wathefni-orchestrator/inbound_enterprise_hardening.py`

| Concern | Behavior |
|---|---|
| Plan catalog | `starter` / `growth` / `enterprise` / `internal` |
| Soft warning | Advisory at `soft_warning_pct` (default 80%) — no reject |
| Hard volume path | `waiting_quota` only — never HTTP reject for quota |
| Burst | Admin override `burst_enabled` + `burst_pct` multiplies caps for a TTL window |
| Admin override | Stored under `company_settings.inbound_enterprise.admin_override` |
| Tenant kill switch | Durable hold (`waiting_budget` / `tenant_kill_switch`) |
| Global kill | Existing `WATHEFNI_INBOUND_EMAIL` |
| Postmark env | `WATHEFNI_POSTMARK_INBOUND_ENV` + header/query/payload marker |
| Retention worker | `retention_privacy` job → `execute_cleanup` (default dry-run; execute via `WATHEFNI_INTAKE_RETENTION_EXECUTE=on`) |
| Outage replay | `list_outage_dead_letters` + `/orchestrator/debug/intake-outage-replay` |
| Address races | `IntegrityError` → HTTP 409 on create/rotate |

**Unchanged / out of scope:** forward-to-Wathefni product path (D2); allowlist fail-closed; mailbox sync off; external GA; D4.

---

## Recommended enterprise defaults

| Plan | Daily msgs | Monthly msgs | Soft warn | Burst | Concurrency |
|---|---:|---:|---:|---:|---:|
| **enterprise** (default for allowlisted prod tenants) | 10,000 | 200,000 | 80% | +50% / 72h (via admin override) | 8 |
| growth | 2,000 | 40,000 | 80% | +50% / 48h | 4 |
| starter | 500 | 10,000 | 80% | +100% / 24h | 2 |
| internal (WATHEFNI / test) | unlimited (`0`) | unlimited | 90% | n/a | 12 |

**Ops pins**

- `WATHEFNI_INBOUND_DEFAULT_PLAN=enterprise`
- `WATHEFNI_INTAKE_TENANT_CONCURRENCY=8` (fair round-robin claim)
- Distinct Postmark servers + secrets for staging vs production
- `WATHEFNI_POSTMARK_INBOUND_ENV=production|staging` and require `X-Wathefni-Inbound-Env`
- Retention: keep dry-run until owner sets `WATHEFNI_INTAKE_RETENTION_EXECUTE=on`
- Keep `WATHEFNI_INBOUND_ALLOWED_COMPANIES` narrow (WATHEFNI + named pilots only)

---

## API / control plane additions

| Endpoint | Purpose |
|---|---|
| `GET .../inbound/usage` | Per-tenant usage, soft warnings, queue health, effective limits |
| `POST .../inbound/admin-override` | Raise caps / enable burst immediately (audited) |
| `DELETE .../inbound/admin-override` | Clear override |
| `POST .../inbound/plan` | Set plan, soft %, kill switch, quota overrides |
| `POST /orchestrator/debug/intake-outage-replay` | Sweep ClamAV/OCR dead-letters → pending |
| Webhook | Optional env marker; mismatch → 401 + audit |

Feature payload now includes `enterprise` usage block + `never_reject_for_volume: true`.

---

## Tests, outage drills, retention proof

**Smoke:** `smoke-test-inbound-enterprise-hardening.py` → **23/23 PASS**

| Drill | Proof |
|---|---|
| Soft warn @ 80% | Unit `evaluate_quota` — warning without `waiting_quota` |
| Hard volume | 2nd message under daily cap=1 → durable + `waiting_quota` |
| Admin override | Raise to 100 → next message not volume-queued |
| Tenant kill switch | Durable `waiting_budget` / `tenant_kill_switch` |
| Tenant isolation | D3TESTB receipt `company_code=D3TESTB` only |
| Postmark env | Missing / mismatched marker rejected; webhook 401 on mismatch |
| ClamAV outage | Plant `scanner_unavailable` dead_letter → list → `replay_dead_letter` → `pending` |
| Retention | Dry-run plan; execute deletes aged nonclean quarantine + deletion audit row |
| Address concurrency | Duplicate active local_part → 409; rotate soft-disables old |

**DB:** `wathefni_local_boundary` via `/tmp/waveC-local-env/postgres.test.env`  
**Marker:** `wathefni-local-boundary-remediation-v1`

---

## Evidence path

`ops/evidence/waveD-phase3-enterprise-multi-tenant-hardening-20260801T132247Z/`

| Artifact | Path |
|---|---|
| This report | `.../REPORT.md` |
| Smoke log | `.../verify/smoke-inbound-enterprise-hardening.log` |
| Key file SHAs | `.../verify/key-files.sha256` |

---

## Enablement posture (local)

- Global inbound ON for local proof only.
- External tenants **not** allowlisted / not enabled.
- Mailbox sync **off**.
- Production deploy **not** started.
- Wave D4 **not** started.

---

## Follow-ups (not this phase)

- Billing-backed plan assignment UI for customer success
- Per-tenant concurrency column in `intake_tenant_queue_state` (today: fair global concurrency + plan defaults)
- Production Postmark dual-server cutover checklist
- Wave D4 (GA expansion) after pilot
