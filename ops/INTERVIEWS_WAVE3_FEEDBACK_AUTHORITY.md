# Interviews Wave 3 — Canonical Feedback Authority & Reconciliation

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260728T014120Z`  
**Host:** `root@76.13.63.68`  
**Company:** WATHEFNI  
**Authority:** `interview_presentation_v1.feedback`  
**Preserved:** Wave 1 state model, Wave 2 allowed-actions contract, drawer layout, colors, unrelated pages

---

## Final verdict

**PASS — Wave 3**

One canonical feedback state (`not_started` / `draft` / `submitted` / `complete`) now drives HR presentation, counts, and allowed actions. Legacy `feedback_status` / `human_feedback_status` / `notes_status` no longer independently create HR-facing truth. The conflicting completed interview (`feedback_status=feedback_complete`, `human_feedback_status=notes_pending`, notes saved) now correctly reads **Feedback not started / needs feedback**. Notes do not complete feedback. Review completion and feedback completion remain separate. Structured submission is idempotent/immutable; permission and tenant boundaries hold.

---

## Canonical feedback contract

`interview.feedback`:

| Field | Meaning |
|---|---|
| `state` | `not_started` / `draft` / `submitted` / `complete` |
| `label` | HR-facing label |
| `complete` | canonical completion (structured submission, not reopened) |
| `submitted` | structured submission exists |
| `needs_feedback` | true when state is `not_started` / `draft` |
| `notes_present` | free-text notes exist (never completion) |
| `submission_id` / `submission_status` | backing structured submission |
| `legacy_conflict` | legacy mirror disagrees with canonical state |

Derivation precedence: structured `interview_feedback_submissions` → `human_feedback_status` → legacy `feedback_status` (hint only) → notes (never completion). Reopened submissions are `draft`, not complete.

---

## Reconciliation rules

- No history deleted; no feedback invented.
- Notes alone never complete feedback.
- Marking async video reviewed does not complete structured feedback.
- Legacy complete + human pending + notes → canonical `not_started`, `needs_feedback=true`, `legacy_conflict=true`.
- If no valid structured feedback exists, state stays incomplete.

---

## Before / after live records

| Interview | Before | After (Wave 3) |
|---|---|---|
| `369997d8` live completed | `feedback_status=feedback_complete` but human pending; Completed + Needs feedback overlap | `feedback_state=not_started`, `needs_feedback=true`, allowed: `write_notes` |
| `669366ae` async completed | Notes pending, review actions mixed | `feedback_state=complete` after proof submission; allowed: `view_feedback`, `open_candidate` |
| `06e4a65d` async consented | review actions possible pre-evidence | `feedback_state=not_started`; no review actions (0 answers) |
| `8552e251` async link sent | same | `feedback_state=not_started`; resend/cancel/open only |

Count/tab parity: `canonical_feedback_counts` = needs_feedback **2**, complete **0** before proof submission; completed interviews still needing feedback remain in Completed but clearly show **Feedback not started**. Feedback-complete rows are excluded from Needs feedback.

---

## Proof highlights

- One authority returned by API for every interview → **PASS**
- Conflicting legacy row is not feedback-complete; needs feedback → **PASS**
- Needs feedback excludes feedback-complete rows → **PASS**
- Notes do not count as completed feedback → **PASS**
- Review completion ≠ feedback completion → **PASS**
- Structured submission idempotent/immutable (second final submit rejected; canonical flips to complete) → **PASS**
- Permission/tenant boundaries preserved → **PASS**
- EN/AR + RTL → **PASS**
- Health 200 → **PASS**
- Rollback / restore → **PASS**
- No unrelated mutations (single intentional feedback submission for proof on `669366ae`) → **PASS**

Evidence: `/opt/wathefni/production-evidence/interviews-wave3-feedback-authority/20260728T014120Z/live-proof.json`

---

## Rollback / restore

| Step | Result |
|---|---|
| Backend rollback (`app.py`, presentation) | Health **200** |
| Dashboard rollback → previous asset | Health **200** |
| Backend restore | Health **200** |
| Dashboard restore | Health **200**; asset `dashboard-BtxR3V_8.js`; post-restore states correct |

---

## Remaining limitations

- One feedback submission was intentionally created during proof (`669366ae`) to verify idempotency/immutability; it is real structured feedback and now canonical complete for that interview.
- Overview signals were not rewired in this wave (no Overview changes were requested here); counts for Interviews use the canonical authority.
- `view_feedback` is exposed as an allowed action but the drawer does not yet open a dedicated structured feedback view (uses existing notes/summary panels).
- Candidate profile consumes interview data through the same payload path; no separate profile redesign was done.

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| One canonical feedback authority | **PASS** |
| Legacy mirrors do not create HR truth | **PASS** |
| Notes ≠ completed feedback | **PASS** |
| Review completion ≠ feedback completion | **PASS** |
| Reconciliation of conflicting records | **PASS** |
| Needs feedback excludes complete | **PASS** |
| Count/tab parity with canonical authority | **PASS** |
| Idempotent/immutable submission | **PASS** |
| Permission/tenant boundaries | **PASS** |
| EN/AR + RTL | **PASS** |
| Health 200 + rollback/restore | **PASS** |
| No unrelated mutations | **PASS** |

**Stop after Wave 3.**
