# Pre-hiring Candidate Knowledge — Phase 8 Staging Execution and Qualification

Date: 2026-07-26  
Plan: `ops/PREHIRING_CANDIDATE_KNOWLEDGE_PHASE_8_PRODUCTION_READINESS_PLAN.md`  
Commit (local modules): `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2`  
Host: `root@76.13.63.68`  
Database: `wathefni_staging` only  
Production changes: **none**  
Production canary: **not started**

Evidence: `ops/evidence/candidate-knowledge-phase8/`

---

## Verdict

| Stage | Result |
|---|---|
| A — Staging service install | **PASS** |
| B — Production-like matrix | **PASS** |
| C — 50k scale + chaos | **PASS** |
| D — Real Voyage | **PASS** |
| E — Shadow tools + Ranking shadow | **PASS** |

| Decision | Result |
|---|---|
| WATHEFNI-only production-dark **execution** | **GO** (requires separate owner authorization to start) |
| Production deploy / canary in this task | **NO-GO / not started** |
| Live tools / Ranking cutover / external tenants / Role Profiles | **NO-GO** |

Blockers: **0**

---

## Staging artifact and configuration

| Item | Value |
|---|---|
| Orchestrator | `/opt/wathefni/staging/orchestrator` |
| CK worker | `wathefni-ck-index-staging.service` |
| Flags file | `/opt/wathefni/staging/var/ck-flags.env` |
| Orchestrator drop-in | `…/wathefni-orchestrator-staging.service.d/candidate-knowledge.conf` |
| Backup | `/opt/wathefni/staging/backups/ck-phase8-20260726T203227Z` |
| Postgres | `wathefni_staging` + `pgvector` |
| Python (Voyage) | `/opt/wathefni/orchestrator/.venv` + `voyageai` |
| Live `action_registry` CK tools | **absent** |

### Flags during Stage E qualification

```
WATHEFNI_CANDIDATE_KNOWLEDGE=on
WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS=WATHEFNI,SYN_CK_P8
WATHEFNI_CANDIDATE_KNOWLEDGE_SCHEMA=on
WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS=on
WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS=off
WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER=off
WATHEFNI_CK_SHADOW_TOOLS_ENABLED=1
WATHEFNI_CK_RANKING_SHADOW=1
WATHEFNI_CK_EMBEDDINGS_ENABLED=1
WATHEFNI_CK_VOYAGE_ENABLED=1
WATHEFNI_CK_SEMANTIC_SEARCH=1   # enabled only after Stage D PASS
```

### Post-qualification safe posture (applied)

Shadow invoke flags returned to `0`. Live tools/Ranking reader remain `off`. Workers/schema/Voyage/semantic remain on for staging allowlisted tenants only. Health **200**.

---

## Stage A — Install

- Backup orchestrator CK modules + CK schema dump.
- Deployed CK + Ranking adapter modules into staging orchestrator (not `/tmp`).
- Additive schema applied idempotently (`chunks`, `index_jobs`, `access_events`).
- Systemd worker installed; start/stop proven.
- Orchestrator restarted; health **200**.
- CK tools **not** registered in live `action_registry`.

**PASS**

---

## Stage B — Production-like matrix

| Gate | Status |
|---|---|
| Mariam surname ambiguous / not Faisal | PASS |
| Multi-application sibling aggregation | PASS |
| Email current CV | PASS |
| WhatsApp/manual gap disclosed (`not_recorded`) | PASS |
| Long CV tail chunk | PASS |
| Held readable, not rankable | PASS |
| Restricted no contact / deletion denied | PASS |
| Tenant search isolation | PASS |
| Arabic lexical | PASS |
| Concurrent shadow tools | PASS |
| Compare no auto-winner | PASS |

**PASS** — no blockers.

---

## Stage C — 50k scale + chaos

| Metric | Bar | Observed | Status |
|---|---|---|---|
| Needle recall @50k | ≥ 0.95 | **1.00** (50/50) | PASS |
| Cross-tenant FP | 0 | **0** | PASS |
| Search p95 | ≤ 2000 ms | **94.1 ms** | PASS |
| Exact read p95 | ≤ 500 ms | **102.4 ms** | PASS |
| Compare p95 | ≤ 1500 ms | **44.5 ms** | PASS |
| Invalidation visibility | 0 current | **0** | PASS |
| Audit fail-closed | deny | **PASS** | PASS |
| Dead-letter | PASS | **PASS** | PASS |
| Worker drain | ≥50 jobs | **51** | PASS |
| Kill switch + restore | PASS | stop→start | PASS |
| Health under load | 200 | **200** | PASS |
| Forbidden mutations | 0 | **0** | PASS |
| Load duration | 10 min | **600 s** | PASS |

Index method (disclosed):

- **200** candidates via production `CandidateKnowledgeIndexer` + Postgres store
- **49,800** via bulk SQL into the same CK tables/GIN path
- Total current chunks after run: ~50.6k (`SYN_CK_P8`)
- Index wall time: **88.35 s** (sample indexer 23.66 s + bulk)

**PASS** with accepted method disclosure (full 50k single-connection indexer was too slow for the window; worker + indexer fidelity proven separately).

---

## Stage D — Real Voyage

| Field | Value |
|---|---|
| Model | `voyage-4-large` (document + query) |
| Dimensions | 1024 |
| Document calls | 5 |
| Query calls | 3 |
| Est. tokens | ~660 |
| Est. cost | **~$0.000079** |
| EN paraphrase hit@10 | **PASS** |
| AR paraphrase hit@10 | **PASS** |
| Bilingual hit@10 | **PASS** |
| Provider failure disclosure | **PASS** |
| PII to Voyage | **none** (redacted skill/experience text only) |
| `WATHEFNI_CK_SEMANTIC_SEARCH` after PASS | **1** |

**PASS**

---

## Stage E — Shadow tools + Ranking shadow

| Gate | Status |
|---|---|
| `search_candidates` shadow | PASS |
| `get_candidate_knowledge` omits full CV | PASS |
| `compare_candidates` no winner | PASS |
| Live tools off | PASS |
| Live Ranking reader off | PASS |
| Unexplained Ranking deltas | **0** PASS |
| Classified delta | `legacy_fallback` → `expected_authority_difference` |
| Held Ranking denied | PASS |
| Ranking writes | **0** PASS |
| Access audit events | PASS |

**PASS**

---

## Kill switch / restore / zero-mutation

- Workers kill (`INDEX_WORKERS=off` + systemd stop) and restore proven in Stage C.
- Mutation helpers raise for lifecycle / communication / ranking / identity / production.
- No outbound messages, Job/lifecycle/identity mutations observed.
- Live tools and Ranking cutover never enabled.

---

## Accepted limitations

1. WhatsApp/manual CV pipelines remain incomplete (honest `not_recorded` coverage).
2. 50k corpus used hybrid indexer-sample + bulk SQL (not 50k serial upserts).
3. External tenants remain off (`…_TENANTS=WATHEFNI,SYN_CK_P8` only).
4. Normal staging users never received live CK tool registration.

---

## GO / NO-GO for WATHEFNI-only production-dark

**GO** to begin WATHEFNI-only production-dark **only after** a separate explicit owner authorization.

Still forbidden without that authorization:

- production deploy
- production canary
- live AI recruiter tools
- Ranking reader cutover
- external tenants
- Role Profiles
- communication / lifecycle mutations

Phase 8 Stages A–E complete. Production-dark and canary **not** started in this task.
