# HR Mobile — Deep-nav / principal isolation debt

Stamp: release-blocker remediation after deep-navigation audit.

## Fixed (correctness — do not reopen without product change)

| Item | Resolution |
| --- | --- |
| Employee shell mounts `/hr/*` | Hard-deny: no Employee `Stack.Screen name="hr"`; sync `Redirect` in ModeRedirect; AuthGate redirects away from `/hr` |
| Dead `/ranking?position=` | Backend prehire priorities emit `/candidates` only |
| Soft-dead filtered `/candidates?…` | Stop emitting query filters the list does not honor |
| Hiring opens without capability gate | `destinationAvailable` on open + section filter (Home/Inbox parity) |
| Delivery Alerts open without gate | `destinationAvailable` before push |
| Leave / Candidate APIs entitlement-only | `_require_mobile_feature_action` fail-closed on list/detail/decision/CV |

Gate: `apps/wathefni-employee-mobile/scripts/verify-hr-deep-nav-blockers.py`

## SAFE POST-LAUNCH DEBT (visual / polish — not blockers)

| Item | Notes |
| --- | --- |
| Cream/black migration of leftover nested screens | Candidates list/detail chrome, interviews, employee detail, leave approval chrome if still nested/legacy |
| Honor candidate filters in mobile list | Optional future: implement filters instead of unfiltered `/candidates` |
| Dedicated `/ranking` mobile surface | Only if product wants role-priority ranking; until then keep `/candidates` |
| Unified confirmation chrome across leave/candidate/tasks | Consistency debt |
| Interview notes confirm UX | Existing product debt |

Do **not** block release on cream migration once correctness gates are green.
