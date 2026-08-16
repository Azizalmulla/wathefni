# Wave D Phase 3 — Production deploy (enterprise multi-tenant hardening)

**Verdict: PASS**  
**Stamp:** `20260801T132649Z`  
**Host:** `root@76.13.63.68`  
**Dashboard:** `https://api.wathefni.ai/dashboard/`  
**Wave D4:** not started  
**External tenants:** not enabled

Local evidence: `/Users/azizalmulla/Desktop/claw/ops/evidence/waveD-phase3-enterprise-hardening-deploy-20260801T132649Z`  
Remote evidence: `/opt/wathefni/production-evidence/waveD-phase3-enterprise/20260801T132649Z`  
Backup: `/opt/wathefni/backups/production-pre-waveD-phase3-enterprise-20260801T132649Z`

---

## Production SHAs (final, after rollback→restore)

```
61d3d8410c5d5785d577712014f1e633c44520a26623347d6dc173a6841ae31b  /opt/wathefni/orchestrator/app.py
48701edb8cffffd07d15348594ff0f60c37876595b8a3c57c9268e8160e1bada  /opt/wathefni/orchestrator/durable_email_ingress.py
3606c0a6f8c8a29f822fe527623ab17a87e2f4de8b67b2566004ef84b532087d  /opt/wathefni/orchestrator/inbound_intake_product.py
d028be75e4417b1ecf22336528ed773722c15b9f8bd95e8a34639d8ea27e9bbd  /opt/wathefni/orchestrator/inbound_enterprise_hardening.py
```

Match local qualified SHAs: **yes** (`verify/local-qualified.sha256` ↔ `verify/sha-final.txt`).

---

## Scope shipped

| Artifact | Action |
|---|---|
| `inbound_enterprise_hardening.py` | **New** — plans, soft warn, burst override, env isolation, outage list, usage |
| `durable_email_ingress.py` | Enterprise quota decision, kill-switch hold, policy resolver, delete helper |
| `inbound_intake_product.py` | Feature payload enterprise visibility |
| `app.py` | Admin override/plan/usage APIs, webhook env check, retention worker, outage replay, address 409, audit |
| systemd `waveD-phase3-enterprise.conf` | Allowlist WATHEFNI, mailbox sync off, Postmark env+PIN, retention execute off, concurrency 8 |

Dashboard dist: **unchanged** (D3 is orchestrator control-plane).

---

## Enablement posture

- `WATHEFNI_INBOUND_EMAIL=on` (continuous freeze)
- `WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI`
- `WATHEFNI_MAILBOX_SYNC=off`
- `WATHEFNI_INBOUND_DEFAULT_PLAN=enterprise` (WATHEFNI company set to `internal` unlimited after proof)
- `WATHEFNI_POSTMARK_INBOUND_ENV=production` + `WATHEFNI_POSTMARK_INBOUND_ENV_PIN=production` (live Postmark continues; staging marker fails closed)
- `WATHEFNI_INTAKE_RETENTION_EXECUTE=off` (dry-run default; proof used explicit `execute_cleanup(dry_run=False)` for one synthetic aged object)
- External companies fail closed
- **D4 not started**

---

## Core rule (production)

| Behavior | Result |
|---|---|
| Normal spikes continue | Soft warn only — no reject |
| Over-limit mail | Durable + `waiting_quota` — never rejected |
| Tenant kill switch | Durable + `waiting_budget` — never drops mail |
| Campaign burst override | Raises caps immediately; expires by TTL |
| Malware / env mismatch | Fail closed (env 401 `inbound_env_mismatch`) |
| Outages | Dead-letter → replay → `pending` |
| Tenant isolation | ACMECORP denied; WATHEFNI-only allowlist |
| Retention | Dry-run plan + opt-in execute on proof object only |

---

## Proof gates

| Gate | Result |
|---|---|
| Health 200 (orchestrator + dashboard) | **PASS** (`health_final=200`, `dashboard_final=200`) |
| WATHEFNI/test only; external disabled | **PASS** |
| Soft warning at threshold | **PASS** |
| Over-limit → `waiting_quota`, never rejected | **PASS** |
| Kill switch → `waiting_budget`, never drops | **PASS** |
| Burst override works + expires | **PASS** |
| Tenant isolation | **PASS** |
| Staging/prod Postmark mismatch fail-closed | **PASS** (401); PIN path still durable 200 |
| ClamAV/OCR outage dead-letter/replay | **PASS** (`scanner_unavailable` → `pending`) |
| Retention dry-run + opt-in execute | **PASS**; platform execute flag remains **off** |
| Address create/rotate race → 409 | **PASS** |
| Audit logs (plan, override, kill, env, rotate/create) | **PASS** (`action_results`) |
| Rollback verified | **PASS** (pre SHAs + module/drop-in removed; restore-new returns D3 SHAs; health 200) |

Source: `verify/prod-d3-proofs.json` (17/17 ok), `verify/rollback.log`, `verify/restore-new.log`.

---

## Queue / replay proof

- Over-cap receipt: durable `status=waiting_quota`, `quota_code=daily_message_quota`
- Kill-switch receipt: durable `status=waiting_budget`, `quota_code=tenant_kill_switch`
- Outage job `02337864-8c66-486f-a6ff-e203dee330e9`: `dead_letter`/`scanner_unavailable` → replay → `pending`

---

## Cleanup proof

- All `wave_d3_prod_proof` intake addresses **disabled** (0 active)
- Continuous WATHEFNI active intake count remains **1** (pre-existing continuous recipient untouched)
- Proof inbound messages/jobs cleaned under synthetic authority
- `inbound_enterprise` restored to `{plan: internal, kill_switch: false}`
- Kill switch off; admin override absent

See `cleanup/cleanup-final.json`.

---

## Rollback

- Scripts: `rollback/ROLLBACK.sh`, `rollback/RESTORE_NEW.sh`
- Rollback restored D2 baseline SHAs and removed `inbound_enterprise_hardening.py` + D3 drop-in
- Restore-new returned D3 SHAs above; health 200

---

## Final

**PASS** — Wave D Phase 3 enterprise hardening live for WATHEFNI/test allowlist only. External tenants disabled. D4 not started.
