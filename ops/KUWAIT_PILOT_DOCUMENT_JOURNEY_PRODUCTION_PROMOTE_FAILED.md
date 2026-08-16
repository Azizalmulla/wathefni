# Kuwait Pilot Document Journey — Production Promote Failed (Rolled Back)

**Status:** **NOT production-green** · rolled back to prior freeze  
**Attempted artifact:** `4be5298e769576cb691b750ec9513c190d32adb13e9bddf2ebb004f694ab85d7`  
**Date:** 2026-07-25 (Kuwait)  
**Production restored to:** Kuwait first-client foundation freeze `73cccafdf4ae6cc57a68bb3d69197110b9413864a0ec361e8a021c8cb0812267`  
**Stop:** do **not** mark document journey production-green; do **not** begin another project until owner decides the next remediation.

---

## Verdict

Promotion of the exact staging-green document-journey artifact was **aborted**. Core document-journey and most frozen regressions passed on production, but the **frozen interviews production matrix failed** after the approved staging dashboard dist overwrote `/var/www/wathefni-dashboard` and dropped interview a11y copy keys that were present in the prior production dashboard. Production was rolled back. Health **200**. Staging-green pin for `4be5298e…` remains valid and **untouched**.

---

## Exact defect

| Item | Detail |
|---|---|
| Gate | `ops/interviews-production-matrix.py` → `a11y_copy_keys_present` |
| Result during promote | **FAIL** (44/45) |
| Cause | Staging document-journey dashboard bundle `dashboard-CdJ5YPdj.js` replaced production `dashboard-CfaEseRj.js` |
| Missing strings after promote | `interviewNotesNotScorecard`, `interviewPanelPlaceholder`, `Free-text notes are not scorecards`, `الملاحظات النصية ليست بطاقة تقييم` |
| Prior production bundle | Still contains those keys (sha256 `a6975562d73e7fede043cc55870fd2263f7935c293a644f2c83f4871f7e2a79a`) |
| After rollback | Interviews matrix **45/45** PASS (`interviews-production-matrix-20260725T043613Z.json`) |

The approved artifact’s dashboard dist is **not** a safe drop-in over the current production dashboard without regressing Interviews UX copy that the frozen Interviews suite asserts.

### Secondary gate (not the rollback trigger, but recorded)

| Suite | Result during promote |
|---|---|
| `assistant-a0a3-production-matrix` | **FAIL** `RankingError('Ranking requires voyage-4-large, got voyage-4')` — process env omitted systemd embedding model pin; treat as harness/env until re-proven with service-equivalent `WATHEFNI_EMBEDDING_MODEL=voyage-4-large` |

Candidates-c3 and ranking-r0r3 were not completed in the failed window (ACK flags not set on first pass).

---

## Artifact identity (verified before deploy)

| Item | Value |
|---|---|
| Staging-green / attempted pin | `4be5298e769576cb691b750ec9513c190d32adb13e9bddf2ebb004f694ab85d7` |
| Staging evidence | `ops/KUWAIT_PILOT_DOCUMENT_JOURNEY_STAGING_GREEN.md` |
| Journey module | `78befeb08da1f94dca5cb10f3bc6514d4799a6ad71e383fda0eeb50b294f99f4` |
| Surgically patched `app.py` | `b266a0d24ff49659fb8966b03818f32f2e12fc76cf659ea28514ad8a447d7602` |
| `ops/lib/doc_type_map.py` | `448d0946807db1ef493fa5bde8825798ead9fa0b0d63ff182b000e4bf6d510f0` |
| Unrelated dirty tree | **not** included |

---

## Backup and rollback

| Item | Value |
|---|---|
| Backup | `/opt/wathefni/backups/pre-kuwait-doc-journey-prod-20260725T043106Z` |
| DB dump SHA256 | `566024d90cf63df089a3b97ae6c1e70d62983a16cfa5e5ea8d4a97e3332a73d5` |
| Rollback command | `bash /opt/wathefni/backups/pre-kuwait-doc-journey-prod-20260725T043106Z/ROLLBACK.sh` |
| Note | Initial generated `ROLLBACK.sh` had broken absolute paths (`/code/app.py`); corrected to `$SNAP/code/...` and executed manually. **DB dump was not restored** (code+dashboard rollback sufficient). |

### Restored production state

| Check | Result |
|---|---|
| `app.py` | `8d2e880aafcf1b639dbb53e3ef8544e013e01546ce8be7e6b491cbba29f22ab2` (foundation-green) |
| `kuwait_pilot_document_journey.py` | **absent** |
| Dashboard | `dashboard-CfaEseRj.js` restored; a11y keys present |
| `/opt/wathefni/production/last-green.sha256` | `73cccafd…` |
| Document-journey production pins | **removed** |
| Production health | **200** |
| Interviews re-qualify after rollback | **45/45** |
| Synthetic companies (`KWDOCPRD*` / offers / boundary / interviews markers) | **0** |
| Post-rollback smoke residue `DOCUPLOADTESTCO` governed rows | purged → **0** versions / **0** events |
| Additive empty `governed_document_*` tables | remain (safe under foundation-green code) |

---

## Migration proof (pre-rollback window)

| Step | Result |
|---|---|
| Additive `governed_document_*` schema while old prod code ran | **PASS** (`PRE_SCHEMA_OLD_CODE_SAFE`, health 200) |
| Old prod code during schema window | foundation `app.py` `8d2e880a…`, no journey module |
| Tables left after rollback | `governed_document_*` remain (additive, ignored by restored code) — **no destructive drop performed** |

---

## What passed before the failing gate (during promote window)

| Suite | Result |
|---|---|
| Document journey production matrix | **68/68** — evidence `…/kuwait-pilot-document-journey-production-20260725T043213Z.json` |
| Kuwait first-client foundation production matrix | **53/53** |
| Offers/Hiring | **38/38** |
| Optional-module-boundary | **301/301** |
| `smoke-test-onboarding-seeding.py` | **38/38** |
| `smoke-test-compliance-actions.py` | **31/31** |
| `smoke-test-document-upload.py` | **25/25** |
| `smoke-test-document-hub.py` | **18/18** |
| Dashboard `npm test` | **49/49** |
| Employee capability + `tsc` | GREEN / PASS |
| offer-lifecycle / offer-hire-override smokes | PASS |
| ranking-result-presentation | **219/219** |
| reports-v1 | **80/80** |
| assessments-on-off | **39/39** |
| Interviews (during promote) | **44/45 FAIL** ← blocking |
| Assistant A0–A3 (during promote) | **33/34 FAIL** (voyage env) |

Document-journey matrix itself proved upload, HR review authority, renewal/versioning, OCR non-authority, EN/AR, tenant isolation, audit, and zero `KWDOCPRD*` residue before rollback.

---

## Residual limitations / next owner decision

1. **Do not re-promote `4be5298e…` as-is** until the dashboard artifact includes **both** document-journey PostHire UX **and** the frozen Interviews a11y / Arabic copy keys asserted by `interviews-production-matrix.py`.  
2. Rebuild / re-freeze a new staging-green artifact that merges those surfaces, re-qualify staging, then seek a fresh owner approval for the **new** SHA.  
3. Additive `governed_document_*` tables may remain empty/unused on production until a successful promote; they were proven safe under foundation-green code.  
4. Staging remains green on `4be5298e…`; production remains on foundation freeze `73cccafd…`.  
5. **Stop. Do not begin another project** from this failure report alone.

---

## Explicit non-claims

No production-green claim for the Kuwait pilot document journey. No PACI/MOI/PAM verification. No automatic Kuwait legal compliance.
