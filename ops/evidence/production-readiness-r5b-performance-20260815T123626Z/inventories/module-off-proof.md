# R5B module-off and composition proof

## Performance disabled after historical use

Staging DB:

- History preserved after disable
- New work blocked when disabled
- Employee feature gate + C1–C4 entitlement_off / company_disabled → 403, not empty lists

Customer UX contract (composition + nav):

- HR Web nav `nav.performance` disappears when module off
- Employee Home tile disappears; deep link → `FeatureUnavailableState`
- HR Mobile `/hr/performance` destination unavailable
- R4 centralized suppression: no new `flow=performance` notifications
- No second Performance inbox

## Composition matrix (qualified)

| Composition | Result |
|---|---|
| Performance only | Employee Home shows exactly the Performance tile (`composition-shapes-test.js`) |
| Performance + Recruiting | Distinct SKUs; Talent still unreleased (not recruiting `talent_pool`) |
| Performance + Payroll | Catalog `recommended_with` empty; both independently enableable |
| Performance + Talent OFF | Required path. `talent_visible` false; `strip_talent`; Talent HTTP 404 `capability_not_released` |
| Performance + competencies OFF | Honest empty competencies; reviews/goals still work |
| Performance + competencies ON | Versioned framework / mappings from C3 |
| Talent completely optional | `customer_enableable("talent")` is false; not a catalog SKU |

## Unreleased neighbours stay fail-closed

Live staging:

- `/dashboard/posthire/talent` 404 `capability_not_released`
- `/dashboard/job-architecture` 404 `capability_not_released`
- `/app/talent` 404 `capability_not_released`
