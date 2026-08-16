# CV Processing Queue, Parallelism, and HR Visibility Audit

**Date:** 2026-07-27 (UTC)  
**Stamp:** `20260727T145600Z`  
**Mode:** Read-only (no production changes; Intake Operations not hidden; concurrency untouched)  
**Host:** `root@76.13.63.68`  
**Scope:** Production CV processing queue / worker architecture vs intended long-term model, plus HR visibility of queue states

---

## Verdict

**Final: FAIL** against the intended long-term architecture *as a healthy production system for parallelism, stuck-job coverage, and HR visibility*.

The **durable email intake queue core is real and mostly correct** (Postgres jobs, lease claim, retries, idempotency, restart durability, tenant fairness).  
It is **not** currently the multi-CV parallel processor described in the intended model, and **HR-facing “attention” incorrectly treats healthy/internal processing (and even finished held CVs) as problems**.

| Intended property | Production reality | Gate |
|---|---|---|
| Durable queue | Postgres `intake_processing_jobs` + events + tenant state | **PASS** |
| Multiple CVs in parallel | Effective **1 job at a time** per tenant (`limit=1`, `TENANT_CONCURRENCY=1`, 15s oneshot) | **FAIL** |
| Bounded concurrency | Yes — deliberately tight | **PASS** (safety) |
| Automatic retries | Max 5, exponential backoff 5s→900s, lease reclaim → retry/DLQ | **PASS** |
| Idempotency | `UNIQUE (company_code, idempotency_key)` | **PASS** |
| Provider rate-limit protection | Indirect via concurrency=1; **no explicit Mistral/OCR rate limiter** | **PARTIAL** |
| No lost jobs after restart | Lease + `FOR UPDATE SKIP LOCKED` + reclaim | **PASS** (durable path) |
| Stuck-job monitoring | Snapshot metrics exist; **no age/depth/duration thresholds**; **orphan apps/submissions invisible** | **FAIL** |
| HR does not see internal queue states | Intake Ops + banner expose Queued/Processing; banner over-counts | **FAIL** |

---

## 1. Exact queue architecture

### Where jobs are stored

Primary durable queue (email inbound / shared intake worker):

| Store | Role |
|---|---|
| `intake_processing_jobs` | Job rows: status, attempts, lease, idempotency, payload/result |
| `intake_processing_job_events` | Claim/complete/retry/replay audit |
| `intake_tenant_queue_state` | Per-tenant running slot + fairness (`last_claimed_at`) |
| `intake_submissions` / `intake_documents` / `inbound_messages` | Durable ingress artifacts |
| `cv_extraction_leases` / `cv_extraction_runs` | Extraction stage leases + run ledger (empty leases at audit time) |
| `cv_processing_stage_runs` (unified ledger, when flags on) | Stage catalog for shared processing |

**Job types** (`durable_email_ingress.JOB_TYPES`):  
`intake_validation`, `file_safety_scan`, `cv_identity_resolution`, `accepted_intake_preparation`, `cv_extraction`, `profile_structuring`, `embedding`, `sender_acknowledgment`, `retention_privacy`.

**Active statuses:** `pending`, `running`, `retrying`, `waiting_quota`, `waiting_budget`  
**Terminal:** `completed`, `dead_letter`, `cancelled`

### How jobs are claimed

`claim_next_job()` in `durable_email_ingress.py`:

1. Reclaim expired leases.
2. Pick a tenant with `running_jobs < per_tenant_concurrency` and ready work (`FOR UPDATE SKIP LOCKED`), ordered by `last_claimed_at` (fairness) then min priority.
3. Claim one job for that tenant: `ORDER BY priority ASC, available_at ASC, created_at ASC` + `FOR UPDATE SKIP LOCKED`.
4. Set `status=running`, `attempts+=1`, `lease_owner`, `lease_expires_at = now() + lease_seconds`.

### Lease / lock behavior

| Setting | Production value |
|---|---|
| `WATHEFNI_INTAKE_JOB_LEASE_SECONDS` | **180** |
| Claim lock | Postgres row lock + `SKIP LOCKED` |
| Expired lease | Reclaim → `retrying` or `dead_letter` if attempts ≥ max; error `lease_expired` |

Worker oneshot `TimeoutStartSec=180` matches lease length — a hung job can lose the lease at the same horizon.

### Idempotency

Enqueue uses `ON CONFLICT (company_code, idempotency_key)` (e.g. `submission:{id}:validate`, `document:{id}:safety-scan`). Duplicate ingress does not create duplicate durable work for the same key.

### Retry policy

| Setting | Production value |
|---|---|
| `WATHEFNI_INTAKE_JOB_MAX_ATTEMPTS` | **5** |
| `WATHEFNI_INTAKE_RETRY_BASE_SECONDS` | **5** |
| `WATHEFNI_INTAKE_RETRY_MAX_SECONDS` | **900** |
| Backoff | Exponential with jitter (`_backoff_seconds`) |
| Exhaustion | `status=dead_letter` |
| Replay | `replay_dead_letter()` exists (ops/explicit) |

Commercial quotas (`daily_*` / `monthly_*`) are **0** (disabled) → `waiting_quota` / `waiting_budget` unused in practice.

### Dead-letter behavior

Supported in schema + fail/reclaim paths. **Production evidence:** **0** dead letters ever for WATHEFNI; **0** `last_error_code` on completed jobs. Events seen: `claimed` (18), `completed` (18), `explicit_replay` (2). Two `cv_extraction` rows are **cancelled** (not DLQ).

### Restart durability

Jobs live in Postgres. Worker is **oneshot** (no in-memory queue). After restart, timer resumes claiming; expired leases reclaim. **No job loss** for rows already in `intake_processing_jobs`.

### Ordering and fairness

- Within tenant: priority → available_at → created_at.
- Across tenants: least-recently-claimed tenant first (`intake_tenant_queue_state.last_claimed_at`).
- Stages of one CV are **separate jobs**; with concurrency 1 they execute **serially**, spaced by the 15s poll.

### Dual / legacy paths (important)

| Path | Mechanism | Production state |
|---|---|---|
| Durable email intake | `wathefni-inbound-intake-worker.timer` → `--limit 1` | **Active** |
| Legacy prehire CV process | `POST /orchestrator/prehire/cv/process?limit=10` via `wathefni-prehire-cv-process.timer` | **Inactive / disabled** |
| Classification | separate `talent_pool_classification_jobs` + timer | Active |
| CK index | long-running `wathefni-ck-index.service` | Active (recent `cv_version_not_found` failures) |

Application flags like `pending_async_processing` are **not** durable queue jobs. With the prehire timer off, they are **orphans** relative to the approved durable path.

---

## 2. Parallelism — exact production numbers

| Knob | Exact value |
|---|---|
| Active intake worker services | **1** oneshot unit, timer-fired |
| Poll interval | **15s** (`OnUnitActiveSec=15s`) |
| Jobs claimed per tick | **`--limit 1`** |
| `WATHEFNI_INTAKE_TENANT_CONCURRENCY` | **1** (orchestrator drop-in + intake.env) |
| Continuous intake workers | **0** (not a pool of long-lived processes) |
| `wathefni-prehire-cv-process.timer` | **disabled / inactive** |
| Host CPUs | **2** |
| RAM | **7.8 GiB** (~4.5 GiB available at audit); **0 swap** |
| ClamAV | Docker `wathefni-production-clamav` reported **healthy**; clamd processes present |

### Do multiple CVs process simultaneously?

**No — not under current production caps.**  
At most **one** `intake_processing_jobs` row runs per tenant at a time. The oneshot worker also only claims one job per invocation. Parallel CVs would require raising tenant concurrency **and** either overlapping worker invocations or a higher `--limit` / long-lived worker pool (out of scope for this audit; not changed).

### Email / WhatsApp / manual capacity

- **Email inbound** is the production path on the durable intake queue (`WATHEFNI_INBOUND_EMAIL=on`).
- Unified adapter flags are on (`WATHEFNI_UNIFIED_ADAPTER_SHARED_PROCESSING`, Wave4, etc.), but the **live drain** observed in `intake_processing_jobs` is the email/intake worker pipeline.
- WhatsApp/manual do **not** currently show a separate parallel worker pool sharing the same jobs table in production drain metrics; capacity is effectively **the same single-slot intake worker** when they enqueue into it.
- Legacy application async (`pending_async_processing`) is **not** drained by the durable worker (prehire timer off).

### OCR / scan / AI serial vs concurrent

Pipeline stages are **separate queue jobs** and, with concurrency 1, run **serially**:

validation → safety scan (ClamAV) → identity / accepted prep → extraction (local → optional Mistral OCR → optional GPT vision rescue) → further jobs as enqueued.

Within a single extraction call, local vs OCR vs rescue are **tiered fallbacks**, not parallel OCR+AI races.

### Current maximum safe throughput (estimate)

Conservative bound under current settings:

- ~**1 job / 15s** claim cadence ≈ **4 jobs/min** upper claim rate when always busy.
- A typical inbound CV is **several jobs** (often 4–6+). Observed end-to-end wall times on recent submissions:
  - ~**40–145s** to identity-review outcomes
  - one earlier accepted path ~**442s** (~7.4 min) wall (includes queue wait between stages)
- Safe concurrent OCR/ClamAV load today: **1 CV-stage at a time** — intentionally protective on a 2-vCPU host with ~1 GiB ClamAV RSS each.

**Throughput bottleneck:** timer + tenant concurrency 1 + serial stages — not Postgres or connection pool (max_connections 100; ~9 sessions observed).

---

## 3. Backpressure and limits

| Resource | Limit / behavior | Assessment |
|---|---|---|
| Mistral OCR | Enabled (`WATHEFNI_CV_MISTRAL_OCR=true`, model pin `mistral-ocr-4-0`); no dedicated RPM semaphore in intake worker | Protected mainly by **serial concurrency**; retries cover transient HTTP failures |
| GPT vision rescue | Enabled | Same — serial behind extraction |
| ClamAV | Scanner `clamav`, timeout 120s, docker healthy | Heavy RAM; OK at concurrency 1 |
| File/body caps | 24 MiB webhook, 8 MiB file, 12 MiB total attachments, 40 PDF pages | Hard admission limits |
| DB | `max_connections=100`; low usage | Not the bottleneck |
| CPU/mem | 2 vCPU, 7.8 GiB, load ~0.5 | Headroom for modest concurrency raise later; **not** for unconstrained parallel OCR |
| Queue growth | Jobs accumulate as `pending`/`retrying` until claimed | Grows safely in DB; drain rate capped |
| Does concurrency scale safely today? | **Only upward with care** — raising without OCR/ClamAV/CPU budgeting would be unsafe | Current 1 is safe, not scalable |

---

## 4. Current production health — the “two queued CVs”

### Critical correction

Ops monitor and Postgres agree:

- **`intake_queue_depth = 0`**
- **No** `pending` / `running` / `retrying` intake jobs for any company

The Candidates banner **“2 CVs need processing attention”** is **not** two durable queue jobs. It comes from `intake_operations_summary()` falling back to **held applications** (`needs_role` / `import_review`) and mis-bucketing them.

### Evidence: the two held applications (WATHEFNI)

| # | `app_key` | App status | `cv.processing.status` | Age (ingest) | Since processing update | Verdict |
|---|---|---|---|---|---|---|
| A | `imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT` | `needs_role` | **`processed`** (facts ready, text extracted, semantic indexed) | ~**23 h** | ~**23 h** | **Not queued.** Finished processing; waiting for **HR job assignment**. Incorrectly counted as attention/`queued` because `"processed"` falls into the summary `else` → queued. |
| B | `imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT` | `needs_role` | **`pending_async_processing`** (`text_extracted=false`) | ~**56 days** ingest; import meta `imported_at` 2026-07-26 | Processing stamp **2026-07-26T01:03:56Z** (~**37 h** stale at audit) | **Stuck / orphaned** relative to durable queue. **Not progressing** on `intake_processing_jobs`. Three `cv_extraction_runs` local_extract rows exist with `quality_ok=t` for this app, but application processing flag never advanced — desync + disabled prehire drain. |

**Bucket math that produces attention_count=2:**

- Durable job statuses contribute **0** queued/processing (only completed/cancelled exist).
- App A (`processed`) → `else` → **queued += 1**
- App B (`pending_async_processing`) → `else` → **queued += 1**
- `attention_count` = queued + processing + incomplete + failed + unsupported + password + quarantined (**excludes** `ready_held`, but A never reaches `ready_held` because status is `processed` not `ready`/`complete`).

### Durable queue health snapshot

| Metric | Value |
|---|---|
| Active jobs | **0** |
| Completed (all time, WATHEFNI) | **18** |
| Cancelled | **2** (`cv_extraction`) |
| Dead letters | **0** |
| Retries in flight | **0** |
| Oldest pending | **null** (monitor) |
| Intake worker journal | Healthy oneshots; `processed: 0` while idle |
| Extra orphan | `intake_submissions` `f01ed86e-…` status **`durable`**, age ~**1 day**, **0** linked jobs — invisible to HR banner |

### Recent processing durations (durable path)

Per-job `run_sec` often **&lt;1–3s**; wall-clock gaps between stages track the **15s poll** (e.g. validation→scan→identity chains spanning ~30–110s). Classification latency avg 24h (monitor): **~65.5s**.

### Worker health / failures

| Unit | State |
|---|---|
| `wathefni-orchestrator` | active |
| `wathefni-inbound-intake-worker.timer` | active |
| Intake worker | succeeding; idle |
| `wathefni-inbound-ops-monitor.timer` | active |
| `wathefni-prehire-cv-process.timer` | **inactive** (monitor flags this) |
| `wathefni-ck-index` | active; recent repeated `ck_job_failed` / `cv_version_not_found` |
| ClamAV container | healthy (monitor) |

---

## 5. Monitoring

### What exists

1. **`wathefni-inbound-ops-monitor`** (every ~1 min)  
   Writes `/var/lib/wathefni/inbound-ops-monitor/latest.json` + `alerts.latest.json` + history.  
   Metrics: queue depth, oldest pending age, success/DLQ/retry 24h, scan/malware, open identity reviews, unit states, etc.

2. **`wathefni-uptime` → Healthchecks.io**  
   Dead-man’s switch on orchestrator `/health` only (5 min / 10 min grace). **Not** queue-depth or stuck-job aware.

### Alert thresholds (actual)

| Concern | Threshold / alert? |
|---|---|
| Stuck-job age | Metric only (`oldest_intake_pending_age_seconds`); **no alert if age &gt; N** |
| Queue depth | Metric only; **no depth threshold alert** |
| Processing time | Classification avg only; **no p95 / SLA alert** |
| Worker down | Intake timer state recorded; **no dedicated “timer inactive” alert** (prehire inactive is recorded but **not** in alert list). Orchestrator down → Healthchecks. |
| Retry exhaustion / DLQ | **Yes** — `intake_dead_letter_24h` / classification DLQ → alert name |
| Provider outage | **No** dedicated Mistral/OCR outage alert |
| Malware / scan failure | **Yes** (24h counts) |
| Open identity reviews | **Yes** (any open → alert) — currently firing |
| Non-WATHEFNI active jobs | **Yes** (isolation) |

**Dispatch:** monitor writes **local JSON**. No evidence in the uptime ping path that `alerts.latest.json` pages on-call. Treat as **platform ops file snapshots**, not HR notifications — but **HR UI separately surfaces a conflicting “attention” signal**.

### Audience

| Signal | Audience today |
|---|---|
| Healthchecks deadman | Platform ops |
| inbound-ops-monitor JSON | Platform ops (if watched) |
| Candidates “CVs need attention” + Intake Operations buckets | **Normal HR** |

---

## 6. Product / UI conclusion

### Should queued and processing ever be shown to normal HR?

**No.** Healthy queue/processing is platform machinery. HR should see candidates when they are **actionable as people/applications** (e.g. ready to assign a job, identity conflict requiring a human decision, unsupported/password file they must re-send), not internal job states.

### Should Intake Operations remain visible to HR?

**Not as a normal-HR default.** Keep it for **platform support / owner admin** (quarantine policy communication, dead letters, unsupported/password counts). Do **not** hide it in this audit (per instructions); recommendation for a later change: gate or move under platform-support.

### What genuinely requires HR action?

- Assign / link job for **ready held** Talent Pool intakes (`needs_role` with successful processing) — preferably from Candidates, not a queue dashboard.
- Re-upload / replace **password-protected** or **unsupported** files (candidate/HR operational).
- Resolve **identity conflicts** only if product policy assigns that to HR (today 6 open reviews are primarily **platform/ops**).
- Never: release malware quarantine (already forbidden in UI copy).

### What should remain platform-support-only?

- Queue depth, leases, retries, dead letters, OCR/provider errors, worker/timer health, stuck `pending_async_*`, orphan `intake_submissions`, CK index failures, ClamAV health.

### Is “CVs need attention” incorrect because it includes normal queued/processing?

**Yes — and worse:** today it includes:

1. Misclassified **fully processed** held CVs (`processed` → counted as queued).
2. Any `pending_async_processing` / unknown status (also → queued), including **stuck orphans**, without distinguishing “waiting a few seconds” vs “stuck 56 days”.
3. Design intent of `attention_count` **explicitly sums queued + processing**, which is wrong for normal HR even when durable jobs are healthy.

`ready_held` is correctly **excluded** from attention — but the `"processed"` status never lands in `ready_held`.

---

## Recommended long-term architecture

Keep the **Postgres leased job queue** as the single authority for all channels (email, WhatsApp, manual) once fully cut over.

Evolve toward the intended model **without** abandoning durability:

1. **Long-lived or multi-claim workers** (or higher `--limit`) with **global and per-tenant concurrency caps**, not “1 job / 15s” as the only parallelism story.
2. **Shared capacity pools** with separate budgets if needed: scan vs OCR vs LLM (so ClamAV and Mistral cannot starve each other blindly).
3. **Explicit provider rate limit / retry classification** (429 → defer `waiting_quota` / backoff).
4. **One drain path** — retire or permanently gate legacy `prehire/cv/process` so `pending_async_processing` cannot exist outside the durable queue.
5. **Stuck detectors** on: lease age, pending age, application processing flags not advanced, submissions stuck in `durable` with zero jobs.
6. **HR surfaces** only outcome states; **platform ops** own queue telemetry and alerts (pager on DLQ, worker down, stuck age, provider outage).

Current tight concurrency is a **valid first-production safety posture**, not the end state for “multiple CVs in parallel.”

---

## Risks

1. **False HR attention** trains distrust of Candidates banner / Intake Ops.
2. **Orphan `pending_async_processing`** and **`durable` submissions with 0 jobs** — silent incompleteness; monitor queue depth stays 0.
3. **Disabled prehire timer** while legacy flags still exist — split-brain drain.
4. **Serial 15s stage spacing** — latency under burst grows linearly; backlog only in DB.
5. **Raising concurrency without OCR/ClamAV budgeting** on 2 vCPU / dual clamd memory — resource risk.
6. **CK index failures** (`cv_version_not_found`) — secondary indexing health, not intake drain, but shows incomplete end-to-end observability.
7. **Monitor alerts may not page** — file snapshot ≠ on-call.

---

## Exact fixes needed (do not implement in this audit)

1. **Fix `intake_operations_summary` attention math**  
   - Map `processed` / successful complete statuses → `ready_held` (or exclude from attention).  
   - **Exclude** healthy `queued`/`processing` (and durable pending/running) from `attention_count` for HR.  
   - Attention = incomplete + failed/DLQ + unsupported + password + quarantine (+ optional identity-review if product says HR).

2. **Fix Candidates banner copy** to match HR-actionable counts only (or remove when zero actionable).

3. **Platform stuck-job coverage**  
   - Alert if `oldest_intake_pending_age_seconds` &gt; threshold.  
   - Alert if applications remain `pending_async_processing` &gt; threshold.  
   - Alert if `intake_submissions.status='durable'` with no jobs &gt; threshold.  
   - Alert if intake timer inactive while inbound email on.

4. **Reconcile / close orphans** (ops runbook): app `imp-wathefni-06ffffc36d7fd375-…`, submission `f01ed86e-…` — after ownership decision; not a concurrency change.

5. **Unify drain:** either finish cutover so all CVs enqueue only to `intake_processing_jobs`, or document and monitor the legacy path — do not leave prehire timer disabled silently.

6. **Later (architecture):** raise parallelism only with explicit global/OCR/scan caps; optional continuous worker; wire monitor alerts to platform paging.

7. **Visibility:** keep Intake Operations for platform-support; do not use it as normal-HR queue theatre.

---

## Final PASS / FAIL

| Area | Result |
|---|---|
| Durable queue mechanics (claim/lease/retry/idempotency/restart) | **PASS** |
| Parallel multi-CV processing as intended | **FAIL** (bounded to 1) |
| Provider rate-limit protection | **PARTIAL** |
| Stuck-job monitoring (complete) | **FAIL** |
| Production “two queued jobs” narrative | **FAIL** (0 durable queued; 1 finished held + 1 orphan async) |
| HR visibility / attention count correctness | **FAIL** |
| **Overall long-term architecture healthy?** | **FAIL** |

**Summary sentence:** The durable leased Postgres queue is the right core and is healthy when idle, but production is a **serial, single-slot** drain with **orphans outside that queue**, and HR currently sees **incorrect “attention”** that includes non-actionable queue-like states.

---

## Audit constraints honored

- No production config/code changes  
- Intake Operations not hidden  
- Queue concurrency / worker counts / retries / provider settings unchanged  
- Stop after audit
