# Pre-Hiring Interviews — End-to-End Assessment

**Assessment date:** 2026-07-24 (Kuwait)  
**Mode:** Read-only source, test, configuration, service, API-guard, and aggregate production-data inspection  
**Implementation/deployment:** None  
**Authoritative source inspected:** `/tmp/wathefni-c3-local`  
**Frozen authorities left unchanged:** Jobs, Candidates, Ranking, Reports, Assistant, and Assessments

## Executive verdict

**Verdict: Interviews has a credible core and strong module boundaries, but it is not yet an enterprise-ready end-to-end authority for the scope stated in this assessment. A contained Interviews-only remediation is justified.**

The parts that should be preserved are:

- interview status is an orthogonal facet, separate from canonical application stage;
- live scheduling can move an application to `interview` only through the explicit canonical lifecycle contract;
- cancellation is the only interview outcome that intentionally moves the application back to `shortlisted`;
- completion, no-show, feedback, and AI summaries do not hire, reject, rank, issue offers, or otherwise make a candidate decision;
- Ranking R0–R3 explicitly keeps interview scoring disabled;
- authenticated list, fetch, mutation, mobile, and media paths are tenant-scoped;
- schedule, invite, and video-send Assistant actions require `interview.manage` and human confirmation;
- public async-video state and mutations use an expiring HMAC token, module gate, cancellation gate, and recording consent;
- async-video transcription has an active production worker, human-advisory summaries, original-video evidence, and a manual retry path;
- Reports and mobile consume the canonical interview rows rather than inventing a parallel interview authority.

The confirmed blockers are at contained Interviews boundaries:

1. **Cancel and reschedule do not synchronize Google Calendar/Meet.** A cancelled interview can remain live in the candidate’s calendar; a reschedule creates a second event and only marks the old database row `rescheduled`.
2. **Scheduling is not idempotent or recoverable across Calendar, interview persistence, and lifecycle transition.** Calendar creation happens first; retries can create duplicates; lifecycle failure can leave a real invitation and interview row while reporting failure.
3. **There is no interviewer or panel assignment authority and no conflict guard.** The “Interviewer” filter actually searches creator/updater phone fields, and Calendar attendees contain only the candidate.
4. **The system does not provide a human feedback/scorecard authority for the stated scope.** Feedback is one mutable free-text field; async completion automatically marks `feedback_complete` before human review; there are no form versions, rater submissions, criteria, or immutable feedback revisions.
5. **Recorded video has no retention/deletion authority.** Video is stored locally and registered, but no retention timestamp, purge policy, candidate deletion flow, or interview-video cleanup worker exists.

Material defects also exist in delivery truth, candidate RSVP/decline handling, transcription crash recovery, Arabic parity, accessibility, audit actor completeness, status constraints, and time-zone/date filtering.

This verdict does **not** justify reopening any frozen module. The smallest safe program is an Interviews-only patch around provider synchronization, scheduling operation state, panel assignment, feedback authority, retention, and presentation parity. Offers/Hiring must remain out of scope.

## Scope and evidence standard

Evidence used:

- frozen orchestrator, dashboard, and HR-mobile source under `/tmp/wathefni-c3-local`;
- current production file fingerprints, service status, configuration presence, API guards, and non-PII aggregate SQL;
- existing smoke, lifecycle, mobile, Reports, and UI tests;
- read-only compile/test runs during this assessment.

No finding is based on another HR product’s feature set. A missing capability is classified as a defect only where it:

- contradicts the explicit authority requested for this assessment;
- creates a demonstrated data, delivery, privacy, scheduling, or audit failure; or
- makes the current UI/API claim materially misleading.

## Production truth snapshot

Read-only production inspection on 2026-07-24 established:

| Evidence | Production observation |
|---|---|
| Health/binding | `/health` returned `status=ok`; application/database environments both production and matched |
| Authentication guard | unauthenticated Interviews, Reports, and Applications dashboard routes returned JSON `401 dashboard_auth_failed` |
| Canonical lifecycle | `WATHEFNI_CANONICAL_LIFECYCLE=true` |
| Registry routing | `WATHEFNI_PREHIRE_VIA_REGISTRY=all` |
| Calendar provider | one OAuth account with Calendar/Gmail scopes is configured; no secret value was exposed |
| Public video base | `PUBLIC_CANDIDATE_BASE_URL` is configured |
| Video token secret | runtime resolves a configured `WATHEFNI_ASSESSMENT_LINK_SECRET`, not the development fallback |
| AI providers | transcription and planner providers are configured |
| Transcript worker | `wathefni-video-interview-worker.service` active since 2026-07-23; polls every 60 seconds; recent passes healthy |
| Interview rows | 4 total: 2 scheduled, 2 completed |
| Type/source | 3 `async_video`; 1 live `schedule_interview` |
| Feedback | 3 `notes_pending`; 1 `feedback_complete` |
| Calendar/Meet | 1 row with event id and Meet link |
| Communication flags | 3 `candidate_notified`; 0 `calendar_invite_sent`; 0 `candidate_invited` |
| Integrity | 0 orphan applications; 0 tenant mismatches; 0 invalid observed status pairs |
| Lifecycle consistency | 0 active live schedules outside application stage `interview`; 0 applications at `interview` without an active live schedule |
| Same-application overlaps | 0 currently observed |
| Transcription | 1 completed response; 0 stuck `processing` rows older than 10 minutes |
| DB session time zone | `Etc/UTC` |
| Interviewer/panel/score/reminder columns | none |

The absence of current overlap, drift, invalid status, and stuck-processing rows is positive operational evidence. It does not prove the missing constraints or recovery paths, because the source permits those states.

### Frozen-to-production fingerprints

The following production hashes exactly matched the frozen source:

| File | SHA-256 |
|---|---|
| `app.py` | `30d8fd130fa304adeafdb5aa99b1d822e92e5a37ebfac54719c4d6659f147cb5` |
| `recruiting_lifecycle.py` | `dc7ead5774517cfb8513667aa874ee78f03a70e3179b28a79512d6eb452a8560` |
| `operator_mobile.py` | `0fa299a11e0fdd2138f38ee4ce928f91ab56b337cfed86a1d43bc9ef36344a45` |
| `operator_mobile_data.py` | `574e9f565c0f50b1f5f893404c0078f9a6a826ee6fbb02fd5290f957ce2621f6` |
| `reports_v1.py` | `d7f52f2a082ff1ad5979e642ce44bf892f3dd41ea3a979f7c92f5b975c147a41` |
| `assistant_policy.py` | `122aad29e15792ce860b878329ad32d39221aac69f08a9228fd9e04dbf92f2ac` |
| `action_registry.py` | `da56619cc8c40782be29a485191d52a598db1052354f598df362c2cfe4a4d2c0` |
| `tool_call_orchestrator.py` | `82cc7fc0a581f6c7e17034398d901ce975fab52f521fae34086953ce048f2a48` |
| `video-interview-worker.py` | `62d98b6031238f2307e7f3050010c7d903f8fe9bded2a665f0f20faf48007f7f` |
| `candidate_messages.py` | `c72487ff530257c1b0a3f25b153c66ad7a15fd590ec4047d456323d58dcc25da` |

## Architecture and authority map

### Runtime architecture

```text
Dashboard candidate drawer / Assistant / WhatsApp
  → action registry + tool permission map
  → human confirmation
  → Google Calendar create + Meet + candidate attendee
  → candidate_interviews
  → candidate_interview_events
  → canonical application transition to interview
  → applications.raw_json.interview projection

Dashboard / mobile
  → company-scoped interview list/detail
  → status and free-text notes
  → optional advisory AI summary

Async video send
  → candidate_interviews(interview_type=async_video)
  → version-like question snapshot rows
  → expiring HMAC public link
  → consent
  → response + file_registry/local file
  → candidate completion
  → transcript worker
  → advisory AI summary

Reports
  → candidate_interviews joined to company-scoped applications
```

### Canonical tables

1. `candidate_interviews`
   - live and async parent record;
   - schedule, Meet/calendar, communication, notes, transcript, summary, consent, and completion fields;
   - source: `app.py:2045-2086`.
2. `candidate_interview_events`
   - append-only event rows with actor and target fields;
   - FK to the parent with `ON DELETE CASCADE`;
   - source: `app.py:2087-2103`, `43083-43140`.
3. `candidate_video_interview_questions`
   - question snapshot per async interview;
   - unique `(interview_id, question_order)`;
   - source: `app.py:2104-2118`.
4. `candidate_video_interview_responses`
   - one current response per interview/question, transcript state, local storage reference, retake count;
   - unique `(interview_id, question_id)`;
   - source: `app.py:2120-2150`.
5. `applications.raw_json.interview`
   - denormalized compatibility projection, not the interview authority;
   - source: `app.py:42693-42731`.

Production has only the `candidate_interviews` primary-key constraint plus indexes; it has no FK to application/company and no status/time CHECK constraints. The source indexes company/status, company/application, async state, and unique non-null calendar event id (`app.py:2602-2605`).

### APIs and surfaces

| Surface | Current authority |
|---|---|
| Dashboard | `GET /dashboard/prehire/interviews`; status PATCH; notes POST; video download; transcript retry; async-video send |
| Dashboard scheduling | no dedicated schedule form/route; candidate drawer opens Assistant prompt (`App.tsx:2612-2614`) |
| HR mobile | list, detail, and notes only; schedule/reschedule/cancel intentionally unavailable |
| Assistant | `schedule_interview`, `send_interview_invite`, `send_video_interview`, `get_interview_invite_status` |
| Public async video | HTML shell; signed state, consent, response, and completion endpoints |
| Worker | polling transcript/summary worker |
| Reports | Interviews export and interview/application funnel metrics |

### Status model

**Canonical application stages:** `awaiting_cv`, `cv_processing`, `ready_for_review`, `shortlisted`, `interview`, `hired`, `rejected`, `withdrawn` (`recruiting_lifecycle.py:29-38`).

**Interview row:** `scheduled`, `completed`, `no_show`, `rescheduled`, `cancelled` (`app.py:42621`).

**Feedback:** `notes_pending`, `feedback_complete` (`app.py:42622`).

**Async status written by code:** `pending`, `link_sent`, `opened`, `consented`, `in_progress`, `completed`.

**Derived async review display:** `cancelled`, `transcription_failed`, `processing`, `ready_for_review`, `summary_pending`, `submitted`, `started`, `link_sent` (`app.py:44001-44071`).

These vocabularies are correctly separate in application logic, but only the application lifecycle has a strict transition authority. Interview row statuses are free text at the database layer.

## Capability matrix

| Capability | Current evidence | Classification | Enterprise readiness |
|---|---|---|---|
| Live scheduling | confirmed Calendar/Meet create + canonical row/stage | Material defects | Blocked by sync/idempotency/conflicts |
| Rescheduling | new event + old row marked `rescheduled` | Confirmed blocker | Not ready |
| Cancellation | DB cancel + application rollback | Confirmed blocker | Not ready until provider/candidate sync |
| Interviewer/panel assignment | no model; candidate-only attendee | Confirmed blocker for stated scope | Not ready |
| Candidate invitations | Calendar and channel sends exist | Material defect | Delivery truth needs correction |
| Reminders | no Wathefni reminder pipeline | Optional enhancement if Google reminders accepted; otherwise material | Owner contract required |
| Secure async links | HMAC, expiry, module/cancel gates | Already sufficient in current production config | Ready |
| Recording consent | required and audited | Already sufficient | Ready |
| Async upload/completion | canonical rows/files/events | Material resilience/privacy defects | Conditional |
| Interview status | distinct facet and dashboard queue | Already sufficient with DB hardening | Functionally ready |
| Candidate RSVP/decline | not ingested from Calendar | Material defect | Not ready for RSVP truth |
| Free-text feedback | web/mobile notes + advisory summary | Already sufficient for notes-only use | Ready as notes, not scorecards |
| Structured scorecards | absent | Confirmed blocker for stated scope | Not ready |
| No-show | explicit status, no automatic candidate decision | Already sufficient | Ready |
| Reports | canonical row export and counts | Already sufficient with delivery caveat | Ready |
| Assistant | schedule/invite/video/status with confirmation | Material parity defect | Cancel/reschedule absent |
| Mobile | read/detail/notes only, by design | Already sufficient for documented thin mobile scope | No action unless owner expands scope |
| Arabic/RTL | bilingual copy exists; Interviews workspace remains partly English | Material defect | Blocks bilingual claim |
| Accessibility | semantic gaps in queue/tabs/drawer | Material defect | Blocks strict accessibility sign-off |
| Tenant isolation | company-scoped authenticated paths | Already sufficient | Ready |
| Video retention/deletion | absent | Confirmed blocker | Not ready for recorded-video governance |

## Scheduling and time-zone analysis

### Current scheduling flow

`_schedule_interview_executor`:

1. resolves the application;
2. parses an ISO or natural-language time;
3. validates candidate email;
4. validates human confirmation;
5. runs `gog calendar create primary --send-updates all --with-meet`;
6. creates/upserts an interview row;
7. marks prior scheduled rows `rescheduled`;
8. moves the application to canonical stage `interview`;
9. returns Calendar/Meet/invitation fields.

Evidence: `action_registry.py:2121-2315`, `app.py:43143-43246`.

The order is the central reliability defect: an external side effect occurs before durable operation/idempotency state and before the lifecycle transition.

### Time handling

- ISO parsing preserves an explicit offset; timezone-less values are assigned fixed `+03:00` (`app.py:42637-42649`).
- Natural-language today/tomorrow parsing uses fixed `KUWAIT_TZ` and a fixed 30-minute duration (`app.py:31762-31784`).
- persisted timezone is hard-coded `Asia/Kuwait` (`app.py:43196`, `44364`);
- candidate invite labels always convert to Kuwait time (`app.py:42899-42905`);
- the date filter uses `ci.scheduled_start::date` (`app.py:44567-44570`);
- production DB session timezone is `Etc/UTC`.

Concrete failure: an interview at 01:00 Kuwait time is the previous UTC date, so dashboard filtering by the candidate/HR’s Kuwait date can omit it. Multi-time-zone tenants also receive a stored timezone label that may not represent the submitted offset.

**Classification:** material defect for date filtering; minor for Kuwait-only fixed-offset scheduling; material if multi-time-zone tenants are in scope.

**Smallest fix:** use company IANA `ZoneInfo`, persist the selected timezone, require or explicitly interpret timezone-less input, and filter using `(scheduled_start AT TIME ZONE company_timezone)::date`.

No DST defect is currently demonstrated for Kuwait because Kuwait does not observe DST. DST qualification is required before any other timezone is enabled.

### Conflicts

There is no:

- candidate overlap query;
- interviewer/panel overlap query;
- Google free/busy check;
- exclusion constraint;
- operation claim before provider create.

Production currently has zero same-application overlaps. This is current cleanliness, not enforcement.

## Invitation and calendar integration

### What is strong

- Google Calendar/Meet is the explicit live provider.
- Candidate email is passed as attendee and `--send-updates all` is requested (`action_registry.py:2207-2225`).
- Meet link and event id are extracted from nested provider output (`app.py:42669-42690`).
- separate email/WhatsApp resend uses the canonical current interview and fails closed for non-active interviews (`app.py:42980-43006`).
- invite copy is bilingual via `candidate_messages.py:101-107` and includes the saved Meet link or a Calendar-contains-details fallback.
- Assistant’s send and schedule actions are confirmation-gated.

### Delivery truth problem

`create_candidate_interview_from_schedule` equates `calendar_event_id + candidate_email` with:

- `calendar_invite_sent=true`;
- `candidate_invited=true`;
- `candidate_notified=true`.

Evidence: `app.py:43163-43171`, `43190-43235`.

`candidate_interview_summary` then emits `communication_status="sent"` if any of those booleans is true (`app.py:42742-42747`). The failed branch at `42760-42761` is unreachable because the summary never derives `failed`.

A failed later channel resend writes `candidate_notified=false`, which can erase previous positive state (`app.py:42926-42945`).

**Smallest fix:** separate provider-accepted Calendar invitation state from candidate-channel send and delivery state; preserve prior successes; derive failure from canonical outbound events; use “send accepted” rather than “notified/delivered” unless provider evidence supports more.

### Candidate confirmation/decline

For live interviews, `candidate_confirmation` is not Calendar RSVP. It is derived from async recording consent or merely from a sent communication (`app.py:42753-42758`). There is no Calendar attendee response ingestion, provider webhook, poller, or `declined/tentative/accepted` interview facet.

**Classification:** material defect.  
**Consequence:** HR cannot rely on the displayed confirmation state as RSVP truth.

### Reminders

No interview reminder columns, templates, scanner, timer, or service were found. Calendar’s own reminders may be acceptable if that is the explicit owner contract.

**Classification:** optional enhancement pending owner decision, not an automatic blocker.  
**No action recommended** if Google Calendar reminders are the approved authority. If Wathefni reminders are promised, add one idempotent reminder operation per interview/time window.

## Feedback and scorecard authority

### Current feedback contract

The current product provides:

- one `notes` field;
- optional transcript;
- binary `feedback_status`;
- advisory `ai_summary`;
- one textarea in dashboard and mobile;
- overwrite-in-place notes POST;
- an event saying feedback completed, but no immutable note revision.

Evidence: `app.py:2045-2085`, `48059-48119`; `App.tsx:5105-5113`; mobile `routes.tsx:722-755`.

This is **already sufficient for a notes-only product** and should not be described as a scorecard.

### Why it is not a scorecard authority

There are no:

- scorecard/form definitions;
- criteria/rating-scale rows;
- form versions;
- interviewer/panel submission rows;
- submit/finalize locks;
- rater identity per scorecard;
- immutable revisions;
- aggregate/final score authority.

Async candidate completion sets `feedback_status='feedback_complete'` automatically (`app.py:43671-43678`), and transcript summary generation does so again (`44249-44253`). That conflates “candidate submitted / machine summary ready” with “human feedback complete,” causing the Needs Feedback queue to omit a completed async interview before human review (`app.py:44543-44546`, `44649-44671`).

The server allows notes to be overwritten after completion even though the web UI stops advertising `write_notes`; mobile advertises write based on capability, not notes state.

**Smallest justified fix for the stated scope:**

1. keep `candidate_interviews` as interview authority;
2. add versioned interview feedback definition and submission tables;
3. bind each interview to a definition version;
4. create one immutable/finalized submission per assigned interviewer, with controlled reopen/revision events;
5. keep AI summary advisory and separate from human completion;
6. derive `feedback_status` from human submission state, never candidate video completion.

Do not add interview scores to Ranking. That remains explicitly disabled.

## Lifecycle, Reports, Assistant, and frozen-module boundaries

### Canonical lifecycle

| Interview event | Canonical application effect |
|---|---|
| Live schedule, lifecycle enabled | application → `interview`, human-confirmed |
| Cancel active live interview | application `interview` → `shortlisted` |
| Complete | no automatic lifecycle transition |
| No-show | no automatic lifecycle transition |
| Save feedback | no automatic lifecycle transition |
| Async video send/complete | no application-stage transition |

Evidence: `action_registry.py:2236-2265`; `app.py:47979-48018`; `recruiting_lifecycle.py:68-86`.

Production has zero observed live interview/application drift. The source consistency report is read-only and excludes async video intentionally (`recruiting_lifecycle.py:445-498`).

### Ranking

Interviews does **not** control frozen Ranking:

- `candidate_ranking.py` says it does not own interviews (`:1-14`);
- interview evidence defaults to `unused`;
- `required` raises `interview_scoring_unavailable` (`:469-473`);
- interview never contributes to the soft score (`:1774`);
- capability reports `interview_scoring=false` (`:3024`).

A legacy `row_interview_signal` path remains in `app.py:12658-12681`. No evidence gathered here proves it is the current R0–R3 presentation authority. **Classification: unknown pending trace evidence; no change recommended to frozen Ranking.**

### Offers and Hiring

Offers/Hiring read canonical application stage and remain separate authorities. An application may move from `shortlisted` or `interview` under their own permissions/contracts; interview completion does not issue an offer or hire.

**Classification:** already sufficient; no action recommended.

### Reports

Reports V1 exports canonical interview rows with status, feedback status, schedule, and invite boolean (`reports_v1.py:1069-1090`). Arabic headers exist. Export audit remains owned by Reports.

The invite boolean inherits the delivery-truth defect; fix its source/derivation inside Interviews without redesigning Reports.

### Assistant

Strong:

- `schedule_interview`, `send_interview_invite`, and `send_video_interview` require confirmation (`action_registry.py:4817-4903`);
- tool permissions require `interview.manage`; invite-status read requires `prehire.read` (`tool_call_orchestrator.py:169-187`);
- current interview is loaded from Postgres;
- schedule is integrated with canonical lifecycle confirmation;
- result/navigation/audit surfaces exist.

Gaps:

- no Assistant cancel or reschedule action;
- `execute_candidate_workflow` requires `candidate.manage`, so a hiring manager with `interview.manage` cannot execute an interview-only composite workflow;
- partial schedule failure can be described as failed after a real Calendar invite exists.

**Classification:** material defect for end-to-end Assistant parity, not a reason to reopen Assistant A0–A3. The smallest fix is to register Interviews-owned cancel/reschedule executors that reuse the same Interview service and confirmation contract.

## Permissions, privacy, audit, and tenant isolation

### Tenant isolation

Authenticated paths consistently bind company:

- list starts with `ci.company_code=%s` (`app.py:44528-44538`);
- fetch requires interview id and company (`42833-42844`);
- status and notes updates include company (`47988-48035`, `48084-48095`);
- mobile loads through company-scoped fetch (`operator_mobile_data.py:1099-1106`);
- video response download checks interview and response company (`app.py:48122-48149`).

Production has zero orphan applications and zero company mismatches.

**Classification:** already sufficient. No action recommended beyond qualification tests.

### Permission model

`interview.manage` belongs to owner, HR manager, recruiter, and hiring manager; viewer has read only (`app.py:6124-6132`). Mutations require `interview.manage`.

The full interview summary returned under `prehire.read` includes contact data, notes, transcript, sent body, Meet link, and async-video evidence. Whether a viewer is authorized for all interview evidence is not defined by an inspected product policy.

**Classification:** unknown pending owner privacy policy.  
**No immediate remediation recommended** solely from role naming. The owner must explicitly decide whether `prehire.read` includes recorded video and interviewer notes. If not, add `interview.feedback.read` / `interview.media.read` or a minimized viewer DTO.

### Recorded-video privacy

Video bytes are written to a company workspace path and registered in `file_registry` (`app.py:43565-43622`). Authenticated download is tenant-scoped. However:

- no retention/expiry field exists on the interview video record or `file_registry`;
- no interview-video purge/deletion worker exists;
- no candidate/interview deletion API removes local objects;
- retakes can create additional local objects.

**Classification:** confirmed blocker for enterprise recorded-video governance.  
**Smallest fix:** explicit retention configuration, a durable purge operation with file/registry/interview event audit, retake supersession cleanup, and owner-visible retention policy. Encryption-at-rest remains an infrastructure verification item; it was not established by this audit.

### Audit

Async-video events carry actor user/role consistently. Production live events do not:

- all current live `scheduled`, status, and feedback events have `actor_user_id` and `actor_role` null;
- phone is present for status/feedback/schedule events;
- invite sent/failed events have no actor fields.

Source cause: live `record_interview_event` calls pass phone but not `actor_context`; invite sends pass neither (`app.py:43024-43025`, `43243-43245`, `48040-48042`, `48100-48107`).

**Classification:** material defect.  
**Smallest fix:** pass authenticated actor context through all live schedule/invite/status/feedback events and preserve before/after facts without storing unnecessary message content.

## Failure and idempotency matrix

| Failure/race | Current behavior | Risk | Classification | Smallest safe control |
|---|---|---|---|---|
| Calendar create fails | no interview row/stage move | visible failure; recoverable retry | Already sufficient | structured provider error |
| Calendar succeeds, DB insert fails | real invite/Meet without canonical row | orphan provider event | Confirmed blocker | durable operation + compensation |
| Calendar+DB succeed, lifecycle fails | returns failed but invite/row exist | false failure, stage drift, cancel 409 | Confirmed blocker | saga compensation/repair |
| request retry/double confirmation | another Calendar create | duplicate invites | Confirmed blocker | idempotency claim before provider call |
| concurrent same-app schedule | no overlap lock | double booking | Confirmed blocker | transaction/advisory lock + exclusion/overlap check |
| reschedule | creates new event; old event remains | two live invites | Confirmed blocker | update provider event or delete superseded event |
| cancel | DB/lifecycle only | ghost Calendar event; candidate uninformed | Confirmed blocker | provider cancel + candidate update + retry |
| failed channel resend | may clear `candidate_notified` | truth regression | Material defect | monotonic success + separate attempt state |
| Calendar RSVP decline | not ingested | confirmation/status stale | Material defect | provider response sync |
| transcript process exception | marks `failed`; manual retry available | queue waits for operator | Already sufficient for explicit failure |
| worker dies after marking `processing` | worker skips `processing`; retry endpoint resets only failed/pending | permanently stuck response | Material defect | lease expiry/reclaim processing |
| concurrent video retakes | pre-read has no row lock; file stored before response upsert | retake-limit bypass/orphan files | Material defect | row lock/idempotency + superseded-file cleanup |
| repeated consent | timestamp idempotent; event duplicated | noisy audit | Minor defect | event idempotency key |
| repeated completion | checks completed and returns current state | safe replay | Already sufficient | none |
| invalid/expired/cancelled async link | 403/410 | fail closed | Already sufficient | none |
| module disabled async link | 403 `module_disabled` | fail closed | Already sufficient | none |

### Transcription recovery detail

The worker queries both `pending` and `processing` (`app.py:43824-43847`) but then explicitly skips `processing` (`44282-44286`). The retry endpoint only resets `failed` or `pending` (`48166-48174`). A process death between setting `processing` and completion therefore has no automatic or manual reclaim path.

Production currently has no stale processing row, and the worker is healthy. The defect is still confirmed by control flow.

## Classified findings

### I-01 — Calendar cancellation is not real cancellation

- **Class:** confirmed blocker
- **Evidence:** `app.py:47979-48018` updates DB/lifecycle only; only smoke cleanup calls Calendar delete (`smoke-test-real-interview-flow-live.py:44-55`, `254-256`).
- **Failure:** candidate Calendar/Meet remains active after HR sees “cancelled.”
- **Affected:** candidate, recruiter, hiring manager, panel operations.
- **Severity:** critical/high.
- **Enterprise readiness:** blocks.
- **Smallest fix:** durable provider-cancel operation with `--send-updates all`, candidate update, retry/audit.
- **If unchanged:** ghost meetings and contradictory source-of-truth states.

### I-02 — Reschedule leaves the superseded event active

- **Class:** confirmed blocker
- **Evidence:** Calendar is always created (`action_registry.py:2207-2226`); old row only becomes `rescheduled` (`app.py:43175-43187`); live smoke expects two rows (`smoke-test-real-interview-flow-live.py:198-204`).
- **Failure:** candidate retains two valid events/Meet links.
- **Affected:** candidate and all interview operators.
- **Severity:** high.
- **Enterprise readiness:** blocks.
- **Smallest fix:** update existing provider event or create-new/delete-old through a durable saga.
- **If unchanged:** every reschedule can produce ambiguity and no-shows.

### I-03 — Scheduling lacks operation idempotency, conflict control, and compensation

- **Class:** confirmed blocker
- **Evidence:** provider create precedes DB and lifecycle (`action_registry.py:2226-2279`); lifecycle idempotency key is applied only after provider create (`2259`); no interview overlap query/constraint exists.
- **Failure:** duplicate event, orphan event, or failed response after real invite.
- **Affected:** HR operators and candidates during retries/concurrency.
- **Severity:** high.
- **Enterprise readiness:** blocks.
- **Smallest fix:** operation table/idempotency claim, lock, overlap check, explicit provider/DB/lifecycle states, compensation.
- **If unchanged:** retries remain unsafe.

### I-04 — No interviewer/panel assignment authority

- **Class:** confirmed blocker for the stated scope
- **Evidence:** source and production schema have no interviewer/panel fields; Calendar attendee is candidate only (`action_registry.py:2217-2218`); “Interviewer” filter searches creator/updater phones (`app.py:44571-44575`).
- **Failure:** no canonical assigned interviewer, panel membership, attendee sync, or panel conflict check.
- **Affected:** hiring managers, recruiters, panel members, candidates.
- **Severity:** high.
- **Enterprise readiness:** blocks the requested panel-assignment authority.
- **Smallest fix:** normalized assignment table with user/email, role, attendance status, tenant FK, and Calendar sync.
- **If unchanged:** panel management remains off-system and the filter is misleading.

### I-05 — Human feedback is not a scorecard authority

- **Class:** confirmed blocker for the stated scope
- **Evidence:** one mutable notes field and binary status (`app.py:2045-2085`, `42621-42634`); no form/version/submission tables; notes overwrite (`48084-48096`); async completion sets feedback complete (`43671-43678`).
- **Failure:** no rater identity, rubric version, immutable submission, controlled edit, or reliable human-complete state.
- **Affected:** interviewers, panels, decision makers, auditors.
- **Severity:** high.
- **Enterprise readiness:** blocks scorecard authority; notes-only use remains sufficient.
- **Smallest fix:** versioned feedback definitions and per-assignee submissions, separated from AI/candidate completion.
- **If unchanged:** Wathefni must accurately claim notes only, not enterprise scorecards.

### I-06 — Recorded-video retention and deletion are undefined

- **Class:** confirmed blocker
- **Evidence:** local storage and registry write (`app.py:43565-43622`); repository search found no interview-video retention/purge path; schema has no retention field.
- **Failure:** recorded candidate video and superseded retakes can persist indefinitely.
- **Affected:** candidates, privacy/compliance owners, infrastructure operators.
- **Severity:** high.
- **Enterprise readiness:** blocks recorded-video governance.
- **Smallest fix:** configured retention + durable audited purge/reconciliation.
- **If unchanged:** deletion and retention obligations cannot be reliably executed.

### I-07 — Invitation and confirmation truth is overstated

- **Class:** material defect
- **Evidence:** event id + email becomes three success booleans (`app.py:43163-43235`); summary derives `sent` (`42742-42747`); no RSVP ingestion; failed resend can clear notified (`42934-42943`).
- **Failure:** HR may see “sent/notified/confirmed” without delivery or RSVP evidence.
- **Affected:** recruiters, candidates, Reports, Assistant.
- **Severity:** medium/high.
- **Enterprise readiness:** blocks communication-SLA claims, not basic scheduling alone.
- **Smallest fix:** separate provider acceptance, channel send, delivery, and RSVP states.
- **If unchanged:** operational follow-up decisions use unreliable truth.

### I-08 — Stale transcription `processing` work cannot be reclaimed

- **Class:** material defect
- **Evidence:** query includes `processing`, processor skips it, retry excludes it (`app.py:43824-43847`, `44282-44286`, `48166-48174`).
- **Failure:** worker crash can strand a response forever.
- **Affected:** HR reviewing async interviews.
- **Severity:** medium/high.
- **Enterprise readiness:** material reliability gap.
- **Smallest fix:** lease owner/expiry and reclaim; manual retry may reset stale processing.
- **If unchanged:** rare process failure requires direct SQL.

### I-09 — Arabic Interviews workspace is incomplete

- **Class:** material defect
- **Evidence:** page sets RTL, but tabs, metrics, filters, pagination, empty state, and drawer sections remain English (`App.tsx:4792-4812`, `4848-4855`, `4881-4892`, `5027-5153`); bilingual keys exist elsewhere.
- **Failure:** Arabic locale is an English-majority workflow.
- **Affected:** Arabic-speaking HR operators.
- **Severity:** medium/high.
- **Enterprise readiness:** blocks bilingual Interviews claim.
- **Smallest fix:** route all Interviews chrome through existing locale infrastructure and set drawer direction.
- **If unchanged:** Arabic/RTL parity remains false.

### I-10 — Interviews queue/drawer accessibility is incomplete

- **Class:** material defect
- **Evidence:** clickable queue row is a non-keyboard `<div>` (`App.tsx:4918-4923`); tabs lack selected/tab semantics (`4829-4845`); drawer lacks dialog semantics/focus management (`4994-4997`).
- **Failure:** keyboard and screen-reader users cannot reliably operate the workflow.
- **Affected:** users requiring assistive technology; procurement/accessibility review.
- **Severity:** medium.
- **Enterprise readiness:** blocks strict accessibility sign-off.
- **Smallest fix:** semantic row control, tablist/selected state, dialog label/modal/focus/escape handling.
- **If unchanged:** core interview management is not fully accessible.

### I-11 — Live interview audit actor identity is incomplete

- **Class:** material defect
- **Evidence:** production live events have null actor user/role; source passes only phone or no actor for schedule/invite/status/feedback (`app.py:43024-43025`, `43243-43245`, `48040-48042`, `48100-48107`).
- **Failure:** canonical event history cannot reliably state which authenticated user/role acted.
- **Affected:** security, HR audit, incident response.
- **Severity:** medium.
- **Enterprise readiness:** material audit gap.
- **Smallest fix:** thread authenticated actor context through every live mutation/event.
- **If unchanged:** phone-level attribution only, and invite events can be unattributed.

### I-12 — Database permits invalid interview states

- **Class:** material defect
- **Evidence:** production constraints contain only the parent PK; no CHECK/FK for status, feedback, times, application, company; application normalization is bypassable by direct SQL.
- **Failure:** invalid status, end-before-start, cross-company application reference, or orphan row.
- **Affected:** APIs, Reports, migrations, operators.
- **Severity:** medium.
- **Enterprise readiness:** material hardening gap; current production rows are clean.
- **Smallest fix:** validate existing rows, then add NOT VALID/validated checks and company+application FK where compatible.
- **If unchanged:** one legacy/direct SQL path can create unsupported authority states.

### I-13 — Calendar date filter and stored timezone can disagree with the user’s date

- **Class:** material defect for date filtering; minor for Kuwait-only scheduling
- **Evidence:** fixed `+03`, hard-coded `Asia/Kuwait`, UTC production DB, and `scheduled_start::date` (`app.py:31762-31784`, `43196`, `44567-44570`).
- **Failure:** early Kuwait interviews can disappear under the intended date filter; non-Kuwait metadata can be false.
- **Affected:** HR queue users.
- **Severity:** medium.
- **Enterprise readiness:** blocks multi-time-zone claim; contained defect for Kuwait.
- **Smallest fix:** company ZoneInfo-aware parse/store/filter.
- **If unchanged:** date filtering is wrong around local/UTC day boundaries.

### I-14 — Assistant/mobile operational parity is intentionally incomplete

- **Class:** optional enhancement / already sufficient under current documented scope
- **Evidence:** Assistant lacks cancel/reschedule specs; mobile explicitly permits notes only (`recruiting_lifecycle.py:1969-1976`, `operator_mobile_data.py:970-991`).
- **Failure:** operators must use web for cancellation/rescheduling.
- **Affected:** chat-first and mobile-only operators.
- **Severity:** low/medium.
- **Enterprise readiness:** not blocking if web is the approved authority.
- **Smallest fix:** after core provider sync exists, expose the same confirmed service; do not duplicate logic.
- **If unchanged:** workflow remains channel-limited but coherent.

### I-15 — Dedicated video-link secret is not independently configured

- **Class:** operational/content issue
- **Evidence:** code can fall back through assessment/dashboard/database/development secrets (`app.py:29195-29205`); production currently resolves configured assessment link secret.
- **Failure:** no independent rotation boundary; future misconfiguration could fall too far.
- **Affected:** security operations and candidates.
- **Severity:** low in current production, high if all configured secrets disappear.
- **Enterprise readiness:** does not currently block.
- **Smallest fix:** production startup requires a configured video or approved shared candidate-link secret and forbids DB/dev fallback.
- **If unchanged:** current links remain HMAC-secured, but key rotation is coupled.

### I-16 — Deterministic smoke assertion is stale

- **Class:** operational/content issue
- **Evidence:** production smoke expected literal `"Google Meet: <url>"`, while current versioned candidate template emits the URL without that prefix; actual invite still includes the correct Meet URL. Production smoke failed only this assertion.
- **Failure:** false-negative qualification signal.
- **Affected:** release operators.
- **Severity:** low.
- **Enterprise readiness:** not a product blocker.
- **Smallest fix:** assert URL presence and template contract, not old wording.
- **If unchanged:** harmless copy changes can fail the smoke.

### Positive classifications

- **Already sufficient:** tenant isolation on authenticated APIs.
- **Already sufficient:** expiring signed async links with module/cancel gate in current production configuration.
- **Already sufficient:** recording consent and candidate event attribution.
- **Already sufficient:** completed/no-show do not auto-decide the application.
- **Already sufficient:** Reports consume canonical interview rows.
- **Already sufficient:** Ranking R0–R3 excludes interview scoring.
- **Already sufficient:** Offers/Hiring remain separate.
- **No action recommended:** Wathefni-hosted secure redirect for live Meet links; Google Meet is the approved join authority.
- **No action recommended:** mobile schedule/cancel parity unless the owner requires mobile-only operation.
- **Unknown pending evidence:** whether viewer `prehire.read` should include full video/notes.
- **Unknown pending trace evidence:** whether the legacy calendar-only pending-action schedule branch still receives traffic.

## Evidence-backed recommendation

**Recommendation: one contained Interviews remediation, followed by isolated local/staging qualification. Do not promote or freeze Interviews yet.**

Required scope:

1. provider-synchronized cancel/reschedule;
2. durable idempotent scheduling operation with conflict check and compensation;
3. interviewer/panel assignment authority;
4. versioned human feedback/scorecard submissions, clearly separated from AI and candidate completion;
5. video retention/deletion and stale-processing recovery;
6. truthful invitation/RSVP state;
7. live actor audit completeness;
8. Arabic/a11y and timezone/date-filter corrections;
9. DB constraints after production data validation;
10. retire or prove unreachable the calendar-only legacy schedule path.

Optional/deferred:

- Wathefni reminders if Google reminders are accepted;
- mobile schedule/cancel/reschedule;
- dedicated video-link secret instead of the approved candidate-link secret;
- Wathefni redirect for live Meet links;
- interview evidence in Ranking.

The remediation must not:

- change Ranking weights or enable interview scoring;
- require interview completion for Offers/Hiring;
- alter Reports definitions except consuming corrected Interview truth;
- redesign Assistant beyond exposing confirmed Interview service actions;
- modify Assessments;
- start Offers/Hiring work.

## Required schema/config changes

The smallest justified schema is:

1. `interview_schedule_operations`
   - tenant, application, idempotency key, requested slot/timezone, provider state, interview id, lifecycle state, retry/lease/error fields.
2. `candidate_interview_assignments`
   - interview id, company, dashboard user/email, panel role, organizer/required flags, RSVP/provider state.
3. `interview_feedback_definitions` and immutable versions
   - tenant/job scope, criteria/rating schema, status/version.
4. `interview_feedback_submissions`
   - interview, definition version, assigned rater, draft/submitted/reopened state, answers, timestamps, revision/audit metadata.
5. provider synchronization fields or operation rows
   - create/update/cancel state, attempt count, last error, next retry.
6. video retention
   - retention expiry/policy reference and purge state, or a durable generic file-retention operation.
7. constraints
   - CHECK interview/feedback/type/async states;
   - CHECK end > start where both exist;
   - company+application referential integrity where migration-compatible;
   - one active live schedule per application if that remains the product contract.

Configuration:

- company IANA timezone;
- approved Calendar account/provider health check;
- video retention duration/policy;
- explicit candidate-link secret policy;
- optional reminder policy;
- optional viewer media/feedback permission policy.

No schema/config change is justified in frozen Ranking, Reports, Assistant, Assessments, Offers, or Hiring.

## Local and staging qualification plan

### Local deterministic

- compile all changed Interview modules;
- unit-test provider result parsing and operation state transitions;
- timezone matrix: Kuwait, UTC, DST zone, naive input rejection/interpretation, local-date filter;
- status/constraint migration tests;
- idempotency replay and concurrent schedule tests;
- overlap tests for candidate and each panel member;
- cancellation/reschedule provider mocks, including retry and compensation;
- delivery-state monotonicity and RSVP mapping;
- scorecard definition/version/submission/reopen rules;
- async completion must remain human-feedback pending;
- retention expiry and retake supersession cleanup;
- stale transcript lease reclaim;
- actor-context completeness;
- Arabic copy inventory and accessibility component tests;
- update the stale invite smoke to assert semantic template truth.

### Isolated staging

Use one synthetic tenant and unique markers only:

1. schedule one live interview with candidate + two panel members;
2. prove one Calendar event, correct attendees, Meet link, timezone, and canonical stage;
3. replay the same idempotency key and prove no second event/row;
4. race two confirms and prove one winner;
5. attempt candidate/panel overlap and prove fail closed;
6. reschedule and prove old event is updated or cancelled, candidate/panel receive update, and one active canonical schedule remains;
7. cancel and prove provider event is cancelled, candidate/panel are updated, DB is cancelled, application returns to shortlisted, and retries are idempotent;
8. force provider, DB, and lifecycle failures independently; prove compensation/recovery;
9. ingest accepted/declined/tentative RSVP and verify UI/Assistant/Reports truth;
10. submit scorecards as two assigned raters; prove version pinning, permissions, immutable finalization, controlled reopen, and AI separation;
11. verify no score reaches Ranking and no automatic offer/hire occurs;
12. run async video EN/AR, expiry, cancellation, consent, retake race, transcript crash/reclaim, manual retry, retention purge;
13. test owner/recruiter/hiring-manager/viewer permissions and cross-tenant IDs;
14. verify dashboard/mobile/Reports/Assistant parity without changing frozen authorities;
15. keyboard/screen-reader and RTL walkthrough;
16. delete all synthetic DB rows, Calendar events, local files, registry rows, events, and operation rows; prove zero residue.

### Production promotion gate

Not part of this assessment. A later plan must require exact staging-green artifact identity, backup/rollback, dry-run or isolated fixtures, no genuine candidate communications, provider cleanup, and frozen-module regressions.

## Owner UX checklist

### Dashboard

- [ ] Upcoming, video, needs-feedback, completed, no-show, cancelled, and all counts match rows.
- [ ] Search, role, local date, and actual interviewer/panel filters are truthful.
- [ ] Schedule preview names candidate, role, local time/timezone, duration, organizer, panel, and communication consequence.
- [ ] Repeat confirmation cannot create a duplicate.
- [ ] Reschedule preview identifies old and new slot; only one active Calendar event remains.
- [ ] Cancel confirmation states Calendar/candidate/panel consequences; provider and DB results agree.
- [ ] Delivery displays provider accepted, channel sent/delivered, and RSVP as separate facts.
- [ ] Assigned interviewers see only their scorecard; submitted feedback is visibly final/reopened.
- [ ] Async candidate completion appears ready for human review, not feedback complete.
- [ ] Retention date/policy is visible for recorded video.
- [ ] Viewer exposure matches the approved privacy policy.

### Assistant

- [ ] Schedule requires confirmation and replays idempotently.
- [ ] Missing time, timezone, duration, candidate email, or panel is clarified before confirmation.
- [ ] Cancel/reschedule reuse the canonical Interview service and require confirmation.
- [ ] “Did the candidate receive/accept?” reports only evidence actually held.
- [ ] Partial provider failure is described accurately and exposes recovery state.
- [ ] Hiring-manager interview-only workflow uses `interview.manage` without gaining candidate decision permission.

### Mobile

- [ ] List/detail local time and Arabic labels are correct.
- [ ] Notes/scorecard permission matches dashboard.
- [ ] No disabled schedule/cancel promise is shown.
- [ ] If mobile mutations remain deferred, the UI directs the operator to web without implying failure.

### Arabic/RTL and accessibility

- [ ] No English-only Interviews chrome in Arabic locale.
- [ ] Drawer direction, icon placement, date/time, and punctuation are RTL-correct.
- [ ] Queue rows are keyboard controls.
- [ ] Tabs expose selected state.
- [ ] Drawer has dialog label, modal semantics, initial focus, focus trap, and Escape close.
- [ ] Error/success states are announced.
- [ ] Video controls and transcripts have accessible labels.

### Reports/audit/privacy

- [ ] Interviews export uses corrected invitation/RSVP truth.
- [ ] Every schedule/reschedule/cancel/invite/feedback action records authenticated actor, target, before/after, and provider operation id.
- [ ] Cross-tenant interview/media/submission identifiers fail closed.
- [ ] Retention purge removes local bytes and updates registry/audit.
- [ ] Reports and Assistant do not expose scorecard content beyond permission.

## Explicit out-of-scope items

- Jobs changes.
- Candidate identity/lifecycle redesign.
- Ranking formula, evidence policy, or interview scoring.
- Reports V1 redesign.
- Assistant A0–A3 redesign.
- Assessments changes.
- Offers or Hiring implementation.
- automatic candidate decisions from interview evidence.
- replacing Google Calendar/Meet.
- building a Wathefni live-video meeting provider.
- mobile scheduling unless separately approved.
- reminders unless the owner rejects Google Calendar as reminder authority.
- production deployment or production mutation.

## Final assessment state

**Interviews is not production-green under the requested enterprise authority contract.**

Its core boundary is sound and should be preserved. The smallest justified next step is one contained Interviews remediation and qualification cycle. No code was changed, no deployment was performed, no production record was mutated, and no frozen production-green module was reopened.
