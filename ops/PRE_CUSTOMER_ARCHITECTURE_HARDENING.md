# Pre-Customer Architecture Hardening — wave report

**Stamp:** `20260811T122043Z` · **Environment:** production (`api.wathefni.ai`, DB marker `2646585bbedb`)
**Predecessor:** `ops/CANONICAL_MULTISURFACE_ARCHITECTURE_VERIFICATION.md` (this wave closes its §5 must-fix list)
**Harnesses:** `ops/mobile-e2e/verify-canonical-multisurface-architecture.py` · `ops/mobile-e2e/verify-pre-customer-hardening.py`
**Evidence:** `ops/evidence/pre-customer-hardening-20260811T122043Z/`

## Verdict

**PRE-CUSTOMER ARCHITECTURE HARDENING PASS** — 13/13 live proofs green, no remaining blocker
before onboarding the first real company.

| Area | Proof | Verdict |
| --- | --- | --- |
| Cross-tenant onboarding reads/writes | H1 | **PASS** |
| Candidate null-tenant prevention | H2 | **PASS** |
| Leave source attribution by surface | H3 | **PASS** |
| Dual-actor task stale-write rejection | H4 | **PASS** |
| Queue visibility at 30 / >50 items | H5 | **PASS** |
| Urgent ordering above high/normal | H6 | **PASS** |
| Web → mobile convergence, no manual refresh | H7 | **PASS** |
| Employee App submission → both HR surfaces | P1 | **PASS** |
| HR Mobile mutation → HR Web + Employee App | P2 | **PASS** |
| HR Web mutation → HR Mobile | P3 | **PASS** |
| HR Mobile document review → HR Web | P4 | **PASS** |
| Assistant canonical reads + governance | P5 | **PASS** |
| Tenant isolation, read and write | P6 | **PASS** |

Nothing in this wave changed the canonical source of truth, RBAC, tenant isolation, frozen
workflow contracts, or Assistant governance. UI changes are limited to continuation affordances.

## 1. Onboarding tenant hardening

`onboarding_items` inferred tenancy from a join plus a company-prefixed `employee_key`, and
`load_onboarding_items` dropped the company clause entirely when no `company_code` was passed.

* Added `onboarding_items.company_code` with a backfill from `employees` and an index; 258/258
  rows stamped, 0 mismatched against their employee's company.
* `load_onboarding_items` now always resolves an owning company (new
  `onboarding_company_for_employee`) and always filters on it — there is no unscoped path left.
* `mark_onboarding_item` selects with `e.company_code=%s` and updates with
  `COALESCE(company_code,%s)=%s`; the same clause was added to the lifecycle updater in
  `employee_migration_lifecycle.py`, which previously assumed a column that did not exist and
  silently rolled back its savepoint.
* Seeders (`seed_onboarding_items`, `onboarding_wave2.seed_wave2_items`) write `company_code`.

**H1 evidence:** reads with no company argument return exactly the owner's 36 items and 0 for the
other tenant; QA-tenant HTTP read/write attempts return 404/403; a direct writer call carrying the
wrong tenant refuses with `employee_not_found` and the item status is unchanged.

## 2. Candidate tenant integrity

15 `candidates` rows had `active_company_code IS NULL`.

* 8 were attributed from their `applications` rows, which named exactly one company each.
* 7 were unreferenced assessment fixtures with no row anywhere else keyed by their phone; deleted
  after an audited reference scan across every `phone` column in the schema. Their full contents
  are in the pre-change CSV backup.
* `active_company_code` is now `NOT NULL`, applied only because zero NULLs remained.
* Application layer fails closed ahead of the constraint: `register_imported_cv` returns
  `company_code_required` for a blank tenant, and
  `backfill_candidate_identity_from_documents` derives the company from single-company
  applications and skips ambiguous cases rather than inserting an unowned hub row.

**H2 evidence:** 0 NULL rows, column `is_nullable=NO`, a direct NULL insert is rejected by the
database, and the import path refuses a blank company before touching the table.

## 3. Employee App leave provenance

`request_leave` hardcoded `metadata.source = "whatsapp"`, so an Employee-App submission was stored
as a WhatsApp submission.

* `request_leave` accepts `origin_surface`, normalized through the new
  `normalize_origin_surface`. The default stays `whatsapp` so untouched legacy callers keep their
  existing provenance; every real surface passes its own value.
* Callers updated: Employee App (`employee_app`), WhatsApp turn handler (`whatsapp`), and the
  action registry, which resolves the surface from the action/state/request and defaults to
  `assistant`.

**H3 evidence:** three submissions through three surfaces in one run produce three distinct
`metadata.source` values (`employee_app`, `assistant`, `whatsapp`). The canonical harness P1 now
records `employee_app` for the Employee-App path.

## 4. Task concurrency parity

HR Web resolved tasks with a bare `status`, so two HR users could silently overwrite each other.

* `outbound_delivery.resolve_hr_task` takes `expected_status` and applies it as `AND status = %s`
  inside the `UPDATE`, returning `stale_decision` with the current status when it does not match.
  The guard is in the write itself, so it also closes the read-then-write race the mobile resolver
  had.
* `POST /dashboard/hr-tasks/{id}/resolve` now requires `expected_status` (same contract as the
  employee status transition endpoint) and answers 409 `stale_decision` on conflict.
* HR Web sends the status it rendered, and on 409 tells the user the task changed and reloads.
* HR Mobile passes the status it read as `expected_status`.

**H4 evidence:** first resolve 200; a second web actor holding the same stale view gets 409
`stale_decision`; a mobile actor holding the same stale view gets 409; a request without
`expected_status` is refused 422; final status is the first writer's `done`.

## 5. Queue pagination, visibility and ordering

Queues rendered a capped page with no indication that more work existed, so a busy company could
look clear.

* New `useHrQueue` hook (one `useInfiniteQuery` contract for every actionable HR queue) and
  `QueueContinuation` component ("Showing X of Y" plus Load more, EN + AR).
* Applied to Documents, Tasks, Onboarding, Delivery Alerts, Attendance (Today and Unresolved) and
  Shift swaps. Section headers and tab counts report the server total, never the fetched length.
* Home and Inbox request the full 30-item window and compute their counts from `section.total`,
  falling back to the visible count only when this viewer's permissions actually hid rows. Inbox
  groups end with an honest count line because the priorities endpoint is a window by design; the
  complete list is in each queue screen.
* `mobile_hr_tasks` returns `has_more`; `mobile_shift_swaps` accepts `offset` and pages
  server-side.
* `list_hr_tasks` orders `urgent` above `high`, `normal`, `low`.

**H5/H6 evidence:** with 112 open tasks, page 1 returns 30 items with `total=112` and
`has_more=true`, page 2 is disjoint, and the totals match the database. Documents, alerts, swaps,
attendance and onboarding all expose `total` and `has_more`. A single urgent task seeded last
appears at position 0, above every high and normal task.

## 6. Cross-surface convergence

* New `HrForegroundQueryRefresh` mounted in the HR shell teaches React Query what "focused" means
  on native (wiring `focusManager` to `AppState`) and runs one throttled soft refresh — `refreshMe`
  plus `refetchQueries({ type: 'active' })` — when the app returns to the foreground.
* `useRefetchOnScreenFocus` refetches a screen that stayed mounted when the operator navigates back
  to it; it is built into `useHrQueue`, so every queue gets it, and is wired into Home and Inbox.
* Unlock dismissal now invalidates without a refetch storm and runs the same soft refresh, so the
  screen catches up instead of flashing a full reload.
* Authenticated surface reads carry `Cache-Control: no-store` (new middleware over `/dashboard/`
  and `/app/`, skipping streaming paths), closing the one staleness layer the client cannot
  invalidate. Hashed static assets keep their own immutable directive.

**H7 evidence:** an HR Web resolve is visible to an already-authenticated mobile session on the
next read with no re-auth and no client refresh — the task leaves the open queue, detail reads
`done`, priorities no longer lists it, and the response is `no-store`.

## Accepted debt (not blockers)

* **Reconnect detection is indirect.** Introducing `NetInfo`/`expo-network` would force a native
  build, so `refetchOnReconnect` is enabled but native online state is not wired to a link-level
  listener. Foreground and screen-focus refresh cover the realistic recovery paths; add a real
  listener at the next native build.
* **Inbox continuation is a count, not a Load more.** `/dashboard/mobile/priorities` is a
  fixed 30-item window per section by design. Inbox says what is missing and the per-queue screens
  paginate fully.
* **Attendance exceptions are filtered twice**, once in `list_attendance` (which is what `total`
  counts) and again in the mobile mapper. Harmless duplication; the totals are honest.
* **Hiring/pre-hire queues were not part of this wave**, which is scoped to the post-hire surfaces
  the first customer will use on day one.

## Deploy and rollback

* Deploy: `ops/deploy-pre-customer-hardening-wave.sh` (backs up every touched file plus the two
  changed tables as CSV, ships code, runs the audited candidate cleanup, applies schema under the
  deploy advisory lock, restarts and health-checks).
* HR Web bundle rebuilt and shipped to `/opt/wathefni/dashboard-dist` (the directory the Caddyfile
  actually serves; `/var/www/wathefni-dashboard` is a stale path left by older deploy scripts and
  was restored untouched). The resolve contract now requires `expected_status`; prior bundle saved
  to `/opt/wathefni/backups/dashboard-dist-20260811T124800Z`.
* Mobile shipped OTA on the `canary` branch (JS only, no native change).
* Rollback: `ops/evidence/pre-customer-hardening-20260811T122043Z/ROLLBACK.sh`.
