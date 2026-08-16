# Pre-Hiring Unified Candidates + Talent Pool — Staging Qualification

**Date:** 2026-07-25 (UTC)  
**Scope:** Contained staging deployment and qualification only  
**Production:** **Not deployed.** Production service remained healthy (`:8010` → 200) with no unified feature flag.  
**Out of scope (not implemented / not enabled):** automatic classification, Role Profiles, advisory ranking, Person Registry, outreach, Link to Job / `intake_admit` execution.

---

## Verdict

| Gate | Result |
| --- | --- |
| Staging feature qualification (unified Candidates + Talent Pool behind flag) | **GO_STAGING_QUALIFIED** — 50/50 core proofs PASS |
| Staging leftover state | Flag **ON** for isolated tenant **`WATHEFNI` only** |
| Production-dark deployment | **NO-GO** |

**Why production-dark is NO-GO:** core unified proofs are green on staging, but the restored-baseline frozen pack set is incomplete and not fully green (C0/C1 staging matrix 21/22 with interviews module gap; several previously limited DB-bound matrices not re-executed end-to-end on this baseline). Do not promote dark production until those packs are re-green without unexplained gaps.

---

## 1. Identity and artifact

| Item | Value |
| --- | --- |
| Source commit | `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2` |
| Contained allowlist artifact SHA | `c0a1fc0d129745999228a657c7acbb602076a42db6ec883a16a4c848bf4bdf45` |
| Evidence stamp | `20260725T142706Z` |
| Host evidence | `/opt/wathefni/staging/staging-evidence/unified-candidates/20260725T142706Z` |
| Staging service | `wathefni-orchestrator-staging.service` on `127.0.0.1:8011` |
| Staging DB | `wathefni_staging` @ `127.0.0.1:5432` |

### Exact changed-file allowlist (deploy artifact)

```
c814d3a65d4ab690d1a57c1867eec4960b3dd208c58f532485eebe15259fa6a3  unified_candidates.py
014036d64a41b2d2d0a274afff664e22ae68ca7e60f0340fa650e18292e157ad  unified_candidates_routes.py
d17b8d2056f6c2749c28798e7d313f09b5e15167c0acdda61f41706797b27c31  test_unified_candidates.py
ba564a749561017ca1e0e42aad96adad162c8dbf15d8f14a46cb40ef18d09d2b  local-qualify-unified-candidates.py
0efc9e40747e7b6fc1de8a17af9d9574c2a247438720d52af4341f296a654bf7  ops/patch-staging-app-unified-candidates.py
```

Plus surgical patch of staging `app.py` (not the dirty local full tree) and feature-gated dashboard dist.

### Deployed host file SHA (post hotfixes)

```
9293382c0efc83d3877c85f1ae168edf3b69ceea5ee46e5ec1a6b3bf58cde12d  app.py
c814d3a65d4ab690d1a57c1867eec4960b3dd208c58f532485eebe15259fa6a3  unified_candidates.py
fc59736415a480765bd4710aba051ce65f39ced495e61173a98e3804e0f26847  unified_candidates_routes.py
```

**Note:** `unified_candidates_routes.py` and patched `app.py` diverged from the initial allowlist SHA after staging-only hotfixes (late route mount before SPA catch-all; held notify/assessment HTTP fail-closed; profile txn rollback). Dashboard dist includes unified Candidates UI strings (`Talent Pool`, `Not linked`, `Intake Operations`).

### HR mobile

No unified-candidates parity delta was included in this contained artifact. Existing HR mobile frozen checks were sampled separately (see §8).

---

## 2. Backup and migration evidence

| Item | Path / proof |
| --- | --- |
| Pre-deploy backup | `/opt/wathefni/backups/staging-pre-unified-candidates-20260725T142706Z` |
| `db.dump` SHA256 | `1b06e2ef4aa0b3bad7c1cf3e08142979b650dcd3451acd6c1198dc850ec1979e` |
| `app.py.pre` SHA256 | `090e82b130cdd83558f5f908bdca7b37ba26ef553a2f9f29b33265dd77283cfb` |
| Rollback helper | `ROLLBACK.sh` in backup dir |
| Additive schema (flag OFF) | `candidate_record_governance`, `candidate_fact_review_events`, `candidate_saved_views` ensured idempotently |

### Mid-qualification restore

During cleanup debugging, a broad `DELETE … phone LIKE '965%'` accidentally removed staging candidates. Staging DB was restored from the pre-deploy dump above; table/function ownership was reassigned to `wathefni_app`; additive unified schema was re-applied. Post-restore counts: `candidates` with Kuwait-style phones restored to **69**; `WATHEFNI` applications **48**. Qualification was re-run cleanly after restore.

---

## 3. Feature-flag state

Suggested / used flags:

- `WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL` (master)
- `WATHEFNI_UNIFIED_CANDIDATES_TENANTS` (allowlist)

Activation sequence executed:

1. Additive schema with master **OFF**
2. Code deploy with master **OFF**
3. Legacy Candidates list healthy (`unified_candidates=false`)
4. Master **ON** + tenants=`WATHEFNI` only
5. Not enabled globally
6. Production unchanged

**Final staging drop-in:**

```
[Service]
Environment=WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=on
Environment=WATHEFNI_UNIFIED_CANDIDATES_TENANTS=WATHEFNI
```

Redacted config manifest: `ops/screenshots/unified-candidates-staging/redacted-config-manifest.json`  
(and host evidence copy under the stamp directory).

---

## 4. Screenshots (staging Chromium)

Captured against live staging dashboard (SSH tunnel to `:8011`) with temporary fixtures, then cleaned.

| Screenshot | Path |
| --- | --- |
| Unified table (All) | `ops/screenshots/unified-candidates-staging/unified-candidates-table.png` |
| Talent Pool filters | `ops/screenshots/unified-candidates-staging/unified-candidates-filters.png` |
| Held governed profile | `ops/screenshots/unified-candidates-staging/held-governed-profile.png` |
| Intake Operations | `ops/screenshots/unified-candidates-staging/intake-operations.png` |
| Index | `ops/screenshots/unified-candidates-staging/INDEX.md` |

Observed on staging UI:

- Held + live rows in one Candidates table
- Held: Job **Not linked**, Status **Talent Pool**, CV processing Ready, Assessment empty/N/A, Communication no-outreach semantics
- Processing-attention banner → **OPEN INTAKE OPERATIONS**
- Intake Operations read buckets with **Release forbidden** on quarantined/malware
- Large Import Review candidate list not used as the primary held surface once Talent Pool rows are available

---

## 5. Database-bound / API qualification (50/50)

Host report: `qualification.json` → **`GO_STAGING_QUALIFIED`**, `pass_count=50`, `fail_count=0`.

Synthetic fixtures covered: active application; held `needs_role`; held `import_review`; hired; archived held; restricted; failed/incomplete intake; multi-CV files; HR fact correction; missing facts; search text match. Existing staging email CV remained readable in Talent Pool without outbound/lifecycle mutation from this pack.

### Views / filters

PASS: `all`, `active`, `talent_pool`, `hired`, `archived`, `restricted` with expected inclusion/exclusion; saved-view create/list/delete; tenant-scoped feature gate.

### Unified table / held display

PASS: held Job Not linked; Talent Pool status presentation; assessment dash / N/A; communication no outreach; `imp-…` hidden; live job preserved; no duplicate held key.

### Held authority gates (UI + HTTP fail-closed)

PASS HTTP denials for held: shortlist, reject, hire, notify, evaluation/ranking, assessment send. Link to Job remains designation-only (`enabled=false`, no `intake_admit`).

### Profile / identity / facts

PASS: profile load; immutable snapshot flag; sender provenance separate; no negative missing-fact language; fact preview/commit; append-only events; supersede path; missing facts as not-extracted/unknown semantics.

### Search / Intake

PASS: match reasons present for CV/profile search; Intake Operations + attention endpoints.

### Rollback

PASS sequence:

1. Flag OFF → legacy list healthy (`unified_candidates` false)
2. Fact-review rows preserved
3. Held row retains `needs_role` and empty job binding
4. Flag ON for `WATHEFNI` → feature re-enabled without migration/rewrite

### Zero residue

PASS after cleanup fix (per-statement commits; no broad `965%` deletes): fixture applications / fact events / saved views = 0 for run prefix. Screenshot fixtures `UCSHOT*` also cleaned to 0.

---

## 6. Held action-gate proof (summary)

| Action | Held result |
| --- | --- |
| Ranking / evaluate | Denied (HTTP fail-closed) |
| Shortlist / reject / hire | Denied |
| Notify / outreach | Denied |
| Assessment send (job-required) | Denied |
| Interview / offer creation | Not exposed as executable held actions; lifecycle packs unchanged for live rows |
| Link to Job / `intake_admit` | Disabled designation only |
| AI-assigned Job | Not enabled |

Backend does not rely on UI hiding alone.

---

## 7. Fact immutability and concurrency

On real staging DB during qualify:

- Extraction snapshot remains immutable (`application-cv-facts-v1` authority preserved)
- confirm/correct/reject/add events append-only with actor/timestamps
- Effective-value precedence + supersede preserve history
- Stale/invalid supersede submissions fail safely (non-200 accepted as safe close)
- Missing skills/languages shown as not extracted — not as candidate absence

---

## 8. Frozen regressions

### Auto-run on staging host during qualify (PASS)

| Pack | Result |
| --- | --- |
| `smoke-test-canonical-recruiting-lifecycle.py` | PASS |
| `smoke-test-offer-lifecycle.py` | PASS |
| `smoke-test-prehire-overview-unit.py` | PASS |
| `smoke-test-prehire-assistant-parity.py` | PASS |
| `test_unified_candidates.py` | PASS |
| `local-qualify-unified-candidates.py` | PASS |

### Extra packs run after restore

| Pack | Result | Notes |
| --- | --- | --- |
| `smoke-test-assessments.py` | PASS | |
| `smoke-test-tenant-isolation-harness.py` | PASS (24/24) | |
| `smoke-test-inbound-email.py` | PASS | durable inbound |
| `smoke-test-dashboard-auth.py` | **NOT RUNNABLE here** | expects `apps/wathefni-dashboard/src` beside staging orchestrator tree (missing on host layout) |
| `smoke-test-jobs-phase1.py` | **FAIL** | publish blocked: required job information incomplete for smoke fixture (pre-existing jobs publishability gate; unrelated to unified Candidates read path) |
| `smoke-test-hr2a-mobile-data.py` | **36 PASS / 1 FAIL** | fail: “candidate status updater is explicitly bound to current environment” — static/source assertion; not a unified-table runtime regression |
| `ops/candidates-c01-staging-matrix.py` | **21/22** | FAIL `confirmed_schedule_succeeds` because fixture company `C01STG` has **interviews module disabled** (`module_disabled`) |

### Explicit gaps (present, not fully re-greened on this baseline)

These were previously limited / branch-specific and are **not** claimed green for this qualification:

- Full Candidates **C0–C3** matrix suite beyond the partial C01 run above (`c2`/`c3` staging matrices not re-executed end-to-end here)
- Ranking staging matrices (`ranking-r0-r3-staging-matrix.py`, result presentation)
- Reports staging matrix
- Interviews staging matrix / live interview packs
- Offers/Hiring staging matrix (offer lifecycle unit smoke did PASS)
- Bulk import / tiered intake smokes (`present_not_auto_run` in qualify harness)
- Full dashboard Vitest against staging host (dashboard build was deployed; local Vitest was part of pre-staging remediation, not re-asserted on VPS)
- HR mobile full Vitest suite on VPS (sampled HR-2A smoke only)

These gaps are why **production-dark remains NO-GO** even though the unified feature proofs themselves are green.

---

## 9. Unresolved risks

1. **Frozen-pack incompleteness** on the post-restore baseline (C2/C3, ranking, reports, interviews matrices).
2. **C01 interviews module entitlement** for isolated matrix companies must be aligned before claiming C0/C1 staging-green again.
3. **Deployed SHA drift** from initial allowlist after staging hotfixes — pin a refreshed allowlist SHA before any future promotion.
4. **Cleanup footgun:** never use broad phone predicates like `965%` for fixture teardown (restored; cleanup script now prefix-scoped).
5. **Governance `archive_state='active'`** is treated as archived by view predicates — operators/fixtures must leave archive_state null for active held rows.
6. Classification / Link to Job / Role Profiles remain intentionally dark — do not interpret Talent Pool rows as Job applications or confirmed unique Persons.

---

## 10. Stop line

- Staging qualification of the unified Candidates experience: **complete** (`GO_STAGING_QUALIFIED`).
- Staging flag left **ON for `WATHEFNI` only**.
- **Production not deployed.**
- **Production-dark: NO-GO.**
- Automatic classification, Role Profiles, advisory ranking, Person Registry, outreach, and Link to Job execution: **not started.**

Evidence bundle: `/opt/wathefni/staging/staging-evidence/unified-candidates/20260725T142706Z`  
Local report mirrors: `ops/screenshots/unified-candidates-staging/` + this file.
