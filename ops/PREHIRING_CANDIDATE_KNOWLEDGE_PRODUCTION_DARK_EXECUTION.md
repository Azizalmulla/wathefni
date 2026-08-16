# Pre-hiring Candidate Knowledge — WATHEFNI Production-Dark Execution

Date: 2026-07-26 (UTC) / 2026-07-27 (Asia/Kuwait)  
Prerequisite: Phase 8 final production-fidelity gate **GO**  
Host: `root@76.13.63.68`  
Database: `wathefni` (production only)  
Stamp: `20260726T213640Z`  
Local commit (modules): `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2`

Evidence:
- Remote: `/opt/wathefni/production-evidence/candidate-knowledge-dark/20260726T213640Z/`
- Local: `ops/evidence/candidate-knowledge-production-dark/20260726T213640Z/`
- Backup / rollback: `/opt/wathefni/backups/production-pre-ck-dark-20260726T213640Z/`

---

## Verdict

| Gate | Result |
|---|---|
| Production-dark sequence (backup → deploy → schema → backfill → shadow → canary → kill/restore → safe posture) | **PASS** |
| Live tools / live Ranking reader / external tenants / Role Profiles | **still OFF** |
| Blockers (tenant leak, identity false-bind, audit bypass, forbidden mutation, held Ranking admission) | **none** |

### Explicit GO / NO-GO

| Decision | Result |
|---|---|
| WATHEFNI-only **production-dark** (this task) | **GO / PASS** |
| Controlled WATHEFNI **live exposure** (normal-user tools or live Ranking cutover) | **NO-GO** |
| External tenants | **NO-GO** |
| Role Profiles | **NO-GO** |

**Live exposure remains NO-GO** because this run intentionally kept Voyage/semantic OFF in production, indexed only the current ready canonical CV set (n=2), and did not authorize normal-user tool registration or Ranking reader cutover. A separate owner authorization is required before any live exposure.

---

## 1) Production backup, artifact, config, schema, flags, health, rollback

| Item | Value |
|---|---|
| Predeploy health | **200** |
| DB | `wathefni` (preflight refused staging) |
| Orchestrator | `/opt/wathefni/orchestrator` |
| `app.py` sha256 (pre) | `b4a9a4b032abee27e75ec6b4fc382b0797889a935af4d6529af29bf6574a7dd5` |
| `action_registry.py` sha256 (pre) | `b7992797bd6db01dd2461c3803e80089e10de91248cddaeecf1f8a2cba8d2bfb` |
| DB dump | `…/db.dump` (custom format, ~5.3 MB) + `db.restore-list` |
| Rollback script | `…/ROLLBACK.sh` (**executable**) |
| Flags file | `/opt/wathefni/var/ck-flags.production.env` |
| Drop-in | `wathefni-orchestrator.service.d/candidate-knowledge.conf` |
| Worker unit | `wathefni-ck-index.service` |

### Exact production flags (final safe posture)

```
WATHEFNI_CANDIDATE_KNOWLEDGE=on
WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS=WATHEFNI
WATHEFNI_CANDIDATE_KNOWLEDGE_SCHEMA=on
WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS=off
WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS=off
WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER=off
WATHEFNI_CK_SHADOW_TOOLS_ENABLED=0
WATHEFNI_CK_RANKING_SHADOW=0
WATHEFNI_CK_EMBEDDINGS_ENABLED=1
WATHEFNI_CK_VOYAGE_ENABLED=0
WATHEFNI_CK_SEMANTIC_SEARCH=0
CK_WORKER_CONCURRENCY=1
WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
WATHEFNI_ALLOW_NON_STAGING_DB=1
WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
WATHEFNI_ENV=production
```

### Deployed artifact (CK modules; not registered in live registry)

Deployed into `/opt/wathefni/orchestrator/`: all `candidate_knowledge_*.py`, `ranking_evidence_adapter.py`, `ranking_evidence_shadow.py`, `candidate_record_state_policy.py`.

Live registry check: `search_candidates` / `get_candidate_knowledge` / `compare_candidates` = **absent**.

---

## 2) Deploy with all live cutovers OFF

- CK code deployed; orchestrator restarted; health **200**.
- Tools OFF, Ranking reader OFF, tenants pinned to `WATHEFNI`, workers initially OFF.
- Existing production behavior unchanged at deploy boundary (health + registry clean).

### Incident fixed mid-run (isolation bug)

Initial worker loop loaded staging postgres/flags after process start (`postgres.staging.env` + staging `ck-flags.env`), so the production unit claimed **staging** jobs while production queue stayed pending.

**Fix shipped in this execution:** `candidate_knowledge_index_worker.load_runtime_env()` is environment-aware (`WATHEFNI_ENV=production` loads only production postgres + production flags). Worker now prints `connected_db` / `expected_db` at start and refuses mismatch.

Also aligned production Phase-3 store column names:
- `assessment_attempts.reviewed_by_user_id AS reviewed_by`
- `candidate_interviews` without non-existent `cancelled_at`

And taught the worker to load `src_*` indexer follow-up jobs via `document_version_id` (indexer always enqueues an `indexed:` marker after write).

---

## 3) Additive CK schema (idempotent)

Applied twice via `PostgresCandidateKnowledgeIndexStore.ensure_schema()`.

Tables present:
- `candidate_knowledge_chunks`
- `candidate_knowledge_index_jobs`
- `candidate_knowledge_access_events`

---

## 4) Health + unchanged behavior

| Checkpoint | Result |
|---|---|
| Health after deploy | **200** |
| Health after backfill / shadow / canary | **200** |
| Health after kill switch | **200** |
| Health after restore | **200** |
| Health at safe posture | **200** |
| Live CK tools in registry | **absent** |

---

## 5–7) WATHEFNI workers, bounded backfill, verification

### Workers

- Enabled only for tenant `WATHEFNI`
- Concurrency **1**
- Embeddings: **mock** (`WATHEFNI_CK_VOYAGE_ENABLED=0`)

### Bounded backfill (current valid canonical evidence only)

| Metric | Value |
|---|---|
| Eligible current ready CVs | **2** |
| Completed backfill jobs | **2** |
| Current chunks | **10** (3 + 7 by app) |
| Poison job | **1** → retries → **dead_letter** after 5 attempts |
| Invalidation probe | **PASS** (3 → 0 → 3 restored) |
| Tenant isolation | **PASS** (0 non-WATHEFNI chunks; foreign tenant list empty) |
| Zero mutation guards | **PASS** |
| Audit fail-closed | **PASS** |

Apps indexed:
- `imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT` → version `44cfbc94-9220-4d11-8af7-fd7823376079`
- `imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT` → version `c36c0291-ceec-4697-91d8-02e4c108d5b5`

**Accepted limitation:** production currently has only two current ready canonical CV text versions; backfill covered **all** of them (bounded by reality, not by artificial sample).

---

## 8–9) Owner-only shadow tools + old-vs-new

Owner shadow runtime only (`ShadowToolRuntime`; **not** live registry).

| Check | Result |
|---|---|
| `get_candidate_knowledge` | PASS (`text_omitted=true`) |
| `search_candidates` | PASS (total=2, mode=`lexical_only`) |
| `compare_candidates` | PASS (no auto-winner) |
| Old vs new AI recruiter | PASS — deltas classified as `expected_authority_enrichment` (canonical CV version + coverage disclosure) |

---

## 10) Ranking shadow

| Check | Result |
|---|---|
| Ranking shadow | **PASS** |
| Classification | `expected_authority_difference` |
| Denial | `held_or_job_ranking_ineligible` |
| Unexplained deltas | **[]** |
| Side effects / live reader | OFF |

Indexed import apps are `needs_role` (held): Ranking correctly denied. No unexplained score delta.

---

## 11) Owner canary C1–C10

| Case | Status | Notes |
|---|---|---|
| C1 exact CV + shadow get/search | PASS | version pin + text omitted |
| C2 surname ambiguity | PASS | `candidate_ambiguous` |
| C3 held | PASS | readable; Ranking denied |
| C4 long chunk | PASS | 8468 chars |
| C5 WhatsApp/manual gap | PASS | `canonical_cv=not_recorded` |
| C6 restricted/governance | PASS | governance table absent on this DB; name-only still fail-closed |
| C7 compare | PASS | no winner |
| C8 Ranking shadow | PASS | expected held denial |
| C9 kill/restore | PASS | see §12 |
| C10 audit fail-closed | PASS | |

Plus: tenant isolation PASS; zero-mutation PASS; registry clean PASS.

---

## 12) Kill switch, rollback, restore, health

| Proof | Result |
|---|---|
| Workers stop (`INDEX_WORKERS=off` + `systemctl stop`) | inactive |
| Health while stopped | **200** |
| Prior recruiter path (registry clean) | PASS |
| Workers restore | active |
| Health after restore | **200** |
| `ROLLBACK.sh` present + executable | PASS |
| DB dump retained for restore | PASS |
| Full module-removal ROLLBACK executed | **No** (would uninstall dark install; proven by script presence + kill/flag/registry drill instead) |

---

## 13) Safe posture (returned)

| Control | Final |
|---|---|
| Live tools | **OFF** |
| Live Ranking reader | **OFF** |
| Shadow tools flag | **0** |
| Ranking shadow flag | **0** |
| Index workers | **OFF** + unit **disabled** |
| Voyage / semantic | **OFF** |
| Tenants | `WATHEFNI` only |
| Health | **200** |

---

## Voyage calls and cost

| Metric | Value |
|---|---|
| Voyage during production-dark backfill | **OFF** |
| Document calls | **0** |
| Query calls | **0** |
| Estimated cost | **$0.00** |
| PII-targeted provider calls | **0** |

Staging Phase-8 fidelity Voyage gate remains the quality reference; production intentionally did not burn Voyage on the 2-CV dark backfill.

---

## Audit / tenant / identity / held-state / zero-mutation proof

| Proof | Result |
|---|---|
| Audit fail-closed on forced write failure | PASS |
| Cross-tenant chunks | 0 |
| Name-only exact bind | blocked (`candidate_ambiguous`) |
| Held (`needs_role`) Ranking admission | denied |
| Lifecycle / communication / Ranking / identity mutation APIs | raise; counters unused |
| Live tool registration | absent |

---

## Accepted limitations

1. Only **2** current ready canonical CV text versions exist in WATHEFNI production today; dark backfill covered all of them.
2. WhatsApp / manual pipeline gaps remain disclosed (`not_recorded` / incomplete coverage) where present.
3. Production Voyage/semantic left **OFF**; index projection used mock embeddings.
4. Full destructive `ROLLBACK.sh` module uninstall was not executed; kill-switch + flag restore + executable rollback artifact + DB dump were proven instead.

---

## Final decision

**Production-dark execution: PASS / GO.**

**Controlled WATHEFNI live exposure: NO-GO** (requires a new explicit owner authorization after production Voyage semantic indexing of current canonical evidence and a live-exposure runbook). Do **not** enable normal-user live tools, live Ranking cutover, external tenants, or Role Profiles from this report.
