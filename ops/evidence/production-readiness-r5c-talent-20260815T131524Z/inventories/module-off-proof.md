# R5C module-off proof

## Talent disabled after historical use

Staging DB after journeys A–F:

1. `sync_catalog_entitlement(..., enabled=False)`
2. Existing profile still readable (`history preserved after disable`)
3. New dimension fact returns not-ok (`talent_profile_company_not_enabled`)

Disable semantics:

- Hide new surfaces (nav + employee feature contract)
- Block new Talent work (C5/C6 `_entitled`)
- Preserve historical Talent state (profiles, facts, assessments, reviews, slates, HiPo versions)
- No new Talent notifications (R4 `flow=talent` → source module `talent`)

## Composition / optionality

| Cell | Proof |
|---|---|
| Talent only | C5/C6 journeys with Performance slice flags OFF |
| Talent + Performance OFF | Journey A |
| Talent + Performance ON | Journey B — evidence link only |
| Talent + Recruiting OFF | Journey F first half |
| Talent + Recruiting ON | Journey F handoff, `writes_talent_pool=false` |
| Talent + JA unavailable | `job_architecture_required=false`; JA still `customer_enableable=false` |
| Talent + Learning unavailable | `learning_required=false`; C3 development reused |
| Performance still ON independently | R5B staging DB 62/0; Performance still strips HiPo |

## Fail-closed HTTP

Unreleased Wave 6 namespaces remain 404 `capability_not_released`. Talent namespaces are no longer stolen by the fail-closed adapter.
