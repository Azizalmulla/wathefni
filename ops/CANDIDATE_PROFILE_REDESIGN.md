# Candidate Profile Redesign

**Date:** 2026-07-27 (UTC)  
**Profile-facts stamp:** `20260727T182941Z`  
**Person-authority stamp:** `20260727T174754Z`  
**UI redesign stamp:** `20260727T160527Z`  
**Host:** `root@76.13.63.68`  
**Dashboard asset:** `dashboard-vA3r1az4.js`  
**Evidence:** `/opt/wathefni/var/evidence/candidate-profile-facts-20260727T182941Z/`  
**Scope:** Canonical Candidate Profile Facts + person-aware profile authority. No color changes. No Candidates list redesign.

**Status:** Person-aware authority **accepted**. Canonical profile-facts contract is now the long-term extraction → API → frontend path.

---

## Final PASS / FAIL

| Gate | Result |
|---|---|
| Canonical `candidate-profile-facts-v1` schema | **PASS** |
| Normalization after extraction (no re-extract / no duplicate facts) | **PASS** |
| Idempotent backfill of existing current snapshots | **PASS** (12 written, rerun 0 written / 12 refreshed; fact snapshot count unchanged) |
| Person-profile returns clean string lists only | **PASS** |
| Frontend never parses `{ value: "..." }` | **PASS** |
| Yasser skills / education display | **PASS** |
| Derived summary / expertise / location when possible | **PASS** |
| Header omits “Not identified · N roles · Not identified” | **PASS** |
| General candidate Applications = 0 | **PASS** |
| Current CV not repeated under previous versions | **PASS** |
| Notes section hidden until real notes authority | **PASS** |
| Human-readable Activity labels | **PASS** |
| Compact empty states | **PASS** |
| Health 200 | **PASS** |
| Colors / list redesign unchanged | **PASS** |

**Verdict: PASS**

---

## Canonical contract: `candidate-profile-facts-v1`

### Fields (clean HR values only)

| Field | Type |
|---|---|
| `skills` | `string[]` |
| `education` | `string[]` |
| `employment` | `string[]` |
| `languages` | `string[]` |
| `certifications` | `string[]` |
| `location` | `string \| null` |
| `professional_summary` | `string \| null` |
| `primary_expertise` | `string \| null` |
| `experience_years` | `number \| null` |
| `field_sources` | per-field `{ origin: hr_confirmed \| extracted \| derived \| missing }` |

Frontend must render these strings only. Raw extraction shapes (`{ value, source, confidence }`) stay in immutable `application_cv_fact_snapshots` and are not part of the normal person-profile UI contract.

### Effective-value priority

1. **HR-confirmed** (`candidate_fact_review_events`)  
2. **Extracted** (normalized from `application-cv-facts-v1`)  
3. **Grounded derived** (summary / location / expertise from CV text or education when missing)

### Materialization

- Module: `wathefni-orchestrator/candidate_profile_facts.py`
- Table: `candidate_profile_facts` (1 projection per `facts_id`, no new extraction rows)
- Hooked after `candidate_cv_facts.materialize_facts`
- Backfill: `ops/backfill-candidate-profile-facts.py` (idempotent)

### Person-profile API

`GET /dashboard/prehire/applications/{app_key}/person-profile` → schema `candidate-person-profile-v2`

Returns:

- `profile_facts` — canonical clean contract  
- `person` — header fields from `profile_facts`  
- `applications` — **live job applications only** (general-only people → `[]`)  
- `cv_versions: { current, previous }` — current not duplicated in previous  
- `notes_enabled: false` / empty `notes` until a real notes authority exists  
- `activity` — human-readable labels  
- `extraction_evidence` — ids/hashes only (not for HR chrome)

---

## Frontend

- `overviewFromProfile` / `canonicalProfileFacts` read `profile_facts` only  
- Header meta joins only present fields (no “Not identified” fillers)  
- Notes tab removed from profile sections  
- Compact empty copy for skills / languages / experience / education  

Asset: `dashboard-vA3r1az4.js`

---

## Yasser proof

Anchor: `imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT`

| Field | Result |
|---|---|
| Skills | Present (clean strings, e.g. Programming / Web & Backend / Data & AI…) |
| Education | Present (GUST, Bachelor in Computer Science, GPA…) |
| Employment | Present (Software Development Intern…) |
| Location | Kuwait (derived) |
| Primary expertise | Bachelor in Computer Science Candidate (derived) |
| Professional summary | Results-oriented Computer Science undergraduate… (derived) |
| Languages | Empty (not in extraction) |
| Applications | `0` (general candidate) |
| CV previous | `[]` (no false duplicate of current file) |

Evidence: `yasser-proof.json`, `backfill.json`, `backfill-rerun.json`

---

## Rollback

```bash
EVIDENCE=/opt/wathefni/var/evidence/candidate-profile-facts-20260727T182941Z
# UI
rm -rf /var/www/wathefni-dashboard && mkdir -p /var/www/wathefni-dashboard
rsync -a $EVIDENCE/dashboard-prev/ /var/www/wathefni-dashboard/
# Backend
systemctl stop wathefni-orchestrator
cp $EVIDENCE/unified_person_profile.py.prev /opt/wathefni/orchestrator/unified_person_profile.py
cp $EVIDENCE/candidate_cv_facts.py.prev /opt/wathefni/orchestrator/candidate_cv_facts.py
# optional: leave candidate_profile_facts table (projection only) or drop if required
systemctl start wathefni-orchestrator
curl -fsS http://127.0.0.1:8010/health
```

---

## Remaining notes

- Languages remain empty when the extractor found no languages section — that is extraction coverage, not UI mapping.  
- `experience_years` stays null unless explicitly extracted; role counts are never shown as years.  
- Real HR notes authority is intentionally deferred (`notes_enabled: false`).  
- Candidates list was not redesigned in this task.
