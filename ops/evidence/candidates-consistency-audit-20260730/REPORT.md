# Candidates Consistency Audit — Stage Buckets, Filters & Talent Pool

**Date:** 2026-07-30  
**Scope:** Candidates follow-up only (audit; **no implement, no deploy**)  
**Tenant proof:** `WATHEFNI` production (unified Candidates on)  
**Verdict:** **FAIL** vs a single consistent stage-bucket / filter / opened-results contract  

Assessments / Ranking: **not touched**. No visual redesign.

Evidence: `ops/evidence/candidates-consistency-audit-20260730/live-proof.json`

---

## 1. Exact current authorities (as coded)

Candidates has **two orthogonal axes**:

| Axis | UI | Authority |
|---|---|---|
| **View** (job / record state) | pills: All / With a job / No job assigned / Hired / Archived / Restricted | `unified_candidates.view_predicate_sql` |
| **Stage** (lifecycle) | toolbar `<Select>` | Frontend expand → `a.status = ANY(...)` |

List `total` for the opened query uses the **same WHERE** as the page list (**PASS** for filter↔count). View pills have **no** badge counts.

### A. Stage display (list badge)

| Layer | Definition |
|---|---|
| Function | `candidateListStageBucket` → `candidateListStageLabel` |
| File | `apps/wathefni-dashboard/src/lib/candidatesListPresentation.ts` ~308–336 |
| Rule | Held Talent Pool → **force `new`**; else `canonical_stage \|\| status`; unknown → `new` |
| Offer branch | raw `offered` / `offer_sent` → `offer` **only if** that string wins over canonical |

```308:326:apps/wathefni-dashboard/src/lib/candidatesListPresentation.ts
export function candidateListStageBucket(application: ApplicationSummary): string {
  if (application.record_state === 'archived' || application.status === 'import_archived') return 'archived'
  if (isGeneralCandidate(application)) {
    // Held intake without a job is a profile state, never an application stage.
    return 'new'
  }
  const raw = String(application.canonical_stage || application.status || '').toLowerCase()
  if (['offered', 'offer_sent'].includes(raw)) return 'offer'
  // ... awaiting_cv set → new, RFR, shortlisted, interview, terminals ...
  return 'new'
}
```

Backend already publishes `status_display: "Talent Pool"` for held rows (`unified_candidates.enrich_application_summary`); the **list Stage column ignores it** and shows **New** (locked by tests).

### B. Stage filter (toolbar)

| Toolbar label | API value | Expanded `a.status` set |
|---|---|---|
| All stages | `''` | none |
| **New** | `awaiting_cv` | `awaiting_cv`, `cv_processing`, `cv_received`, `screening`, `cv_request`, `cv_upload` |
| Ready for review | `ready_for_review` | `ready_for_review`, `screening_complete`, `review_pending` |
| Shortlisted | `shortlisted` | `shortlisted` only |
| Interview | `interview` | `interview`, `scheduled` |
| Hired / Rejected / Withdrawn | same | singleton |

**Not in toolbar:** Offer, Archived (as stage), Talent Pool / `needs_role` / `import_review`, `reviewed` (label exists, never bucketed).

Expand path: `useDashboardServerState.ts` ~209–213 → comma list → `_append_prehire_application_status_filter` (`app.py` ~47803–47826, 47918).

### C. View pills (not Stage)

| Pill | `view=` | Predicate (summary) |
|---|---|---|
| All | `all` | held active **or** live; exclude archived/restricted |
| With a job | `active` | live pipeline; not hired/rejected/withdrawn/archived/restricted |
| **No job assigned** | `talent_pool` | `status ∈ (needs_role, import_review)`; not restricted/archived |
| Hired / Archived / Restricted | matching | governance / status |

Source: `unified_candidates.py` ~29–45, 362–401; UI `CandidatesTable.tsx` ~25–32.

### D. Counts

| Metric | Behavior |
|---|---|
| List `total` | `COUNT(*)` with **identical** WHERE as opened list — **aligned** |
| Per-stage tab counts | **None** (Stage is a select, not counted segments) |
| View pill counts | **None** |
| Ownership counts | Orthogonal (`mine` / `unassigned`) — not Stage |

---

## 2. Talent Pool decision (audit conclusion)

**Talent Pool is a job-assignment / intake record state, not a lifecycle stage.**

Evidence:

1. Backend: `needs_role` / `import_review` are `INTAKE_STATUSES` — explicitly excluded from `APPLICATION_STAGES` (`recruiting_lifecycle.py` ~42–43, 154–155).
2. `record_state = talent_pool`; `status_display = "Talent Pool"` (`unified_candidates.py` ~263–273, 580–582).
3. Module docstring: unified Candidates is a read model; lifecycle predicates remain frozen.
4. UI View pill is labeled **“No job assigned”**, not a Stage.
5. Display code comment admits held intake is “never an application stage” — then incorrectly paints Stage as **New**.

**Do not force Talent Pool into Stage filter New.** That would conflate intake with early CV lifecycle and break the View axis. Correct contract: Stage badge must not claim “New” for Talent Pool; job column / View already express “no job.”

---

## 3. Offer audit

| Aspect | Current behavior |
|---|---|
| Lifecycle authority | `offered` / `offer_sent` → **`shortlisted`** (`LEGACY_STATUS_MAP`) |
| Serialize | `canonical_stage = normalize_stage(status) or status` → live Offer rows become **`shortlisted`** |
| Display intent | Separate **Offer** bucket if raw is offer_* |
| Filter | **No Offer option**; Shortlisted does **not** expand to offer_* |
| Live WATHEFNI | `0` rows with raw `offer_sent`/`offered`; **1** app with `employment_offers` row is status **`shortlisted`**, display **Shortlisted** |

**Verdict:** Offer is display-oriented and mostly **dead** under live canonicalization. Employment Offer is a **separate module**, not Stage toolbar authority.

---

## 4. Stage-by-stage display / filter parity

| Bucket | Display | Filter includes same statuses? | Opened list ≡ filter? | Live note (view=all) |
|---|---|---|---|---|
| New | CV-early **plus** Talent Pool forced New **plus** unknown fallthrough | CV-early only — **no** held | Yes for filter set | New filter **2**; Talent Pool **2** also show New but excluded |
| Ready for review | RFR + legacy | Yes | Yes | 3 |
| Shortlisted | `shortlisted` (and live offers) | `shortlisted` only | Yes | 3 |
| Interview | interview + scheduled | Yes | Yes | 0 |
| Offer | rare / overridden | **No filter** | N/A | 0 raw; offers show Shortlisted |
| Hired / Rejected / Withdrawn | exact | Yes | Yes | hired 3; rej/wd 0 |
| Archived | record_state / import_archived | **View=archived**, not Stage | Via view | 0 |
| Talent Pool | Displayed as **New** | **View=talent_pool** | Via view | 2; badge mismatch |

---

## 5. Edge coverage

| Case | Behavior | Parity risk |
|---|---|---|
| **Unassigned (recruiter owner)** | `gov.recruiter_owner_user_id` empty; live **12**, Talent Pool **2** | Orthogonal to Stage / Talent Pool — must not merge into New |
| **Multiple applications** | Person group; Stage badge = **primary** app only; job may show “N applications” | Secondary apps’ stages hidden on list |
| **Archived** | View + badge Archived; excluded from All by default | OK if users use View, not Stage |
| **Restricted** | Restricted view (elevated); excluded elsewhere | Held+restricted still `isGeneralCandidate` → Stage **New** while restricted |
| **Legacy aliases** | Filter expand covers screening → New, screening_complete → RFR, scheduled → Interview | Offer aliases intentionally map to shortlisted in lifecycle, not Offer filter |
| **Unknown status** | Displays New; only visible under All stages | Same class of badge/filter lie as Talent Pool |

---

## 6. Live proof (WATHEFNI, unified on)

| Check | Result |
|---|---|
| View `talent_pool` total | **2** (`needs_role`, `status_display=Talent Pool`) |
| Those 2 Stage display buckets | **New** |
| Stage filter New total | **2** (`awaiting_cv`, `screening` only) |
| Talent Pool rows in New filter | **0** |
| Gap | **2 rows** badge New ≠ New filter results |
| Offer Stage filter | **absent** |
| Employment-offer app Stage | **Shortlisted** (canonical) |
| List total ≡ opened Stage filter SQL | **PASS** |

---

## 7. Root cause

1. **Primary:** Stage **display** reuses the label **New** for Talent Pool (job-assignment state) while Stage **filter New** is only early CV lifecycle statuses — intentional product comment, incorrect shared label.
2. **Secondary:** **Offer** is a list display bucket with no filter, while lifecycle authority collapses offer → **shortlisted**, so badge and filter cannot agree.
3. **Tertiary:** Backend `status_display: "Talent Pool"` is ignored by the list Stage column; tests lock the New override.
4. **Not a root cause:** list `total` vs opened filter SQL (already aligned). Missing view-pill counts are a UX gap, not a predicate bug.

---

## 8. Exact files

| Area | Path |
|---|---|
| Display + filter maps | `apps/wathefni-dashboard/src/lib/candidatesListPresentation.ts` |
| Stage select UI | `apps/wathefni-dashboard/src/pages/CandidatesPage.tsx` |
| View pills + row badge | `apps/wathefni-dashboard/src/components/candidates/CandidatesTable.tsx` |
| Filter expand → API | `apps/wathefni-dashboard/src/lib/query/useDashboardServerState.ts` |
| View SQL + enrich | `wathefni-orchestrator/unified_candidates.py` |
| Status filter + count | `wathefni-orchestrator/app.py` (`prehire_applications_query`, `_append_prehire_application_status_filter`) |
| Canonical / Offer map | `wathefni-orchestrator/recruiting_lifecycle.py` |
| Profile stage | `apps/wathefni-dashboard/src/lib/candidateProfilePresentation.ts` |
| Locked mismatch tests | `candidatesListPresentation.test.ts` (Talent Pool → New; Offer filterValue `''`) |

---

## 9. Proposed Candidates stage-bucket contract (for approval)

Named scopes — display, filter expand, and opened list/total must cite the same sets. **No UI redesign in the audit**; wiring only when approved.

### Axis separation (required)

| Axis ID | Meaning | Must not mix |
|---|---|---|
| `candidates.view.*` | Job / governance record state | All, with_job, no_job (Talent Pool), hired, archived, restricted |
| `candidates.stage.*` | Application lifecycle only | New → … → Hired / Rejected / Withdrawn |

**Talent Pool / no job** stays on `candidates.view.no_job` (`needs_role`, `import_review`). It is **not** a Stage and must **not** display as Stage **New**.

### Stage buckets (lifecycle only)

| Bucket ID | Display label | Canonical + legacy `a.status` (filter = display membership) |
|---|---|---|
| `candidates.stage.new` | New | `awaiting_cv`, `cv_processing`, `cv_received`, `screening`, `cv_request`, `cv_upload` |
| `candidates.stage.ready_for_review` | Ready for review | `ready_for_review`, `screening_complete`, `review_pending` |
| `candidates.stage.shortlisted` | Shortlisted | `shortlisted` **and** legacy `offered`, `offer_sent` (until Offer is a real lifecycle stage) |
| `candidates.stage.interview` | Interview | `interview`, `scheduled` |
| `candidates.stage.hired` / `rejected` / `withdrawn` | same | singleton |

Rules:

1. **Display bucket ≡ filter membership** for every lifecycle row (same status sets, including legacy).
2. **Opened results `total` ≡ same predicate** (already true; keep).
3. **Talent Pool:** Stage column shows a non-lifecycle placeholder (e.g. em dash / “—” / omit stage) **or** surfaces `record_state` without using the New label — **not** New. Job column / View pill remain the authority for “no job.”
4. **Offer:** Until Offer is promoted in `APPLICATION_STAGES` + transitions, **do not** keep a display-only Offer bucket. Map offer_* → **Shortlisted** in both display and filter (matches `normalize_stage`). Employment Offer module stays separate.
5. **Archived / Restricted:** View axis only; Stage badge may mirror archived/restricted for clarity but Stage toolbar need not duplicate View.
6. **Unknown / legacy unmapped:** Prefer explicit “Unknown” (or All-only) over silent New.
7. **Multi-app:** Document that list Stage = primary application; no change required for this contract beyond consistency of that primary.

### Optional later (out of this audit)

- View pill counts using `view_predicate_sql`.
- First-class Offer lifecycle stage (schema + transitions + filter) — separate product decision.

---

## 10. PASS / FAIL

| Check | Result |
|---|---|
| Stage display ≡ Stage filter membership for every row | **FAIL** (Talent Pool → New; Offer display-only / dead) |
| Stage filter New includes `needs_role` / `import_review` | **N/A / must remain false** — Talent Pool is not New |
| Talent Pool treated as job-assignment, not forced into New | **FAIL today** (forced New); **correct decision = exclude from New** |
| Offer display ≡ Offer filter | **FAIL** (no filter; canonical → shortlisted) |
| Other lifecycle stages (RFR, Shortlisted, Interview, terminals) display ≡ filter | **PASS** (with legacy expansions) |
| Opened list `total` ≡ filter SQL | **PASS** |
| View pill counts ≡ opened View | **N/A** (no counts) |
| Unassigned owner ≠ Talent Pool | **PASS** (separate) |
| Automated contract locking display≡filter for Talent Pool / Offer | **FAIL** (tests currently lock the mismatch) |
| Implementation / deploy | **NOT STARTED** (audit only) |

---

## 11. Approval gate

Do **not** implement or deploy Candidates stage fixes until this contract is approved. After approval, implementation should:

1. Stop mapping Talent Pool / held general candidates to Stage **New**.
2. Align Offer with Shortlisted (or introduce a real Offer stage end-to-end — product choice).
3. Keep View `talent_pool` as the sole no-job authority.
4. Add regression tests that prove display bucket ∈ filter set for each lifecycle status, and prove Talent Pool is **not** in Stage New.
5. Re-run live WATHEFNI matrix (2 Talent Pool rows, New filter, Shortlisted + employment offer).

**Out of scope:** Assessments, Ranking, Jobs (already shipped), visual redesign.
