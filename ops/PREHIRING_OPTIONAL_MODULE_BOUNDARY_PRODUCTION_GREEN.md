# Pre-Hiring — Optional Module Boundary Production Green / Frozen

**Status:** production-green · **optional module boundaries frozen**  
**Promoted artifact:** exact staging-green optional-module-boundary only  
**Artifact SHA:** `077103b2c4463470197e9c5fa44ebeb377b4aea86112fe5cb17d9b4d9b652af7`  
**Source:** `/tmp/wathefni-c3-local` at staging-green pin  
**Next:** wait for owner instruction — **do not begin another project**

---

## Verdict

Guarded production promotion of the optional-module-boundary staging-green artifact is **green**. Live `interviews` and async `video_interviews` are independently switchable across all four ON/OFF combinations; disabled modules disappear from UI, Reports, Assistant, mobile, overview, queues and APIs; Assessments OFF exposes no Assistant chip or link; Ranking/Offers/Hiring stay non-blocking; historical interview records preserve and restore; already-issued public offer links follow the approved policy; frozen-module regressions pass; cleanup leaves zero residue. **Stop.**

---

## Promoted identifiers

| Item | Value |
|---|---|
| Staging-green / promoted artifact SHA | `077103b2c4463470197e9c5fa44ebeb377b4aea86112fe5cb17d9b4d9b652af7` |
| Staging evidence | `ops/PREHIRING_OPTIONAL_MODULE_BOUNDARY_STAGING_GREEN.md` |
| Production pin file | `/opt/wathefni/production/optional-module-boundary-production-green.json` |
| Host | `root@76.13.63.68` |
| Backend | `wathefni-orchestrator.service` · `127.0.0.1:8010` · health **200** |
| Database | `wathefni` · marker `wathefni-production-isolation-v1` |
| Dashboard | `/var/www/wathefni-dashboard` (from staging-green dist) |
| Delivery during quals | process-local `WATHEFNI_DELIVERY_MODE=dry_run` only |
| Explicit backup | `/opt/wathefni/backups/pre-optional-module-boundary-prod-20260725T021957Z` |
| DB dump sha256 | `34973fd4f58b912d6eac63513607d9fb0fc67e38d47d27f2e031e5d4d0f642a1` |
| Daily backup | `/opt/wathefni/backups/daily/20260725T021957Z` |
| Deploy snapshot | `/opt/wathefni/backups/predeploy-20260725T022126Z` |
| Matrix evidence | `/opt/wathefni/orchestrator/reports/optional-module-boundary-production-matrix.json` |
| Owner search markers | **`PRODBND1–4`**, **`PRODBNDH`**, **`PRODBNDO`** |

### Rollback command

```bash
snap=/opt/wathefni/backups/pre-optional-module-boundary-prod-20260725T021957Z
bash "$snap/ROLLBACK.sh"
# Or manually:
# tar -xzf "$snap/orchestrator.tgz" -C /opt/wathefni/orchestrator
# restore dashboard from "$snap/dashboard-public.tgz"
# systemctl restart wathefni-orchestrator.service; systemctl reload caddy
# DB restore ONLY if required (destructive):
#   set -a; . /root/.openclaw/secrets/postgres.env; set +a
#   pg_restore --clean --if-exists -d "$WATHEFNI_DATABASE_URL" "$snap/wathefni.dump"
# Optional backfill row revert (inert under old code):
#   DELETE FROM company_modules
#   WHERE module_key='interviews'
#     AND source='migration:interviews-module-carveout-v1';
```

---

## Artifact identity

| Check | Result |
|---|---|
| Local recomputed artifact SHA | `077103b2…` |
| `/opt/wathefni/staging/last-green.sha256` | same |
| Staging boundary record | same |
| `ops/deploy.sh production` gate | passed (artifact == staging-green) |
| Unrelated dirty worktree files | **not** deployed |

### Per-file SHA256 (production == staging-green product bytes)

| File | SHA256 (prefix) |
|---|---|
| `app.py` | `6c237cab102f` |
| `module_catalog.py` | `2a1d4264343e` |
| `action_registry.py` | `d5d9b587f3ec` |
| `interview_service.py` | `17e1a33d85ee` |
| `offer_service.py` | `993c1bbdea97` |
| `reports_v1.py` | `52c7bade5335` |
| `operator_mobile.py` | `72c492297e1a` |
| `operator_mobile_data.py` | `aaccb47ea332` |

---

## Before deployment

### Backup

| Item | Result |
|---|---|
| Explicit snapshot | `/opt/wathefni/backups/pre-optional-module-boundary-prod-20260725T021957Z` |
| `orchestrator.tgz` | readable · sha `0dd8d1be…` |
| `dashboard-public.tgz` | readable · sha `a3052e74…` |
| `wathefni.dump` | 5.2M · sha `34973fd4…` · `pg_restore -l` OK |
| `ROLLBACK.sh` | present and executable |
| Daily backup | `20260725T021957Z` SUCCESS |

### Inert `interviews` backfill (before code)

| Step | Result |
|---|---|
| Dry run | `pending_count: 1` → `WATHEFNI` |
| Apply | `inserted_count: 1` |
| Idempotent re-run | `pending_count: 0`, `already_present_count: 1`, no disabled flips |

### Current production artifact unaffected after backfill

While production still served Offers/Hiring bytes (`app.py` `bd1c94ee…`):

| Check | Result |
|---|---|
| Catalog lacked `interviews` | `catalog_has_interviews False` |
| Unconditional `or True` still present | `True` |
| `assessments_page_reachable` absent | `True` |
| Registry row for `WATHEFNI` | `interviews` present |
| Runtime binding / health | production match · **200** · service active |

---

## Deploy

`ops/deploy.sh production` synced the exact artifact, compiled, migrated schema, restarted the service, published the dashboard dist, and passed the public-route guard (API JSON, SPA `#root`, hashed JS asset).

Post-deploy:

| Check | Result |
|---|---|
| `or True` gone | **0** occurrences |
| `assessments_page_reachable` present | **3** |
| Catalog has `interviews` | yes |
| Health | **200** |
| Public edge `/dashboard/auth/me` | **401** JSON |

---

## Production qualification matrix

| Item | Value |
|---|---|
| Harness | `ops/optional-module-boundary-production-matrix.py` |
| Tenants | PRODBND1–4, PRODBNDH, PRODBNDO |
| Delivery | `dry_run` |
| Gates | **301** |
| Failed | **0** |
| Observations | 12 |
| Verdict | **PASS** |
| Residue | zero (`cleanup_leaves_zero_residue`, 8 files removed) |

### Four combinations

| Tenant | `interviews` | `video_interviews` | Result |
|---|---|---|---|
| PRODBND1 | ON | ON | PASS |
| PRODBND2 | ON | OFF | PASS |
| PRODBND3 | OFF | ON | PASS |
| PRODBND4 | OFF | OFF | PASS |

Proven on production:

- modules independently switchable;
- disabled modules absent from UI/API/Assistant/Reports/mobile/overview/queues;
- live Interviews OFF creates no interview debt;
- async-video OFF blocks only recorded-video flows;
- Assessments OFF → zero Assistant Assessments chip/link; Interviews nav unchanged;
- enabled modules still work;
- Ranking, Offers, Hiring non-blocking in every combination (hire → exactly one employee);
- historical rows preserved when both interview modules OFF and restored on re-enable;
- issued public offer links stay servable with `reason=issued_before_module_disabled` while HR reads/mutations fail closed;
- token/expiry/privacy protections intact;
- zero residue after cleanup.

### Public offer-link policy (PRODBNDO)

| Gate | Result |
|---|---|
| HR offer routes blocked when Offers OFF | PASS (`module_disabled`) |
| Issued candidate link stays active | PASS (`issued_before_module_disabled`) |
| Candidate can still accept | PASS |
| Invalid token refused | PASS |
| Terminal/expired link refused | PASS |
| Policy matrix (8 statuses) | PASS |

### Historical preservation (PRODBNDH)

| Gate | Result |
|---|---|
| Rows unchanged after disable | `{video:1, live:2}` → same |
| Surface/record not exposed | `module_disabled` |
| Reports hide interview step | PASS |
| Re-enable restores history | PASS |

---

## Frozen-module regressions

| Suite | Result |
|---|---|
| `smoke-test-entitlement-hardening.py` | PASS |
| `smoke-test-module-catalog.py` | 50/50 PASS |
| `smoke-test-toolcall-orchestrator.py` | PASS |
| `smoke-test-prehire-registry-parity.py` | 61/61 PASS |
| `smoke-test-hr1-operator-mobile.py` | 87/87 PASS |
| `smoke-test-hr3-mobile-data.py` | 70/70 PASS |
| `smoke-test-mobile-action-authority.py` | 55/55 PASS |
| Public-route guard (deploy) | PASS |
| Production health | **200** |

Real tenant `WATHEFNI` resolves `interviews=True`, `video_interviews=True` after promote.

---

## Schema / config delta

| Change | Kind |
|---|---|
| Canonical `interviews` module in catalog | additive |
| `LEGACY_IMPLIED_MODULES` / backfill for registry tenants with `pre_hiring` | additive entitlement row |
| Live-interview surfaces entitled by `interviews` | entitlement remap (no hire-authority change) |
| `video_interviews` narrowed to async-only | documentation + gating clarity |
| `public_offer_link_policy` | additive policy helper |
| Reports funnel/export/metric module ownership | additive omission when disabled |
| Assistant Assessments chip reachability gate | presentation-only |

No frozen hire authority, Ranking evidence policy, or Offers lifecycle semantics were reopened.

---

## Residuals

1. Production entitlement smoke temporarily staged `App.tsx` / `App.test.tsx` under `/opt/wathefni/apps/wathefni-dashboard/src` for static checks, then **removed**. Served dashboard remains dist-only.
2. Production boundary wrapper patches the matrix refuse gate in memory so the frozen artifact SHA stays exact; wrapper itself is not part of the artifact hash.
3. Disabling Employment Offers does **not** revoke an already-sent valid candidate link.

---

## Production health

| Check | Result |
|---|---|
| `systemctl is-active wathefni-orchestrator.service` | active |
| `http://127.0.0.1:8010/health` | **200** |
| Public API edge JSON | PASS |
| Dashboard shell + asset | PASS (deploy guard) |

---

## Freeze

Optional module boundaries are **production-green and frozen** at artifact `077103b2c4463470197e9c5fa44ebeb377b4aea86112fe5cb17d9b4d9b652af7`.

**Stop. Do not begin another project.**
