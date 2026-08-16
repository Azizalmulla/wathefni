# Assessments Wave 3 — Canonical Report & Review Authority

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260728T024922Z`  
**Host:** `root@76.13.63.68`  
**Company:** WATHEFNI  
**Authority:** `assessment_report_presentation_v1`  
**Preserved:** Waves 1–2, page layout, admin/authoring surfaces, deterministic immutable scoring

---

## Final verdict

**PASS — Wave 3**

One backend report-presentation contract now drives HR. Assessment completed, scoring complete, report ready, HR review pending, and HR reviewed are separate truths. Scores match across surfaces, raw technical bands no longer leak to HR, and the review action is idempotent and audited. The raw “Official deterministic score JSON” HTML is superseded by a canonical presentation payload (`report_presentation`); final visual redesign remains a later wave.

---

## Canonical report contract

`assessment_report_presentation_v1`:

- `assessment_completed`, `scoring_complete`, `report_ready` (separate booleans)
- `review_state` (`not_applicable` / `unreviewed` / `reviewed`) + `review_label`
- `executive_summary`
- `scores { overall, job_match, ability_fit, competency_fit }`
- `labels { overall_band, job_match_band, role_profile }` (humanized)
- `strengths`, `growth_areas`
- `interview_probes`
- `review { state, label, reviewed_at, reviewed_by_user_id }`
- `next_human_action`, `allowed_actions`
- `report_version`, `norm_version`, `immutable`

Raw bands are mapped: `needs_review` → “Needs review”, `low` → “Needs review”, `mixed` → “Mixed evidence”, `development` → “Development area” (values shown under `growth_areas`, not as raw keys).

---

## Live record (AZIZ ALMULLA — Accounting)

| Field | Value |
|---|---|
| Overall | 48.4% |
| Job match | 46.7% |
| Ability fit | 41.7% |
| Competency fit | 52.9% |
| Report ready | true |
| Review state | reviewed (proof marked) |
| Norm version | `wathefni_ability_v1_local` |
| Next action | `view_report` |
| Allowed actions | `view_report` only after review |

Score parity: attempt list percent (48.4) ≡ report presentation overall (48.4) ≡ raw `job_match_percent` 46.7 mapped consistently.

---

## Proof (`20260728T024922Z`)

| Assertion | Result |
|---|---|
| One report authority (`report_presentation`) | **PASS** |
| One review authority | **PASS** |
| Score parity across surfaces | **PASS** (48.4 / 46.7 / 41.7 / 52.9) |
| Reviewed vs unreviewed clarity | **PASS** |
| No raw technical labels (`needs_review`/`low`/`mixed`/`development` as keys) | **PASS** (no leaks) |
| Immutable report versioning + norm version preserved | **PASS** |
| Mark reviewed only when valid report exists | **PASS** |
| Review action idempotent + audited | **PASS** |
| EN/AR + RTL | **PASS** |
| Permissions + tenant safety | **PASS** |
| Health 200 | **PASS** |
| Rollback / restore | **PASS** |
| No unrelated mutations | **PASS** |

Evidence: `/opt/wathefni/production-evidence/assessments-wave3-report-review-authority/20260728T024922Z/live-proof.json`

---

## Rollback / restore

| Step | Result |
|---|---|
| Backend rollback (`app.py`) | Health **200** |
| Backend restore (+ `assessment_report_presentation.py`) | Health **200**; proof PASS, no raw labels |

> Note: the first restore cycle kept a pre-rename copy of the presentation module; it was redeployed and the final live state passes all gates.

---

## Remaining limitations

- The HR report UI still uses the legacy HTML view for display; the canonical `report_presentation` payload is now the authority and a visual report surface is the next wave.
- `assessment_report_html` remains for backward compatibility during transition.
- Review state was marked on the live completed attempt for idempotency proof (real HR review by `aw3-proof`).
- Candidate profile and Ranking do not yet consume `report_presentation` directly; parity is proven via the shared score source.

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| One report authority | **PASS** |
| One review authority | **PASS** |
| Completed/scoring/report-ready/review separate | **PASS** |
| Score parity | **PASS** |
| No raw technical labels | **PASS** |
| Immutable versioning + norm version | **PASS** |
| Mark reviewed gated on valid report | **PASS** |
| Review idempotent + audited | **PASS** |
| EN/AR + RTL | **PASS** |
| Permissions/tenant safety | **PASS** |
| Health 200 + rollback/restore | **PASS** |
| No unrelated mutations | **PASS** |

**Stop after Wave 3.**
