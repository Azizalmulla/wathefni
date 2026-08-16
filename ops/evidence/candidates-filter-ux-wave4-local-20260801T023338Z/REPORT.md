# Candidates filter UX simplification — Wave 4 (local)

**Verdict: PASS**  
**Stamp:** `20260801T023338Z`  
**Deploy:** none  
**Wave 5:** not started  

## Scope

UI-only Candidates filter simplification. Preserved unchanged:

- filter logic / predicates (`applyCandidateFilterUpdate`, clear contracts)
- URL authority (Wave 3)
- saved views
- counts (`Filters (N)` = specialist/advanced count)
- permissions / tenant isolation
- classification as saved-view/session only
- backend behavior

## Implemented

| Requirement | Result |
|---|---|
| Default bar: Search, Job, Stage, Filters (N) | **PASS** |
| Active context chips (removable) | **PASS** |
| Follow-up needed × when active | **PASS** |
| Desktop side drawer for specialist filters | **PASS** |
| Mobile full-height filter sheet | **PASS** (`<md` full-bleed; `md+` end drawer) |
| Clear all easy to find | **PASS** (chip row + drawer footer) |
| Open/close never loses state | **PASS** (overlay toggles UI only) |

## Screenshots

| File | What |
|---|---|
| `screenshots/en-desktop-chips.png` | EN default bar + Follow-up / Completed / Email chips + Clear all |
| `screenshots/en-desktop-drawer.png` | EN desktop side drawer (3 active) |
| `screenshots/en-mobile-sheet.png` | EN mobile full-height sheet |
| `screenshots/ar-desktop-chips-rtl.png` | AR RTL chips + مرشحات (3) + مسح الكل |
| `screenshots/ar-mobile-sheet-rtl.png` | AR mobile sheet RTL |

## Tests

```
vitest: candidateFilterChips + candidateFilterAuthority + dashboardNavigation
        + CandidatesWave3Contract + CandidatesWave4Contract + App
→ 6 files / 40 tests PASS
```

Log: `verify/targeted-tests.log`

## Qualification gates

| Gate | Result |
|---|---|
| EN/AR + RTL | **PASS** |
| Desktop drawer / mobile sheet | **PASS** (screenshots) |
| Reload / back-forward URL authority | **PASS** (Wave 3 suite unchanged) |
| Saved views controls still present | **PASS** |
| Active filter counts `Filters (N)` | **PASS** |
| Deploy | **not done** |

## Files

- `apps/wathefni-dashboard/src/pages/CandidatesPage.tsx`
- `apps/wathefni-dashboard/src/lib/candidateFilterChips.ts` (+ test)
- `apps/wathefni-dashboard/src/pages/CandidatesWave4Contract.test.tsx`
- `apps/wathefni-dashboard/src/pages/CandidatesWave3Contract.test.tsx` (Clear all label)
- Local harness only: `filter-ux-harness.html`, `src/filter-ux-harness.main.tsx` (not in prod rollup input)
