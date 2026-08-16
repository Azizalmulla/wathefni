# Employees 360 Wave 3D — Production synthetic canary (WATHEFNI only)

**Stamp:** `20260801T210838Z`  
**Evidence (remote):** `/opt/wathefni/production-evidence/employees360-wave3d-synthetic-canary/20260801T210838Z/`  
**Evidence (local):** `ops/evidence/employees360-wave3d-synthetic-canary-20260801T210838Z/`  
**Backup:** `/opt/wathefni/backups/production-pre-employees360-wave3d-20260801T210838Z/`  
**Policy base:** `ops/evidence/employees360-wave3d-public-law-policy-20260801T205907Z/`

---

## Dual verdicts

| Track | Verdict |
|---|---|
| **Technical synthetic canary** (WATHEFNI-only, synthetic records, dual approval, no money) | **GO — PASS** |
| **Real-employee production use** (live terminations, external tenants, legal guidance, monetary calcs) | **NO-GO** |

Wave 4 / pre-hiring / Wave D: **unchanged**.

---

## Production SHAs (final)

| Artifact | SHA256 |
|---|---|
| `app.py` | `c3f9f1483ff916eabc7392f48e58f62debf27527851b9a1efa5152f13c66dc31` |
| `employee_lifecycle_wave3.py` | `17c8927dc3449b305a74c7eb8abaa05bd0461c14d498459b97ba02e8d71f6e25` |
| `employee_lifecycle_wave3c.py` | `bc95081cf016bb68acf4e7afc7d43cafd07c1e8cd621968be708e48e3ee6151e` |
| `lifecycle-effective-worker.py` | `b3548984055180b12f1197234708c22c0a545a58b3b1e87cc624f841ea92b6f7` |
| `canary-prod-wave3d-synthetic.py` | `94a9085d7294b97898dfe68d1d63fac2153c956b4add088c48f6c0b3352b8e91` |

Pre-deploy `app.py`: `92addc3b7d132ee1d9f6900d6fe6d9625303c57e04589545be9da616c467b58b`

---

## Runtime flags (production)

```
WATHEFNI_ENV=production
WATHEFNI_EMPLOYEE_AUTHORITY_V2=on
WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES=WATHEFNI
WATHEFNI_EMPLOYEE_LIFECYCLE_V3=on
WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES=WATHEFNI
WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY=on
WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_PHONE_PREFIXES=965522
WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_NAME_PREFIX=W3D-SYNTH|
WATHEFNI_LIFECYCLE_COUNSEL_GATE=on
```

Drop-in: `/etc/systemd/system/wathefni-orchestrator.service.d/employee-lifecycle-v3-synthetic.conf`  
Oneshot scheduler unit installed (`wathefni-lifecycle-effective.service`); **timer not enabled**.

---

## Synthetic-only gate

When `WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY=on` (default in production):

- Lifecycle create / decide / downstream / scheduler / access-revoke **refuse** non-synthetic targets (`403 synthetic_only_gate`).
- Synthetic markers: phone prefix `965522*`, name prefix `W3D-SYNTH|`, and/or provenance `lifecycle_synthetic_canary=true`.

**Proved blocked (all four real WATHEFNI employees):**

- `WATHEFNI-96550252254` (Talal Fadhli)
- `WATHEFNI-96566363363` (Fouad Burhamad)
- `WATHEFNI-96597727743` (mohammad alqattan)
- `WATHEFNI-96599411617` (Brian Saleh)

---

## Production-safe defaults (unchanged)

| Knob | Value |
|---|---|
| `show_notice_hints` | `false` |
| `allow_reinstate_after_effective` | `false` |
| `jurisdiction_mode` | `kuwait_private_sector_only` |
| `monetary_calculations_owner` | `payroll` |
| `settlement_packet_mode` | `inputs_only` |
| `auto_cancel_shifts` | `false` |
| `auto_decline_leave` | `false` |
| `document_retention_mode` | `retain` |
| `allow_self_approval` | `false` |

---

## Synthetic canary IDs (passing rerun)

| Field | Value |
|---|---|
| Tag | `2ac2b5b8` |
| Phone | `96552202357` |
| employee_key | `WATHEFNI-96552202357` |
| person_id | `cca60e2f-f88e-572b-9055-ab7e1e1f1382` |
| employment_id (term path) | `c24d1604-7430-5183-97c4-64e80cd972d6` |
| assignment_id | `144e53fe-bfca-5d7b-b955-6a5e0bea53e2` |
| future_request_id | `d13c9c92-5943-4347-8672-5c3b560ad921` |
| rehire employment_id | `068c496c-269d-59ba-8028-e183fd58eadf` |
| rehire assignment_id | `cdfcc085-3320-531b-ab19-8e58bf7c2b18` |
| same_employee_key | `true` |
| requester | `88b17ca9-aff4-4721-a553-c1b5514ef95f` |
| approver | `b69f4cad-589d-4029-8a2d-cfa85399966c` |

Canary result: **45/45 PASS** (`canary-rerun.log`)

### Proofs covered

- Request + separate approval (self-approval forbidden)
- Future-dated termination → `notice_period`, hub stays `active`
- Scheduler execution → `terminated`, hub `left`
- Access active before LWD cutoff; revoked afterward
- Mandatory impact acknowledgment
- Settlement packet inputs-only, **no amounts**
- Explicit reversible downstream shift cancel
- Cancel-before-effective (same employment)
- True rehire: same person + same employee_key + new employment/assignment
- Idempotency, stale conflict, manager scope, tenant isolation
- Cleanup/rollback + final hub delete of synthetic row

---

## Cleanup proof

1. Canary `rollback_lifecycle_wave3c` OK  
2. Final hard delete of leftover synthetic hub `WATHEFNI-96552202357`  
3. `synthetic_hub_leftover=0`  
4. All four real employees remain `active` (`cleanup-final.json`, `real-employees-final.json`)

Rollback script for code: `$BACKUP/ROLLBACK.sh`

---

## Explicit non-actions / still NO-GO

- No notice hints exposed  
- Reinstate remains disabled  
- No real employee terminations  
- No external tenants  
- No EOSB / notice-pay / garden-leave / leave-encashment calculations  
- No Wave 4  
- Recurring prod lifecycle timer **not** enabled  

---

## Health

`GET /health` → `200` after deploy (`health-final.txt`)
