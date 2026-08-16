# Kuwait First-Client Foundation — Staging Green

**Status:** staging-green  
**Production:** **not promoted / untouched**  
**Date:** 2026-07-25 (Kuwait)  
**Prior staging-green:** `077103b2c4463470197e9c5fa44ebeb377b4aea86112fe5cb17d9b4d9b652af7` (optional-module-boundary)  
**This staging-green artifact:** `73cccafdf4ae6cc57a68bb3d69197110b9413864a0ec361e8a021c8cb0812267`  
**Staging-green file:** `/opt/wathefni/staging/last-green.sha256`  
**Artifact record:** `/opt/wathefni/staging/kuwait-first-client-foundation-artifact.sha256`  
**Freeze manifest:** `ops/KUWAIT_FIRST_CLIENT_FOUNDATION_FREEZE.txt`  
**Delivery:** `WATHEFNI_DELIVERY_MODE=dry_run`  
**Stop:** do **not** deploy to production until explicit owner approval of **exactly** this artifact.

---

## Verdict

The exact Kuwait first-client foundation artifact was surgically promoted to isolated staging and fully qualified. Architecture acceptance (country-neutral core + KW-profile scope) passed before deploy. Additive schema was applied while old code remained safe. Foundation matrix **53/53**, frozen Offers/Hiring **38/38**, optional-module-boundary **301/301**, and prior frozen pre-hiring matrices remained green. Synthetic residue cleaned to zero. **Production untouched. Stop.**

---

## Artifact SHA

| Item | Value |
|---|---|
| Staging-green artifact | `73cccafdf4ae6cc57a68bb3d69197110b9413864a0ec361e8a021c8cb0812267` |
| Hash inputs | `kuwait_first_client_foundation.py` + `hire_operations.py` + `ops/lib/doc_type_map.py` + surgically patched staging `app.py` |
| Host | `root@76.13.63.68` |
| Backend | `wathefni-orchestrator-staging.service` · `127.0.0.1:8011` |
| Database | `wathefni_staging` |
| Evidence | `ops/kuwait-first-client-foundation/kuwait-first-client-foundation-staging-20260725T032943Z.json` |

### Contained file SHAs

| File | SHA256 |
|---|---|
| `kuwait_first_client_foundation.py` | `643001b762d833c8566cb2769a8f2db0c3231461380896a832b48fcfc2ff0325` |
| `hire_operations.py` | `de24a1a943a15d33980fec77782bd19a4c61e9e63bbf647c30b4641675fab8c7` |
| `ops/lib/doc_type_map.py` | `448d0946807db1ef493fa5bde8825798ead9fa0b0d63ff182b000e4bf6d510f0` |
| `app.py` (staging-green base + foundation patches only) | `8d2e880aafcf1b639dbb53e3ef8544e013e01546ce8be7e6b491cbba29f22ab2` |
| `ops/kuwait-first-client-foundation-staging-matrix.py` (ops harness) | `61855aa2375fa73362b758aaa4300653254d0adaa3c00ee841542840c9d5ec2b` |

Unrelated local dirty tree content was **not** included. Staging `app.py` was derived from optional-module-boundary green `6c237cab…` with only foundation hooks/labels/seed patches.

---

## Architecture acceptance proof

**Result: PASS (0 failures) — before staging deploy.**

| Gate | Proof |
|---|---|
| Core tables country-neutral | `legal_entities`, `employment_applicability_snapshots`, `employee_identity`, `employee_document_metadata` — no `kuwait_*` table names |
| No SQL default forcing KW/KWD | `country_code` / `default_currency` require explicit values (no `DEFAULT 'KW'` / `DEFAULT 'KWD'`) |
| KW concepts profile-scoped | `COUNTRY_PROFILES["KW"]` owns `article_18_expatriate`, `kuwaiti_national`, Civil ID presentation, PAM ref key, `residence`/`work_permit` |
| Civil ID / PAM / Article 18 not universal | `assert_category_allowed_for_country("article_18_expatriate","SA")` → `employee_category_country_mismatch`; `assert_pam_allowed("AE",…)` → `pam_ref_kw_only`; national-id storage slots presented as Civil ID under `identity_profile=kw_civil_id` |
| SA/UAE packs not enabled | No `SA`/`AE` entries in `COUNTRY_PROFILES`; SA only appears in thin `_GCC_CURRENCY` bootstrap (`SAR`) |
| Future SA/UAE without hire rewrite | Snapshot + legal-entity + identity tables remain country-coded; hire authority still accepted-offer / offers-disabled / hire-override; new packs add profile entries |
| No leave/EOS/PIFSS/OT/fine/gov API | Static scan of foundation + hire hook: no `enforce_leave`, `eos_calculate`, `pifss_calculate`, `statutory_ot_multiplier`, `fine_calculate`, `pam_submit`, `moi_file`, `paci_verify`, `government_api`, `payroll_payment` |

---

## Backup and rollback

| Item | Value |
|---|---|
| Backup | `/opt/wathefni/backups/staging-pre-kuwait-foundation-20260725T032515Z` |
| DB dump SHA256 | `0f171195aaa6f3023fd55a4278c315a4a9d581cf160bdcb81567945069d809f2` |
| Rollback | `bash /opt/wathefni/backups/staging-pre-kuwait-foundation-20260725T032515Z/ROLLBACK.sh` |
| Rollback restores | prior `app.py`, `hire_operations.py`, removes foundation module, restores prior `last-green.sha256` |

---

## Migration order (executed)

1. **Verify frozen artifact identity** — local freeze → `73cccafd…` (after hire-country resolution fix from interim `9a8664f1…`).  
2. **Verified staging backup** — dump + code snapshot + `ROLLBACK.sh`.  
3. **Additive schema while old code running** — `ensure_foundation_schema` via `/tmp/kw-pre-schema` only; hire hook **absent**; health OK (`PRE_SCHEMA_OLD_CODE_SAFE`).  
4. **Old code remained safe** — staging still on boundary green `077103b2…` / app `6c237cab…` during pre-schema window.  
5. **Deploy exact frozen files** — foundation module, hire hook, `doc_type_map`, patched `app.py`; restart staging; Civil ID key via staging EnvironmentFile.  
6. **Full staging qualification** — foundation matrix + frozen regressions.  
7. **Clean synthetic fixtures** — matrix schema drops + orphan foundation rows for deleted synthetic companies.  
8. **Stop before production** — prod app unchanged; no foundation module on prod.

---

## Deployed files

| Path on staging | Role |
|---|---|
| `/opt/wathefni/staging/orchestrator/kuwait_first_client_foundation.py` | Legal entity, snapshot, identity, residence compat, Arabic contract link |
| `/opt/wathefni/staging/orchestrator/hire_operations.py` | Atomic hire TX creates applicability snapshot |
| `/opt/wathefni/staging/orchestrator/ops/lib/doc_type_map.py` | Canonical `residence` + legacy aliases |
| `/opt/wathefni/staging/orchestrator/app.py` | `ensure_foundation_schema`; onboarding `residence`; category-aware compliance seed |
| `/opt/wathefni/staging/orchestrator/ops/kuwait-first-client-foundation-staging-matrix.py` | Staging harness |

Production `/opt/wathefni/orchestrator/` has **no** foundation module; prod health **200**.

---

## Full gate matrix (foundation)

**Harness:** `ops/kuwait-first-client-foundation-staging-matrix.py`  
**Marker:** `kuwait-first-client-foundation-staging-v1`  
**Result:** **53 passed / 0 failed**  
**Evidence:** `ops/kuwait-first-client-foundation/kuwait-first-client-foundation-staging-20260725T032943Z.json`

Includes:

- architecture acceptance gates (10);  
- default legal-entity uniqueness + multi-entity + EN/AR names;  
- accepted-offer / offers-disabled / hire-override snapshots;  
- national vs Article 18 compliance seeds;  
- `residency_iqama` compatibility without destructive merge;  
- Civil ID mask / privileged reveal; OCR non-authoritative until confirm;  
- Arabic contract upload link + immutable snapshot core;  
- replay + concurrency; tenant isolation; entity switch does not rewrite history.

---

## Frozen regression results

| Suite | Result | Notes |
|---|---|---|
| offer-lifecycle smoke | PASS | |
| offer-hire-override smoke | PASS | |
| candidates-c3 schema + matrix | PASS | |
| ranking R0–R3 | PASS | |
| ranking presentation | PASS | |
| reports-v1 | PASS | |
| assistant A0–A3 | PASS | |
| assessments ON/OFF | PASS | |
| interviews | PASS (45/45) | |
| offers-hiring | PASS (**38/38**) | Re-run after hire country resolution from offer/defaults |
| optional-module-boundary | PASS (**301/301**) | |

Interim offers-hiring failure (`Cannot auto-create legal entity without companies.country`) was fixed in-artifact by resolving country from **companies.country → accepted offer → company defaults** (still never invents KW when none exist). Artifact re-frozen to `73cccafd…` before green pin.

---

## Cleanup proof

| Check | Result |
|---|---|
| Throwaway `kw_foundation_*` schemas | **0** |
| Matrix companies `KWPILOT`/`KWPEER`/`KWNOOFF`/`KWOVR` | **0** |
| Orphan foundation rows for deleted synthetic companies (`OFFERSTG`, `STBND*`) | deleted; counts **0** |
| Prohibited feature scan | **PASS** |

---

## Residual risks

- Frozen Offers/Hiring and optional-module-boundary cleanups did not originally drop new foundation tables; staging required an explicit orphan purge after those matrices hired. **Production promote** should extend those harness cleanups (or post-matrix orphan sweep) before claiming zero residue.  
- `civil_id_*` column names remain the national-id storage slots; KW profile presents them as Civil ID. SA/AE packs must add their own `identity_profile` labels — do not treat Civil ID as global product copy.  
- PAM / CR / licence remain employer-entered text; **not** API-verified.  
- Arabic contracts remain **upload-only**; no generated Arabic legal text.  
- Leave / EOS / PIFSS / statutory OT / fines / payroll / PAM-MOI-PACI filings remain **out of scope**.  
- Staging Civil ID Fernet key is staging-local (`wathefni-civil-id.staging.env`); production needs its own key management before promote.

---

## Production promotion plan

**Do not execute until owner approves exact artifact `73cccafd…`.**

1. Owner approval of this staging-green pin only.  
2. Production backup + documented rollback.  
3. Additive `ensure_foundation_schema` while current prod code runs (prove health).  
4. Surgical install of the **same four product files** at the SHAs above.  
5. Production Civil ID key EnvironmentFile.  
6. Restart prod service; health + environment binding.  
7. Re-run foundation matrix in isolated schemas + frozen pre-hiring/post-hire production matrices (dry_run delivery).  
8. Orphan/residue sweep; pin production-green only if all pass.  
9. Do **not** claim automatic Kuwait legal compliance in product copy.

---

## Owner next step

Approve production promotion of **exactly** `73cccafdf4ae6cc57a68bb3d69197110b9413864a0ec361e8a021c8cb0812267`. Do not ship a different tree. **Do not deploy to production from this report alone.**
