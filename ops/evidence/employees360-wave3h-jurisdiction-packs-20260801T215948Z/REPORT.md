# Employees 360 Wave 3H — Jurisdiction policy-pack architecture

**Stamp:** `20260801T215948Z`  
**Evidence:** `ops/evidence/employees360-wave3h-jurisdiction-packs-20260801T215948Z/`  
**Schema:** `employees360-wave3h-jurisdiction-packs-v1`  
**Production deploy:** **NOT DONE** (staging sync only)  
**Additional countries / worker categories:** **NOT IMPLEMENTED** (reserved IDs only)  
**Wave 4 prod / pre-hiring / Wave D:** **UNTOUCHED**

---

## Verdict: **PASS**

| Gate | Result |
|---|---|
| Policy-pack contract + schema | **PASS** |
| Only `KW_PRIVATE_SECTOR` verified/enabled | **PASS** |
| Reserved packs fail closed (no legal rules) | **PASS** |
| Missing jurisdiction / worker category fail closed | **PASS** |
| Pack version freeze on approved lifecycle requests | **PASS** (15 freezes in staging WATHEFNI) |
| Tenant override cannot weaken mandatory rules | **PASS** (unit) |
| Wave 3F KW behaviour preserved for verified path | **PASS** (staging smoke) |
| Scheduler / approvals / rehire / settlement / service certificate | **PASS** (no regression) |
| Prod deploy / other countries | **Not done** (by design) |

---

## Architecture

```
employment (jurisdiction_code + worker_category)
        │
        ▼
 resolve_pack_code() ──► ENABLED → KW_PRIVATE_SECTOR v1.0.0
                      ├─► RESERVED → fail closed (pack_not_implemented)
                      └─► unknown/missing → fail closed (remediation)
        │
        ▼
 merge_tenant_override()  (tighten only)
        │
        ▼
 lifecycle request stamps pack_code + version + hash
        │
        ▼
 on approve → employee_lifecycle_policy_freezes (immutable snapshot)
```

**Module:** `wathefni-orchestrator/employee_policy_packs_wave3h.py`  
**Wired into:** `employee_lifecycle_wave3c.py` (generic lifecycle resolves packs; KW law lives in the pack, not hard-coded service branches)

### Initial verified pack
- `KW_PRIVATE_SECTOR` `1.0.0` — Wave 3F public-law closure content (hash `fc0f28b1…`)

### Reserved identifiers (enabled=false, no rules)
`KW_GOVERNMENT`, `KW_DOMESTIC_WORKERS`, `KW_OIL_SECTOR`, `KW_MARITIME`, `SA_PRIVATE_SECTOR`, `UAE_PRIVATE_SECTOR`, `QA_PRIVATE_SECTOR`, `BH_PRIVATE_SECTOR`, `OM_PRIVATE_SECTOR`

---

## Schema

See `schema/wave3h-policy-packs.sql` and `schema/PACK-CONTRACT.md`.

| Table / columns | Purpose |
|---|---|
| `employee_policy_pack_registry` | Immutable pack versions |
| `employee_policy_pack_tenant_overrides` | Tighten-only company overlays |
| `employee_policy_pack_remediation` | Uncertain records (no silent classify) |
| `employee_employments.jurisdiction_code/worker_category/policy_pack_*` | Binding |
| `employee_lifecycle_requests.policy_pack_*` | Request-time stamp |
| `employee_lifecycle_policy_freezes` | Approved-action immutable freeze |

---

## Migration / remediation

Staging WATHEFNI migration (`wave3h-migrate-20260801T215948Z-final`):

```json
{"resolved": 0, "already_resolved": 0, "remediation": 10, "total": 10}
```

Existing employments without explicit jurisdiction/category entered **remediation** (not silently classified). HR must confirm via `confirm_employment_kw_private_sector` (or supply fields on lifecycle payload). Lifecycle create with explicit `jurisdiction_code=KW` + `worker_category=private_sector` binds the pack.

---

## Staging evidence

| Suite | Result |
|---|---|
| Wave 3H unit | **31/31** `verify/w3h-unit.txt` |
| Wave 3C/3H unit | **42/42** `verify/w3h-unit3c.txt` |
| Wave 3 unit | **22/22** `verify/w3h-unit3.txt` |
| Wave 3C/3H smoke | **57/57** `verify/w3h-smoke3c.txt` |
| Wave 3 smoke | **51/51** `verify/w3h-smoke3.txt` |

Prod orchestrator still on prior Wave 3D/3F module; `employee_policy_packs_wave3h.py` **absent** on prod (by design).

---

## Remaining risks

1. Historical employments remain in remediation until HR confirms jurisdiction/category.  
2. Wave 3 base path (`employee_lifecycle_wave3.py`) does not yet require packs — product APIs should continue via Wave 3C/3H wrappers.  
3. Future pack versions need DB-backed historical load (v1 is in-process + registry seed; freezes already immutable).  
4. Oil/maritime residual coverage under Law 6/2010 is reserved, not enabled.  
5. No production deploy / canary this wave.

---

## Explicit non-goals honored

- No Saudi/UAE/Qatar/Bahrain/Oman legal rules  
- No KW government/domestic/oil/maritime rules  
- No production deploy  
- No Wave 4 production deployment  
- No pre-hiring / Wave D changes  
- Exceptional legal decisions remain manual; monetary math remains Payroll-owned  
