# Kuwait Pilot Document Journey — Production Green / Frozen

**Status:** production-green · **Kuwait pilot document journey frozen**  
**Promoted artifact:** exact reconciled staging-green only  
**Artifact SHA:** `6018796d265c1a8d77e3bd880849b8e65f627003dc20ca544403db426d2097e1`  
**Do not reuse:** `4be5298e769576cb691b750ec9513c190d32adb13e9bddf2ebb004f694ab85d7`  
**Source:** staging reconciliation green (`ops/KUWAIT_PILOT_DOCUMENT_JOURNEY_DASHBOARD_RECONCILIATION_STAGING_GREEN.md`)  
**Next:** wait for owner instruction — **do not begin another project**

---

## Verdict

Guarded production promotion of the reconciled Kuwait pilot document-journey staging-green artifact is **green**. Interviews a11y copy and document-journey PostHire UX are both present on `/var/www`. Document journey **68/68**, Interviews **45/45**, foundation **53/53**, Offers/Hiring **38/38**, optional-module-boundary **301/301**, smokes and frozen pre-hiring suites green, zero synthetic residue, production health **200**. **Stop.**

**Do not claim automatic Kuwait legal compliance. Do not claim PACI / MOI / PAM verification.**

---

## Promoted identifiers

| Item | Value |
|---|---|
| Staging-green artifact SHA | `6018796d265c1a8d77e3bd880849b8e65f627003dc20ca544403db426d2097e1` |
| Staging evidence | `ops/KUWAIT_PILOT_DOCUMENT_JOURNEY_DASHBOARD_RECONCILIATION_STAGING_GREEN.md` |
| Production pin file | `/opt/wathefni/production/kuwait-pilot-document-journey-production-green.json` |
| Production last-green | `/opt/wathefni/production/last-green.sha256` |
| Artifact record | `/opt/wathefni/production/kuwait-pilot-document-journey-artifact.sha256` |
| Host | `root@76.13.63.68` |
| Backend | `wathefni-orchestrator.service` · `127.0.0.1:8010` · health **200** |
| Database | `wathefni` · marker `wathefni-production-isolation-v1` |
| Delivery during quals | process-local `WATHEFNI_DELIVERY_MODE=dry_run` only |
| Service delivery pin | **unset** (not globally dry_run) |
| Explicit backup | `/opt/wathefni/backups/pre-kuwait-doc-journey-recon-prod-20260725T045039Z` |
| DB dump sha256 | `d3a0235db0a2e427627093d7648acc6490022d8ca862b620bb49c1d77d3b5df5` |
| Journey matrix evidence | `/opt/wathefni/production/evidence/kuwait-pilot-document-journey-production-20260725T045227Z.json` |
| Interviews evidence | `/opt/wathefni/orchestrator/ops/interviews/interviews-production-matrix-20260725T045150Z.json` |
| Promoted at | `2026-07-25T04:54:52Z` (approx; see pin JSON) |

### Rollback command

```bash
snap=/opt/wathefni/backups/pre-kuwait-doc-journey-recon-prod-20260725T045039Z
bash "$snap/ROLLBACK.sh"
# Restores prior app.py, removes journey module, restores prior last-green.sha256,
# restores prior /var/www dashboard from dashboard-public.tgz, restarts service.
# DB restore ONLY if required (destructive):
#   set -a; . /root/.openclaw/secrets/postgres.env; set +a
#   pg_restore --clean --if-exists -d "$WATHEFNI_DATABASE_URL" "$snap/wathefni.dump"
```

---

## Artifact identity

- Staging `last-green.sha256` / artifact record == `6018796d…` before promote  
- Contained staging product SHAs matched freeze  
- Staging dist `dashboard-Cibp23sm.js` == `c3562ee1…`  
- Forbidden pin `4be5298e…` was **not** reused  
- Unrelated dirty worktree files were **not** deployed  

### Per-file SHA256 (production == reconciled staging-green)

| File | SHA256 |
|---|---|
| `kuwait_pilot_document_journey.py` | `78befeb08da1f94dca5cb10f3bc6514d4799a6ad71e383fda0eeb50b294f99f4` |
| `ops/lib/doc_type_map.py` | `448d0946807db1ef493fa5bde8825798ead9fa0b0d63ff182b000e4bf6d510f0` |
| `app.py` (foundation-green + journey hooks only) | `b266a0d24ff49659fb8966b03818f32f2e12fc76cf659ea28514ad8a447d7602` |
| `PostHire.tsx` | `e73d7027e6fc9a443d8a1f8fbae0ce055d010f7d189fc94cd56b9aaf64d00cf9` |
| `api.ts` | `2b767b3b25facd8aebd624f5a8b3da177b2cc57eed6e21fd93f734ef37057f01` |
| `recruitingLifecycle.ts` | `09d5135fc0ec325b21858b191f49a58b58dae01e706271f013abecaa825f639e` |
| `dashboard-Cibp23sm.js` | `c3562ee18f36e59367445e912739dc77ea1871e3c45081fb5109fa2a1137f085` |

Employee-mobile source SHAs remain as in reconciliation freeze.

---

## Backup and migration proof

| Step | Result |
|---|---|
| Production backup | `/opt/wathefni/backups/pre-kuwait-doc-journey-recon-prod-20260725T045039Z` |
| Dump verified | sha256 `d3a0235d…` · `pg_restore --list` OK |
| Rollback script | `$snap/ROLLBACK.sh` with correct `$SNAP/code/...` paths |
| Pre-code additive schema | `ensure_document_journey_schema` via `/tmp` module only |
| Old prod code during pre-schema | app still `8d2e880a…`; journey module **absent**; health **200** (`PRE_SCHEMA_OLD_CODE_SAFE`) |
| Tables present before code cutover | `governed_document_versions`, `governed_document_events` |
| Exact deploy | staging-green bytes only; dashboard keys re-verified on `/var/www` before start |

---

## Deployed files

| Path | Role |
|---|---|
| `/opt/wathefni/orchestrator/kuwait_pilot_document_journey.py` | Governed versions, HR review, employee renew, dual-write |
| `/opt/wathefni/orchestrator/app.py` | Journey hooks on foundation-green base |
| `/opt/wathefni/orchestrator/ops/lib/doc_type_map.py` | Canonical `residence` + legacy aliases |
| `/var/www/wathefni-dashboard/` | Reconciled dist with journey UX + Interviews a11y |
| `/opt/wathefni/apps/wathefni-dashboard/src/lib/recruitingLifecycle.ts` | Exact restored Interviews copy source |
| `/opt/wathefni/production/employee-mobile-artifact/` | Frozen employee documents / i18n sources |

---

## Restored interview copy proof

Production `/var/www` bundle contains (asserted post-deploy and by Interviews matrix):

- `interviewNotesNotScorecard` / `interviewPanelPlaceholder`
- EN: `Free-text notes are not scorecards. Submit structured feedback separately.`
- AR: `الملاحظات النصية ليست بطاقة تقييم. أرسل الملاحظات المنظمة بشكل منفصل.`
- `قائمة المقابلات` / `interviewAgenda`

Interviews production matrix: **45/45** PASS · gate `a11y_copy_keys_present` PASS.

---

## Document-journey UX proof

Production dashboard bundle contains:

- `HR reviewed`, `Mark as HR reviewed`, `not PACI`
- `Reject — re-upload`, `Enter dates`
- canonical `residence`
- API actions `approve` / `reject` / `request_reupload` / `correct_metadata` (matrix + `api.ts`)

Journey matrix proved: residence/work-permit compliance handoff, employee `/documents` renewal, OCR non-authoritative until HR confirm, no PACI/MOI/PAM claim wording, versioning/reminder reset, tenant isolation, append-only audit.

---

## Full qualification results

| Suite | Result |
|---|---|
| Document journey production matrix | **68/68** PASS |
| Interviews production matrix | **45/45** PASS |
| Dashboard `npm test` | **49/49** PASS |
| Kuwait first-client foundation | **53/53** PASS |
| Offers/Hiring | **38/38** PASS |
| Optional-module-boundary | **301/301** PASS |
| Onboarding seeding smoke | **38/38** PASS |
| Compliance actions smoke | **31/31** PASS |
| Document upload smoke | **25/25** PASS |
| Document hub smoke | **18/18** PASS |
| Offer lifecycle / hire-override smokes | PASS |
| Employee capability smoke | GREEN |
| Candidates C3 | **49/49** PASS |
| Ranking R0–R3 | **55/55** PASS |
| Ranking result presentation | **219/219** PASS |
| Reports v1 | **80/80** PASS |
| Assistant A0–A3 (service embedding env) | **79/79** PASS |
| Assessments ON/OFF | **39/39** PASS |
| Production health | **200** · service **active** |

### Ops harness note (not product artifact)

First document-journey production run failed only `artifact_pin_file` because the ops matrix still expected superseded `4be5298e…` while the live pin was already `6018796d…`. Updated **ops harness only** (`kuwait-pilot-document-journey-*-matrix.py` `ARTIFACT=` constant). Product artifact SHAs remained `6018796d…`. Re-run: **68/68**.

---

## Cleanup proof

| Check | Result |
|---|---|
| `KWDOCPRD*` companies | **0** |
| Governed versions/events after sweep | **0** |
| Smoke residue `DOCUPLOADTESTCO` governed rows | purged → **0** |
| Offers / boundary / interviews / assessments synthetic companies | **0** |
| Production health after cleanup | **200** |

---

## Explicit non-introductions (proved)

Production does **not** introduce:

- PACI / MOI / PAM government verification  
- automatic legal-compliance claims  
- leave-law enforcement / EOS / PIFSS  
- statutory OT multipliers / fine calculations / payroll payments  
- Saudi / UAE / other unqualified country packs  

---

## Residual limitations

- Employee-mobile is frozen as source artifact + API-proven; native Expo OTA/store binary publish remains outside this VPS host.  
- Sync OCR remains optional; HR metadata entry covers OCR-unavailable.  
- HR mobile remains review-oriented; primary mutate path is dashboard.  
- Classifier bucket codes may still say `needs_review`/`valid`; HR-facing labels map to Pending HR review / HR reviewed.  
- Service delivery is **not** globally dry_run; quals used process-local dry_run only.  
- Additive `governed_document_*` tables are live and used by journey code.

---

## Freeze

1. Kuwait pilot document journey marked **production-green**.  
2. Exact artifact **frozen**: `6018796d265c1a8d77e3bd880849b8e65f627003dc20ca544403db426d2097e1`.  
3. Production pin written: `/opt/wathefni/production/kuwait-pilot-document-journey-production-green.json`.  
4. **Stop.**  
5. **Do not begin another project.**
