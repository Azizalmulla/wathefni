# Kuwait First-Client Foundation — Production Green / Frozen

**Status:** production-green · **Kuwait first-client foundation frozen**  
**Promoted artifact:** exact staging-green only  
**Artifact SHA:** `73cccafdf4ae6cc57a68bb3d69197110b9413864a0ec361e8a021c8cb0812267`  
**Source:** staging tree at green pin (surgical promote)  
**Next:** wait for owner instruction — **do not begin another project**

---

## Verdict

Guarded production promotion of the Kuwait first-client foundation staging-green artifact is **green**. Country-neutral legal-entity / employment-applicability / identity / document / audit core, KW-profile scoping, atomic hire snapshots, residence compatibility, Civil ID masking, Arabic contract upload link, frozen pre-hiring / Offers/Hiring / optional-module-boundary regressions, zero synthetic residue, and production health **200** all passed. **Stop.**

**Do not claim automatic Kuwait legal compliance.**

---

## Promoted identifiers

| Item | Value |
|---|---|
| Staging-green artifact SHA | `73cccafdf4ae6cc57a68bb3d69197110b9413864a0ec361e8a021c8cb0812267` |
| Staging evidence | `ops/KUWAIT_FIRST_CLIENT_FOUNDATION_STAGING_GREEN.md` |
| Production pin file | `/opt/wathefni/production/kuwait-first-client-foundation-production-green.json` |
| Production last-green | `/opt/wathefni/production/last-green.sha256` |
| Artifact record | `/opt/wathefni/production/kuwait-first-client-foundation-artifact.sha256` |
| Host | `root@76.13.63.68` |
| Backend | `wathefni-orchestrator.service` · `127.0.0.1:8010` · health **200** |
| Database | `wathefni` · marker `wathefni-production-isolation-v1` |
| Delivery during quals | process-local `WATHEFNI_DELIVERY_MODE=dry_run` only |
| Service delivery pin | **unset** (not globally dry_run) |
| Explicit backup | `/opt/wathefni/backups/pre-kuwait-foundation-prod-20260725T033629Z` |
| DB dump sha256 | `e514e05b366b4e1207579cbed3f0a855ecc1403927c049507fbee5572e98711f` |
| Matrix evidence | `ops/kuwait-first-client-foundation/kuwait-first-client-foundation-production-20260725T033725Z.json` |
| Promoted at | `2026-07-25T03:40:50Z` |

### Rollback command

```bash
snap=/opt/wathefni/backups/pre-kuwait-foundation-prod-20260725T033629Z
bash "$snap/ROLLBACK.sh"
# Restores prior app.py + hire_operations.py + doc_type_map.py, removes foundation module,
# removes civil-id drop-in, restores prior last-green.sha256, restarts service.
# DB restore ONLY if required (destructive):
#   set -a; . /root/.openclaw/secrets/postgres.env; set +a
#   pg_restore --clean --if-exists -d "$WATHEFNI_DATABASE_URL" "$snap/wathefni.dump"
```

---

## Artifact identity

- Staging `last-green.sha256` / artifact record / live staging file SHAs == `73cccafd…`
- Recomputed hash of staging live product bytes == `73cccafd…` before promote
- Production live product bytes recomputed == same after deploy
- Unrelated dirty worktree files were **not** deployed

### Per-file SHA256 (production == staging-green)

| File | SHA256 |
|---|---|
| `kuwait_first_client_foundation.py` | `643001b762d833c8566cb2769a8f2db0c3231461380896a832b48fcfc2ff0325` |
| `hire_operations.py` | `de24a1a943a15d33980fec77782bd19a4c61e9e63bbf647c30b4641675fab8c7` |
| `ops/lib/doc_type_map.py` | `448d0946807db1ef493fa5bde8825798ead9fa0b0d63ff182b000e4bf6d510f0` |
| `app.py` | `8d2e880aafcf1b639dbb53e3ef8544e013e01546ce8be7e6b491cbba29f22ab2` |

---

## Backup and migration proof

| Step | Result |
|---|---|
| Production backup | `/opt/wathefni/backups/pre-kuwait-foundation-prod-20260725T033629Z` |
| Dump verified | sha256 `e514e05b…` |
| Rollback script | `$snap/ROLLBACK.sh` recorded |
| Pre-code additive schema | `ensure_foundation_schema` via `/tmp/kw-prod-pre-schema` only |
| Old prod code during pre-schema | app still `6c237cab…`; hire hook **absent**; health OK (`PRE_SCHEMA_OLD_CODE_SAFE`) |
| Tables present before code cutover | `legal_entities`, snapshots, identity, document metadata, compat map, event tables |
| Exact deploy | copied staging-green bytes; artifact recomputed on prod == `73cccafd…` |
| Civil ID key | `/root/.openclaw/secrets/wathefni-civil-id.production.env` + systemd drop-in |

---

## Deployed files

| Path | Role |
|---|---|
| `/opt/wathefni/orchestrator/kuwait_first_client_foundation.py` | Legal entity, snapshot, identity, residence compat, Arabic contract link |
| `/opt/wathefni/orchestrator/hire_operations.py` | Atomic hire TX + applicability snapshot |
| `/opt/wathefni/orchestrator/ops/lib/doc_type_map.py` | Canonical `residence` + legacy aliases |
| `/opt/wathefni/orchestrator/app.py` | Schema ensure, onboarding `residence`, category-aware compliance seed |

---

## Full foundation matrix (production)

| Item | Value |
|---|---|
| Harness | `ops/kuwait-first-client-foundation-production-matrix.py` |
| Marker | `kuwait-first-client-foundation-production-v1` |
| Isolation | throwaway `kw_foundation_*` schemas only |
| Gates | **53** |
| Failed | **0** |
| Evidence | `ops/kuwait-first-client-foundation/kuwait-first-client-foundation-production-20260725T033725Z.json` |

Proven:

- country-neutral core + KW profile scope (architecture gates);  
- one active default legal entity; multi-entity tenant isolation;  
- accepted-offer / offers-disabled / hire-override snapshots;  
- immutable snapshot vs later entity switch;  
- national vs Article 18 residence/work-permit behaviour;  
- non-destructive `residency_iqama` compatibility;  
- Civil ID encrypt/mask + privileged reveal; OCR non-authoritative until confirm;  
- Arabic contract upload linked without rewriting snapshot core;  
- replay + concurrency; cleanup of throwaway schemas.

---

## Frozen regression results

| Suite | Result |
|---|---|
| offer-lifecycle smoke | PASS |
| offer-hire-override smoke | PASS |
| candidates-c3 production | PASS |
| ranking R0–R3 | PASS |
| ranking presentation | PASS |
| reports-v1 | PASS |
| assistant A0–A3 | PASS |
| assessments ON/OFF | PASS |
| interviews | PASS (**45/45**) |
| Offers/Hiring | PASS (**38/38**) |
| optional-module-boundary | PASS (**301/301**) |

### Ops harness note (not product artifact)

First interviews production run failed with `module_disabled` because `INTVLIVEP` was entitled with `video_interviews` only (missing `interviews`) under the already-promoted optional-module-boundary contract. Fixed **ops harness only** (`interviews-production-matrix.py` LIVE entitlements). Product artifact SHAs remained `73cccafd…`. Boundary matrix required `WATHEFNI_BOUNDARY_ALLOW_PRODUCTION=1`.

---

## Cleanup proof

| Check | Result |
|---|---|
| Throwaway `kw_foundation_*` schemas | **0** |
| Synthetic companies from foundation/offers/interviews matrices | **0** |
| Orphan foundation rows for deleted synthetic companies | purged → **0** |
| Prohibited feature scan | **PASS** |
| SA/AE country packs | **not present** in `COUNTRY_PROFILES` |
| Production health | **200** · binding match · service **active** |

---

## Explicit non-introductions (proved)

Production does **not** introduce:

- leave-law enforcement  
- EOS / PIFSS calculations  
- statutory OT multipliers  
- fine calculations  
- payroll payments  
- PAM / MOI / PACI filings  
- government API verification  
- automatic legal-compliance claims  
- Saudi, UAE, or other unqualified country packs  

---

## Residual risks

- Frozen Offers/Hiring and optional-module-boundary cleanups do not yet delete foundation tables; production promote included an explicit orphan sweep after those matrices. Extend those harnesses before the next promote cycle.  
- Civil ID Fernet key is production-local; rotate/backup under normal secret ops.  
- `civil_id_*` columns are national-id storage slots; KW profile presents Civil ID — do not treat as universal product copy for SA/AE.  
- Arabic contracts remain upload-only; leave/EOS/PIFSS/fines/OT/payroll/filings remain out of scope.  
- Service delivery is **not** globally dry_run; quals used process-local dry_run only.

---

## Freeze

1. Kuwait first-client foundation marked **production-green**.  
2. Exact artifact **frozen**: `73cccafdf4ae6cc57a68bb3d69197110b9413864a0ec361e8a021c8cb0812267`.  
3. Production pin written: `/opt/wathefni/production/kuwait-first-client-foundation-production-green.json`.  
4. **Stop.**  
5. **Do not begin another project.**
