# Needs Attention Wave 1 — Surface + Grouping Freeze

**Gate:** `PROD_NEEDS_ATTENTION_WAVE1_SURFACE_GROUPING_GO`  
**Stamp:** `20260804T055739Z`  
**Evidence:** `ops/evidence/needs-attention-wave1-surface-grouping-20260804T055739Z/`  
**Page id (unchanged):** `inbox`  
**User-facing name:** Needs Attention / يحتاج متابعة · title الأمور التي تحتاج متابعتك

## Frozen surface (presentation)

- Ranked list is the primary composition (slim rows, not a dashboard of cards)
- Filters: Needs action · Due soon · Blocked · All
- Details expand in-row; Follow up routes to the owning module
- Onboarding honors `?employee=` / deep-link employee focus
- Employee focus is passed only to destinations that honor it today (`employees`, `onboarding`)

## Frozen grouping contract (compose)

Backend compose in `action_inbox_wave1.py` groups compliance findings when **all** match:

| Key | Meaning |
|---|---|
| `employee_key` | Same person |
| `deep_link.page` / destination | Same system-of-action page |
| `owner_role` | Same owner |
| resolution workflow | Same action class |

Workflows:

- `missing` → one case (“{Name} is missing N required documents”)
- `expired` / `expiring_soon` → renewal case
- `needs_review` → review case

Separate ranked cases when owner, destination, deadline class, or workflow/action class genuinely differs.

Grouped cases expose `grouped`, `grouped_count`, `grouped_document_types`, `grouped_member_ids`.  
UI displays backend groups only — **no client-side regrouping**.

Contract version: `action_inbox_wave1` **1.0.2**.

## Rollout gate (not final product behavior)

Phase 0 subject allowlist remains **Talal-only**:

- Approved subject: `WATHEFNI-96550252254` (Talal Fadhli)
- Approved viewer: Aziz `96599338566`

Other employees are **hard-excluded by this allowlist**, not ranked below a result limit.  
There is **no result-count cap** on the ranked list after filters/grouping.

**This allowlist is a controlled real-HR rollout gate.** It is not the intended long-term product visibility model. Widening requires a separate change-control (not part of this freeze).

## Explicit NO-GO

- Widening viewer or subject allowlists in this deploy
- Starting the next post-hire page refinement until owner visual review
- AI / mutations / Compliance or Analytics Wave 2 / Payroll money / Attendance ingest / Shifts manager expansion
- Reopening frozen module systems-of-action boundaries
- Client-side fake grouping that hides distinct owners/destinations/workflows

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-needs-attention-wave1-*`

See also:

- `ops/ACTION_INBOX_WAVE1_FREEZE.md`
- `ops/ACTION_INBOX_REAL_HR_CANARY_FREEZE.md`
- `ops/ACTION_INBOX_PHASE0_SAFETY_GATES.md`

**Production deploy stamp:** `20260804T055739Z`  
**Backup:** `/opt/wathefni/backups/production-pre-needs-attention-wave1-20260804T055739Z/`
