# R5C E2E journeys A–F

Proved on staging DB tenant `R5CB840DF` (`smoke-test-r5c-talent-surface-db.py`).

## A — Talent without Performance

1. HR creates a governed Talent profile (`master_talent_score` is null)
2. Explicit dimension evidence added (`strength` / `hr_assessed`)
3. Potential framework + explicit potential assessment (`performance_equals_potential` is false)
4. Talent review created and prepared with frozen population
5. Dimension history intact

Performance slice flags were OFF for this journey.

## B — Performance optional integration

1. `performance_evidence_consume` enabled
2. Sealed Performance subject linked as optional evidence
3. Link `becomes_potential` is false
4. No automatic HiPo designation
5. Prior explicit potential assessments still present

## C — Succession

1. Critical / target role designated
2. Succession plan created
3. Two successors nominated with different target-specific readiness (`ready_now` vs `ready_lt_1y`)
4. Slate has ≥2 nominations; `global_readiness_score` is null
5. Authorized HR path; manager without `talent.succession` is 403

## D — 9-box

1. Nine-box enabled + config created (`canonical_employee_box` false)
2. Projection from configured axes (`available`, `does_not_imply_hipo`)
3. Explicit HiPo decision recorded separately (`auto_inferred` false, `top_right_implies_hipo` false)
4. Potential assessments preserved after projection

## E — Employee self

1. Employee updates career aspiration
2. Employee workspace hides potential / HiPo / succession
3. Employee potential API returns `potential_hidden_from_employee`
4. HTTP `/app/talent` body has no `potential` / `hipo` / `succession` keys

## F — Recruiting optional

1. Recruiting OFF: mobility surface works; `silent_candidate_creation` false; interest is not an application
2. Recruiting ON (`pre_hiring`): `handoff_available` true; `writes_talent_pool` false
3. Module disable after use: history preserved; new dimension facts blocked
