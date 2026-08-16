# Alerts & Delivery Page Refinement Wave 1 — Production deploy

**Stamp:** `20260804T134718Z`  
**Evidence:** `ops/evidence/alerts-delivery-page-refinement-wave1-prod-deploy-20260804T134718Z/`  
**Freeze:** `ops/ALERTS_DELIVERY_PAGE_REFINEMENT_WAVE1_FREEZE.md`  
**Bundles (live):**  
- `/var/www/wathefni-dashboard/assets/PostHire-BD2c6nFG.js`  
- `/var/www/wathefni-dashboard/assets/NotificationsPage-Jme8bOo7.js`  
**Backup:** `/opt/wathefni/backups/production-pre-alerts-delivery-page-refinement-wave1-20260804T134718Z/`

## Verdict

| Gate | Result |
|---|---|
| Production UI deploy | **GO** |
| Safe smoke | **GO** (`ALERTS_DELIVERY_PAGE_WAVE1_SMOKE_OK`) |
| Mutation / permission proof | **GO** (`MUTATION_PERMISSION_PROOF_OK`) |
| Freeze Alerts & Delivery Page Wave 1 | **GO / FROZEN** |
| Provider / delivery infrastructure | **NO-GO** (not changed) |
| Compliance / Analytics / Payroll freezes | **UNTOUCHED** |

## Implementation-truth findings

| Finding | Truth |
|---|---|
| Mount | `NotificationsPage` (`page=notifications`) + former `PostHireDeliveryCenter` (now null stub) |
| Discarded rows | `moduleScopedNotificationRows(...)` computed then `void issues` dropped them |
| Nested hierarchy | Up to 3 delivery cards + Urgent HR alerts + group sections + mini-cards |
| Specialist strips | Still on attendance / leave / workforce before this wave |
| Retry API on this page | None — only `resolveHrTask` (Mark done); automatic retries stay in outbound sweep |
| CTA gaps | Several action labels rendered as text “Suggested next step” with no navigate |

## Discarded-row root cause and fix

**Cause:** `groupedNotificationAlerts` accepted scoped `NotificationRow[]` then executed `void issues`, so prehire delivery rows never entered the render tree.

**Fix:** Remove nested alert-card builder. Scoped rows are mapped through `issueFromPrehireRow` into the unified live-issues list with working navigate CTAs or non-actionable status text.

## Exact duplication removed

- Nested **Urgent HR alerts** card / group sections / mini-cards  
- Separate **Needs your follow-up** + **Delivery issues** + **Reminder activity** competing cards  
- `DeliveryStatusStrip` on all specialist post-hire modules  
- `PostHireDeliveryCenter` nested inside NotificationsPage  
- Silent “Suggested next step” pseudo-CTAs without destinations  
- `void issues` discarded-row path  

## Final issue structure and status model

1. Compact header + purpose  
2. One-line issue summary  
3. Filters: Needs follow-up · Failed · Retrying · Resolved · All  
4. Dominant live-issues list: recipient, purpose, channel, plain reason, latest attempt, one primary action, Details  

| Filter | Mapped from (existing contracts) |
|---|---|
| Needs follow-up | Open HR tasks + `needs_hr_action` + actionable workspace alerts |
| Failed | Outbound `failed` + failed prehire delivery rows + failed action aggregates |
| Retrying | Outbound `throttled` (“retrying later”); in-flight `pending` remains backend-owned and not listed until it needs HR |
| Resolved | HR tasks with status `done` |
| All | Live (non-resolved) issues |

## CTA / navigation proof

- **Mark done** → `POST /dashboard/hr-tasks/{id}/resolve` when `users.manage` or any `{module}.manage`  
- **Navigate** → Assessments / Interviews / Onboarding / Compliance / AI / Employees / module pages  
- **Non-actionable status** → `data-alerts-status-cta` text (never a silent button)  
- Technical evidence behind **Details**  

## Permissions and retry proof

- Read: existing HR-tasks / outbound needs-follow-up / prehire notifications  
- Mutate: `resolveHrTask` only on this page  
- Provider retries / idempotency / outbound sweep: unchanged  
- Live proof: `verify/mutation-permission-proof.out`

## Screenshots

`ops/evidence/alerts-delivery-page-refinement-wave1-prod-deploy-20260804T134718Z/screenshots/`

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-alerts-delivery-page-refinement-wave1-20260804T134718Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-alerts-delivery-page-refinement-wave1-20260804T134718Z
```
