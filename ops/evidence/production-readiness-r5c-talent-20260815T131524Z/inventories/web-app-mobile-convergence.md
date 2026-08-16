# R5C Web / App convergence

HR Mobile is not in the Talent ship set.

| Concept | HR Web | Employee App | Same authority |
|---|---|---|---|
| Workspace | `TalentWorkspace` Overview | `/talent` hub | C5/C6 via `talent_surfaces` |
| Profile | People tab + profile detail | `/talent/profile` stripped | C5 profile + facts |
| Evidence | People / add evidence | Employee-declared facts only | C5 dimension facts |
| Potential / HiPo | People / reviews when authorized | Hidden | C5/C6; employee strip |
| Talent review | Reviews tab | Not exposed | C6 reviews |
| Succession slate | Succession tab | Not exposed | C6 nominations |
| Readiness | Per-role on slate | Not exposed | C6 target-specific |
| 9-box | Derived tab | Not exposed | C6 projection |
| Mobility | Mobility tab + recruiting handoff | Self preference only | C5 facts; no `talent_pool` write |
| Development | Development context | Listed without judgments | C3 reuse |
| Empty / error / forbidden | `ResourceState` | `QuietEmpty` / `ErrorState` / `FeatureUnavailableState` | R4 truth states |
| Module off | Nav + workspace hidden | `FeatureUnavailableState` | catalog + C5/C6 settings |

Web helpers (`getTalentWorkspace`, `getTalentProfiles`, `getTalentProfile`, `getTalentSlate`, `postTalentJson`) call `/dashboard/posthire/talent/...` only — not recruiting `getTalentPool*` helpers.
