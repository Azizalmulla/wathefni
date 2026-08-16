# Civil ID dual-side — evidence stamp

**Stamp:** `20260806T014717Z`  
**Scope:** Front + back parts on one `civil_id` checklist item · draft attempt → pair gate → same version promoted to HR · disposable canary prove path · Aziz accepted Civil ID untouched.

## Decisions implemented

| Decision | Implementation |
|---|---|
| Persistent draft attempt | `governed_document_versions.review_status=draft_parts` created on first part |
| Attach parts to same version | `governed_document_version_parts` (`front`/`back`) |
| Promote same version | `promote_draft_to_hr_review` → `pending_hr_review` (no second version) |
| `side=unknown` soft | Part accepted with `hr_warning`; never treated as missing_side |
| Disposable canary first | `civil_id_dual_side_canary` + `ops-aziz-civil-id-dual-side-canary.py` |
| Flags | `WATHEFNI_CIVIL_ID_DUAL_SIDE` + `_COMPANIES` + `_EMPLOYEE_ALLOWLIST` |
| DocVal | Soft canary unchanged · HARD stays off |
| Scanner | Not built — camera/library only |

## Invariants preserved

- One checklist item with two parts
- Parts only pair inside the same attempt/version
- No silent mix of historical opposite sides
- No HR approve unless both parts present + pair gate OK
- Duplicate sides / identity mismatch block
- Replacement opens a new empty attempt (does not copy prior opposite side)
- Legacy accepted single-file Civil IDs stay accepted
- Aziz SHA `fe98f7d9d481578804a3ca3e19ca96ad4b4fa6e046f46e25d4ab21d9e15f0bb7` must not change during canary prove

## Local smoke

```text
python3 smoke-test-onboarding-civil-id-dual-side.py
→ OK (see audit/smoke-dual-side.txt)
```

## Flags (deploy)

```bash
WATHEFNI_CIVIL_ID_DUAL_SIDE=on
WATHEFNI_CIVIL_ID_DUAL_SIDE_COMPANIES=WATHEFNI
WATHEFNI_CIVIL_ID_DUAL_SIDE_EMPLOYEE_ALLOWLIST=WATHEFNI-96599338566
# DocVal unchanged:
WATHEFNI_ONBOARDING_DOC_VALIDATION_SOFT=on
WATHEFNI_ONBOARDING_DOC_VALIDATION_HARD=off
```

Aziz is allowlisted **only** so the disposable canary item can use dual-side. His real `civil_id` remains `accepted` (upload blocked); projection treats it as `legacy_single`.

## Rollback

1. Set `WATHEFNI_CIVIL_ID_DUAL_SIDE=off` (or empty allowlist) and reload orchestrator.
2. Optional: `ops-aziz-civil-id-dual-side-canary.py cleanup` — removes canary lane only.
3. Confirm real Civil ID SHA unchanged via `snapshot-civil-id`.

Draft/pending dual-side versions become inert when the flag is off (clients fall back to single-file actions). Do not delete governed history unless cleanup is intentional.

## Live retest steps (exact)

On orchestrator host after deploy:

```bash
# 1) Snapshot Aziz real Civil ID (must stay accepted + same SHA)
WATHEFNI_ENV=production .venv/bin/python ops-aziz-civil-id-dual-side-canary.py snapshot-civil-id

# 2) Ensure flags (company + Aziz allowlist; HARD off)
#    WATHEFNI_CIVIL_ID_DUAL_SIDE=on
#    WATHEFNI_CIVIL_ID_DUAL_SIDE_COMPANIES=WATHEFNI
#    WATHEFNI_CIVIL_ID_DUAL_SIDE_EMPLOYEE_ALLOWLIST=WATHEFNI-96599338566

# 3) Create disposable canary item (does not touch civil_id)
WATHEFNI_ENV=production .venv/bin/python ops-aziz-civil-id-dual-side-canary.py create
WATHEFNI_ENV=production .venv/bin/python ops-aziz-civil-id-dual-side-canary.py verify

# 4) Mobile (Aziz): open Onboarding → see canary card with Front + Back slots
#    Upload front (camera/library) → status stays incomplete / in_progress
#    Upload back → pair gate → processing / pending HR
#    Preview each side independently
#    Confirm real Civil ID still accepted (no dual-side demand)

# 5) Negative checks on canary:
#    - Same file for both sides → duplicate_sides
#    - Back image in Front slot (when OCR side known) → wrong_side
#    - Random non-doc → existing DocVal block
#    - HR approve while draft_parts / one side only → rejected (parts_incomplete)

# 6) HR web: open Aziz onboarding → canary shows front+back previews; review as one attempt

# 7) Re-snapshot Civil ID SHA — must match step 1
WATHEFNI_ENV=production .venv/bin/python ops-aziz-civil-id-dual-side-canary.py snapshot-civil-id

# 8) After soak: cleanup disposable canary only
WATHEFNI_ENV=production .venv/bin/python ops-aziz-civil-id-dual-side-canary.py cleanup
```

## Key modules

- `wathefni-orchestrator/onboarding_civil_id_dual_side.py`
- `wathefni-orchestrator/onboarding_doc_validation_parity.py` (`expected_part`, canary alias)
- `wathefni-orchestrator/onboarding_lifecycle_wave2a.py` (projection decoration)
- `wathefni-orchestrator/kuwait_pilot_document_journey.py` (approve gate)
- `wathefni-orchestrator/app.py` (`part` form field + draft attach/promote)
- `apps/wathefni-employee-mobile` two-slot UX
- `apps/wathefni-dashboard` dual-side HR preview
- `ops-aziz-civil-id-dual-side-canary.py`
- `smoke-test-onboarding-civil-id-dual-side.py`
