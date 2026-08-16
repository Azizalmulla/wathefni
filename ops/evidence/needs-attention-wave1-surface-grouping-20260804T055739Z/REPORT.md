# Needs Attention Wave 1 — Surface + Grouping production deploy

**Stamp:** `20260804T055739Z`  
**Gate:** `PROD_NEEDS_ATTENTION_WAVE1_SURFACE_GROUPING_GO`  
**Freeze:** `ops/NEEDS_ATTENTION_WAVE1_SURFACE_AND_GROUPING_FREEZE.md`  
**Evidence:** `ops/evidence/needs-attention-wave1-surface-grouping-20260804T055739Z/`

## Verdict

| Decision | Result |
|---|---|
| Freeze surface + grouping contract | **GO** |
| Production visual deploy | **GO** |
| Widen Phase 0 allowlists | **NO-GO** (unchanged) |
| Next post-hire page | **NO-GO** until owner review |

## Deployed

- Dashboard dist → `/var/www/wathefni-dashboard` (Needs Attention rename, slim rows/filters, Onboarding employee focus, grouped-doc expand)
- `action_inbox_wave1.py` → `/opt/wathefni/orchestrator/action_inbox_wave1.py` (contract **1.0.2** grouping)
- Freeze doc copied under orchestrator `ops/`

## Production compose (Aziz viewer)

| Metric | Value |
|---|---|
| `pre_group_total` | 19 |
| Ranked `total` after group + Phase 0 | **2** |
| Grouped compliance cases | 4 (18 members collapsed pre-filter) |
| Visible employee keys | `WATHEFNI-96550252254` only |
| Phase 0 `dropped_subject` | **3** |

Visible items:

1. **Talal Fadhli is missing 5 required documents** (`grouped=true`, docs: civil_id, medical, passport, residence, work_permit) → Onboarding
2. **Onboarding incomplete** (Employees 360 next action; separate workflow/stream) → Onboarding

## Allowlist confirmation

Subject allowlist remains Talal-only; viewer remains Aziz-only.  
**Other employees are hidden only because of this Phase 0 subject allowlist** (`dropped_subject`), not because they ranked below a result limit. There is no result-count cap.

This allowlist is a **rollout gate**, not final product visibility.

Live drop-in unchanged:

```
WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST=96599338566
WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST=WATHEFNI-96550252254
```

## Screenshot

`screenshots/talal-missing-documents-grouped.png` — production-backed visual from live payload showing Talal’s five missing docs as one case.

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-needs-attention-wave1-20260804T055739Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-needs-attention-wave1-20260804T055739Z
```

Restores previous dashboard dist + `action_inbox_wave1.py` and restarts orchestrator.

## Explicit hold

Do not begin the next page until owner reviews production Needs Attention.
