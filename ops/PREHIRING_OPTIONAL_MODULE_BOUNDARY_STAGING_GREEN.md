# Pre-Hiring — Optional Module Boundary Staging Green

**Status:** staging-green  
**Production:** **not promoted / untouched**  
**Date:** 2026-07-25 (Kuwait)  
**Source worktree:** `/tmp/wathefni-c3-local`  
**Staging artifact SHA:** `077103b2c4463470197e9c5fa44ebeb377b4aea86112fe5cb17d9b4d9b652af7`  
**Staging-green file:** `/opt/wathefni/staging/last-green.sha256`  
**Artifact record:** `/opt/wathefni/staging/optional-module-boundary-artifact.sha256`  
**Prior staging-green:** `71dd4d10d51605968436885c5867a79ace73452e33849d64441ef23801f0ebf5` (Offers/Hiring)  
**Delivery:** `WATHEFNI_DELIVERY_MODE=dry_run`  
**Stop:** do **not** run `ops/deploy.sh production` until owner approval.

---

## Verdict

The exact optional-module-boundary remediation was promoted to isolated staging in the approved order: inert `interviews` backfill first, currently deployed artifact verified unaffected, frozen artifact deployed, full Interviews × Video Interviews ON/OFF matrix green (301/301, zero residue). Assessments Assistant chip gating is live. Production remains stopped.

---

## Ordered execution proof

### 1. Inert `interviews` module-row backfill (before code deploy)

| Step | Result |
|---|---|
| Dry run | `pending_count: 11` including `WATHEFNI` |
| Apply | `inserted_count: 11` |
| Idempotent re-run | `pending_count: 0`, `already_present_count: 11`, no disabled flips |

### 2. Currently deployed artifact remained unaffected

While staging still served Offers/Hiring green `71dd4d10…`:

| Check | Result |
|---|---|
| Catalog still lacked `interviews` key (old code) | `catalog_has_interviews False` |
| Unconditional `or True` still present in deployed `app.py` | `True` |
| `assessments_page_reachable` absent (old code) | `True` |
| Registry row present for `WATHEFNI` | `interviews` in enabled modules |
| Service active / runtime binding | `active`, staging match |
| Staging-green unchanged until this promote | `71dd4d10…` |

### 3. Deploy exact frozen artifact

Product code synced and staging service restarted onto remediation bytes (`app.py` `6c237cab…`, `module_catalog.py` `2a1d4264…`, `reports_v1.py` `52c7bade…`). Dashboard dist published. Staging smoke, Ranking, Reports (after fixture entitlement fix), Assistant A0–A3, Assessments ON/OFF, Interviews (after live-module entitlement fix), and Offers/Hiring matrices passed.

**Staging matrix fixture alignments (ops only, not product authority):**

- `reports-v1-staging-matrix.py` — REPORTSV1 now entitles `interviews` + `employment_offers` so the full funnel fixture matches the module-boundary contract.
- `interviews-staging-matrix.py` — INTVLIVE entitles `interviews`; INTVVID keeps `video_interviews` only.
- `optional-module-boundary-staging-matrix.py` — STBND* tenants; sets `WATHEFNI_APPLY_WHATSAPP_NUMBER` for CLI job publish.

These ops adjustments re-froze the deploy artifact from local `75ec779f…` to staging-green `077103b2…`. Contained product file SHAs are unchanged.

### 4. Full ON/OFF staging matrix

| Item | Value |
|---|---|
| Harness | `ops/optional-module-boundary-staging-matrix.py` |
| Tenants | STBND1–4, STBNDH, STBNDO |
| Gates | **301** |
| Failed | **0** |
| Verdict | **PASS** |
| Residue | zero (`cleanup_leaves_zero_residue`) |
| Evidence | `/opt/wathefni/staging/orchestrator/reports/optional-module-boundary-staging-matrix.json` |

Proven on staging:

- four Interviews × Video Interviews combinations independently switchable;
- disabled-module UI/API/Assistant/Reports/mobile/queues absent;
- Assessments chip ON → may appear; OFF → zero chip/suggestion/link; Interviews nav unchanged;
- Ranking / Offers / Hiring non-blocking;
- historical interview rows preserved and restored;
- public offer-link policy (`issued_before_module_disabled`);
- zero residue after cleanup.

### 5. Stop before production

Staging-green recorded as `077103b2c4463470197e9c5fa44ebeb377b4aea86112fe5cb17d9b4d9b652af7`. Production was not touched.

---

## Contained product file SHAs (staging)

| File | SHA256 (prefix) |
|---|---|
| `app.py` | `6c237cab102fce507396…` |
| `module_catalog.py` | `2a1d4264343e17e40668…` |
| `action_registry.py` | `d5d9b587f3ec217ec4d0…` |
| `interview_service.py` | `17e1a33d85eea15bdb17…` |
| `offer_service.py` | `993c1bbdea97d30165fb…` |
| `reports_v1.py` | `52c7bade5335141630bb…` |
| `operator_mobile.py` | `72c492297e1aaa36da6d…` |
| `operator_mobile_data.py` | `aaccb47ea332d9f28cc7…` |

Full freeze manifest: `ops/OPTIONAL_MODULE_BOUNDARY_FREEZE.txt`.

---

## Residuals / notes

- Disabling Employment Offers does **not** revoke an already-sent valid candidate link.
- Staging CLI matrices that publish jobs need `WATHEFNI_APPLY_WHATSAPP_NUMBER` (now defaulted in the boundary staging wrapper).
- Production promotion requires explicit owner approval of artifact `077103b2…`.

---

## Owner next step

Approve production promotion of **exactly** `077103b2c4463470197e9c5fa44ebeb377b4aea86112fe5cb17d9b4d9b652af7`. Do not ship a different tree.
