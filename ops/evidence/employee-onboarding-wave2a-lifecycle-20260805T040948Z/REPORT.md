# Employee Onboarding Wave 2A — Shared Lifecycle Foundation

**Stamp:** `20260805T040948Z`  
**Scope:** Shared checklist/document lifecycle for employee app + HR web. No bank ESS, no OCR classify parity, no template overlays, no GA.
**Canary deploy:** production orchestrator + flags enabled for Aziz + Talal only.

## Feature flags (canary)

```
WATHEFNI_ONBOARDING_LIFECYCLE_V2A=on
WATHEFNI_ONBOARDING_LIFECYCLE_V2A_COMPANIES=WATHEFNI
WATHEFNI_ONBOARDING_LIFECYCLE_V2A_EMPLOYEE_ALLOWLIST=WATHEFNI-96599338566,WATHEFNI-96550252254
```

Empty employee allowlist = all employees in listed companies. Prefer explicit Aziz+Talal during canary.

## State contract

| From | To | Owner |
|---|---|---|
| pending | in_progress | employee_app \| hr \| system |
| pending / in_progress | submitted | employee_app |
| submitted | processing | document_pipeline |
| submitted / processing | accepted | hr_review |
| submitted / processing | rejected → replacement_required | hr_review |
| replacement_required | submitted | employee_app |
| * | waived / blocked | hr_review \| system |

**Legacy:** `received` → employee-facing `processing` (awaiting HR). Never treated as final when flag on. Backfill does not auto-reject weak OCR.

## Migrations

```sql
ALTER TABLE onboarding_items
  ADD COLUMN IF NOT EXISTS rejection_reason text,
  ADD COLUMN IF NOT EXISTS completed_at timestamptz,
  ADD COLUMN IF NOT EXISTS lifecycle_meta jsonb NOT NULL DEFAULT '{}'::jsonb;

-- Canary backfill (deterministic):
UPDATE onboarding_items ... SET status='processing' WHERE status='received' AND employee in allowlist;
```

Also applied via `ensure_schema` / `ensure_lifecycle_schema`.

## Routes / services

| Change | Location |
|---|---|
| Lifecycle module | `onboarding_lifecycle_wave2a.py` |
| GET `/app/onboarding` grouped projection | `app_onboarding` |
| GET `/app/onboarding/items/{item_id}/versions` | new |
| POST `/app/onboarding/documents` → submitted/processing + idempotent sha | `app_onboarding_document_upload` |
| HR approve/reject sync checklist | `kuwait_pilot_document_journey.approve_version` / `reject_version` |
| Mobile grouped UX + preview/resubmit | `OnboardingView`, `onboarding.tsx` |

Governed versions remain append-only authority. Approved evidence is never deleted by employee paths.

## Rollback

1. Set `WATHEFNI_ONBOARDING_LIFECYCLE_V2A=off`, restart orchestrator.
2. Mobile falls back to legacy pending/received lists.
3. Optional: leave `processing` rows as-is (legacy map still understands them as non-complete when flag re-enabled).

## Remaining blockers for Wave 2B (bank ESS)

- No `/app` bank submit API yet
- Aziz synthetic phone prefix vs `W5C-SYNTH|` name mismatch for ESS gates
- Empty `ESS_V5_BANK_REAL_ALLOWLIST`
- Bank card remains informational only in Wave 2A

## Tests

- `smoke-test-onboarding-lifecycle-wave2a.py` (local)
- Canary smoke on prod after flag enable (upload → processing; HR reject → replacement_required; preview self-scope)
