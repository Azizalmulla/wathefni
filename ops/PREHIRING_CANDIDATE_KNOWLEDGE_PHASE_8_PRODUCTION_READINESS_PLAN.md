# Pre-hiring Candidate Knowledge — Phase 8 Production-Readiness Plan

Date: 2026-07-26  
Prerequisite: Phase 7 local + staging **GO**  
`ops/PREHIRING_CANDIDATE_KNOWLEDGE_PHASE_7_LOCAL_AND_STAGING_QUALIFICATION.md`  
Authority: `ops/PREHIRING_CANONICAL_CANDIDATE_KNOWLEDGE_ARCHITECTURE_AND_IMPLEMENTATION_PLAN.md`

**This document is planning only.**  
Do **not** deploy production, start owner canary, expose live tools, cut over Ranking, enable external tenants, mutate lifecycle/communication, or begin Role Profiles in this task.

---

## Verdict (this task)

| Decision | Result |
|---|---|
| Phase 8 plan complete | **YES** |
| Execute staging service install | **NOT IN THIS TASK** (next authorized execution) |
| Production-dark execution | **NO-GO until Stage A–E gates PASS** |
| Live tools / Ranking cutover / external tenants / Role Profiles | **NO-GO** |

---

## Objective

Make Candidate Knowledge production-ready by installing it into the **real staging service** with production-identical runtime, then freeze a WATHEFNI-only production-dark runbook. Execution is a separate owner-authorized task after every gate below is **PASS**.

---

## Flag contract (default OFF everywhere)

Canonical production flags (empty tenant allowlist = nobody):

| Flag | Default | Purpose |
|---|---|---|
| `WATHEFNI_CANDIDATE_KNOWLEDGE` | `off` | Master module entitlement |
| `WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS` | `` | Comma allowlist (`WATHEFNI` only until external GO) |
| `WATHEFNI_CANDIDATE_KNOWLEDGE_SCHEMA` | `off` | Permit additive CK index DDL / ensure-schema |
| `WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS` | `off` | Index / invalidate workers |
| `WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS` | `off` | Live AI recruiter tool registration |
| `WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER` | `off` | Live RankingEvidenceAdapter cutover |
| `WATHEFNI_CK_SHADOW_TOOLS_ENABLED` | `0` | Shadow invoke path only (no normal-user exposure) |
| `WATHEFNI_CK_RANKING_SHADOW` | `0` | Dual-path Ranking compare; no write path change |
| `WATHEFNI_CK_EMBEDDINGS_ENABLED` | `0` | Embedding subsystem |
| `WATHEFNI_CK_VOYAGE_ENABLED` | `0` | Real Voyage provider (requires key + Stage D PASS) |
| `WATHEFNI_CK_SEMANTIC_SEARCH` | `0` | Semantic/hybrid mode in search (blocked until Voyage PASS) |
| `VOYAGE_API_KEY` | unset | Secret; never logged |

Kill switches (independent; any one restores safe posture):

1. `WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS=off` — stop indexing  
2. `WATHEFNI_CK_SEMANTIC_SEARCH=0` / `WATHEFNI_CK_VOYAGE_ENABLED=0` — lexical/structured only  
3. `WATHEFNI_CK_SHADOW_TOOLS_ENABLED=0` + `WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS=off` — no model-facing CK tools  
4. `WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER=off` + `WATHEFNI_CK_RANKING_SHADOW=0` — Ranking uses existing evidence path  
5. `WATHEFNI_CANDIDATE_KNOWLEDGE=off` or clear `…_TENANTS` — full tenant kill  

Disabling semantic must preserve exact reads + lexical search. Disabling tools/Ranking must not delete canonical data or index tables.

---

## Rollout order (strict)

### Stage A — Staging service fidelity install

**Goal:** Same runtime planned for production.

1. Backup staging orchestrator + `pg_dump` schema-only of CK tables.  
2. Deploy CK modules into `/opt/wathefni/staging/orchestrator` (not `/tmp`).  
3. Add systemd unit `wathefni-ck-index-staging.service` (low concurrency, e.g. `CK_WORKER_CONCURRENCY=2`).  
4. Set flags:  
   - `WATHEFNI_CANDIDATE_KNOWLEDGE=on`  
   - `WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS=WATHEFNI,SYN_CK_P8`  
   - `WATHEFNI_CANDIDATE_KNOWLEDGE_SCHEMA=on`  
   - `WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS=on`  
   - tools / Ranking live / Voyage / semantic = **off**  
   - shadow tools / Ranking shadow = **off** until Stage B green  
5. Apply additive DDL idempotently (`candidate_knowledge_chunks|index_jobs|access_events`).  
6. Restart staging orchestrator + CK worker; health **200**.  
7. Prove: worker start/stop clean; ensure-schema idempotent; no tool registration in live `action_registry`; no outbound messages.

**Exit:** staging service install **PASS** or **BLOCKER**.

### Stage B — Production-like candidate matrix (staging)

Synthetic + fixture corpus only. Required shapes:

| Case class | Must prove |
|---|---|
| Arabic / English / bilingual PDF | lexical hit; coverage honest; no identity via embeddings |
| Long CV (>12k chars) | tail evidence retrievable by focus question |
| Scanned / image / two-column / tables | gap disclosed if extraction incomplete |
| Incomplete (no phone/email) | unknown stays unknown |
| Held (`needs_role` / import) | searchable + readable; contact/lifecycle/Ranking denied |
| Restricted / deletion-completed | denied / metadata-only per policy |
| Multi-application same phone | exact `app:` bind; sibling aggregation only via existing authority |
| Cross-channel email / WhatsApp / manual | WhatsApp/manual incompleteness disclosed |
| Open identity review | unresolved; no model merge |
| Mariam vs other Almulla | no surname bind |

Run: concurrent `search_candidates` + `get_candidate_knowledge` + `compare_candidates` under shadow flag **on** for synthetic actor only (not normal staging users).

**Exit:** matrix **PASS**; any identity/tenant/audit/mutation fail = **BLOCKER**.

### Stage C — 50k synthetic scale + chaos (staging)

Pool: **50,000** synthetic candidates in `SYN_CK_P8` (or equivalent), indexed by real worker.

Concurrent load (minimum 10 min steady):

- search (lexical; semantic only if Stage D already PASS)  
- exact knowledge reads  
- compare (2–5 refs)  
- worker crash / restart  
- Voyage outage (force fail → labeled `retrieval_degraded` / lexical)  
- audit write failure → evidence denied  
- stale index + invalidation (CV supersede / identity correction)  
- dead-letter enqueue + recovery  
- kill-switch + rollback drill  

**Thresholds (must record):**

| Metric | PASS bar |
|---|---|
| Needle recall @50k (lexical) | ≥ 0.95 on planted set (≥50 needles) |
| False-positive cross-tenant | **0** |
| Search p95 (lexical, warm) | ≤ 2.0 s |
| Exact read p95 | ≤ 500 ms |
| Compare p95 (≤5) | ≤ 1.5 s |
| Index lag (current CV → searchable) | ≤ 5 min p95 under load |
| Invalidation visibility | **0** current hits after invalidate |
| Audit success for returned evidence | **100%** (else deny) |
| Dead-letter recovery idempotent | **PASS** |
| Forbidden mutations | **0** |
| Health during chaos | **200** (or documented brief restart window) |
| Unexplained Ranking shadow deltas | **0** material unexplained |

**Exit:** scale/chaos **PASS** or **FAIL** / **BLOCKER**.

### Stage D — Real Voyage qualification (before semantic)

Enable only on staging with explicit owner key install:

```
WATHEFNI_CK_EMBEDDINGS_ENABLED=1
WATHEFNI_CK_VOYAGE_ENABLED=1
WATHEFNI_CK_SEMANTIC_SEARCH=0   # keep off until D PASS
```

Model pin: `voyage-4-large` (doc + query). Dimensions: as configured (no silent switch).

Record: model, input type, dimensions, doc/query call counts, latency p50/p95, cost estimate, AR/EN/bilingual recall vs lexical, mock-vs-real deltas.

Forbidden Voyage inputs: contacts, identity-review alternatives, private notes, assessment answer bodies, full unrestricted CV dumps beyond redacted chunks.

**Voyage PASS bars:**

| Metric | Bar |
|---|---|
| Arabic paraphrase recall (planted) | ≥ 0.80 |
| English paraphrase recall | ≥ 0.85 |
| Bilingual query useful hit@10 | ≥ 0.80 |
| Provider failure disclosure | always labeled; never silent “equivalent” |
| PII leakage to provider logs | **0** |

Only after **PASS**: set `WATHEFNI_CK_SEMANTIC_SEARCH=1` on staging allowlisted tenants.

### Stage E — Ranking shadow + tool shadow (staging, no live cutover)

```
WATHEFNI_CK_SHADOW_TOOLS_ENABLED=1
WATHEFNI_CK_RANKING_SHADOW=1
WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS=off
WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER=off
```

- Shadow tools: synthetic/owner actor only; not normal user registry.  
- Ranking: dual-path compare; classify deltas (`expected_evidence_improvement` | `expected_authority_difference` | `bug` | `missing_canonical_evidence` | `unexplained`).  
- Any **unexplained** material delta = **FAIL**.  
- Held exclusion + no ranking writes from CK reads = mandatory.

### Stage F — Production-dark runbook (plan freeze; do not execute here)

WATHEFNI-only, after Stages A–E **PASS** + separate owner auth:

1. **Read-only dark** — deploy code + schema flag on; workers off; tools/Ranking off.  
2. **Additive schema preflight** on production (idempotent; no backfill yet).  
3. **Bounded WATHEFNI backfill** — current canonical CV versions only; low concurrency; coverage dashboard.  
4. **Shadow tools** — owner/synth actor; no normal recruiter exposure.  
5. **Ranking shadow** — compare only; live reader off.  
6. **Owner canary** — fixed case list (below); kill-switch proof; restore proof.  
7. **Final release decision** — separate GO for tools and/or Ranking reader (independent).

External tenants remain off (`…_TENANTS=WATHEFNI` only).

---

## Owner canary cases (production-dark; later execution)

| ID | Case | Expect |
|---|---|---|
| C1 | Exact `app:` WATHEFNI candidate with current email CV | grounded knowledge; version pin |
| C2 | Mariam-style surname ambiguity | no false bind |
| C3 | Held `needs_role` | search/read OK; Ranking/contact denied |
| C4 | Long CV tail fact | chunk retrieval hits |
| C5 | WhatsApp/manual gap candidate | coverage incomplete disclosed |
| C6 | Restricted / open identity review | deny or unresolved; no leak |
| C7 | Compare 2–3 candidates | no auto winner |
| C8 | Ranking shadow vs legacy | no unexplained delta |
| C9 | Kill switch tools/workers | immediate safe posture; health 200 |
| C10 | Audit deny on forced audit failure | no model evidence |

---

## Monitoring (staging + future production-dark)

Metrics:

- index lag; job queue depth; dead-letter count  
- chunk state mix (`current` / `invalidated` / `restricted`)  
- search mode mix (`hybrid` / `lexical_only` / `retrieval_degraded` / `index_not_ready`)  
- Voyage call count, latency, error rate, estimated cost  
- exact-read / search / compare latency p50/p95  
- audit write success rate  
- model-facing evidence payload size  
- mutation counters (must stay 0 for CK paths)

Alerts (page / block canary):

- any cross-tenant assertion  
- restricted/invalidated chunk returned as current  
- audit failure with evidence still returned  
- unexplained Ranking shadow delta  
- index lag > threshold  
- unexpected mutation count > 0  
- Voyage error spike with undisclosed degradation  

Dashboards: one staging CK board; production-dark board reused with tenant filter `WATHEFNI`.

---

## Rollback & restore

| Action | Effect | Data loss |
|---|---|---|
| Tools kill | restore prior recruiter tools | none |
| Ranking reader kill | restore existing Ranking inputs | none |
| Workers kill | stop new index writes | none |
| Semantic kill | lexical/structured remain | none |
| Master/tenant clear | CK disabled for tenant | none |
| Drop CK index tables | removes search projection only | rebuildable from canonical |

Restore drill: disable → prove prior path → re-enable workers → reindex sample → prove parity.  
**Never** rewrite canonical CV/facts/lifecycle tables as rollback.

---

## Final PASS / FAIL / BLOCKER criteria

| Class | Examples | Effect |
|---|---|---|
| **BLOCKER** | tenant leak; identity false bind; audit bypass; forbidden mutation; held Ranking admission; PII to Voyage; live tools on without GO | stop; no Stage F |
| **FAIL** | recall/latency below bar; unexplained Ranking delta; worker non-recovery; health non-200 outside restart window | fix; re-run stage |
| **ACCEPTED_LIMITATION** | WhatsApp/manual pipeline incomplete (disclosed); non-WATHEFNI tenants off | document; may proceed |
| **PASS** | stage thresholds met; kill switch proven; zero forbidden mutations | advance |

Production-dark execution **GO** only if:

- Stage A–E all **PASS** (or accepted limitations explicitly owner-signed)  
- Voyage **PASS** before semantic on  
- Kill switch + restore drill **PASS**  
- External tenants / live tools / Ranking reader / communication / lifecycle / Role Profiles remain **OFF**  
- Separate written owner authorization for production-dark  

---

## Execution checklist (next authorized task — not this one)

- [ ] Stage A staging service install  
- [ ] Stage B production-like matrix  
- [ ] Stage C 50k + chaos  
- [ ] Stage D real Voyage  
- [ ] Stage E shadow tools + Ranking shadow  
- [ ] Freeze Stage F production-dark runbook + owner sign-off  
- [ ] **Stop** before production-dark unless new authorization  

Evidence target (when executed): `ops/evidence/candidate-knowledge-phase8/`

---

## GO / NO-GO (this task)

| Item | Decision |
|---|---|
| Phase 8 plan | **GO** (accepted as executable plan) |
| Start Stage A now | **NO** (requires separate execution authorization) |
| Production-dark deploy | **NO-GO** |
| Canary start | **NO-GO** |
| Live tools / Ranking cutover / external tenants / Role Profiles | **NO-GO** |

Phase 8 planning complete. Stop.
