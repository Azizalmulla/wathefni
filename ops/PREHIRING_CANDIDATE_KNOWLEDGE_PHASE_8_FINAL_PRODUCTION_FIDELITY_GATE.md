# Pre-hiring Candidate Knowledge — Phase 8 Final Production-Fidelity Gate

Date: 2026-07-26  
Prerequisite staging A–E: `ops/PREHIRING_CANDIDATE_KNOWLEDGE_PHASE_8_STAGING_EXECUTION_AND_QUALIFICATION.md`  
Host: `root@76.13.63.68` · DB: `wathefni_staging`  
Production changes: **none**  
Live tools / Ranking reader: **OFF**  
Production-dark / canary started: **no**

Evidence: `ops/evidence/candidate-knowledge-phase8-fidelity/`

---

## Verdict

| Gate | Result |
|---|---|
| Real index-worker / backfill (3,000 jobs via queue + indexer) | **PASS** |
| Expanded real Voyage (156 queries / 120 docs) | **PASS** |
| Blockers (tenant / identity / audit / PII / held Ranking / live cutover) | **none** |

### Final unconditional GO/NO-GO

**GO** for WATHEFNI-only production-dark **execution** (qualification complete).

This task does **not** start production-dark. Starting still requires a separate explicit owner authorization command. Until then:

- production deploy / canary = **NO**
- live tools / Ranking cutover / external tenants / Role Profiles = **NO**

---

## 1) Real index-worker / backfill qualification

### Method

- Tenant: `SYN_CK_P8F` (synthetic only)
- Enqueued **3,000** jobs into `candidate_knowledge_index_jobs`
- Processed **only** by `wathefni-ck-index-staging.service` + `CandidateKnowledgeIndexer` + Postgres index store
- Payload via `source_key=synjson:…` (no bulk SQL insert path for this subset)
- Embeddings: **mock** for the 3k worker run (`WATHEFNI_CK_VOYAGE_ENABLED=0`) to avoid burning Voyage on bulk; Voyage cost projected separately
- Worker runtime: orchestrator venv Python (Voyage SDK available when enabled)
- Concurrency during test: **4**
- Poison jobs: every 50th (empty payload) → retries → **dead letter**

### Pause / resume / restart

| Drill | Result |
|---|---|
| Stop worker mid-queue → completed count stable | PASS |
| Start worker → progress resumes | PASS |
| Restart worker mid-flight → progress continues | PASS |
| Dead-letter poison jobs | **60/60** PASS |

### Measured results

| Metric | Value |
|---|---|
| Jobs completed | **2,940** (all non-poison) |
| Dead-letter jobs | **60** |
| Current chunks written | **11,760** |
| Effective throughput | **5.653 jobs/s** |
| RSS peak (worker) | **32.7 MB** |
| CPU peak (worker) | **37.7%** |
| Queue-wait lag p95 | **517.5 s** |
| Health | **200** |
| Live tools | off |
| Ranking reader | off |

**Lag note:** jobs were batch-enqueued then drained. `lag_p95` is **oldest-pending queue age from enqueue time**, not single-job CPU time. Steady drain rate (~5.7/s) is the backfill planning signal.

### Voyage call estimate (if worker embeddings were real)

| Estimate | Value |
|---|---|
| Document calls | ~8,820 |
| Approx tokens | ~352,800 |
| Approx cost | **~$0.042** |

### Projected WATHEFNI backfill duration (at measured throughput)

| Scale | Projection |
|---|---|
| 1,000 candidates | **~3.0 minutes** |
| 5,000 candidates | **~14.7 minutes** |
| 20,000 candidates | **~0.98 hours** |

Assumes similar CV size mix, concurrency 4, mock or cached embedding cost profile; real Voyage adds provider latency/cost on top.

**Worker/backfill gate: PASS**

---

## 2) Expanded real Voyage evaluation

### Method

- Model: `voyage-4-large` (document + query), dimensions **1024**
- Corpus: **120** planted docs (EN finance/HR, AR finance/HR, bilingual, long-tail, hard-negative tech)
- Queries: **156** (synonyms, paraphrases, Arabic, bilingual, long-CV markers, hard negatives)
- No emails, phones, passwords, identity-review alternatives, or private notes in Voyage inputs
- Indexed via production `CandidateKnowledgeIndexer` (not SQL bypass)

### Results

| Metric | Value | Bar | Status |
|---|---|---|---|
| Overall recall@10 | **0.9359** | ≥ 0.80 | PASS |
| English recall@10 | **0.9891** | ≥ 0.85 | PASS |
| Arabic recall@10 | **0.9167** | ≥ 0.80 | PASS |
| Bilingual recall@10 | **0.8250** | ≥ 0.80 | PASS |
| Hard-negative FP rate | **0.0000** | ≤ 0.20 | PASS |
| Query latency p95 | **274 ms** | ≤ 5000 ms | PASS |
| Document calls | 120 | — | — |
| Query calls | 156 | — | — |
| Est. tokens | ~20.6k | — | — |
| Est. cost | **~$0.00247** | — | — |
| PII / restricted leakage | **0** | 0 | PASS |

**Voyage gate: PASS**  
Staging semantic flag left **on** for allowlisted synthetic tenants only after this PASS. Live tools remain **off**.

---

## Safety posture after gate

```
WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS=off
WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER=off
WATHEFNI_CK_SHADOW_TOOLS_ENABLED=0
WATHEFNI_CK_RANKING_SHADOW=0
WATHEFNI_CK_VOYAGE_ENABLED=1
WATHEFNI_CK_SEMANTIC_SEARCH=1
TENANTS=WATHEFNI,SYN_CK_P8,SYN_CK_P8F,SYN_CK_P8V
```

Health **200**. Production untouched.

---

## Prior gaps closed

| Prior Phase 8 limitation | This gate |
|---|---|
| 50k used bulk SQL bypass for most rows | **Closed** for 3k via real queue + indexer + worker |
| Voyage bench was small planted set | **Closed** with 156-query / 120-doc AR/EN/bilingual bench |

---

## Final decision

**Unconditional qualification GO** for WATHEFNI-only production-dark execution planning/start authorization.

**Do not execute production-dark in this task.**  
Next step is a separate owner-authorized production-dark runbook execution only.
