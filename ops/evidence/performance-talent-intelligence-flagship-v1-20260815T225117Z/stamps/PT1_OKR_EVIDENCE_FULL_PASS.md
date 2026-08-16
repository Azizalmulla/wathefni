# PT1 — OKR Operating Depth + Talent Evidence Index

**Status:** `PT1_OKR_EVIDENCE_FULL_PASS`  
**Date:** 2026-08-16  
**Programme:** Performance & Talent Intelligence Depth (PT)  
**Prior freeze:** `PERFORMANCE_TALENT_INTELLIGENCE_PT0_DESIGN_ACCEPTED`  
**Paused:** Production Readiness R7  
**Do not begin:** PT2 Configurable Talent Models + WHY Graph  
**Do not resume:** R7

---

## 0. What shipped

PT1 deepens frozen Performance C1 OKR authority into an operating system for objectives, and adds a reusable Talent Evidence Index.

Shipped:

- First-class OKR cycles (`perf_okr_cycles`) distinct from C2 review cycles
- Company → department → team → individual alignment tree with history
- Governed OKR update / check-in thread (check-in ≠ progress)
- Optional confidence/health as a separate configured signal
- Trajectory-ready timestamped history without trajectory labels
- `talent_evidence_ref` pointer index with provenance + consume contracts
- Explicit opt-in `okr_as_talent_evidence_v1`
- Employee App + Manager/HR Web + Setup EN/AR/RTL depth on existing surfaces

Did **not** ship (PT2+):

- Configurable Talent classification models
- Role-fit engine
- Talent Map
- Succession intelligence
- Trajectory labels (`accelerating` / `declining` / `emerging`)
- Assistant Talent tools

---

## 1. Binding authorities preserved

| Authority | PT1 rule |
|---|---|
| C1 `perf_objectives` / `perf_key_results` / measures / progress / owners / alignment links | Remain canonical. No `okr_objectives_v2`. No second Goals table. No `goal_kind` storage for OKRs. |
| C1 `compute_progress` / `objective_rollup` | Unchanged. No frontend progress truth. |
| C2 `perf_review_cycles` | Not reused as OKR cycles. |
| C3 check-ins | Reused when enabled. Never mutate KR progress. |
| C5 / C6 Talent | No potential / HiPo / readiness writes from PT1. |
| Wave 5 analytics | No second analytics engine. |
| R2–R6 + R5 surfaces | Remain valid. |
| R7 | Stays paused. |

---

## 2. Qualification

Run: `ops/qualify-pt1-okr-evidence.sh`

Evidence: `ops/evidence/pt1-okr-evidence-20260815T221631Z/`

Required proofs (unit + staging DB journeys A–H):

- C1 remains OKR SoT
- C2 review cycles not reused as OKR cycles
- OKR cycle authority exists
- Company → department → team → individual alignment
- Alignment does not imply score inheritance
- Objective → multiple KRs
- KR progress remains canonical
- Check-in ≠ progress authority
- Optional confidence ≠ progress
- Alignment / target / progress history reconstructable and trajectory-ready
- Evidence index stores references + provenance, not a second rating
- Indexing is idempotent
- Contradictory evidence coexists
- Source + Talent permission intersection
- Consume contracts default off
- OKR Talent evidence is explicit opt-in
- OKR evidence does not alter Potential / HiPo / readiness
- AI-SYNTHESIZED is not a classification input
- Employee-claimed skill is not silently verified
- Performance works with Talent OFF
- Talent works with Performance OFF
- JA / Learning / Assessments remain OFF without blocking PT1
- Tenant isolation
- EN and AR/RTL journeys
- No second analytics engine

---

## 3. Surfaces

**Employee App:** current OKR cycle, My Objectives, KR detail, measure-authoritative progress, separate update/check-in, alignment hint, history.

**Manager / HR Web:** team/company objectives, cycle administration (HR), alignment on request (not the default screen), updates, history.

**Setup:** OKR confidence policy + `okr_as_talent_evidence` consume contract. No infrastructure settings. No duplicate Performance policy truth.

**Talent:** evidence-index retrieval on the existing profile surface. No model / classification UI.

---

## 4. Rollback

```text
Do not drop PT1 tables — history must remain reconstructable.
Disable company Performance entitlement to stop OKR writes.
Set okr_as_talent_evidence=false in Setup (Talent consume contract OFF).
Optional: WATHEFNI_PERFORMANCE_GOALS_C1=off
R7 remains paused. PT2 must not start automatically.
```

---

## 5. Next

PT1 is frozen. Stop.

Owner may later charter **PT2 — Configurable Talent Models + WHY Graph**.

Do not begin PT2 automatically.  
Do not resume R7 automatically.
