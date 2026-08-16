# R5C surface inventory

## HR Web

| Surface | Path / mount | Notes |
|---|---|---|
| Talent workspace | `apps/wathefni-dashboard/src/posthire/TalentWorkspace.tsx` via PostHire `case 'talent'` | Overview, People, Reviews, Succession, Mobility, 9-box |
| Setup policy owner | `Wave4TalentPoliciesCard` `scope="talent"` | Deep-link `#classic-wave4-talent`. Performance card remains mounted separately |
| Nav | `workspaceCapability` `nav.talent` | Module + `talent.read` gated |

IA:

- Overview — review work, succession gaps, readiness distribution, key roles. No invented score.
- People — governed profiles, evidence, potential / HiPo where authorized, readiness, development context.
- Talent Reviews — governed process, explicit signals, decisions / history.
- Succession — role-based, multiple successors, target-specific readiness, gaps.
- Mobility — internal interest; Recruiting optional handoff. Distinct from `talent_pool`.
- 9-box — optional derived visualization. Never canonical storage.
- Configuration — `ConfigureInSetupBanner` only.

## Manager (same HR Web workspace, scoped)

| Surface | Scope source | Forbidden |
|---|---|---|
| Team Talent profiles | `context_manager_employee_keys` | Company-wide Talent |
| Permitted signals | `talent.manage` within scope | Compensation |
| Talent-review participation | `talent.review` | Unrestricted HiPo lists without `talent.sensitive` |
| Succession nominations | `talent.succession` | Unrelated succession plans |
| Development / mobility context | manager scope | Empty scope is fail-closed empty, not company-wide |

## Employee App

| Route | Journey |
|---|---|
| `/talent` | Limited hub — facts / skills / mobility counts |
| `/talent/profile` | Self-service aspirations, skills, mobility preference |

Composition: `MODULE_SURFACES.talent`, Home tile when entitled, `FeatureUnavailableState` when module off. EN + AR (`talent.*` including `hiddenJudgments`).

Employee never sees: potential, HiPo, succession slate, private readiness, 9-box, confidential manager / HR notes.

## HR Mobile

Not required for Talent enablement. No `/hr/talent` admin. Standalone `wathefni-hr-mobile` remains retired.

## Setup

Customer-facing Talent enablement remounted after `customer_enableable=true`.

Performance Setup card remains mounted. Wave 6 cards remain omitted.
