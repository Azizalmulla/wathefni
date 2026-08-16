# Pre-hiring Candidate Knowledge — Phase 7 Local and Staging Qualification

Date: 2026-07-26  
Commit: `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2`  
Branch: `authority-cutover`  
Production deploy: none  
Production tool exposure: none  
Production Ranking cutover: none  
External tenants: none  
Role Profiles: none  
Phase 8 execution: not started

## Verdict

| Gate | Result |
|---|---|
| Local qualification | **GO** |
| Staging qualification | **GO** (PASS) |
| Phase 8 production-readiness planning | **GO** |
| Production execution | **NO-GO** |
| Live tool exposure / Ranking cutover / Role Profiles | **NO-GO** |

Evidence: `ops/evidence/candidate-knowledge-phase7/`

Phase 7 stops here. Phase 8 was not begun in this task.

---

## Environment identity

- Host: `Mac` (local) + staging `root@76.13.63.68`
- Platform: `macOS-26.5.2-arm64`
- Python (local): `3.14.2`
- Git commit: `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2`
- Tree dirty: `True` (unrelated local worktree changes present; qualification used CK modules at this commit)
- Voyage enabled: unset
- Voyage API key present: `False`
- Staging DB: `wathefni_staging`
- Staging health: **200** before and after

---

## Qualification order completed

1. Local deterministic qualification — **PASS**
2. Local real-provider (Voyage) — **ACCEPTED_LIMITATION** (no credentials / not enabled)
3. Staging additive schema — **PASS** (idempotent)
4. Staging synthetic data load — **PASS** (1,000 `SYN_CK_P7` rows; cleaned after)
5. Staging index build — **PASS** as direct synthetic chunk insert into additive tables (no live worker unit installed)
6. Staging tool shadow qualification — **PASS** (in-process `/tmp` modules; live service flags unset)
7. Staging Ranking shadow qualification — **PASS** (adapter held denial + compare no-winner)
8. Failure / rollback / recovery drills — **PASS** (audit fail-closed local; invalidation; job dead-letter + idempotency; synthetic cleanup; index schema retained, canonical data untouched)
9. Final GO/NO-GO for Phase 8 planning — **GO**

---

## Local regression batteries

| Suite | Result |
|---|---|
| Phase 0–5 + Ranking adapter + `test_candidate_ranking` + Phase 7 matrix | **174/174 PASS** |

Artifacts:
- `ops/evidence/candidate-knowledge-phase7/local-regression.json`
- `ops/evidence/candidate-knowledge-phase7/local-phase7-gates.json`

---

## Local Phase 7 matrix

| Gate | Category | Status | Detail |
|---|---|---|---|
| `auth_matrix` | authorization | **PASS** | `backend_current`, empty/missing `prehire.read`, actor/tenant mismatch, cross-tenant non-leak |
| `audit_fail_closed` | audit | **PASS** | restricted/deletion denied; audit write failure blocks evidence |
| `identity_mariam_surrogate` | identity | **PASS** | Mariam ≠ Faisal/Aziz/Hamad; name-only ambiguous; surrogate ≠ real phone |
| `canonical_channels` | canonical_knowledge | **PASS** | current CV selected; WhatsApp/manual gaps disclosed; conflict fail-closed |
| `search_tools_ranking_scale` | retrieval_tools_ranking | **ACCEPTED_LIMITATION** | 1k/10k needle recall PASS; full 50k not executed |
| `invalidation_zero_mutation` | zero_mutation | **PASS** | invalidated chunks unsearchable; lifecycle/production helpers raise |
| `voyage_real` | voyage | **ACCEPTED_LIMITATION** | mock only |

Blockers: **0**  
Fails: **0**

---

## Quality thresholds

| Metric | Threshold | Observed | Status |
|---|---|---|---|
| retrieval needle recall @1k | found | true | **PASS** |
| retrieval needle recall @10k | found | true | **PASS** |
| search p95 @10k (mock) | ≤ 2000 ms | 182.66 ms | **PASS** |
| full 50k executed | if capacity permits | false (est. ~844 s index) | **ACCEPTED_LIMITATION** |
| Voyage real provider | credentials + enable | not available | **ACCEPTED_LIMITATION** |
| cross-tenant leak | 0 | 0 | **PASS** |
| forbidden mutations | 0 | 0 | **PASS** |
| Ranking unexplained deltas | 0 | 0 | **PASS** |
| audit fail-closed | deny on audit failure | true | **PASS** |
| hallucination / grounding (shadow tools) | no winner without Ranking; CV omitted | proven in suite | **PASS** |
| invalidation delay | immediate unsearchable | immediate | **PASS** |

---

## Local retrieval benchmarks (mock embeddings)

```json
{
  "1000": {
    "index_ms": 1213.1,
    "search_p50_ms": 15.58,
    "search_p95_ms": 15.97,
    "chunks": 3017,
    "retrieval_mode": "hybrid",
    "needle_found": true
  },
  "10000": {
    "index_ms": 168859.01,
    "search_p50_ms": 170.98,
    "search_p95_ms": 182.66,
    "chunks": 33016,
    "retrieval_mode": "hybrid",
    "needle_found": true
  },
  "50000_estimate": {
    "estimated_index_ms": 844295.05,
    "executed_full_50k": false
  }
}
```

Modes proven locally: structured / lexical / hybrid; provider-failure → `retrieval_degraded`; long-CV tail chunk retrieval; stable tooling without name-based merge.

---

## Voyage qualification

- Exact model (configured, not called): `voyage-4-large`
- Real document/query call counts: **0**
- Cost estimate: **$0**
- Arabic/English real retrieval quality: **not measured**
- Mock-versus-real differences: **not measured**
- Status: **ACCEPTED_LIMITATION**

No contact details, identity-review alternatives, or private notes were sent to Voyage.

---

## Staging proof

Host: `root@76.13.63.68` · service health `127.0.0.1:8011` · DB `wathefni_staging`

| Proof | Status |
|---|---|
| Schema apply idempotent (×2) | **PASS** — tables `candidate_knowledge_chunks`, `candidate_knowledge_index_jobs`, `candidate_knowledge_access_events` |
| Synthetic load 1,000 + other-tenant decoy | **PASS** |
| Lexical search finds needle; other tenant not leaked | **PASS** |
| Index job dead-letter + idempotency conflict | **PASS** |
| Access audit content-free | **PASS** |
| Invalidation removes current visibility | **PASS** |
| Shadow tools + Ranking held denial (in-process) | **PASS** |
| CK live flags unset on staging unit/env | **PASS** |
| Synthetic residue cleaned (`SYN_CK_*` → 0) | **PASS** |
| Health remains 200 | **PASS** |
| Outbound messages / lifecycle / Ranking cutover | **0 / none** |
| Canonical data deleted | **No** (index schema retained additive) |

Artifact: `ops/evidence/candidate-knowledge-phase7/staging-qualify-result.json`

### Staging accepted limitations

- Synthetic pool on staging was **1,000** (not 10k/50k).
- CK modules were **not** installed into the live staging orchestrator service; shadow/Ranking proofs ran in-process from `/tmp` against additive schema.
- No index-worker systemd unit was installed or left running.
- Real Voyage was not executed on staging.
- Normal staging users were **not** exposed to Candidate Knowledge tools.

Rollback posture proven conceptually: drop/disable index+tool exposure without deleting canonical application/CV/facts tables. Additive index tables were **retained** (empty of synthetic rows) for subsequent Phase 8 planning; live flags remain unset.

---

## Authorization / identity / canonical / tools / Ranking (summary)

- Explicit `backend_current` + `prehire.read` required; empty/missing permissions denied; actor/tenant mismatch denied; cross-tenant existence not leaked.
- Exact `app:` only for exact reads; names discovery-only / ambiguous; Mariam Almulla does not bind to other Almullas; manual surrogate and real-phone remain separate.
- Current canonical CV selected; no legacy profile/raw JSON fallback in assembled knowledge; WhatsApp/manual CV gaps disclosed as `not_recorded` / incomplete; conflicting current versions → `conflict`.
- Tools: `search_candidates`, `get_candidate_knowledge`, `compare_candidates` grounded, CV omitted by default, no winner without governed Ranking context, shadow default-off.
- RankingEvidenceAdapter: held denied; reads create no ranking rows; unexplained score deltas = 0 in qualified shadow cases; legacy profile/raw differences classified as expected evidence improvement where applicable.

---

## Accepted limitations

1. Full local **50k** index not executed (10k measured; 50k estimated ~14 minutes).
2. **Real Voyage** not authorized/credentialed in this environment.
3. Staging scale limited to **1k** synthetic rows.
4. Staging live orchestrator **not** cut over to CK modules; proofs were additive schema + in-process shadow.
5. Cross-channel completeness for WhatsApp/manual remains honestly incomplete (by design disclosure).

## Blockers

None.

---

## GO / NO-GO for Phase 8 planning

**GO** for Phase 8 production-readiness *planning* only.

Still forbidden until a separate Phase 8 task + explicit production authorization:

- production deploy
- live AI recruiter tool exposure
- live Ranking cutover
- external tenant enablement
- Role Profiles
- production backfill

---

## Harnesses

- Local: `ops/qualify-candidate-knowledge-phase7.py`
- Local matrix: `wathefni-orchestrator/test_candidate_knowledge_phase7_qualification.py`
- Staging: `ops/candidate-knowledge-phase7-staging-qualify.py`

Phase 7 complete. Phase 8 not started.
