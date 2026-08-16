# Wave D6B — Production deploy (cv_extraction repair)

**Stamp:** `20260801T174712Z`  
**Mode:** Production deploy of local-qualified D6B only  
**Local qualifier:** `ops/evidence/waveD-phase6b-cv-extraction-repair-20260801T172536Z/` (LOCAL PASS)  
**Host:** `root@76.13.63.68`  
**Remote evidence:** `/opt/wathefni/production-evidence/waveD-phase6b-cv-extraction/20260801T174712Z`  
**Backup / rollback:** `/opt/wathefni/backups/production-pre-waveD-phase6b-cv-extraction-20260801T174712Z`

---

## Verdict: **PASS**

| Gate | Result |
|---|---|
| Health orch + dashboard 200 | **PASS** |
| Rich PDF CV completes extraction + promotes email | **PASS** |
| Rich DOCX CV same path (full success) | **PASS** |
| Conflict/Held uses `held_identity_review_scan_clean` (not `intake_document_not_clean`) | **PASS** |
| Weak/opaque Held + warning + `extraction_soft_failed` | **PASS** (attempts=1) |
| Retries bounded / idempotent (re-drain=0; Message-ID dup) | **PASS** |
| No duplicate candidate / document / application | **PASS** (1/1/1) |
| No indefinite pending extraction | **PASS** (open=0) |
| D6A durable→Held preserved (opaque + conflict warned Held) | **PASS** |
| Tenant isolation (unknown recipient ignored) | **PASS** |
| Quarantine clean path | **PASS** (all `safety_state=clean`) |
| Explicit admit unchanged (all `needs_role`) | **PASS** |
| Quotas / allowlist / mailbox sync posture | **PASS** (WATHEFNI-only, sync=off) |
| Cleanup (proof apps archived; continuous Postmark default only) | **PASS** |
| Rollback verified + D6B restored | **PASS** |
| External tenants / post-hiring | **Not enabled / not started** |
| Remaining D6 GA job | **Classified synthetic; left untouched** |

---

## Production SHAs (final)

| Artifact | SHA-256 |
|---|---|
| `orchestrator/app.py` | `27c7e2f0d8fe110b2683a0173b29122c5293411a64a71fcb865cdab8d079e790` |
| `orchestrator/inbound_cv_authority.py` | `8cf1759371a2a3d4f1f42125e1ba960ae34db23f6c173f657aa1532cd95a4fab` |

Pre-deploy (rollback target = post-D6A):

| Artifact | SHA-256 |
|---|---|
| `app.py` | `661dd600f83d97f5b78cd88928f1edf1ed549c5d4700e8c601db621650863070` |
| `inbound_cv_authority.py` | `8e1b843f211c73a2c917e514d9caa9da05b52a5d96eda6d31e2bcb57d5affd92` |

Source: `verify/sha-final.txt`, `verify/sha-before.txt`, `rollback/`

---

## Remaining D6 GA job classification

| Field | Value |
|---|---|
| Job ID | `90887c19-8492-4fcc-87bd-a3992f856dee` |
| Status at classify | `dead_letter` (was the prior `remaining_open=1`; no longer pending/retrying) |
| Attempts | 5 |
| Provider Message-ID | `d6ga-08343d30-kill` |
| Subject / label | `wave_d6_ga_proof CV` / `wave_d6_ga_proof-08343d30-general` |
| Synthetic | **Yes** |
| Action | **Preserve — do not cancel** (confirmed synthetic but not in the cancelled-28 set and not authorized for cancellation in this deploy) |

Evidence: `before/d6ga-job-classification.json`  
Post-deploy recheck: still `dead_letter`, untouched (`cleanup/final-intakes.txt`)

Open `cv_extraction` at classify / after gate: **0**

---

## Deployed changes (qualified D6B only)

- Split `intake_document_not_clean` / `durable_clean_scan_authority_missing` / `identity_binding_not_authorized`
- `held_review_extraction_authorized` → Held review extraction under `held_identity_review_scan_clean`
- Soft-complete terminal quality/OCR/`file_not_found` as `extraction_soft_failed`
- Semantic upsert `provider=none` / `model=unembedded` fallback
- Identity enrichment (name/phone fill for conflict detection)

`durable_email_ingress.py` unchanged in this deploy.

---

## PDF / DOCX evidence + timing

Gate: `verify/prod-d6b-gate.json` (passed=true)

### Rich PDF
| Metric | Value |
|---|---|
| Auth mode | `accepted_identity_binding` |
| Promoted email | `d6b.rich.e36f24a5@example.com` |
| Extraction | 9113 ms |
| End-to-end | 12425 ms |
| Held stage timings (ms) | validation 938 · scan 769 · identity 389 · accepted-prepare 441 · held-mat 60 |

### Rich DOCX
| Metric | Value |
|---|---|
| Auth mode | `accepted_identity_binding` |
| Full success | **true** (`extraction_status=ok`) |
| Extraction | 3877 ms |
| End-to-end | 6203 ms |

### Conflict / opaque
| Path | Auth mode | Notes |
|---|---|---|
| Conflict | `held_identity_review_scan_clean` | warned Held; not `intake_document_not_clean` |
| Opaque | `held_identity_review_scan_clean` | `extraction_soft_failed` / `low_quality_text`; attempts=1 |

---

## Cleanup proof

- Gate archived **4** proof apps (`needs_role` → `import_archived`)
- Active WATHEFNI intakes after cleanup: **1** continuous Postmark default `2493b577-09e3-45c2-b923-b0c382c251df`
- Open `cv_extraction`: **0**
- D6 GA dead_letter job preserved

Source: `cleanup/final-intakes.txt`, gate `cleanup` block

---

## Rollback verification

1. Executed `rollback/ROLLBACK.sh` → restored pre-D6B SHAs; D6B symbols absent (`verify/rollback-symbol-check.txt`)
2. Orch briefly unreachable during cutover (`rollback_orch=000`); dashboard stayed 200 — then orch 200
3. Re-deployed D6B files; orch/dash **200**; final SHAs match deploy; symbols present
4. `wathefni-inbound-intake-worker.timer` restored (`active`)

---

## Kept canary posture (live)

- `WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI`
- `WATHEFNI_MAILBOX_SYNC=off`
- External tenants disabled; post-hiring not started

---

## Evidence path

Local: `ops/evidence/waveD-phase6b-cv-extraction-deploy-20260801T174712Z/`  
Remote: `/opt/wathefni/production-evidence/waveD-phase6b-cv-extraction/20260801T174712Z/`
