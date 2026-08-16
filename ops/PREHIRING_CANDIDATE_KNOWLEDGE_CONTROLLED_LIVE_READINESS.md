# Pre-hiring Candidate Knowledge — WATHEFNI Controlled-Live Readiness

Date: 2026-07-26 (UTC) / 2026-07-27 (Asia/Kuwait)  
Prerequisite: `ops/PREHIRING_CANDIDATE_KNOWLEDGE_PRODUCTION_DARK_EXECUTION.md` **PASS**  
Host: `root@76.13.63.68`  
Database: `wathefni` (production only)  
Stamp: `20260726T220131Z`

Evidence:
- Remote: `/opt/wathefni/production-evidence/candidate-knowledge-controlled-live/20260726T220131Z/`
- Local: `ops/evidence/candidate-knowledge-controlled-live/20260726T220131Z/`

---

## Verdict

| Gate | Result |
|---|---|
| Clean restart + DB/flags identity | **PASS** |
| Real Voyage reindex (`voyage-4-large`) of 2 current CVs | **PASS** |
| Lexical / hybrid / semantic search | **PASS** |
| Owner-allowlisted canary tools (not normal users) | **PASS** |
| Ranking shadow only (live reader OFF) | **PASS** |
| Kill switch + restore | **PASS** |
| Safe posture restored | **PASS** |
| Blockers | **none** |

### Explicit GO / NO-GO

| Decision | Result |
|---|---|
| Controlled-live **readiness** (owner/admin canary path) | **GO / PASS** |
| Normal WATHEFNI **recruiter exposure** (live `action_registry` tools) | **NO-GO** |
| Live Ranking reader cutover | **NO-GO** |
| External tenants / Role Profiles | **NO-GO** |

Normal-user tools were **not** enabled in this task. Live Ranking reader remained **OFF**.

---

## Exact production flags (final safe posture)

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
WATHEFNI_CK_VOYAGE_ENABLED=1
WATHEFNI_CK_SEMANTIC_SEARCH=1
WATHEFNI_CK_OWNER_CANARY_ACTORS=ck-owner-canary
CK_WORKER_CONCURRENCY=1
WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
WATHEFNI_ALLOW_NON_STAGING_DB=1
WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
WATHEFNI_ENV=production
```

Worker unit: **inactive** + **disabled**. Health: **200**.  
Registry: `search_candidates` / `get_candidate_knowledge` / `compare_candidates` = **absent**.

During owner canary only, temporary flags were:
- `WATHEFNI_CK_SHADOW_TOOLS_ENABLED=1`
- `WATHEFNI_CK_RANKING_SHADOW=1`
- `WATHEFNI_CK_OWNER_CANARY_ACTORS=ck-owner-canary`
- `WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS=off` (hard pin)
- `WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER=off` (hard pin)

---

## 1–2) Clean restart + database identity proof

| Check | Result |
|---|---|
| Orchestrator restart | health returned **200** |
| Worker start `connected_db` | `wathefni` |
| Worker start `expected_db` | `wathefni` |
| `WATHEFNI_ENV` | `production` |
| Tenants loaded | `WATHEFNI` only (no `SYN_*` staging leak) |
| Staging DB/config mismatch refuse | **PASS** (`ck_worker_db_mismatch` when expected=`wathefni_staging`) |
| Production flags file | `/opt/wathefni/var/ck-flags.production.env` |

---

## 3–4) Real Voyage reindex

| Item | Value |
|---|---|
| Model | `voyage-4-large` |
| Eligible current ready CVs | **2** |
| Current chunks after reindex | **10** |
| Chunks with vectors | **10/10** |
| `embedding_provider` | `voyage` |
| `embedding_model` | `voyage-4-large` |

Apps:
- `imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT` → `44cfbc94-9220-4d11-8af7-fd7823376079`
- `imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT` → `c36c0291-ceec-4697-91d8-02e4c108d5b5`

### Fix applied in this run

Postgres upsert `ON CONFLICT` previously updated `embedding` but not `embedding_provider` / `embedding_model`, so Voyage rewrites could remain labeled `mock`. Fixed in `candidate_knowledge_postgres_index_store.py` before the successful reindex.

---

## Voyage calls and cost

| Metric | Value |
|---|---|
| Approx document calls (chunk proxy) | **10** |
| Query calls (harness) | **5** |
| Approx tokens | ~7.7k |
| Estimated cost | **~$0.00092** |
| PII emails in current chunks | **0** |

---

## 5) Search / invalidation / audit / tenant / health

| Gate | Result |
|---|---|
| Lexical search | **PASS** (`lexical_only`, total=1) |
| Hybrid search | **PASS** (`hybrid`, total=1) |
| Semantic/hybrid paraphrase probe | **PASS** (`hybrid`, total=2) |
| Invalidation → restore with Voyage | **PASS** (3→0→3 voyage chunks) |
| Audit fail-closed | **PASS** |
| Tenant isolation | **PASS** (0 foreign chunks) |
| Zero mutation guards | **PASS** |
| Health | **200** |

---

## 6–8) Owner canary + Ranking shadow

Owner tools used **shadow runtime + actor allowlist** only. Normal recruiter actor denied.

| Case | Status | Notes |
|---|---|---|
| C1 exact CV | PASS | version pin |
| C1 owner get | PASS | `text_omitted=true` |
| C1 owner search | PASS | mode=`hybrid` |
| Owner allowlist denies normal user | PASS | |
| C2 surname ambiguity | PASS | `candidate_ambiguous` |
| C3 held | PASS | Ranking denied |
| C4 long chunk | PASS | 8468 chars |
| C5 gap disclosure | PASS | `not_recorded` |
| C6 identity no false bind | PASS | via C2 |
| C7 compare | PASS | no auto-winner |
| C8 Ranking shadow | PASS | expected held denial; live reader OFF |
| C10 audit fail-closed | PASS | |
| Registry no live tools | PASS | `TOOLS=off` |
| Ranking reader off | PASS | |
| PII email absent | PASS | |

---

## 9) Kill switch + restore

| Proof | Result |
|---|---|
| Workers stop | inactive |
| Health while stopped | **200** |
| Registry still clean | PASS |
| Workers restore | active |
| Journal `connected_db=wathefni` | PASS |
| Health after restore | **200** |

---

## 10) Safe posture

Returned to:
- live tools **OFF**
- live Ranking reader **OFF**
- shadow tools **0**
- Ranking shadow **0**
- workers **off + disabled**
- Voyage/semantic credentials/config retained idle (`VOYAGE=1`, `SEMANTIC=1`) for future owner runs only when shadow is explicitly re-enabled
- health **200**

---

## Final decision

**Controlled-live readiness: GO / PASS** for the owner/admin canary path on WATHEFNI.

**Normal WATHEFNI recruiter exposure: NO-GO.**  
Requires a separate owner authorization to register live tools for normal users and/or cut over the live Ranking reader. This task did not do either.
