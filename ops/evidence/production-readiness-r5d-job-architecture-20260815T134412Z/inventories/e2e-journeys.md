# R5D E2E journeys A–G

Proved on staging tenant `R5DA71FF7` (`R5D_JOB_ARCHITECTURE_SURFACE_DB_PASS`, 81/0).

| Journey | Result |
|---|---|
| A Authoring | family → function → profile → grade → level → publish → retrieve |
| B Legacy mapping | unique title/grade auto-map; raw values preserved; canonical assignment added |
| C Ambiguity | two published “Engineer” profiles → `unmapped_ambiguous`; unmatched “Chief Wizard” → `unmapped_none`; human resolve to `manual` with raw preserved |
| D Career path | promotion / lateral / specialist / manager edges; `is_eligibility=false`; eligibility_score forbidden |
| E Talent | C6 critical role + optional JA ref; JA payload has no HiPo/potential; Talent still `job_architecture_required=false` |
| F Recruiting | optional `recruiting_opening` ref; editing note does not rewrite JA profile name/version |
| G History | rename bumps `effective_version`; stable id + raw mapping + assignment remain reconstructable |
