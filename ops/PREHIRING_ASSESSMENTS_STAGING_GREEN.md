# Pre-Hiring Assessments — Staging Green (stop before production)

**Status:** staging-green  
**Production:** **not promoted / untouched**  
**Source of truth:** `/tmp/wathefni-c3-local` (closed local remediation tree)  
**Claw trail mirror:** `claw/ops/PREHIRING_ASSESSMENTS_STAGING_GREEN.md`  
**Delivery:** `WATHEFNI_DELIVERY_MODE=dry_run`  
**Scope:** Isolated staging qualification only. Do **not** run `ops/deploy.sh production`.

---

## Verdict

Assessments Tenant ON/OFF staging qualification is **green**. Staging runs the remediated Assessments contracts with zero residue on `ASSESSON`/`ASSESSOFF`, frozen-module regressions all pass, delivery wording never treats `sent`/`send_accepted` as confirmed delivery, and production fingerprints/health are unchanged. **Stop here — do not promote.**

Documented residuals (invitation recovery worker absent; legacy WhatsApp reminder still writes `sent`) are classified as staging/ops residuals, not reopen triggers.

---

## Identifiers

| Item | Value |
|---|---|
| Staging artifact SHA | `240416fe3d1abfb48beff9a10f0f1a7eff8868dd0d5af83d75aaaf2e1f83190d` |
| Staging-green file | `/opt/wathefni/staging/last-green.sha256` |
| Host | `root@76.13.63.68` |
| Backend | `wathefni-orchestrator-staging.service` · `127.0.0.1:8011` |
| Database | `wathefni_staging` · marker `wathefni-staging-hr2-isolation-v1` |
| Dashboard dist | `/opt/wathefni/staging/dashboard-dist` |
| Pre-promote backup | `/opt/wathefni/backups/staging-pre-assessments-onoff-20260724T012904Z` |
| Backup orch tgz sha256 | `3f012d11338c27523b0b8fe5c1b0a5ca4c804f754d7fd16c8df0ab5690038b78` |
| Backup dash tgz sha256 | `267d9ab999f14ae034d02abefd472265d217e6b8daf2201a7f96e599c486ab15` |
| ON/OFF evidence | `/opt/wathefni/staging/orchestrator/ops/assessments/assessments-on-off-staging-matrix-20260724T020012Z.json` |
| Owner search markers | **`ASSESSON`** / **`ASSESSOFF`** |

---

## Promote path

1. Fingerprint freeze of `/tmp/wathefni-c3-local` remediation tree.
2. Staging-only pre-backup under `/opt/wathefni/backups/staging-pre-assessments-onoff-20260724T012904Z`.
3. Added `ops/assessments-on-off-staging-matrix.py` and wired into `ops/deploy.sh` `deploy_staging`.
4. Synced frozen tree → `/opt/wathefni/staging/orchestrator` (+ dashboard dist); schema + `migrate-assessments-cleanup1.py`; restarted staging.
5. Ran the full `deploy_staging` gate sequence on staging (smoke → C3 → Ranking R0–R3 → presentation → Reports V1 → Assistant A0–A3 → Assessments ON/OFF).
6. Recorded artifact SHA into `/opt/wathefni/staging/last-green.sha256`.
7. **Stopped before production.**

Staging-revealed product gates fixed in the frozen tree before green (allowed reopen):

- `assessment_pending_predicate` expression bug (`la.` vs `latest_assessment.`) in overview/apps lateral join.
- Ranking R0–R3 matrix + presentation pin updates for explicit `assessment_selection`.
- Smoke expectations for assigned-only pending.

---

## Fingerprints (staging vs production)

| Path | Production | Staging |
|---|---|---|
| `app.py` | `52fe37c329df34c5945194a2f5ef793d4ffe98fa5b023f8e11bc7c8f70d037e9` | `30d8fd130fa304adeafdb5aa99b1d822e92e5a37ebfac54719c4d6659f147cb5` |
| `prehire_overview.py` | `7e7a7e323c2f6dece1014a43e0f8ac0f9dd6890a789c5eaefc4ec565cd435819` | `9a99959ca6672cb8f961daa8601df3a20f59982820da593fda2f2c64274c8380` |
| `candidate_ranking.py` | `f288c917058ed5c9621861030fa79d4f0cdba84d74a229b43eb612bf4a57c4f9` | `9b8a54f19d10da7ddd8c1ef8b5207833cde4aa1cfc71e3b72d47bae1f3efd8c8` |
| `ranking_result_presentation.py` | `0c8297a88d5760d83bd4dc8d62e0cf85f59dbb6073f31d438cd65aff902c2bbe` | `8d2f3c9f10931e2d528dc98282c1bfec892301e3838e7c6b0b2b13ff953be64b` |
| `assessment_lifecycle.py` | `2e2f9bffa184b2c6c3c8567cf29efd8d9e9e733e9b76130a7bde8922dc99c2e3` | `d531133bb60d94fe1bb1f4af2fb2a5ab3f1bf1235d1369c5a342d670e842ec7b` |
| `assessment_service.py` | `75343310d3ccc7f101b82469932280b0ff62229f35476b14d48463c7b1e54644` | **SAME** |
| `reports_v1.py` | `15e3f9ca64eb6f90c67f0fa17f87539335d731643785c57a335c4fa859e25692` | `d7f52f2a082ff1ad5979e642ce44bf892f3dd41ea3a979f7c92f5b975c147a41` |

Production untouched proof (after promote):

- `app.py` sha unchanged: `52fe37c3…037e9`
- `GET http://127.0.0.1:8010/health` → 200 · `application_environment=production`
- Staging `GET http://127.0.0.1:8011/health` → 200 · `application_environment=staging`

---

## Pass / fail matrix

| Suite | Result | Evidence |
|---|---|---|
| Staging smoke (incl. cleanup1 29/29) | **PASS** | `ALL STAGING SMOKE CHECKS PASSED` @ 2026-07-24T01:58:13Z |
| Assessments cleanup1 | **29/29 PASS** | inside staging-smoke |
| Candidates C3 schema | **18/18 PASS** | `ops/reports/candidates-c3-schema-verify.json` |
| Candidates C3 matrix | **49/49 PASS** | `ops/reports/candidates-c3-staging-matrix.json` |
| Ranking R0–R3 | **57/57 PASS** | `ops/reports/ranking-r0r3-staging-matrix-20260724T015825Z.json` |
| Ranking presentation | **213/213 PASS** | `ops/assistant/ranking-result-presentation-staging-matrix.json` |
| Reports V1 | **80/80 PASS** | `ops/reports/reports-v1-staging-matrix-20260724T015828Z.json` |
| Assistant A0–A3 | **79/79 PASS** | `ops/assistant/assistant-a0a3-staging-matrix.json` |
| Assessments Tenant ON/OFF | **35/35 PASS** | `ops/assessments/assessments-on-off-staging-matrix-20260724T020012Z.json` |
| Cleanup zero residue (`ASSESSON`/`ASSESSOFF`) | **PASS** | matrix `cleanup_zero_residue` |
| Production untouched | **PASS** | hashes + health above |

---

## Assessments ON/OFF gates (summary)

**ON (`ASSESSON` = `pre_hiring` + `assessments`):**

- Create + dry-run send → `intentionally_skipped` (truthful; not delivered)
- Terminal application send blocked
- Unassigned candidate has no attempt / not forced into pending definition
- Public link `needs_begin`; HTML has Begin + EN/AR RTL markers
- Default Ranking policy keeps assessment unused without approved selection
- Assistant discovers `send_assessment`

**OFF (`ASSESSOFF` = `pre_hiring` only after history seed):**

- Historical completed attempt/scores/reports preserved after module delete
- Open pending link after disable → `module_disabled` / unavailable
- Overview omits assessment pending; Reports omit assessment metrics/export
- Ranking forced unused; mobile omits assessments capability
- Payload word-scan zero assessment owner wording
- Assistant hides assessment tools
- Cross-tenant token blocked

**Delivery wording:**

- `prehire_report_status_label("sent"|"send_accepted")` → `"Send accepted"` (no “delivered” / “confirmed”)

---

## Documented residuals (not reopen)

| Residual | Classification | Evidence |
|---|---|---|
| Legacy WhatsApp reminder path still writes `delivery_status='sent'` | documented residual | matrix `legacy_whatsapp_sent_path_documented`; labels never treat as delivered |
| Invitation committed without successful send — no recover worker | documented residual | matrix `invitation_recovery_residual_no_worker`; `recover_syms=[]` |
| Expiry sweep / projection repair (from local close-out) | staging/ops residual | out of scope this phase |
| Pre-backup DB dump file was empty (`wathefni_staging.dump` 0 bytes) | ops note | orch+dash tgz captured; re-dump before any future prod promote if needed |

---

## Out of scope / stop line

- **Do not** run `ops/deploy.sh production`
- **Do not** enable Product-2 live authoring
- **Do not** reopen local product scope for residuals above unless a claimed-fixed gate regresses
- Next human decision: production promote plan (separate), only after explicit approval

---

## Close checklist

- [x] Staging service active on `:8011`
- [x] Artifact sha recorded in `last-green.sha256`
- [x] Tenant ON/OFF matrix all required gates PASS
- [x] Marker tenants leave zero residue
- [x] Frozen regressions PASS
- [x] Delivery wording truthful for `sent`/`send_accepted`
- [x] Production hashes + health unchanged
- [x] This STAGING_GREEN written (tmp ops + claw/ops)
- [x] Production **not** invoked
