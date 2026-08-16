# Prior production evidence accepted into this qualification

| Area | Pack | Verdict | Notes |
|---|---|---|---|
| Lifecycle freeze | `ops/PREHIRING_FINAL_PRODUCTION_REQUALIFICATION.md` (2026-07-25) | 536/536 PASS | Synthetic tenants; dry_run delivery; mutation/idempotency/hire atomicity |
| Teams | `ops/evidence/m365-teams-matrix-20260730T235844Z` | PASS | joinUrl, reschedule, cancel, AAP deny, Sent Items |
| Outbound mail | `ops/evidence/hybrid-email-m365-outbound-recheck-20260731T024000Z` | FULL PASS | allow evidence mailbox / deny outside |
| Follow-up tenant | `ops/evidence/follow-up-tenant-strict-wave1-prod-20260801T015103Z` | PASS | strict company equality |
| Candidates URL | `ops/evidence/candidates-url-filter-authority-wave3-deploy-20260801T021935Z` | PASS | durable filters |
| Candidates UX | `ops/evidence/candidates-filter-ux-wave4-deploy-20260801T023636Z` | PASS | drawer/sheet |
| Overview work-queue | `ops/evidence/overview-work-queue-wave2-deploy-20260801T020208Z` | PASS | mine/company |
| Smoothness | `ops/evidence/workspace-smoothness-deploy-20260801T030232Z` | PASS | skeletons, sticky page |
| Calendar scopes/cards | calendar-scope-labels + event-card-redesign deploys | PASS | |

Fresh live mutation of Teams meeting / outbound mail **not** re-executed in this run to avoid duplicate Graph noise; connection/settings surfaces rechecked live.
