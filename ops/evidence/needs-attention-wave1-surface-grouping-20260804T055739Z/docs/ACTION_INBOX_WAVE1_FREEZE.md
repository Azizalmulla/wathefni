# Unified Action Inbox Wave 1 — Freeze

**Gate:** `PROD_SYNTHETIC_ACTION_INBOX_WAVE1_GO`  
**Phase 0-B:** `PROD_ACTION_INBOX_PHASE0_SAFETY_GO`  
**Real-HR canary:** `PROD_ACTION_INBOX_REAL_HR_CANARY_GO` → `ops/evidence/action-inbox-real-hr-canary-20260803T175831Z/`  
**Needs Attention surface + grouping:** `PROD_NEEDS_ATTENTION_WAVE1_SURFACE_GROUPING_GO` → `ops/NEEDS_ATTENTION_WAVE1_SURFACE_AND_GROUPING_FREEZE.md`  
**Freeze:** **GO** for controlled real-HR use (Aziz viewer / Talal subject only)

## Frozen posture

- Read-only composition; frozen modules remain systems of action
- Inbox **composes and ranks only** — frozen modules remain systems of action
- Same-employee compliance findings that share destination + owner + workflow are **grouped** (contract 1.0.2)
- User-facing label: **Needs Attention** (page id remains `inbox`)
- `WAVE1=1` · `SYNTHETIC_ONLY=1` · `EXCLUDE_PAYROLL=1` · markers `AIW1`
- `mutates_records`: **false**
- Viewer allowlist: `96599338566` (Aziz) — **rollout gate, not final product visibility**
- Subject allowlist: `WATHEFNI-96550252254` (Talal) — **rollout gate, not final product visibility**
- Alerts & Delivery owns notifications; Hiring Reports separate
- No AI; no Compliance/Analytics Wave 2; no Payroll money; no Attendance ingest; no Shifts manager expansion

## Explicit NO-GO

- Widening viewer or subject allowlists
- Broad HR / manager rollout
- AI / mutations / Wave 2 / money / ingest / shifts-manager expand
- Reopening frozen module boundaries

See also `ops/ACTION_INBOX_REAL_HR_CANARY_FREEZE.md` and `ops/NEEDS_ATTENTION_WAVE1_SURFACE_AND_GROUPING_FREEZE.md`.
