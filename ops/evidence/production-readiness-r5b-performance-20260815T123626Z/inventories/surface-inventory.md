# R5B surface inventory

## HR Web

| Surface | Path / mount | Notes |
|---|---|---|
| Performance workspace | `apps/wathefni-dashboard/src/posthire/PerformanceWorkspace.tsx` via PostHire | Overview, Goals, Reviews, Calibration (authorized), Development |
| Setup policy owner | `Wave4PerformancePoliciesCard` `scope="performance"` | Deep-link `#classic-wave4-performance`. Talent toggles omitted |
| Nav | `workspaceCapability` `nav.performance` | Module + `performance.read` gated |

IA:

- Overview — active cycle, completion, overdue / needs-attention, upcoming dues. No fake metrics.
- Goals — Objective → measurable KRs, progress from backend, alignment, history.
- Reviews — cycles, launch / readiness, self / manager / 360 kept separate.
- Calibration — HR / `performance.calibrate` only. Pre-cal vs calibrated vs sealed distinct.
- Development — plans / actions / evidence. Learning-off copy. Does not break when L&D is unreleased.
- Configuration — `ConfigureInSetupBanner` only. No duplicate policy editor.

## Manager (same HR Web workspace, scoped)

| Surface | Scope source | Forbidden |
|---|---|---|
| Team goals | `context_manager_employee_keys` | Company-wide Performance |
| Review queue | `/dashboard/performance/manager/queue` | Calibration unless `performance.calibrate` |
| Review detail / submit | manager assignment | Confidential 360 identity when anonymous |
| Check-ins / feedback | manager scope | Talent |
| Development follow-up | manager scope | Cycle admin (launch / configure / close) |

Empty manager scope is fail-closed empty, not an error and not company-wide.

## Employee App

| Route | Journey |
|---|---|
| `/performance` | Hub — entitled, calm |
| `/performance/goals` | My Goals |
| `/performance/goals/[id]` | Objective / KR detail + progress update when policy allows |
| `/performance/reviews` | My Reviews |
| `/performance/reviews/[id]` | Self-review / requested 360. Cannot submit manager reviews |
| `/performance/check-ins` | Feedback / check-ins |
| `/performance/development` | Development actions + history |

Composition: `MODULE_SURFACES.performance`, Home tile when entitled, `FeatureUnavailableState` when module off. EN + AR (`performance.*` including `talentOff`).

Employee never sees: manager drafts, other employees' ratings, anonymous respondent identity, Talent / HiPo / potential.

## HR Mobile (thin cobundle)

| Route | Journey |
|---|---|
| `/hr/performance` | Pending review queue |
| `/hr/performance/[reviewId]` | Review detail + rating picker + submit |
| Home / Inbox deep-link | `destinationAvailable` includes `/performance` paths |

Not cloned: cycle configuration, calibration administration, full Goals workspace.

Standalone `wathefni-hr-mobile` remains retired. Ship target is employee-mobile cobundle.

## Setup

Customer-facing Performance enablement remounted after `customer_enableable=true`.

Talent Setup card remains unmounted. Wave 6 cards remain omitted.
