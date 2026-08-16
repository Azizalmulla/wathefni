# Pre-hiring Candidate Knowledge — Final Controlled Live Release and Freeze

Date: 2026-07-26 (UTC) / 2026-07-27 (Asia/Kuwait)  
Prerequisite: `ops/PREHIRING_CANDIDATE_KNOWLEDGE_CONTROLLED_LIVE_READINESS.md` **accepted**  
Host: `root@76.13.63.68`  
Database: `wathefni` (production only)  
Stamp: `20260726T221015Z`

Evidence:
- Remote: `/opt/wathefni/production-evidence/candidate-knowledge-final-live/20260726T221015Z/`
- Local: `ops/evidence/candidate-knowledge-final-live/20260726T221015Z/`
- Backup: `/opt/wathefni/backups/production-pre-ck-final-live-20260726T221015Z/` (+ `ROLLBACK.sh`, `db.dump`)

---

## Final verdict

| Gate | Result |
|---|---|
| Fresh production backup + artifact/config hashes | **PASS** |
| CK workers WATHEFNI-only + health 200 | **PASS** |
| Small allowlist live tools | **PASS** |
| Final real-user tests (AR/EN/bilingual, exact, compare, long-CV, held/restricted/ambiguous/incomplete, audit, tenant, zero-mutation) | **PASS** |
| Monitoring (latency, errors, Voyage, audit, freshness, hallucinations, mutations) | **PASS** |
| Expand tools to authorized WATHEFNI recruiters | **PASS** |
| Ranking shadow + live Ranking reader gates | **PASS** (reader **ON**) |
| Kill switch + restore after live exposure | **PASS** |
| External tenants OFF | **PASS** |
| Role Profiles OFF | **PASS** |
| Candidate Knowledge freeze posture left live | **PASS** |

### Explicit GO / NO-GO

| Decision | Result |
|---|---|
| **Candidate Knowledge final controlled release** | **PASS / GO** |
| Live tools for authorized WATHEFNI owners | **GO** |
| Live Ranking reader (held-deny overlay) | **GO** |
| External tenants | **NO-GO (OFF)** |
| Role Profiles | **NO-GO (OFF)** |
| iOS / Android / post-hiring audit | **not started** (out of scope) |

---

## Exact flags and users exposed (freeze posture)

### Flags (`/opt/wathefni/var/ck-flags.production.env`)

```
WATHEFNI_CANDIDATE_KNOWLEDGE=on
WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS=WATHEFNI
WATHEFNI_CANDIDATE_KNOWLEDGE_SCHEMA=on
WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS=on
WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS=on
WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER=on
WATHEFNI_CK_SHADOW_TOOLS_ENABLED=0
WATHEFNI_CK_RANKING_SHADOW=1
WATHEFNI_CK_EMBEDDINGS_ENABLED=1
WATHEFNI_CK_VOYAGE_ENABLED=1
WATHEFNI_CK_SEMANTIC_SEARCH=1
WATHEFNI_CK_OWNER_CANARY_ACTORS=ck-owner-canary
WATHEFNI_CK_LIVE_TOOL_ACTORS=88b17ca9-aff4-4721-a553-c1b5514ef95f,b69f4cad-589d-4029-8a2d-cfa85399966c
CK_WORKER_CONCURRENCY=1
WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
WATHEFNI_ALLOW_NON_STAGING_DB=1
WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
WATHEFNI_ENV=production
```

### Users

| Phase | Actors | Emails | Roles |
|---|---|---|---|
| Small allowlist first | `88b17ca9-aff4-4721-a553-c1b5514ef95f` | azizalmulla16@gmail.com | owner |
| Expanded (freeze) | + `b69f4cad-589d-4029-8a2d-cfa85399966c` | f.burhama@disruptv.tech | owner |
| Explicitly denied | `201d0b3b-…`, `90b78a42-…` | viewer accounts | viewer |

No `hr_manager` / `recruiter` role rows exist yet; authorized recruiter exposure = both active WATHEFNI **owners**. Viewers remain denied (`ck_actor_denied`).

### Live tools registered

`search_candidates`, `get_candidate_knowledge`, `compare_candidates`  
- Registry notes: `candidate-knowledge-live-v1 allowlisted actors only`  
- Schema gate: `candidate_knowledge_tools_enabled()`  
- Executor gate: tenant `WATHEFNI` + `WATHEFNI_CK_LIVE_TOOL_ACTORS`

### Runtime units

| Unit | State |
|---|---|
| `wathefni-orchestrator` | active, health **200** |
| `wathefni-ck-index` | **active** + **enabled** (WATHEFNI-only) |

---

## 1) Backup and hashes

| Item | Value |
|---|---|
| Backup path | `/opt/wathefni/backups/production-pre-ck-final-live-20260726T221015Z/` |
| DB dump | `db.dump` (custom format) + `db.restore-list` |
| Rollback script | `ROLLBACK.sh` |
| Predeploy stamp | `2026-07-26T22:10:20Z`, health 200, db=`wathefni` |
| Predeploy artifact hashes | recorded in evidence `PREDEPLOY.txt` |

---

## 2) Workers + health

| Check | Result |
|---|---|
| Worker active | `active` |
| `connected_db` | `wathefni` |
| Tenants | `WATHEFNI` only |
| Orchestrator health | **200** |

---

## 3–6) Live tool results

### Small allowlist

All gates **PASS**. Highlights:

| Test | Result | Notes |
|---|---|---|
| Allowlisted search | PASS | hybrid, total=2, ~1202 ms cold |
| Viewer denied | PASS | `ck_actor_denied` |
| Non-small owner denied | PASS | second owner blocked in small phase |
| Arabic search | PASS | hybrid, ~287 ms |
| English search | PASS | hybrid, ~310 ms |
| Bilingual search | PASS | hybrid, ~292 ms |
| Exact candidate knowledge | PASS | chunks + coverage + canonical metadata |
| Long-CV evidence | PASS | `text_omitted=true`; snippets via chunks only |
| Compare | PASS | `best_candidate=null` without Job Ranking context |
| Held denied for ranking | PASS | `needs_role` → `held_or_job_ranking_ineligible` |
| Incomplete | PASS | fail-closed (`ck_get_failed`) without invention |
| Ambiguous fail-closed | PASS | |
| Restricted classes | PASS | adapter deny classes retained |
| Audit fail-closed | PASS | |
| Tenant isolation | PASS | 0 non-WATHEFNI chunks |
| Zero mutation guards + fingerprint | PASS | applications status histogram unchanged |
| Index freshness | PASS | 10/10 voyage-4-large current chunks |
| Audit events (2h) | PASS | |

### Expanded allowlist

All gates **PASS**, including second owner allowed and viewers still denied.

Monitoring (expanded): p95 ≈ **419 ms**; error_count **0**; hybrid retrieval stable.

---

## 7) Ranking shadow + live reader

| Gate | Result |
|---|---|
| Ranking shadow | **PASS** (`expected_authority_difference` on held indexed app; unexplained=[]) |
| Held remain denied | **PASS** (`held_or_job_ranking_ineligible`) |
| Unexplained material deltas | **0** |
| Evidence versions | present (`canonical_cv_version_id`, `facts_id`, `knowledge_version`) |
| Live reader rollback proven | **PASS** (on → off → on; health 200 each) |
| Live Ranking reader decision | **ON** |

Live reader behavior: `candidate_ranking.rank_job_applications` overlays CK eligibility; held/restricted force `insufficient_information` and clear advisory score; provenance stamps `ck_ranking_reader`.

---

## Voyage usage / cost

| Metric | Value |
|---|---|
| Model | `voyage-4-large` |
| Current voyage chunks | **10** |
| Approx indexed doc tokens | ~5735 |
| Query calls observed (final release) | **6** |
| Approx query tokens | ~144 |
| Estimated incremental query cost | **~$0.000017** |
| Estimated retained index cost | **~$0.000688** |

No full reindex was required in this release; controlled-live Voyage index retained.

---

## Audit, tenant, identity, held-state, zero-mutation proof

| Proof | Result |
|---|---|
| Audit fail-closed | PASS (`ERROR_AUDIT_WRITE_FAILED`) |
| Audit success path | PASS (recent access events > 0) |
| Tenant isolation | PASS (0 other-company chunks; empty OTHERCO list) |
| Held-state | PASS (readable, ranking ineligible) |
| Identity | schema-compatible resolution read (production `strong_keys`/`weak_keys` aliased); no identity mutation |
| Lifecycle / communication / Job / identity fingerprint | PASS (status histogram + criteria-set counts unchanged across tool runs) |
| Store mutation guards | PASS (`mutate_lifecycle` / `mutate_communication` / `mutate_ranking` / `mutate_identity` / `access_production` raise) |

---

## Kill-switch / rollback proof

| Step | Result |
|---|---|
| Kill: TOOLS=off, RANKING_READER=off, WORKERS=off, actors cleared | PASS |
| Post-kill search | denied `ck_tools_disabled`; health 200 |
| Restore freeze posture | TOOLS=on, RANKING_READER=on, WORKERS=on, expanded actors |
| Post-restore owner search | success (total=2) |
| Post-restore viewer | still denied |

DB dump retained for full restore if needed; flag rollback script at backup `ROLLBACK.sh`.

---

## Mid-release production fix (included)

`list_identity_resolutions` was selecting non-existent `strong_key_types` / `policy_version` columns. Production table `inbound_cv_identity_resolutions` uses `strong_keys` / `weak_keys` / `identity_policy_version`. Store query updated to alias those columns so `get_candidate_knowledge` / Ranking reader assemble paths work on production.

---

## Remaining accepted limitations

1. Only two WATHEFNI owners exist as authorized recruiter/admin actors; viewers remain denied.  
2. No `hr_manager` / `recruiter` role rows to expand beyond owners.  
3. External tenants remain OFF.  
4. Role Profiles remain OFF.  
5. Indexed corpus remains the bounded current ready CV set (2 apps / 10 voyage chunks).  
6. Live Ranking reader is a CK eligibility/evidence overlay (held/restricted deny + version stamps), not a full soft-score rewrite of every legacy ranking path.  
7. Incomplete candidates may fail closed on exact get (`ck_get_failed`) rather than invent coverage — accepted.

---

## Freeze declaration

Candidate Knowledge is **frozen** in the successful final-live posture above:

- WATHEFNI-only tools ON for the two owner allowlisted actors  
- Index workers ON  
- Live Ranking reader ON  
- External tenants OFF  
- Role Profiles OFF  

Do **not** begin iOS/Android work, Role Profiles, or the post-hiring audit from this task.

---

## PASS/FAIL verdict for Candidate Knowledge

**PASS**
