# Jobs Phase 2 — Stage B Assessment & Contained Implementation Plan

**Mode:** Design / audit only. **Do not implement until owner approval.**  
**Depends on frozen Stage A:** authority `6745622…`, share-surface `62f13c9…`, staging-green `faab3619…`.

## 1. Goal

Convert a uniquely bound temporary job context into a canonical application, then continue into CV processing — without weakening Stage A fail-closed authority.

```
temporary job context
  → explicit apply confirmation OR qualifying CV intent
  → transactional eligibility recheck
  → same-role duplicate handling
  → canonical awaiting_cv application creation
  → pending media attachment (if any)
  → continuation into CV processing
```

## 2. Existing implementation inventory (audit)

### 2.1 What Stage A already owns (reuse)

| Piece | Location | Stage B use |
|---|---|---|
| Exact APPLY + eligibility | `app.resolve_public_role_by_apply_code`, `prehire_jobs.assert_job_accepts_applications` | Recheck at convert |
| Context upsert / one-active uniqueness | `app.upsert_candidate_job_context`, unique index on active contexts | Input to convert |
| `preview_rendered_at` | set on context upsert | Not sufficient for apply intent |
| `preview_sent_at` column | DDL only; **never written** | Stage B delivery truth |
| CV hold table | `hold_candidate_pending_media` → `candidate_pending_media` | Attach after create |
| Same-role active lookup | `app.active_same_role_application` | Duplicate gate |
| Lifecycle stages / transitions | `recruiting_lifecycle` (`awaiting_cv` → …) | Post-create CV path |
| Conversation binding | `bind_conversation_application` (`bound_reason` includes `explicit_apply`) | Bind on convert |
| Withdrawal confirm pattern | `handle_candidate_withdrawal_turn` + idempotency keys | Mirror for apply confirm |
| Inbound claim/dedupe | `whatsapp_inbound_messages` | Crash-safe retries |
| Candidate copy stubs | `job_context_ready`, `cv_held_for_job_context`, `role_resolved_cv_request` | Wire confirm / post-create |

### 2.2 Orphaned / incomplete pieces (must be redesigned, not blindly revived)

| Piece | Gap |
|---|---|
| `start_public_candidate_application` | Defined in `app.py`; **no callers**. Delegates to external `WORKSPACE/tools/db/update_state.py start-application` (not in-tree). Must be replaced by an in-process, transactional Postgres create that writes `awaiting_cv` under lifecycle rules. |
| `attach_public_pending_cv_to_application` | Targets **`public_candidate_sessions.pending_media` jsonb**, not `candidate_pending_media`. Stage A CV holds use the table. Unify on the table. |
| `cv_counts_as_apply_intent` | Computed from `preview_sent_at` in `handle_candidate_file_turn` but **never acted on**; always false today because `preview_sent_at` is unset. |
| Context statuses `converted` / `declined` | Allowed by DDL; **never written**. |
| Source columns on contexts (`source_channel`, `source_ref_token`, `source_campaign`) | Present; **unused**. |
| Luna intents | Has `apply_role` (re-enters interest/selection only). **No** `confirm_apply` / ready-to-apply intent. Router must not invent application state. |
| Dual pending-media stores | Table (Stage A CV hold) vs session jsonb (interest path). Stage B attach must prefer the table; migrate or expire session jsonb holds. |

### 2.3 Binding and multi-role reality

- One **active** job context per `(phone, account_id, conversation_id)`.
- Switching APPLY codes expires prior active contexts for that conversation.
- Conversation→application binding is unique per `(company_code, conversation_id)` and can be overwritten on re-bind.
- Multiple non-terminal applications for one phone → CV mutations fail closed until exact role bind (`ambiguous_applications`).
- Same-role active app (not `rejected`/`withdrawn`/`hired`) short-circuits APPLY to “existing application” copy — Stage B must preserve this and never reset.

---

## 3. Exact conversion contract

### 3.1 Preconditions (all required)

1. **Unique active context** for this phone + account + conversation: status `awaiting_apply_confirmation`, `expires_at > now()`.
2. **Preview delivery truth:** `preview_sent_at IS NOT NULL`  
   - `preview_rendered_at` alone is insufficient (render ≠ send).
3. **Convert trigger** is one of:
   - **`apply_confirm`:** explicit ready-to-apply confirmation while context is uniquely bound; or
   - **`qualifying_cv`:** current-turn CV upload **and** `preview_sent_at` set (CV counts as apply intent only then).
4. **Transactional eligibility recheck** against live `positions` + vacancy counts with `access_mode="exact_token"` immediately before insert. Fail closed with the same unavailable reasons as Stage A.
5. **No vague interest conversion.** Discovery / NL interest / ordinal selection only bind or re-bind context; they never create applications.

### 3.2 Transactional convert unit (single DB transaction)

Order inside one transaction (advisory lock on the same phone/account/conversation key used by context upsert):

1. Lock + re-read active context; abort if missing, expired, or not unique.
2. Re-resolve role by exact `apply_code`; abort if ineligible (`job_paused`, `job_closed`, `job_deadline_passed`, `job_vacancies_exhausted`, `job_visibility_denied`, `job_content_incomplete`, `job_not_accepting`).
3. **Same-role duplicate handling:**
   - If active same-role application exists → do **not** create; mark context `converted` or leave awaiting with “existing application” reply; attach pending media to the **existing** app only if safe and same role; return `application_created=false`.
   - If prior same-role application is **terminal** (`withdrawn`/`rejected`/`hired`) → allow a **new** application (new `app_key`), do not revive the terminal row.
4. Insert/upsert canonical application at stage **`awaiting_cv`** with:
   - company/position/phone from context
   - locale from `preview_locale` / request
   - `source_conversation_id`, `account_id`
   - copied attribution: `data_source*`, and when present `source_channel` / `source_ref_token` / `source_campaign`
   - idempotency key (see §5)
5. Bind conversation: `bound_reason="explicit_apply"` (or `qualifying_cv` if CV-triggered — still explicit apply intent under Stage B rules).
6. Mark context `status='converted'`, set `converted_at` / `application_app_key` if columns added (prefer additive columns rather than overloading metadata).
7. Attach held `candidate_pending_media` rows for this phone/account/conversation: register CV file onto the application, set media `status='attached'`, then hand off to existing `register_candidate_cv_file` / lifecycle `mark_cv_received` → `cv_processing`.
8. Write audit / lifecycle event; commit.
9. **Only after commit** send success copy (`role_resolved_cv_request` or “CV received, processing”). Never claim success before backend confirmation.

### 3.3 Idempotency keys (proposed)

| Event | Key shape |
|---|---|
| Convert from confirm | `jobctx-convert:{context_id}:{provider_message_id\|confirm_nonce}` |
| Convert from qualifying CV | `jobctx-convert-cv:{context_id}:{media_sha256\|pending_id}` |
| Preview sent stamp | `jobctx-preview-sent:{context_id}:{outbound_delivery_id}` |
| Context→converted | Unique partial index or lifecycle event uniqueness prevents double apps |

Retries with the same key return the same application without creating a second row.

---

## 4. Scenario matrix (required Stage B behavior)

| Scenario | Required behavior |
|---|---|
| **`apply_confirm` with one uniquely bound context** | Recheck eligibility → create `awaiting_cv` (or short-circuit to existing same-role) → bind → convert context → ask for CV if none held → success only after commit. |
| **CV after preview actually sent** (`preview_sent_at` set) | Qualifying CV intent → same convert path → attach this CV → enter `cv_processing`. |
| **CV before preview delivery** (`preview_sent_at` null) | Hold media only; `cv_counts_as_apply_intent=false`; **no application**. Optionally bind context if caption APPLY resolved; still no convert. |
| **CV with no context** | Hold media; ask for role / APPLY; **no application**; no role guess. |
| **CV with multiple possible contexts** | Should not occur under one-active unique index for a single conversation. If multi-conversation / multi-app ambiguity → fail closed; ask for exact APPLY; hold media; never pick. |
| **Repeated confirmation** | Idempotent: second confirm returns existing converted app / same reply; zero extra applications. |
| **Repeated CV delivery** | After app exists: update/replace via existing CV registration + SHA dedupe. Before convert: replace pending media (expire prior pending). |
| **Same candidate + same role active application** | No new app; preserve pipeline; allow CV update / status; existing-application copy. |
| **Same candidate + another role** | New context for other role (expires prior context on that conversation). Convert creates a **separate** application. **No automatic CV reuse** across roles — prior pending media must not auto-attach to the new role unless the candidate re-sends or explicitly confirms reuse (default: **no reuse**). |
| **Terminal prior application** | New application allowed for same role after withdraw/reject/hire terminal; do not reopen terminal row. |
| **Source attribution copying** | Copy context attribution + request data_source into application at convert; REF tokens reserved for Stage C but columns must not be dropped. |
| **Locale + conversation binding** | Persist `preview_locale` onto application `candidate_locale`; bind `conversation_id`/`account_id` before any further mutations. |
| **Eligibility changes between preview and confirmation** | Convert aborts; context expired or left awaiting; candidate gets unavailable reason; held media stays pending (not attached to a non-existent app). |
| **Vague interest only** | Never creates application (Stage A rule preserved). |
| **Success claim** | Outbound “application started” / “CV received” only after committed application row (and attach where applicable). |

---

## 5. Transaction boundaries, audit, cleanup, crash recovery

### 5.1 Boundaries

- **Preview send stamp:** separate short transaction after verified outbound success (dry_run staging may stamp on dry-run accept — product decision; production requires real send ack).
- **Convert:** one transaction for lock → recheck → insert app → bind → convert context → attach pending metadata pointers.
- **CV binary registration / extraction:** may continue after commit (existing `register_candidate_cv_file` + async `process_candidate_cv_document`), but application row and attach status must already be durable.

### 5.2 Audit events (minimum)

- `job_context_preview_sent`
- `job_context_convert_started` / `job_context_convert_committed` (or single lifecycle `explicit_apply` event)
- `job_context_convert_rejected` (eligibility / duplicate / ambiguity)
- `pending_media_attached`
- Reuse lifecycle `application_lifecycle_events` idempotency where possible

### 5.3 Cleanup / expiry

- Expire `awaiting_apply_confirmation` contexts past `expires_at` (already constrained by queries; add sweeper if missing).
- Expire `candidate_pending_media` past TTL; never attach expired media.
- Converted contexts retained for audit; not reusable for a second convert.
- Crash after commit but before reply: inbound dedupe + convert idempotency key → safe retry returns same app, re-sends deterministic copy.

### 5.4 Failure modes

| Failure | Result |
|---|---|
| Lock contention | Retry once; else ask candidate to resend confirm/CV |
| Eligibility fail at convert | No app; unavailable copy; media remains pending |
| External tool / IO during create | Must not be on the critical path — in-process Postgres only |
| Extraction failure after attach | App remains; CV facet/status follows existing processing recovery |

---

## 6. Contained implementation plan (no code yet)

### Workstream B0 — Delivery truth (prerequisite)

1. Define the single place outbound candidate preview replies are considered sent.
2. On success, set `candidate_job_contexts.preview_sent_at` (idempotent).
3. Staging dry_run policy: explicit documented rule (stamp on dry-run acceptance vs require a synthetic ack). Prefer stamping in dry_run so Stage B can be tested without WhatsApp, while production stamps only on real ack.

### Workstream B1 — Convert authority module

1. New in-process `convert_job_context_to_application(...)` in jobs/lifecycle boundary (not external `update_state.py`).
2. Implements §3.2 with advisory lock + idempotency.
3. Writes `awaiting_cv`, bind, context `converted`.
4. Unit tests for every row in §4.

### Workstream B2 — Triggers

1. Deterministic `apply_confirm` parser (and optional Luna intent that **only** classifies; backend still executes convert).
2. Wire `handle_candidate_file_turn`: if unique context + `preview_sent_at` → convert+attach; else keep Stage A hold behavior.
3. Remove/avoid success copy until convert returns committed app.

### Workstream B3 — Pending media unification

1. Attach path reads `candidate_pending_media` for the conversation.
2. Stop writing new CV holds only to session jsonb; migrate any interest-path holds into the table or expire them with “please resend CV”.
3. **No cross-role auto-reuse** of attached or pending CVs.

### Workstream B4 — Post-create continuation

1. If convert without CV → send `role_resolved_cv_request`.
2. If convert with CV → register file → `mark_cv_received` / `cv_processing` → existing extraction worker.
3. Preserve withdrawal / status / multi-app fail-closed behaviors.

### Workstream B5 — Validation & staging gate

1. Expand unit matrix for §4 scenarios.
2. Guarded staging smoke: convert creates exactly one app; repeats are idempotent; CV-before-preview still zero apps; eligibility flip blocks convert; share-surface rules unchanged.
3. No production promotion in Stage B design phase; staging-green only after smokes.

### Explicit non-goals for Stage B

- Luna factual Q&A over job fields (may be parallel thin slice later; not required to land convert).
- REF / campaign attribution product UX (Stage C).
- Public web apply.
- Automatic shortlist/reject/hire.
- CV reuse across roles.
- Weakening Stage A shareability / eligibility / exact APPLY rules.

---

## 7. Recommended sequencing

1. B0 preview-sent stamp (unblocks qualifying CV intent).
2. B1 convert module + tests (no WhatsApp handler change yet).
3. B2 confirm + CV triggers.
4. B3 pending-media attach unification.
5. B4 copy + processing continuation.
6. B5 staging qualification.

Stop point after each workstream: owner review. **No coding starts until this assessment is approved.**

## 8. Open decisions for owner (before coding)

1. **Dry-run `preview_sent_at`:** stamp on staging dry-run accept, or require a test-only ack hook?
2. **Confirm UX:** keyword/phrase list only, or also Luna `confirm_apply` classification feeding the same backend convert?
3. **Terminal re-apply:** confirm new `awaiting_cv` app after withdraw/reject (recommended above).
4. **Interest-path pending media:** expire-and-ask-resend vs best-effort migrate into `candidate_pending_media`.

---

## 9. References

- Stage A closure: `ops/JOBS_PHASE2_STAGE_A_CONTRACT.md`
- Context/pending schema: `prehire_jobs.py` (`candidate_job_contexts`, `candidate_pending_media`)
- File turn / hold: `app.handle_candidate_file_turn`, `hold_candidate_pending_media`
- Orphaned create/attach: `app.start_public_candidate_application`, `attach_public_pending_cv_to_application`
- Lifecycle: `recruiting_lifecycle.py` stages, bind/resolve, `mark_cv_received`
- Candidate copy: `candidate_messages.py`
