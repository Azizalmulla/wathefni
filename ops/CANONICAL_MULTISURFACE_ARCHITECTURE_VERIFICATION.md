# Canonical multi-surface data architecture — verification

**Run:** 2026-08-11 · production (`api.wathefni.ai`, DB `wathefni`) · canary company **WATHEFNI**
**Harness:** `ops/mobile-e2e/verify-canonical-multisurface-architecture.py` (repeatable, self-cleaning)
**Fixtures mutated:** synthetic only — `WATHEFNI-9655237101` (W2B-SYNTH), `WATHEFNI-9655280101` (VISQA| Sara), `hr_tasks` titled `VISQA|%`. All ARCHVERIFY rows deleted after the run; VisQA fixtures re-provisioned.

---

## 1. Tenancy model

**Shared Postgres, application-enforced `company_code` scoping. Not database-per-company. No Postgres RLS.**

| Fact | Evidence |
|---|---|
| One process-wide pool from one DSN | `app.py:167–244` (`_DB_POOL`), `runtime_environment.py:98–149` |
| Databases on the host | `postgres`, `wathefni`, `wathefni_staging` — staging split, not per-tenant |
| Schemas | `public` only |
| RLS | `pg_policies` empty, `pg_class.relrowsecurity` empty — **zero** policies |
| Tenant column coverage | 461 of 530 public tables carry `company_code` |
| Live tenants | WATHEFNI (116 employees), WATHEFNIQA (14) |

Enforcement is a four-layer application chain:

1. Session → context: `dashboard_context` (web), `build_operator_mobile_context` (HR mobile), `employee_app_context` (employee), `_base_memory_scope` (assistant). Company comes from the stored session row, never from the client.
2. Client-supplied `company_code` is dropped: `_POSTHIRE_EXTRA_ARG_KEYS` whitelist (`app.py:65042–65044`); assistant args are overwritten — `args = {**args, "company_code": scope.get("company_id")}` (`tool_call_orchestrator.py:1510`).
3. Shared list/write helpers take `company_code=` and emit `WHERE company_code=%s`.
4. Manager sub-scope on top via `employee_scope_sql` / `_employee_scope_where`.

Per-turn scope is a ContextVar that **fails closed** (`resolved_company_scope`, `app.py:294–328`); identity lookups return `None` when unset.

---

## 2. Canonical source-of-truth map

| Domain | Canonical table(s) | HR Web | HR Mobile | Employee App | Assistant |
|---|---|---|---|---|---|
| Leave | `leave_requests` (+`leave_events`); balances `leave_ledger` → `leave_balances` (materialized) | `dashboard_posthire_leave` → `list_leave_requests` | `mobile_leave` → same `list_leave_requests` | `/app/leave*` → same tables | registry `list_leave_requests` → same fn |
| Attendance | `attendance_day_projections` (authority) / `attendance_records` (compat) | `dashboard_posthire_attendance` → `list_attendance` | `mobile_attendance_list` → `dashboard_posthire_attendance` | `/app/workday` | `list_attendance` |
| Shifts / swaps | `shift_assignments`, `shift_swap_requests` | `dashboard_posthire_shifts` | `list_shifts` / `list_shift_swaps` | `/app/schedule/history` | registry |
| Onboarding | `onboarding_items` (tenant via join to `employees`) | `dashboard_posthire_onboarding[_detail]` | `mobile_onboarding_detail` → same fn | `/app/onboarding*` | `list_onboarding_status` |
| Documents | `compliance_documents` (+`file_registry`) | `dashboard_compliance_payload` | same payload fn | `/app/documents` | `list_compliance_documents` → same payload fn |
| HR tasks | `hr_tasks` | `dashboard_hr_tasks` | `mobile_hr_tasks` → `dashboard_hr_tasks` | — | — |
| Outbound | `employee_messages` | `/dashboard/outbound/*` | `/dashboard/mobile/delivery-alerts` | `/app/notifications` | — |
| Employees | `employees` (Wave2 `employee_persons`/`_employments` = non-authoritative shadow dual-write) | `list_employees_page` | same | `/app/me` | `summarize_employee_360` |
| Hiring | `applications` (`company_code`); `candidates` is a phone-keyed person hub | `/dashboard/prehire/*` | `/dashboard/mobile/candidates` | — | registry |

HR Mobile is an adapter (DTO shaping + capability gates) over the **same functions** as HR Web. There is no mobile-only business table; the only `mobile_*` tables are `dashboard_operator_mobile_sessions`, `_login_attempts`, and `_confirmations` (SOD staging).

---

## 3. Cross-surface mutation proof (live, production)

| # | Proof | Result |
|---|---|---|
| P1 | Employee App submits leave → visible on HR Web **and** HR Mobile | **PASS** — 1 DB row, `company_code=WATHEFNI`, status `requested` identical on all three surfaces |
| P2 | HR Mobile rejects → HR Web + Employee App reflect | **PASS** — prepare→confirm two-step, `row_version` 1→2, `decided_by_phone=96599338566`, mobile detail + employee history both `rejected`, row leaves the web pending queue |
| P3 | HR Web resolves an HR task → HR Mobile reflects | **PASS** (×2 runs) — `hr_tasks.status=done`, task drops out of the mobile open queue, mobile detail shows `done` |
| P4 | HR Mobile reviews a document → HR Web reflects | **PASS** — DB `needs_review`→`valid`; web compliance `pending_hr_review`→`hr_reviewed` **carrying the note written on mobile**; mobile needs-review queue drops it |
| P5 | Assistant reads canonical + governed actions | **PASS** — shared action registry returned the same row, `scope.company_code=WATHEFNI` echoed by the backend; after the HR Mobile rejection the assistant read returned `rejected` with no extra step |
| P6 | Tenant isolation, read and write | **PASS** — 8/8 cross-tenant attempts returned 404 while the same id read 200 for the owning tenant |
| P7 | No duplicate status store | **PASS** — exactly 1 `leave_requests` row; only sibling with rows is `leave_events` (append-only log, 2 rows) |

**Isolation matrix (all 404):** QA mobile read/write of a WATHEFNI leave; QA mobile document review; QA mobile employee read; QA web employee documents; QA web document review; QA web onboarding detail; employee session cancelling another tenant's leave. QA web leave list returned `WATHEFNIQA` only. Prehire is scoped through `applications.company_code` — no WATHEFNI rows leaked to the QA tenant on candidates, applications, onboarding, or mobile candidate lists.

**Assistant governance:** `approve_leave_request`, `reject_leave_request`, `correct_attendance_record` all carry `requires_confirmation=true` in the shared registry. `WATHEFNI_ASSISTANT_MUTATIONS=0` in production, so `assistant_mutations_allowed()` is **false** — the assistant is read-only on assistant/WhatsApp channels while the dashboard channel keeps normal write access. Injecting a different `company_code` in tool args is overwritten by server scope before execution.

---

## 4. Duplicate / shadow truth — findings

| Store | Verdict |
|---|---|
| `leave_events`, `shift_events`, `leave_payroll_handoff_events`, `assistant_spine_events` | Append-only logs — legitimate |
| `leave_balances` (from `leave_ledger`) | Materialized rollup, ledger is SoT — legitimate, can lag if recompute is skipped |
| `attendance_day_projections` vs `attendance_records` | Intentional versioned dual-path during the authority migration |
| `employee_persons` / `_employments` / `_assignments` | Wave2 shadow dual-write, non-authoritative; `employees` remains the API source |
| `dashboard_operator_mobile_confirmations` | Ephemeral SOD staging, not business state |
| `hr_turns`, `memory_snapshots`, `dashboard_chat_*`, `semantic_documents` | Conversation/embedding memory. No leave/attendance/employee state duplicated |
| Mobile HR demo modules (7) | All gated; defaults `'0'` in `app.config.js`; **no** `EXPO_PUBLIC_HR_*_DEMO` set in any `eas.json` profile including canary/production |
| Client local storage | Tokens, PIN, locale, UI prefs only. No react-query disk persistence anywhere in the mobile app |

**No mobile-only DB, no frontend demo array in a production path, no shadow workflow table, no duplicated status store, and no fake production data was found in a real production path.**

---

## 5. Must-fix before first real customer onboarding

> **Closed 20260811T122043Z** by the Pre-Customer Hardening Wave —
> see `ops/PRE_CUSTOMER_ARCHITECTURE_HARDENING.md`. Every item below is fixed and
> proved live (13/13). Kept here as the original finding record.

1. **`onboarding_items` has no `company_code`.** Tenancy is inferred from `employee_key` prefix plus a join to `employees`, and `load_onboarding_items` **drops the company clause entirely when `company_code` is not passed** (`app.py:34895–34900`). It is safe today only because `employee_key` is globally unique and company-prefixed. Add the column (or make the company filter mandatory) before a second real tenant exists.
2. **`candidates.active_company_code` is nullable** — 15 production rows are NULL. Access is currently mediated by `applications.company_code`, which held under test, but a person-hub row with no tenant is a latent cross-tenant surface for any future direct-candidate query.
3. **Provenance mislabelling on canonical rows.** `/app/leave/request` correctly reuses the single canonical writer `request_leave`, but that writer hardcodes `metadata.source = "whatsapp"` (`app.py:20166`), so an Employee-App submission is stored as a WhatsApp submission. The true channel survives only in `record_admin_audit`. Business truth is not fake, but its origin is, which will matter in a customer dispute or audit.
4. **Pagination blockers** already logged in `ops/HR_MOBILE_QUEUE_PAGINATION_PRE_CUSTOMER_BLOCKERS.md` (items 1–3) remain must-fix. Real-scale queues can silently hide actionable work; this is the highest-impact correctness risk at customer scale.
5. **No optimistic-concurrency guard on the HR Web task resolve path.** HR Mobile sends `expected_status` on task resolve and document review; the web `/dashboard/hr-tasks/{id}/resolve` body accepts only `status`. Two HR users on different surfaces can silently overwrite each other. `row_version` exists on `leave_requests` and is used by the leave path — extend the same pattern.

### Safe debt (not blockers)

- **Cross-device convergence window.** Each client only invalidates its own cache; there is no server push. HR mobile `staleTime` is 20s with `refetchOnWindowFocus: false` and no polling, so a *mounted* HR screen can stay stale indefinitely until remount, pull-to-refresh, reconnect, or unlock. Employee app converges on foreground; the web dashboard refetches immediately after its own mutation and soft-polls every 60s while visible. Within a single client, every mutation refreshes its own list plus `mobile-priorities`. Two same-client gaps: document review does not invalidate `['onboarding']`, and employee leave request does not invalidate `['home']` / `['leave-history']`.
- **An OTA publish could flip a demo flag** if `EXPO_PUBLIC_HR_*_DEMO=1` were present in the publish environment, since `eas update` does not inherit `eas.json` `build.env`. No checked-in script does this; worth a publish-time guard.
- `compliance_documents.rejection_reason` is reused to carry HR review notes. Works, reads wrong.
- `whatsapp_suppressions` is phone-global by design, not tenant-scoped.
- No `Cache-Control`/`ETag` on any surface read endpoint. Fine today (no intermediary cache), but it means conditional-request revalidation is unavailable if a CDN is ever introduced.
