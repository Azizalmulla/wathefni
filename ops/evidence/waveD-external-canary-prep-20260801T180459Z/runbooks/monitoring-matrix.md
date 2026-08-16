# Monitoring matrix & alert thresholds (external canary)

Audience: **platform operations** (not normal HR).  
Sources: `wathefni-inbound-ops-monitor.timer` + usage API + DB queries below.

## Thresholds (current defaults)

| Signal | Threshold | Env override |
|---|---|---|
| Pending intake job age | > **900s** (15m) | `WATHEFNI_OPS_PENDING_JOB_MAX_AGE_SEC` |
| Running intake job age | > **600s** (10m) | `WATHEFNI_OPS_RUNNING_JOB_MAX_AGE_SEC` |
| Stuck async pending | > **1800s** (30m) | `WATHEFNI_OPS_PENDING_ASYNC_MAX_AGE_SEC` |
| Intake queue depth | ≥ **25** | `WATHEFNI_OPS_QUEUE_DEPTH_ALERT` |
| OCR provider failures / 24h | ≥ **3** | `WATHEFNI_OPS_OCR_FAILURE_ALERT_24H` |
| Soft quota warning | **80%** of plan | `inbound_enterprise.soft_warning_pct` |
| Canary plan (recommended) | **starter** | company `inbound_enterprise.plan` |

## Always-on alert codes (ops monitor)

| Alert | Severity for canary |
|---|---|
| `intake_dead_letter_24h` | High — investigate same day |
| `scan_failure_24h` / `malware_detected_24h` | High |
| `clamav_unhealthy` / `orchestrator_inactive` / `intake_worker_timer_inactive` | Critical |
| `pending_job_too_old` / `intake_queue_depth_high` | High |
| `open_identity_reviews` | Medium — expected volume; watch backlog growth |
| `non_wathefni_active_intake_jobs` | Info during canary (will fire for canary tenant — **tune or accept**) |

**Note:** Today’s monitor is WATHEFNI-centric (`non_wathefni_*` alerts). Before enablement, either:
1. Accept those alerts as expected for the canary company, or  
2. Add a canary-scoped dashboard query (recommended) so “non-WATHEFNI” is not confused with spillover.

## Canary-scoped daily report (SQL template)

```sql
-- Replace :company
SELECT
  current_date AS report_day,
  :company AS company_code,
  (SELECT count(*) FROM inbound_messages
     WHERE company_code=:company AND received_at::date = current_date) AS inbound_today,
  (SELECT count(*) FROM intake_submissions
     WHERE company_code=:company AND created_at::date = current_date) AS submissions_today,
  (SELECT count(*) FROM intake_submissions
     WHERE company_code=:company AND status IN ('waiting_quota','waiting_budget')) AS waiting_quota_or_budget,
  (SELECT count(*) FROM intake_processing_jobs
     WHERE company_code=:company AND status IN ('pending','retrying','leased')) AS open_jobs,
  (SELECT count(*) FROM intake_processing_jobs
     WHERE company_code=:company AND status='dead_letter'
       AND updated_at >= now() - interval '24 hours') AS dead_letter_24h,
  (SELECT count(*) FROM applications
     WHERE company_code=:company AND status IN ('needs_role','import_review')) AS held_open,
  (SELECT count(*) FROM intake_documents
     WHERE company_code=:company AND safety_state NOT IN ('clean','pending_scan')
       AND created_at >= now() - interval '24 hours') AS non_clean_docs_24h;
```

## Usage API

- Dashboard/enterprise usage visibility via inbound plan/usage endpoints (owner + `settings.manage`)
- Soft warnings at 80% of starter caps; never-reject for volume (queue `waiting_quota` instead of hard SMTP reject)

## Recommended canary plan caps (starter)

| Cap | Value |
|---|---|
| Daily messages | 500 |
| Monthly messages | 10_000 |
| Daily source bytes | 2 GiB |
| Concurrency | 2 |
| Soft warning | 80% |
| Burst | optional, ≤24h, only if hiring spike approved |
