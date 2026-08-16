# Pre-Hiring End-to-End Qualification

**Date:** 2026-07-25
**Scope:** Jobs, Candidates, Ranking, Reports, Assistant, Assessments, Interviews, Offers/Hiring — qualified together as one workflow
**Mode:** Read-only with respect to product code. No frozen module was modified, reopened, or deployed.
**Environment:** isolated staging (`wathefni_staging`), proven byte-identical to production across all 26 frozen-module files
**Evidence:** `ops/prehire-e2e/prehire-e2e-staging-matrix-20260725T001900Z.json` — SHA256 `d263654da2be0da3ce260c9e952b942b255ca79f8ef743abb2e5c96b5403081e`
**Harness:** `ops/prehire-e2e/prehire-e2e-qualification-matrix.py` — SHA256 `957821ce3afb578fdc9d9fea00ef905bca66e9e2d91fcb20e8db136390fd5429`
**Result:** **360 gates passed / 22 failed**, the 22 failures reducing to **5 distinct findings**

---

## 1. Executive verdict

The eight frozen modules operate as **one coherent workflow with a single, unambiguous chain of authority**. Across every module combination tested, a job can be created and published, a candidate can apply and be processed, CV-based Ranking runs before any optional module exists, and an offer can be created, approved, sent, accepted and converted into exactly one employee with the approved post-hire handoff. No conflicting authority, duplicate action, misleading state or broken handoff was found in the hiring path itself.

**The pre-hiring lifecycle is qualified for production.** All 118 gates covering the two fully-enabled tenants (`E2EAVO`, `E2EPEER`) passed with zero failures, as did all Ranking, Offers/Hiring, hire-atomicity, authority, privacy, tenant-isolation and cleanup gates in every other tenant.

**One requirement in the stated contract cannot be satisfied today.** Wathefni has no Interviews module. The approved catalog contains `pre_hiring`, `assessments`, `video_interviews` and `employment_offers`; live interviews are part of `pre_hiring` and are therefore always on. The "Interviews OFF" half of the contract is not implemented — this is a product-scope decision, not a code fault, and it does not block or degrade any other pre-hiring function. Four of the five findings trace to this single root cause.

**Verdict:** production-qualified for tenants where Interviews is intended to be available. Do not commit an "Interviews OFF" contract to any tenant until the owner decides whether live interviews should become a switchable module.

---

## 2. Authority and handoff map

Every stage change in the system passes through exactly one function. This was verified by enumerating callers in source and then exercising each entrypoint.

### Single write authority

`recruiting_lifecycle.transition_application` is the sole writer of `applications.status` and `lifecycle_version`. A database trigger blocks any direct status write unless the session flag `wathefni.lifecycle_authority='canonical'` is set, which only that function sets.

| Concern | Mechanism | Proven by |
|---|---|---|
| Allowed stages | `awaiting_cv → cv_processing → ready_for_review → shortlisted → interview → hired/rejected/withdrawn` | `canonical_cv_lifecycle_to_ready_for_review`, `canonical_shortlist_*` |
| Terminal stages | `hired`, `rejected`, `withdrawn` have no outbound transitions | `terminal_stage_cannot_be_hired` |
| Stale state | `expected_version` mismatch returns `stale_state` | `stale_version_rejected` (expected 10, current 3) |
| One-time confirmation | Replaying a used token returns `confirmation_already_used` | `confirmation_token_single_use` |
| Concurrency | Two simultaneous confirmed rejects yield one winner | `concurrent_decisions_single_winner` |
| AI limits | `actor_type="ai"` on a decision transition returns `ai_cannot_mutate_stage` | `ai_cannot_reject_candidate`, `ai_cannot_hire_candidate` |

### Per-module authority

| Module | Owns | Reads | May not do |
|---|---|---|---|
| **Jobs** | `positions` draft/open/paused/closed, apply code, publish eligibility | company display name, vacancy counts | create applications; accept intake while not `open` |
| **Candidates / Lifecycle** | application stage, confirmations, lifecycle events | permissions, ranking presentation | bypass the canonical transition; let AI decide |
| **Ranking** | `ranking_runs`, `ranking_run_items`, narratives, criteria versions | job pool, approved criteria, optional assessment scores | mutate any lifecycle stage; auto-shortlist or auto-hire |
| **Assessments** | attempts, invitations, responses, scores, reports | application identity for targeting | change stage; force ranking eligibility |
| **Interviews** | `candidate_interviews`, assignments, feedback, calendar sync | application identity | auto-hire or auto-reject from an outcome |
| **Offers** | offer entity, versions, events, tokens, deliveries, hire gate, override audit | accepted offer, application stage | be approved, sent, withdrawn or overridden by AI |
| **Hire** | `hire_operations`, `employees`, post-hire seeding | accepted-offer gate, confirmation | complete outside a single transaction |
| **Reports** | `report_export_audits` only | lifecycle events, offers, interviews, ranking | mutate pipeline state |
| **Assistant** | proposals, tool selection, confirmation UX | registry tools within entitlement | execute a decision without a human confirmation |

### Handoff chain (verified end to end in all six tenants)

Job published (`open` + `APPLY-{COMPANY}-{POSITION}` + `wa.me` link) → application at `awaiting_cv` → `mark_cv_received` → `cv_processing` → `mark_cv_ready_for_review` → `ready_for_review` → CV Ranking (advisory, no mutation) → human shortlist → *optional* assessment / *optional* interview → offer draft → two-person approval → send → candidate accepts via token → hire gate → `prepare_hire_operation` → confirmation mint → `execute_hire_operation` → single transaction writes `hired` + one `employees` row + three `compliance_documents` → post-hire modules.

The Offers module is deliberately orthogonal to stage: an application stays `shortlisted` or `interview` while its offer moves through its own lifecycle. This was confirmed — no offer transition ever moved a candidate's stage.

---

## 3. Module ON/OFF contract: stated vs. implemented

| Contract requirement | Assessments | Offers | Interviews |
|---|---|---|---|
| Has a tenant switch | Yes (`assessments`) | Yes (`employment_offers`) | **No module key exists** |
| Disappears from navigation | Yes | Yes | n/a |
| Disappears from Reports | Yes (counts and wording) | Counts yes, **labels no** | No |
| Disappears from Assistant | Yes (tools hidden) | Yes (no mutation tools exist) | No |
| Disappears from mobile | Yes (key omitted) | Yes (`enabled:false`, `module_disabled`) | No |
| Disappears from queues/counts | Yes | Yes | **No — scheduling debt still raised** |
| Blocks reads/mutations server-side | Yes at route and entitlement layer | Yes at route, service and gate layer | n/a |
| Preserves history without exposing it | Yes | History preserved; **public link still exposes it** | n/a |
| Non-blocking for Ranking/Offers/Hiring | Yes | Yes (hire gate relaxes correctly) | Yes |
| Optional when enabled, never required | Yes | Yes | Yes |

The catalog is the authoritative statement of what is switchable:

```
pre_hiring, assessments, video_interviews, employment_offers,
onboarding, compliance, attendance, shifts, leave, payroll, analytics, employee_app
```

`video_interviews` covers only the asynchronous AI video product. Live interviews — scheduling, panel, notes, feedback, Google Calendar — are gated on `pre_hiring` and on the `interview.manage` permission. In `app.py` the overview callers pass `interviews_enabled=("interviews" in enabled_modules) or True`; because no `"interviews"` key exists, the left operand is always false and the `or True` makes the expression unconditionally true. Interview queues and SLAs are therefore permanently enabled.

---

## 4. Scenario and combination matrix

Six isolated synthetic tenants, five candidates each (`main`, `bare`, `reject`, `withdraw`, `ardoc`), all marked `prehire-e2e-qualification-v1`.

| Tenant | Assessments | Video interviews | Offers | Purpose | Gates |
|---|---|---|---|---|---|
| `E2EAVO` | ON | ON | ON | Assessments ON / Interviews ON | **59 pass / 0 fail** |
| `E2EAXO` | ON | OFF | ON | Assessments ON / Interviews OFF | 57 pass / 5 fail |
| `E2EXVO` | OFF | ON | ON | Assessments OFF / Interviews ON | 58 pass / 1 fail |
| `E2EXXO` | OFF | OFF | ON | Assessments OFF / Interviews OFF | 56 pass / 6 fail |
| `E2ENOOF` | OFF | OFF | OFF | Offers disabled per tenant contract | 46 pass / 7 fail |
| `E2EPEER` | ON | ON | ON | Cross-tenant peer + history preservation | **59 pass / 0 fail** |
| contract | — | — | — | Catalog and default-policy invariants | 3 pass / 2 fail |
| cross_cutting | — | — | — | AI limits, concurrency, isolation, public routes, history | 15 pass / 1 fail |
| cleanup | — | — | — | Zero residue | 1 pass / 0 fail |

Additional dimensions exercised inside these tenants: Google Calendar connected and disconnected; interview used and skipped; assessment used and skipped; offer accepted, expired, withdrawn and resent; rejection at `ready_for_review`; withdrawal at `shortlisted`; hire attempted on a terminal application; duplicate hire confirmation; stale lifecycle version; concurrent decisions; cross-tenant application, confirmation and offer identifiers; public assessment, public offer and expired-link routes.

---

## 5. Pass / fail results by requirement

| # | Requirement | Result | Evidence |
|---|---|---|---|
| 1 | Job creation and publication | **Pass** (6/6 tenants) | `job_created_draft`, `job_published_open_with_apply_identity` → `APPLY-E2EAVO-E2E_ROLE`, `https://wa.me/96599338566?text=...`, `published_job_accepts_applications` |
| 2 | Application, CV processing, canonical lifecycle | **Pass** | `canonical_cv_lifecycle_to_ready_for_review`, `lifecycle_events_recorded` (≥10 per tenant) |
| 3 | CV Ranking works before Assessments or Interviews | **Pass** | `cv_ranking_functional_before_optional_modules` (5 items), `ranking_does_not_mutate_lifecycle`, `ranking_run_declares_no_lifecycle_mutations` |
| 4 | Assessments ON: optional, no penalty for unassigned | **Pass** | `assessment_optional_send_available`, `assessment_send_not_claimed_delivered` (`intentionally_skipped`), `unassigned_candidate_has_no_attempt`, `overview_assessment_pending_assigned_only` |
| 5 | Assessments OFF: zero wording/fields/tools/counts; history preserved | **Pass** except service-layer guard | `overview_omits_assessment_counts_when_off`, `reports_zero_assessment_wording_when_off` (`[]`), `reports_assessments_export_blocked_when_off`, `mobile_omits_assessments_when_off`, `assistant_hides_assessment_tools_when_off`, `assessments_off_entitlement_403`; **fails** `assessments_off_service_mutation_blocked` (finding F5) |
| 6 | Interviews ON: async video and live work; do not control Ranking/Offers/Hiring | **Pass** | `live_interview_schedulable_when_on`, `async_video_interview_works_when_on`, `google_calendar_connected_path_works`, `google_calendar_disconnected_still_works`; the `bare` candidate skipped interviews and still reached hire |
| 7 | Interviews OFF: zero wording/fields/tools/counts/links | **Fail** | Findings F1–F3 |
| 8 | Offer creation, approval, send, acceptance, expiry, withdrawal, resend | **Pass** | `offer_draft_created`, `offer_approved_two_person`, `offer_sent`, `offer_resend_ok`, `offer_accepted_by_candidate`, `offer_expiry_canonical_and_idempotent`, `expired_offer_status_is_terminal_and_not_rewritable`, `sent_offer_withdrawable_and_tokens_revoked` (1 token revoked) |
| 9 | Hire requires the canonical accepted-offer gate when Offers is enabled | **Pass** | `hire_requires_accepted_offer_when_offers_on` → `accepted_offer_required`; `offers_off_hire_gate_not_required` → `{"required": false}` |
| 10 | Hire atomically creates one employee and performs the handoff | **Pass** | `atomic_hire_one_employee` (1 employee, `hire_operations.status=completed`), `post_hire_handoff_seeded` (3 compliance documents), `duplicate_hire_confirmation_no_second_employee`, `no_half_hire` |
| 11 | Reports counts consistent; disabled sections omitted | **Partial** | `reports_funnel_matches_lifecycle_truth` and `reports_offer_accepted_matches_truth` pass in all six tenants; disabled-module *labels* remain (finding F3) |
| 12 | Assistant exposes only enabled, permitted, valid actions | **Partial** | `assistant_hides_assessment_tools_when_off` passes; `assistant_exposes_no_offer_mutation_tools` passes; interview tools remain visible (finding F2) |
| 13 | Arabic/English, mobile, permissions, isolation, audit, privacy, public routes | **Pass** | Section 9 |
| 14 | No Ranking/Assessment/Interview/AI output changes candidate authority | **Pass** | `ai_cannot_reject_candidate`, `ai_cannot_hire_candidate`, `ai_cannot_use_hire_override` (`ai_forbidden`), `ranking_does_not_mutate_lifecycle` |

---

## 6. Cross-module state consistency

Reports were compared against database truth in every tenant, not merely inspected. For each of `ready_for_review`, `shortlisted`, `interview` and `hired`, the reported funnel count was checked against `COUNT(DISTINCT app_key)` of lifecycle events entering that stage, and `offer_accepted` against distinct applications holding an accepted offer.

`reports_funnel_matches_lifecycle_truth` returned `{"mismatch": {}}` in all six tenants. Representative results:

- `E2EAVO` (everything on): `cv_received 5, ready_for_review 5, shortlisted 3, interview 0, offer_sent 3, offer_accepted 1, hired 1` against status truth `hired 1, rejected 1, shortlisted 2, withdrawn 1`.
- `E2ENOOF` (offers off): `offer_sent 0, offer_accepted 0, hired 1` — the offer stages report zero, correctly, because no offer exists.

No stage was double-counted, no terminal candidate leaked into an open bucket, and no offer or interview state contradicted the application stage.

---

## 7. Ranking independence proof

Ranking was executed in all six tenants after CV evidence and facts were materialised, and before any assessment or interview existed.

1. **Functional without optional modules.** `rank_job_applications` returned five ranked items in every tenant, including `E2EXXO` and `E2ENOOF` where both optional modules are off.
2. **No lifecycle mutation.** Stages were captured before and after each run and were identical: `{"main": "ready_for_review", "bare": "ready_for_review", "reject": "ready_for_review", "withdraw": "ready_for_review", "ardoc": "ready_for_review"}`. Runs are stamped `lifecycle_mutations: false`.
3. **No assessment or interview evidence by default.** The default policy is `assessment: unused, interview: unused`. Component scores contained only `skills_alignment`, `experience_alignment` and `education_cert_alignment` — `assessment_evidence` was `0.0` and no `interview_evidence` key existed, in every tenant including the ones where Assessments is on.
4. **No penalty for absence.** The `bare` candidate, which never received an assessment or an interview, ranked normally and was never marked as missing evidence.
5. **Stale history is inert.** On `E2EPEER`, an assessment attempt, three interviews and five offers were created while the modules were on; after disabling all three modules, re-ranking produced identical component scores with `assessment_evidence` still `0.0` (`stale_history_does_not_affect_ranking`).

---

## 8. Offers/Hiring independence proof

1. **Independent of Assessments.** Offer draft → approve → send → accept → hire completed in `E2EXVO` and `E2EXXO` where Assessments is off.
2. **Independent of Interviews.** The same chain completed for the `bare` candidate, who never had an interview, in every tenant.
3. **Correct behaviour when Offers itself is off.** In `E2ENOOF`, `create_draft` raised `module_disabled`, `enforce_hire_gate` returned `{"ok": true, "required": false, "offer_id": null, "override": false}`, mobile reported `{"enabled": false, "reason": "module_disabled"}`, and hire still completed atomically with one employee.
4. **One accepted offer governs an application.** After acceptance, a second offer could still be drafted and approved, but the accepted count stayed at exactly `1`, enforced by the unique index (`one_accepted_offer_governs_application`).
5. **Privacy on stale links.** After expiry, the public link raised `This offer link was revoked` and disclosed no compensation (`expired_link_reveals_no_compensation`). Withdrawing a sent offer revoked its outstanding token.
6. **Terminal statuses are not rewritable.** An expired offer could not be withdrawn; status remained `expired`.
7. **Document control.** Approving an Arabic offer without a company-approved uploaded Unicode PDF raised `arabic_upload_required`.

---

## 9. Permissions, privacy, audit, Arabic, mobile and public routes

**Permissions and authority.** Hire requires `candidate.decide`; offer withdrawal requires `offer.withdraw`; hire override requires the grant-only `offer.hire_override` permission plus explicit confirmation and a reason. An AI actor attempting override was rejected with `ai_forbidden: Only a human operator can use offer hire override.`

**Tenant isolation.** Using tenant A's application key under tenant B returned no row; minting a confirmation returned `application_not_found`; the transition was refused; loading tenant A's offer under tenant B returned `offer_not_found`.

**Audit.** Every stage change wrote an `application_lifecycle_events` row (≥10 per tenant before decisions). Offer events, delivery operations and hire operations were all recorded. Report exports write `report_export_audits`.

**Arabic and English.** Jobs were created with `title_ar` "مهندس عمليات", Arabic summary and Arabic requirements, and published successfully. The public assessment page carries both `بدء التقييم` and `dir="rtl"`. Arabic offer documents are gated on an approved Unicode PDF at approval time.

**Mobile.** Capability payloads were built per tenant. With Assessments off, the `assessments` key is absent entirely rather than present-and-false. With Offers off, `employment_offers` is `{"enabled": false, "actions": [], "reason": "module_disabled"}`. With interviews off, no interview wording appeared in the mobile payload.

**Public routes.** The assessment unavailable page renders a neutral "Link unavailable" shell with no tenant identifier. Public offer preview works for a live token and refuses a revoked one. The one exception is finding F4.

---

## 10. Historical record preservation

On `E2EPEER`, one assessment attempt, three interviews and five offers were created while all modules were enabled. All three modules were then disabled and the same counts re-read:

```
before: {"attempts": 1, "interviews": 3, "offers": 5}
after:  {"attempts": 1, "interviews": 3, "offers": 5}
```

Nothing was deleted or cascaded. Disabling a module writes `company_modules.enabled = false`; no data is removed. With the modules off, Reports, mobile capabilities and overview counts were scanned for assessment wording and returned `[]` (`disabled_history_not_exposed_in_payloads`), and re-ranking ignored the preserved assessment entirely.

---

## 11. Cleanup proof

The harness removes every row it created and then counts residue across thirty tables plus the synthetic phone range.

```
companies 0            applications 0         lifecycle_events 0     confirmations 0
company_modules 0      positions 0            ranking_runs 0         ranking_items 0
cv_evidence 0          cv_facts 0             semantic_docs 0        files 0
assessment_attempts 0  assessment_invitations 0
interviews 0           interview_events 0     interview_schedule_ops 0
offers 0               offer_events 0         offer_tokens 0         offer_deliveries 0
offer_send_ops 0       hire_operations 0      hire_override_audits 0
employees 0            compliance_documents 0 employee_documents 0   onboarding_items 0
report_export_audits 0 candidates 0
```

Twenty generated offer PDFs were deleted from disk. No cleanup errors occurred.

**Production was never touched.** Counting the same synthetic company codes and the `+9658860` phone range against the production database returned `PRODUCTION_SYNTHETIC_TOTAL 0`.

---

## 12. Findings

### F1 — Interviews is not a switchable tenant module — *confirmed integration blocker for the stated contract*

The module catalog has no Interviews key. Live interview scheduling, panels, notes, feedback and calendar sync are gated on `pre_hiring` and `interview.manage`; only asynchronous AI video has its own switch (`video_interviews`). The overview callers pass `interviews_enabled=("interviews" in enabled_modules) or True`, which is unconditionally true because the key does not exist.

Observed with `video_interviews` disabled, in three tenants:

- `interviews_off_blocks_live_scheduling` — a live phone interview was scheduled successfully (`status: scheduled`).
- `interviews_off_no_interview_queue_or_warning` — the work queue raised `interview_scheduling_debt` items for `bare` and `ardoc` with reason *"Interview scheduling still needed"*, priority 40, destination page `interviews`, authority `prehire_overview.interview_scheduling_debt`. This is exactly the "unassigned candidates must have no interview warning or SLA" clause, and it is violated.

**Impact on the hiring workflow: none.** Ranking, Offers and Hiring all completed normally in these tenants. The defect is confined to the module contract.

**Classification note.** This is a product-scope decision rather than a code fault: live interviewing appears to have been designed as a core Pre-Hiring capability. Remediation is not a bug fix — it is an owner decision on whether to introduce a switchable Interviews module. Until that decision is made, an "Interviews OFF" contract must not be offered to a tenant.

### F2 — Assistant discovers interview tools for tenants without the module — *minor defect*

`TOOLCALL_GATED_MODULES` contains only `assessments` and the post-hire modules. `video_interviews` and `employment_offers` are not toolcall-gated, so with `video_interviews` off the Assistant still lists `schedule_interview`, `reschedule_interview`, `cancel_interview`, `send_interview_invite`, `get_interview_invite_status` and `send_video_interview`.

Execution does not leak. The tool-to-module mapping was verified directly: `send_video_interview → video_interviews`, `send_assessment → assessments`, `schedule_interview → pre_hiring`; and `_require_tool_entitlements` returned a block for every tool tested. This is a discovery and wording leak, not an authority bypass. Note that `schedule_interview` maps to `pre_hiring`, so it would remain executable even if it were hidden — that part is F1, not F2.

### F3 — Reports name interview and offer stages regardless of module state — *minor defect*

With interviews off, the payload still contains a funnel stage keyed `interview`, a matching `applications_by_stage` label, and an `interviews` export type. With `employment_offers` off, the funnel still contains `offer_sent` and `offer_accepted` stages and labels.

**No data leaks.** The counts are zero in those tenants (`offer_sent 0, offer_accepted 0, interview 0`) and every funnel count matched lifecycle truth. This is cosmetic wording only, but the contract requires disabled modules to disappear from Reports entirely. Assessments, by contrast, is handled correctly: wording, counts and the export type are all removed.

### F4 — Public offer links stay live after the Offers module is disabled — *material integration defect*

`public_offer_preview` resolves purely on token validity and never checks `employment_offers`. Disabling the module mid-flight and re-fetching a previously issued token returned the full payload including `base_salary`, `allowances` and `authorized_signatory`. HR-side offer reads and mutations correctly return 403 in the same state.

This is the one place where a disabled module still *exposes* preserved history rather than merely retaining it. It is genuinely two-sided: the token was legitimately delivered to a candidate while the module was enabled, and silently revoking a live offer link when an operator toggles a module could be worse than leaving it. This needs an explicit product decision — revoke on disable, keep serving with a notice, or keep current behaviour and document it — rather than an automatic code change.

### F5 — Two service functions do not re-check module state — *minor defect (defense in depth)*

`create_or_resume_assessment_attempt` and `create_or_resume_async_video_interview` create records even when their module is disabled. Both were called directly in the harness and succeeded in tenants where the module was off.

**No exploitable path was found.** Every caller was enumerated: the video route calls `require_entitlement(context, "video_interviews", "interview.manage")` first; the registry executor is gated by `ACTION_REQUIRED_MODULES`; the assessment path runs behind `assessments_dashboard_context`; the candidate WhatsApp path returns a safe unavailable reply. The entitlement layer itself was confirmed to deny with `required_module: assessments`. This is a missing inner guard, not a reachable bypass.

### Explicitly not findings

The following were examined and are **already sufficient**; no action is recommended.

- A second offer can be drafted and approved after one is accepted. The accepted count is held at one by a unique index, and an approved-but-not-accepted offer is a legitimate state (for example, a corrected offer prepared before withdrawal). No misleading state was produced.
- Expired offers cannot be withdrawn. This is correct terminal-status behaviour, not a gap.
- Assistant may propose a stage change. Execution still requires a human-minted confirmation and the canonical transition, both of which were proven to hold.
- Ranking falls back to an automatic advisory role profile when no approved criteria set exists. The result is still stamped advisory and still cannot mutate anything.

---

## 13. Production qualification recommendation

**Qualify the integrated pre-hiring lifecycle for production.** The workflow is coherent, the authority model holds under concurrency, retries, stale state and cross-tenant probing, and hire remains atomic with a correct post-hire handoff in every configuration tested. Nothing found here justifies reopening a frozen module.

Recommended actions, in priority order:

1. **Decide the Interviews module question (F1).** Either introduce a switchable Interviews module, or formally record that live interviewing is a core Pre-Hiring capability and remove "Interviews OFF" from the tenant contract. Until then, do not sell or configure an Interviews-disabled tenant. Also remove the dead `("interviews" in enabled_modules) or True` expression whichever way the decision goes, since it currently implies a switch that does not exist.
2. **Decide the public offer link policy (F4).** Choose deliberately between revoking outstanding candidate links when the Offers module is disabled and continuing to honour them. Document the choice.
3. **Fold F2, F3 and F5 into ordinary maintenance.** Adding `video_interviews` and `employment_offers` to `TOOLCALL_GATED_MODULES`, gating the interview and offer funnel labels on their modules, and adding inner module checks to the two service functions are small, low-risk changes with no cross-module dependency. None is urgent; none blocks production.

No remediation is recommended for Jobs, Candidates, Ranking, Reports, Assistant, Assessments or the hire path. All remain frozen and green.

---

## 14. Coverage limits

Stated so the verdict is not read as broader than the evidence:

- Dashboard navigation was verified from module keys in source (`App.tsx`), not by rendering the React application.
- Mobile behaviour was verified at the capability-builder and data-layer level, not over HTTP against the device client.
- Google Calendar was exercised with the provider layer mocked in both connected and disconnected states; no live Google account is attached to staging. Real calendar sync remains covered by the frozen Interviews matrix and the live soak report.
- Arabic offer document rendering fidelity is covered by the frozen Offers/Hiring matrix; this qualification proved the approval-time control, not the glyph output.
- The Assistant was qualified at tool discovery, entitlement mapping and confirmation-authority level; no live LLM conversation was replayed.
