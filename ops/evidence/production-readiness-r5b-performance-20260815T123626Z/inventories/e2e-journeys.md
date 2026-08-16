# R5B E2E journeys A–F

Proved on staging DB tenant `R5BA7D377` (`smoke-test-r5b-performance-surface-db.py`). Talent OFF throughout.

## A — Goals

1. HR creates measure + Objective + two Key Results
2. Employee sees own objective
3. Progress recorded; decorative `progress_pct` rejected
4. Backend rollup matches surface rollup (shared C1 math)
5. Other employee empty (not error)
6. Manager empty-scope fail-closed empty; in-scope manager sees the goal
7. Objective history + KR versions reconstructable

## B — Review

1. Scale + template + cycle configured
2. Launch freezes snapshot (`snapshot_frozen`)
3. Post-launch setup mutation rejected
4. Employee self-review submitted
5. Manager review submitted
6. Layers not collapsed; self and manager preserved separately
7. Cycle close produces final; self still distinct after close
8. Employee workspace shows allowed final outcome only

## C — 360

1. 360 enabled on cycle; request assigned
2. Below minimum-response threshold: aggregate fail-closed
3. After threshold: aggregate available
4. Employee does not see respondent identities
5. Raw 360 without `performance.sensitive` forbidden

## D — Calibration

1. Calibration session created
2. Authorized facilitator sees session (pre-cal vs calibrated distinct)
3. Unauthorized calibration forbidden
4. Prior self / manager / 360 layers remain after close

## E — Development

1. Development plan created with Learning-off (`require_learning` false)
2. Development action created
3. Employee sees own development
4. Learning completion does not close the development action

## F — Modularity

1. Talent still not required / not enableable
2. Employee + HR workspace `talent_visible` false; no `hipo` key
3. Competencies optional OFF after sync — Performance still works
4. Module disable: history preserved; new work blocked
5. Performance remains catalog-enableable; Talent does not
