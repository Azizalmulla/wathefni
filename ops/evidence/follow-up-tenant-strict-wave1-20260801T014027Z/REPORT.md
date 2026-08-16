# Wave 1 STRICT — outbound delivery tenant ownership

**Verdict: PASS (local)** — not deployed. Wave 2 not started.

## Problem
`COALESCE(ode.company_code, a.company_code) = a.company_code` is not a true tenant
boundary: a legacy `company_code IS NULL` event can qualify any tenant that shares
`app_key`.

## Fix
1. **Audit** all null-`company_code` `outbound_delivery_events`.
2. **Backfill** only when `applications.app_key` maps to exactly one `company_code`.
3. **Quarantine/report** orphans and ambiguous multi-tenant collisions (leave
   `company_code` NULL; stamp `payload.tenant_ownership` on apply).
4. **Strict runtime predicate**: `ode.company_code = a.company_code`.
5. **Write path**: `record_outbound_delivery_event` requires resolvable
   `company_code` (`company_code_required`).

## Prod dry-run classification (read-only)
| Class | Rows |
|------|------|
| `backfill_unambiguous_application` | 32 |
| `quarantine_ambiguous_multi_tenant` | 0 |
| `quarantine_orphan_no_application` | 690 |
| **null total** | **722** / 791 |

Authority used for ownership: **applications** only.
Heuristics (`account_id` matches a company, subject_key embeds WATHEFNI) are
**reported as signals only** and never assigned.

## Proofs
| Check | Result |
|-------|--------|
| Null events strict-qualify count | **0** |
| Cross-tenant explicit company_code | blocked |
| WATHEFNI after simulated unambiguous backfill | **2 people / 4 apps** |
| Ambiguous silently assigned | **none** (0 ambiguous; orphans reported) |
| Local smokes | PASS |

## Apply (not run)
```bash
# staging/prod only with explicit ack — do not run from this local pass
python3 ops/migrate-outbound-delivery-company-ownership.py \
  --apply --ack-db="$WATHEFNI_EXPECTED_DATABASE_NAME" \
  --out /path/to/audit.json
```

## Affected files
- `wathefni-orchestrator/prehire_overview.py` — strict predicate + JOINs
- `wathefni-orchestrator/app.py` — require/persist company_code on new events; thread through Octopus sends
- `wathefni-orchestrator/ops/migrate-outbound-delivery-company-ownership.py` — audit/backfill/quarantine
- `wathefni-orchestrator/smoke-test-follow-up-tenant-safety.py`
- `wathefni-orchestrator/smoke-test-prehire-overview-unit.py`
