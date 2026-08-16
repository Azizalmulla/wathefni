# Wathefni Normal HR Workspace — Objective UI/UX Audit

**Date:** 2026-07-27  
**Scope:** Normal HR workspace only  
**Method:** Read-only inspection of the current React frontend, navigation model,
page components, shared UI primitives, permission/module gates, translations,
responsive classes, tests, and API-facing states in
`apps/wathefni-dashboard/src/`.

## How to read this report

- **Observed fact** means the behavior or copy is directly present in the current
  frontend source.
- **Expert judgment** is the audit conclusion drawn from those facts.
- **Assumption** means runtime data or real-user behavior could change the
  conclusion and should be validated.
- **Product decision** means the code cannot resolve the question; product
  ownership must choose.

This is not a redesign proposal and contains no implementation plan.

---

## 1. Executive verdict

### Short answer

**Expert judgment:** The product is functionally broad but not yet simple. It
looks more polished than a typical internal admin tool, and several workflows
show good safety thinking, but the normal HR workspace still feels like many
backend capabilities placed side by side rather than one deliberately edited HR
product.

The first-use experience is difficult because:

1. the navigation can expose up to twenty destinations;
2. the main recruiting objects and the operational queues are fragmented;
3. tables are wide and state-heavy;
4. several pages expose system vocabulary, technical evidence, calibration, or
   data-authority concepts;
5. Arabic support covers only parts of pre-hiring and is effectively absent from
   post-hire;
6. mobile behavior is largely “stack and horizontally scroll,” not a genuinely
   mobile interaction model.

The product is most usable for a trained, English-speaking full-time recruiter
who understands Wathefni's internal lifecycle. It is less natural for:

- a first-time HR administrator;
- an occasional hiring manager;
- an Arabic-first HR team;
- a company using only post-hire modules;
- a small company that needs only two modules and expects a compact, focused
  workspace.

### Direct answers to the twelve main questions

1. **Is it simple on first use?**  
   **No.** The overview helps, but navigation breadth, overlapping statuses, and
   technical copy create a high learning burden.

2. **Is navigation logically organized?**  
   **Partly.** Module visibility is generally correct, but `Pre-Hiring`,
   `Post-Hire`, and `Workspace` are system/product lifecycle groupings rather
   than strong user mental models.

3. **Are pages too dense or technical?**  
   **Several are.** Candidates, Assessments, Interviews, Payroll, Compliance,
   Settings, and the candidate profile are the clearest examples.

4. **Is important information easy to find?**  
   **For trained daily users, often. For new or occasional users, no.** Critical
   facts are distributed between tables, drawers, queues, alerts, and module
   pages.

5. **Are primary actions obvious?**  
   **In some workflows.** The overview hero, job creation, and guarded candidate
   actions are good. Dense pages often present several actions with similar
   visual weight.

6. **Are there too many statuses, cards, columns, tabs, and controls?**  
   **Yes.** The issue is not any single control; it is their cumulative number
   and inconsistent meaning across application, interview, assessment,
   communication, document, delivery, and review states.

7. **Are related capabilities fragmented?**  
   **Yes.** Candidates, ranking, assessment queues, interview queues,
   communication failures, intake exceptions, and reports repeatedly expose
   different slices of the same hiring population.

8. **Does the product expose backend concepts?**  
   **Yes.** Examples include “authority,” “governed profile,” stable taxonomy
   node IDs, tenant scope, extraction snapshots, sender provenance, dead letters,
   calibration, item banks, internal user IDs, and storage/extraction states.

9. **Does Arabic/RTL feel natural?**  
   **No.** Some recruiting views have useful Arabic copy, but the shell,
   navigation, many controls, the candidate profile, most advanced filters, and
   all post-hire pages remain substantially English-first.

10. **Does every enabled module feel complete and coherent?**  
    **No.** Functional depth varies. Some modules have clear queues and actions;
    others look like operational consoles, reports, or configuration mixed into
    one page.

11. **Does a two-module company feel clean?**  
    **Cleaner than the full suite, but not fully intentional.** Module gating
    hides disabled destinations, which is good. Always-visible Workspace items,
    the generic shell, and cross-module pages can still feel disproportionate.

12. **What will frustrate a real HR team?**  
    Finding the correct queue, understanding which status matters, horizontal
    table scrolling, repeated filtering, untranslated English, duplicated
    candidate views, and uncertainty about whether an AI label is fact,
    suggestion, or decision.

---

## 2. Ten biggest product usability problems

### 1. The workspace mirrors product modules more than HR work

**Observed fact:** The sidebar can show Overview, Wathefni Assistant, Jobs,
Candidates, Intake Operations, Interviews, Assessments, Ranking, Reports,
Employees, Onboarding, Attendance, Leave, Shifts, Payroll, Analytics,
Compliance, Alerts & Delivery, Activity, and Settings.

**Expert judgment:** Users must choose a system destination before they can
complete a task. A real recruiter thinks “review Sara for Sales Manager,” not
“should I open Candidates, Ranking, Assessments, Interviews, Alerts, or Reports?”

### 2. Candidates is a unified area in name but still application- and
pipeline-centric

**Observed fact:** Rows are keyed and handled as `ApplicationSummary`; the UI
mixes Talent Pool and live job applications but exposes row state, job state,
application stage, communication, CV processing, assessment, and recruiter
ownership.

**Expert judgment:** One area is defensible, but one flat table with identical
semantics is not. A person open to opportunities and an applicant for a specific
job are related records with different primary questions.

### 3. State overload obscures the actual decision

**Observed fact:** The frontend separately represents application stage, record
state, CV processing, screening, assessment, interview, interview feedback,
communication, delivery, review, offer, and hiring states. Legacy stage aliases
remain filterable.

**Expert judgment:** Users can see a large amount of “truth” but still struggle
to answer: “What should I do next?” The product needs fewer user-facing state
systems, not merely better labels for all current systems.

### 4. The current Candidates filter system is an expert query builder

**Observed fact:** The page supports standard status/search, saved views,
seventeen advanced filter fields, and six classification dimensions. Copy
explains taxonomy IDs, within-dimension OR, cross-dimension AND, authority, and
AI confidence.

**Expert judgment:** This is too technical for default recruiter use and
especially unsuitable for occasional hiring managers. Powerful filters are
valuable, but their current presentation dominates the product.

### 5. Tables are desktop spreadsheets rather than responsive work surfaces

**Observed fact:** Candidates uses `min-w-[1180px]`, Jobs `min-w-[1100px]`,
Interviews `min-w-[1160px]`, Team Access `min-w-[900px]`; many post-hire tables
use 520–820px minimum widths and horizontal overflow.

**Expert judgment:** Desktop is workable but wide. Tablet and mobile become
horizontal-scroll exercises, with identity and actions separated across the
scroll.

### 6. Arabic is a partial feature, not a workspace language

**Observed fact:** Locale state is concentrated in recruiting lifecycle copy and
selected pages. The main sidebar is English. `PostHire.tsx` has no locale/RTL
handling. Many strings inside RTL recruiting containers remain English.

**Expert judgment:** An Arabic-first user receives a mixed-language product, not
an Arabic product. This is more disruptive than untranslated labels because
direction, reading order, drawer anchoring, date/number formatting, and action
placement also remain English/LTR-oriented.

### 7. Operational and backend concepts are presented to normal HR users

**Observed fact:** Candidates can show “Talent Pool,” “authority,” “Advisory,”
“grounded contact,” “sender provenance,” “extraction completeness,” “append-only,”
“immutable snapshot,” fact paths, privacy/retention IDs, dead letters,
quarantine, stable taxonomy IDs, tenant nodes, item banks, norms, calibration,
and internal user IDs.

**Expert judgment:** These concepts may be important for governance and support,
but they should not define the daily HR experience.

### 8. Pages repeatedly combine operations, configuration, analytics, and
evidence

**Observed fact:** Assessments contains a send queue, recent attempts,
authoring, setup, calibration details, reports, and norms refresh. Settings
contains account, capabilities, WhatsApp identity, recovery access, team
management, integrations, and intake settings.

**Expert judgment:** Mixed page purposes weaken action hierarchy and make role
differences harder to understand.

### 9. Responsive navigation is incomplete

**Observed fact:** The desktop sidebar becomes the first full-width grid item
below the `lg` breakpoint; there is no separate compact/mobile navigation
pattern in the main shell.

**Expert judgment:** On a phone or tablet, users must pass a long navigation
block before page content. That is not an acceptable mobile workspace, even if
individual cards stack.

### 10. Permission handling is safe but not always explanatory

**Observed fact:** Some unauthorized actions are hidden, some are disabled with
tooltips, and some pages remain visible with limited content. Backend-provided
`allowed_actions` gates candidate/interview actions.

**Expert judgment:** The safety model is good, but the experience is
inconsistent. Users may interpret missing controls, disabled controls, and
empty sections as product defects rather than role limitations.

---

## 3. Current information architecture

### Observed navigation

The normal workspace uses three sidebar groups:

- **Pre-Hiring**
  - Overview
  - Wathefni Assistant
  - Jobs
  - Candidates
  - Intake Operations
  - Interviews
  - Assessments
  - Ranking
  - Reports
- **Post-Hire**
  - Employees
  - Onboarding
  - Attendance
  - Leave
  - Shifts
  - Payroll
  - Analytics
  - Compliance
- **Workspace**
  - Alerts & Delivery
  - Activity
  - Settings

### Observed routing model

**Observed fact:** This is not a conventional route-per-page React router. Page
state is a union in `App.tsx`. The URL only seeds Settings on initial load
(`?page=settings`) and invite acceptance; normal page changes do not update the
URL.

**Expert judgment:** This can work for an app shell, but it weakens deep linking,
browser navigation expectations, and sharable task context.

### Module visibility

**Observed facts:**

- Most destinations are filtered by `enabled_modules`.
- Assessments is hidden when the assessment module is disabled.
- Employees appears when any people-surface module is enabled.
- Employee App is explicitly excluded from HR navigation.
- Alerts & Delivery appears when pre-hiring or any post-hire module is relevant.
- Activity requires `audit.read`.
- Settings is always visible.
- If the requested page is unavailable, the app falls back to Overview,
  Employees, or Settings depending on available modules.

**Expert judgment:** This is one of the stronger product foundations. Disabled
modules generally disappear instead of appearing as dead upsell pages.

**Issue:** Visibility is mostly module-level, not task- or role-level. A user can
still enter a large module page containing areas they cannot operate.

### Partial-module company

**Observed fact:** Tests explicitly cover an assessment-disabled company and a
post-hire-only compliance company.

**Expert judgment:** A company with two enabled modules receives fewer sidebar
items, so the workspace is materially cleaner. However:

- the group labels can feel artificial when only one item exists in a group;
- Employees may appear as a supporting surface rather than a purchased module;
- Alerts, Activity, and Settings still occupy a full Workspace group;
- the header and page chrome remain optimized for a broad suite.

**Product decision:** Should a small-module company see the same suite shell
with fewer items, or a deliberately compact workspace?

---

## 4. Page-by-page critique

### Home / Overview

**Purpose today — observed:** A pre-hiring control center showing one suggested
next action, four attention cards, a priority queue, and role next steps.

**What is clear:** The “what should I do next?” framing is strong. Counts link
to filtered work. The quiet state is reassuring.

**Problems — expert judgment:**

- It is a pre-hiring home, not a company HR home.
- It repeats the same urgency in a hero, attention cards, priority queue, and
  role next steps.
- Four action cards plus two lower cards still creates a dashboard of summaries
  rather than a concise worklist.
- A post-hire-only user falls into Employees rather than receiving a tailored
  home.

**Stay/merge/remove:** Preserve the action-oriented home concept. Its role as a
pre-hiring-only “Overview” needs a product decision.

**Responsive/RTL:** Cards stack sensibly. Arabic is strongest here, but the
surrounding shell remains English.

### Candidates

**Purpose today — observed:** One table for Talent Pool and active job
applications, with saved views, classification filters, advanced filters,
import, paging, and a detailed drawer.

**Clarity:** The base purpose is understandable. The description itself exposes
“authority differs by row state,” which signals underlying complexity.

**Biggest problems:**

- up to nine columns and a 1180px minimum table width;
- multiple filter rows before data;
- “Talent Pool” is both a view and a row badge;
- general/held records inherit application-stage vocabulary;
- contact, match reasons, classification, and candidate identity compete in the
  first cell;
- important “received” date is not a list column while CV processing and
  communication are;
- status and job semantics differ by row type;
- held and live rows open two substantially different profile drawers, but that
  distinction is only weakly signalled by the Talent Pool badge;
- source filter tokens and displayed source labels are not consistently aligned
  (`bulk` versus `bulk_import`, `dashboard` versus `manual`), creating a risk of
  filters that appear to return the wrong results.

**Confusing terminology:** Talent Pool, active application, held, record state,
authority, grounded contact, classification authority, High AI, CV processing,
entry method.

**Unnecessary in default list:** CV processing, communication state, recruiter
owner, assessment state, match reasons, and classification authority all at
once.

**Missing from default list:** A clearly formatted received date/age; a compact
expertise summary; an unmistakable relation to a job; explicit “needs action.”

**Action hierarchy:** Clicking a row is the primary action, but the page gives
greater visual space to filters than to candidate triage.

**Duplication:** Ranking, assessment queue, interview queue, Intake Operations,
Overview work queue, and Alerts all expose candidate subsets.

**Stay/merge/remove:** Keep a single Candidates destination, but do not preserve
the current single-table semantics unchanged. Detailed judgment is in section 5.

### Candidate profile / drawer

**Purpose today — observed:** A right-side drawer combining identity, job
relationship, contact provenance, held/live applications, documents,
classification, fact correction, privacy/retention, AI analysis, communication,
interviews, offers, actions, and timeline.

**Expert judgment:** This is the most information-rich and least edited surface
in the product. It is simultaneously a recruiter profile, governance console,
evidence viewer, data-correction tool, and workflow cockpit.

**Backend concepts visible:** “Governed candidate profile,” sender provenance,
extraction completeness, missing policy, held intake rows, live application
rows, privacy notice ID, retention policy ID, extraction method, storage state,
fact path, append-only events, immutable extraction snapshots, and a disabled
“Future action.”

**What is good:** Actions are permission/stage gated; AI is described as
advisory; historical documents are preserved; offers and interviews remain
contextual to the candidate.

**What should change at product level:** The profile needs a clear HR summary
first. Governance and technical evidence should be secondary, permissioned, or
support-only.

**Observed workflow gap:** For held/no-job candidates, “Link to Job” is rendered
disabled and labelled as not implemented. A unified candidate pool therefore
exposes candidates whom HR cannot move into the normal job workflow from this
profile.

**Responsive/RTL:** Full-width on small screens, max 3xl on desktop. It always
anchors right using `ml-auto` and a left border, even in RTL.

### Jobs

**Purpose today — observed:** Create, draft, publish, edit, filter, share, and
track openings and application counts.

**Clarity:** Stronger than most pages. “Create job” and “Draft with Assistant”
are visible, and the list supports operational filtering.

**Problems:**

- five metrics before the list;
- nine columns with 1100px minimum width;
- the code column shows apply codes in monospace;
- recruiter/hiring manager inputs use internal user IDs;
- bilingual authoring, approval flags, salary rules, ownership, visibility, and
  dates make the form long and admin-heavy.

**Unnecessary default information:** Apply code and age are less important than
job title, status, applicants, owner, deadline, and vacancies.

**Missing:** A clearer hiring progress/bottleneck summary per opening and a
human-friendly owner picker.

**Stay/merge/remove:** Stay separate. Jobs is a strong primary object.

**Responsive/RTL:** RTL exists on the page and Arabic fields explicitly use
RTL, but the wide table and several English tooltips remain.

### Applications

**Purpose today — observed:** There is no standalone Applications navigation
item. Applications are represented in Candidates and Job applicant counts.

**Expert judgment:** Not having a separate Applications page is correct if
Candidates cleanly expresses a person’s job relationships. Today it does not
fully do so because the core frontend type and many actions are still
application-centric.

**Product decision:** Should the primary record be a person with applications,
or an application with candidate details? The answer changes table structure,
profile hierarchy, duplicate handling, and “general CV” behavior.

### Screening

**Purpose today — observed:** Screening is a lifecycle/status concept surfaced
in candidate evidence, overview counts, reports, and readiness logic; it is not
a top-level destination.

**Expert judgment:** Keeping screening contextual is sensible. However, the user
cannot easily tell whether “CV processing,” “screening,” “ready for review,” and
“AI analysis” are sequential steps or overlapping evidence states.

**Stay/merge/remove:** Preserve as a candidate/job workflow step, not a separate
navigation destination.

### Ranking

**Purpose today — observed:** Select a job, run ranking, and view candidate
cards with score, AI fit summary, strengths, gaps, risks, evidence, criteria,
and next-step recommendations.

**Clarity:** The basic job-first workflow is clear.

**Problems:**

- a separate page duplicates job and candidate context;
- score, job match, evidence confidence, AI review source, fit profile, criteria,
  strengths, gaps, risks, and recommendation create false precision;
- “Rank” looks like a deterministic command even when evidence is incomplete;
- no Arabic/RTL support.

**What is good:** Missing evidence is explicitly shown; detailed score breakdown
is collapsed; the user can open the candidate profile.

**Stay/merge/remove:** The capability is valuable. Whether it remains top-level
or becomes a job/candidate view is an unresolved product decision.

### Assessments

**Purpose today — observed:** Manage candidates awaiting assessment, attempts,
delivery, results, reports, authoring, setup, item-bank metadata, calibration,
and norms refresh.

**Clarity:** Daily assessment operations are understandable, but the page has
too many audiences.

**Problems:**

- five headline metrics;
- an authoring panel inside the daily queue;
- queue plus recent attempts plus setup plus reports plus setup details;
- technical language: battery, item bank, norm version, deterministic scoring,
  calibration, role profiles;
- two different candidate tables;
- 960px attempt table;
- English only.

**Action hierarchy:** Sending, reviewing, resending, cancelling, opening a
candidate, refreshing norms, and authoring content coexist.

**Stay/merge/remove:** Assessments can remain a module destination, but daily
operations and assessment administration should not feel like one undifferentiated page.

### Scheduled interviews

**Purpose today — observed:** Upcoming interviews, search/filter, schedule,
status changes, invite truth, notes, feedback, Meet access, and timeline.

**Clarity:** Candidate, job, application stage, interview state, schedule, and
next action are separated, which is conceptually sound.

**Problems:**

- six metrics, seven tabs, four filters, and a wide seven-column queue;
- application state and interview state appear together throughout;
- drawer repeats invite, status, and timeline information in several blocks;
- free-text notes and structured feedback are discussed but not presented as
  one obvious feedback workflow.

**Stay/merge/remove:** Interviews should stay as a coherent destination. It is
one of the better justified queues.

### Video interviews

**Purpose today — observed:** A tab within Interviews, with candidate video,
transcription status, question coverage, AI summary, retry, review, and
feedback.

**Expert judgment:** Combining scheduled and video interviews under one
Interviews destination is correct. They are distinct modalities, not separate
products. The current screen still exposes transcript-processing mechanics more
than most HR users need.

**Stay/merge/remove:** Preserve as an Interviews sub-view, not a top-level item.

### Notes and collaboration

**Purpose today — observed:** Notes are contextual in interview drawers and
candidate workflows. Interview notes can generate summaries; candidate actions
use message/notes inputs. Activity provides a separate audit trail.

**Expert judgment:** Contextual notes are preferable to a standalone Notes page.
The current experience does not yet read as one collaboration system: comments,
feedback, audit events, mentions, and generated summaries appear in different
surfaces and use different rules.

**Stay/merge/remove:** Preserve context-first collaboration. Do not create a
top-level Notes destination.

### Communication

**Purpose today — observed:** Candidate communication state is shown in the
Candidates table/profile; sends happen from candidate/interview/assessment
actions; failed delivery also appears in Alerts & Delivery.

**Expert judgment:** Communication is correctly contextual but too fragmented.
The same user may see “Communication,” “Invitation status,” “Candidate
notified,” “Delivery alerts,” “Follow-up,” and “No outreach.”

**Stay/merge/remove:** Keep communication actions in context and preserve a
central exception queue, but simplify the user-facing state vocabulary.

### Offers and hiring

**Purpose today — observed:** Offers are handled through an `OfferPanel` in the
candidate drawer; Hire is a guarded candidate action. Legacy `offered` and
`offer_sent` stages map to `Shortlisted` in the canonical stage labels.

**Expert judgment:** Contextual offer handling is appropriate, but mapping offer
states to Shortlisted hides meaningful commercial/legal progress. Offers are
also easy to miss because they have no obvious aggregate queue.

**Stay/merge/remove:** Keep offers under candidate/job context. Decide whether
HR needs a dedicated offer queue inside Hiring—not necessarily a top-level
page.

### Intake Operations

**Purpose today — observed:** Show counts for queued, processing, incomplete
extraction, failed/dead-letter, unsupported, password-protected, quarantined,
and ready-held CVs.

**Clarity:** It accurately describes system operations.

**Problem:** It is explicitly an operational exception console. “Dead letter,”
“quarantine,” “malware,” “unsupported,” and “release forbidden” are not normal
recruiter navigation concepts.

**Action hierarchy:** The current page mostly shows counts and no clear normal
HR remediation workflow. There is no drill-down from the operational buckets,
so the Candidates attention banner can lead to a count-only dead end.

**Stay/merge/remove:** It should not be a normal top-level recruiter item.
Whether it belongs in admin/support or becomes a human “CV issues” queue is a
product decision.

### Reports

**Purpose today — observed:** Export candidate, role, assessment, interview, and
follow-up spreadsheets; show simple current pipeline metrics and breakdowns.

**What is good:** The page clearly distinguishes daily work from leadership
reporting. Export actions are permission-gated and confirmed.

**Problems:** No visible date range, saved reporting context, trend comparison,
or Arabic. “Reports” overlaps with post-hire Analytics, creating two insights
mental models.

**Stay/merge/remove:** Reporting should remain available. The relationship
between Hiring Reports and Workforce Analytics needs clarification.

### Employees

**Purpose today — observed:** Employee directory with employee, department,
contact, and onboarding columns, search, import/create actions, employee profile,
and prioritized next actions.

**Clarity:** Strong. The table is relatively restrained compared with
Candidates.

**Problems:** Employee profile can become a second module dashboard containing
onboarding, documents, timesheets, leave, shifts, payroll, and tasks. Some
companies may see Employees even though they purchased only a supporting people
module. Status and activation flows also expose “internal-canary,” approval
reference, and invite identifiers that are platform-control language rather than
normal HR language.

**Stay/merge/remove:** Employees should stay as a primary People object.

**Responsive/RTL:** 640px table scrolls on small screens. No Arabic/RTL mode.

### Employee onboarding

**Purpose today — observed:** Track new hires in progress, open checklist/doc
items, details, reminders, and exceptions.

**Clarity:** Generally clear and task-oriented.

**Problems:** Overlaps with the onboarding column and next actions in Employees,
plus Compliance documents. A user may not know whether to start from Employees,
Onboarding, or Compliance.

**Stay/merge/remove:** Keep a queue for onboarding specialists, while preserving
employee context. Its boundary with Compliance must be explicit.

### Compliance

**Purpose today — observed:** Missing, expired, and expiring employee documents,
with expiry, days left, reminder, review, and actions.

**Clarity:** The module purpose is clear.

**Problems:** Seven-column operational table, document review inside another
drawer/modal, and overlap with onboarding document collection. “Compliance”
may be too broad for what is currently an employee-document expiry tracker.

**Stay/merge/remove:** Keep if the product intends broader compliance. If it is
only document validity, the label should be more specific.

### Attendance

**Purpose today — observed:** Attendance records, date/range filtering,
check-in/out, status, corrections, and import.

**Clarity:** Clear for daily HR operations.

**Problems:** Table-first experience, no strong exception-first default, English
only, and date/time formatting depends on browser locale rather than an explicit
company locale. Present/Late/Absent metric cards are calculated from the
currently loaded page rows rather than server totals, so they can become
misleading at scale. Device import guidance also refers to assigning a device
identifier on the employee record, but Employee edit does not expose that field.

**Stay/merge/remove:** Stay separate for companies using attendance.

### Shifts

**Purpose today — observed:** Schedule shifts, view a weekly schedule, manage
swap requests, reschedule/cancel, and notify employees.

**Clarity:** Purpose is clear.

**Problems:** Scheduling, swap approval, and historical/table review coexist.
The create form accepts a free-text employee name rather than an employee
picker, making identity errors more likely. The schedule is still
table/form-driven rather than spatial. Mobile scheduling will be cumbersome.

**Stay/merge/remove:** Stay separate if shift planning is a real purchased
workflow.

### Leave

**Purpose today — observed:** Pending decisions, upcoming leave, leave history,
balances, and new requests.

**Clarity:** Strong because sections correspond to HR questions.

**Problems:** Pending, upcoming, and history create repeated employee/date/type
views; manager scope and team calendar context are not visually prominent.

**Stay/merge/remove:** Stay separate. This is one of the more coherent modules.

### Payroll

**Purpose today — observed:** Timesheet review, payroll preview, estimated
amounts, payroll policy, approvals, exports, and export history.

**Clarity:** The broad flow is visible, but the page mixes operational review,
calculation policy, preview, and exports.

**Problems:** “Estimated amount,” “payable hours,” policy details, approval, and
export can look like a payroll engine even where the product is an export
workflow. The risk and responsibility boundary is not prominent enough.

**Stay/merge/remove:** Stay separate, but the product must clearly state whether
Wathefni calculates payroll or prepares an export.

### Analytics

**Purpose today — observed:** Executive workforce, attendance, and post-hire
trend metrics.

**Clarity:** Reasonably clear.

**Problems:** Competes with pre-hire Reports. Empty-state and period behavior
are basic. English only.

**Stay/merge/remove:** Keep insights, but product ownership must decide whether
users need one cross-workspace Insights destination or separate Hiring Reports
and Workforce Analytics.

### Alerts & Delivery

**Purpose today — observed:** A shared Workspace page combining urgent hiring
alerts, onboarding exceptions, delivery alerts, completions, and employee
message follow-up.

**What is good:** Centralized exception handling is valuable. Static suggestions
are not rendered as fake buttons, and actionable labels navigate to real pages.

**Problems:** “Alerts & Delivery” is a system phrase. It mixes alerts, work
queues, communication delivery, and employee messages across domains. Some of
the same work also appears on Overview and module pages.

**Stay/merge/remove:** Preserve a central action/exception center, but its scope
and naming need a product decision.

### Team and permissions

**Purpose today — observed:** Invite users, assign built-in roles, view
capabilities, link WhatsApp identity, change role/status, and deactivate users.

**What is good:** Dangerous changes use confirmation; permissions are translated
into readable capability descriptions; unauthorized users receive explanatory
copy.

**Problems:** Team management lives inside Settings alongside account recovery
and integrations. The team table has eight columns and internal role complexity.
The exact effect of a role is separated from the role selector.

**Stay/merge/remove:** Team access is an administrative area and deserves a
clear subsection. It should not compete with personal account recovery.

### Settings

**Purpose today — observed:** Personal identity, workspace access, recovery
token, company code/phone, WhatsApp mapping, team access, integrations, and
intake policy.

**Expert judgment:** This is overloaded and exposes setup/recovery mechanisms in
the everyday product. “Backup access code,” registered HR phone, company code,
and WhatsApp identity mapping are operational concepts.

**Stay/merge/remove:** Settings stays, but current contents need stronger
separation between My account, Team access, Workspace settings, and
Integrations. This is an information-architecture judgment, not an
implementation recommendation.

### Activity

**Purpose today — observed:** Permission-gated read-only audit history.

**Clarity:** Clear for admins.

**Problem:** “Activity” is ambiguous: it could mean user activity, candidate
activity, or audit history.

**Stay/merge/remove:** Preserve for authorized users; “Audit history” is the more
accurate term.

---

## 5. Candidates-area objective critique

### Should all candidate types appear in one area?

**Expert judgment: Yes, as one discoverable Candidates area—but not as one
undifferentiated record type.**

Reasons to unify:

- HR searches for a person, not the channel that delivered the CV.
- Email, WhatsApp, manual upload, general CV, and job application are acquisition
  paths, not separate products.
- Duplicates and multiple applications are easier to understand in a
  person-centric area.
- Separate destinations would recreate fragmentation and hide reusable talent.

Reasons not to flatten:

- A general candidate has no application stage for a specific job.
- One person may have multiple applications with different stages.
- Source and intake quality matter operationally but not as primary identity.
- Retention, communication permission, and “next action” can differ between a
  general profile and a job application.

### Should general CVs and job applicants share the same table?

**Expert judgment:** They can share the same area and base list, provided the
list explicitly represents the relationship:

- job applicant → job title + application stage;
- general candidate → “Not assigned to a job” or “Open to opportunities” +
  profile state, not a fabricated application stage.

They should not be forced to have identical meanings in every column.

### What must be visible in the list?

Recommended priority as product requirements, not a design:

1. Candidate identity: name and one reliable contact or a clear contact warning.
2. Expertise/target role: concise, source-labelled, and never presented as fact
   when AI-derived.
3. Job relationship: job title, multiple-application indicator, or explicit
   no-job state.
4. Current HR state: one dominant user-facing stage/next action.
5. Received/last activity: a human date or age.
6. Exception only when actionable: missing CV, failed processing, unreachable,
   duplicate review, or restricted access.

Recruiter owner may be useful for larger teams but should not be mandatory for
all tenants.

### What belongs inside the profile?

- full contact details and provenance;
- CV preview and document history;
- employment/education/skills evidence;
- all applications and their individual stages;
- screening details;
- assessment attempts/reports;
- interview history/feedback/video;
- communication timeline and delivery detail;
- offers and hire history;
- collaboration notes/mentions;
- privacy/retention controls for authorized users;
- AI evidence, confidence, and correction tools.

### Is AI-detected Expertise useful?

**Both useful and potentially misleading.**

Useful when:

- it helps scan a large general-CV pool;
- it uses plain labels meaningful in Kuwait/GCC hiring;
- users can distinguish AI suggestion from HR confirmation;
- evidence and confidence are available in the profile;
- uncertain/multi-domain candidates are not forced into one label.

Misleading when:

- shown as “Expertise” without its source;
- a likely role is treated as verified experience;
- the model infers seniority or industry from weak evidence;
- Arabic CV extraction produces lower confidence but looks equally certain;
- one classification suppresses a candidate’s other viable roles.

**Product decision:** Is the list label “Expertise,” “Likely role,” “Professional
area,” or an HR-confirmed category? These are not interchangeable.

### How should “No job assigned” candidates be handled?

They should be valid candidates, not errors and not fake applicants.

Reasonable English concepts:

- Open to opportunities
- General candidate
- Not assigned to a job
- Available for matching

Reasonable Arabic concepts:

- **مرشح غير مرتبط بوظيفة** — precise, neutral
- **مرشح عام** — short but potentially vague
- **متاح للفرص المناسبة** — candidate-friendly but less operational
- **بانتظار الربط بوظيفة** — implies HR action is required

Avoid using a dash alone: it hides an important distinction. Avoid “Talent Pool”
as the only explanation unless product ownership wants that concept explicitly
in the HR product.

### Terminology for an Arab HR user

Prefer plain HR concepts:

- Candidates → المرشحون
- Job applicants → المتقدمون للوظيفة
- General candidates → المرشحون العامون
- Not assigned to a job → غير مرتبط بوظيفة
- Ready for review → جاهز للمراجعة
- Needs information → يحتاج معلومات
- Suggested expertise → مجال مقترح
- HR confirmed → مؤكّد من الموارد البشرية
- Source → مصدر الاستلام
- Received → تاريخ الاستلام

Avoid literal technical translations of authority, provenance, grounded,
taxonomy node, immutable snapshot, dead letter, or tenant.

### Remove, merge, preserve

**Remove from normal default experience:**

- “authority differs by row state”;
- stable taxonomy ID / OR-AND explanatory text;
- tenant/global taxonomy scope;
- dead-letter terminology;
- append-only/immutable snapshot copy;
- privacy policy identifiers;
- disabled “Future action” controls.

**Merge conceptually:**

- candidate identity and all applications in one person profile;
- communication and delivery history;
- screening and CV-processing explanation;
- candidate-related work queues as saved/default views rather than parallel
  candidate lists.

**Preserve:**

- one Candidates destination;
- source visibility;
- job relationship;
- human decision ownership;
- AI advisory labels and evidence;
- duplicate-aware identity;
- historical CV/document versions;
- contextual assessments, interviews, offers, and notes;
- explicit restricted/privacy handling.

---

## 6. Navigation critique and alternative directions

### Current mental model

**Observed fact:** The actual model is `Pre-Hiring`, `Post-Hire`, and
`Workspace`, not Hiring, People, Workforce, and Settings.

**Expert judgment:** “Pre-Hiring/Post-Hire” describes the vendor’s module
portfolio and an employee lifecycle boundary. It is not how all HR users
organize daily work:

- recruiters think Jobs, Candidates, Interviews, Decisions;
- HR operations thinks People, Time, Leave, Documents, Payroll;
- managers think My approvals, My team, Interviews;
- admins think Team access, Policies, Integrations.

“Post-Hire” is particularly broad: Employees, onboarding, attendance, leave,
shifts, payroll, analytics, and compliance have different users and rhythms.

### What is too fragmented

- candidate decisions across Candidates, Ranking, Assessments, Interviews,
  Overview, Alerts, and Reports;
- employee document work across Employees, Onboarding, and Compliance;
- communication issues across candidate actions, interview/assessment pages,
  Overview, and Alerts & Delivery;
- insights across Reports and Analytics;
- team/admin functions inside Settings.

### What is grouped incorrectly

- Intake Operations as normal Pre-Hiring work;
- Alerts & Delivery under Workspace despite being cross-workflow tasks;
- Activity under Workspace with a generic name;
- Analytics under Post-Hire while Reports is under Pre-Hiring;
- Wathefni Assistant as a peer to core business objects.

### What should probably not be top-level

**Expert judgment, pending product decisions:**

- Intake Operations for ordinary recruiters;
- Ranking if it is fundamentally a job/candidate view;
- Wathefni Assistant if it is a cross-workspace affordance;
- Activity if it is only admin audit history.

### Are Hiring, People, Workforce, Settings a better mental model?

Potentially, but not automatically:

- **Hiring** naturally holds Jobs, Candidates, Interviews, Assessments, Offers.
- **People** naturally holds Employees, onboarding, documents, employee profile.
- **Workforce** can hold Attendance, Leave, Shifts, Payroll, but the word may be
  vague for small GCC companies and may not translate naturally.
- **Settings/Admin** is clear for team, policies, integrations, and audit.

The key improvement would be organizing around objects and responsibilities,
not merely renaming current groups.

### Alternative direction A — Object-based workspace

Possible concepts: Home, Jobs, Candidates, Employees, Time, Pay, Insights,
Admin.

**Strengths:**

- easy for first-time users;
- fewer top-level destinations;
- stable as capabilities grow;
- candidates and employees become clear primary objects.

**Weaknesses:**

- queues such as Interviews and Assessments need strong contextual subnavigation;
- specialist recruiters may want one-click access to daily queues;
- “Time” can become another broad container.

### Alternative direction B — Lifecycle hubs

Possible concepts: Recruit, Hire, Onboard, Manage workforce, Analyze, Configure.

**Strengths:**

- tells a process story;
- useful for first-time admins;
- makes module dependencies understandable.

**Weaknesses:**

- real HR work is not linear;
- employees and candidates can participate in several processes at once;
- occasional managers may not know which lifecycle hub owns an approval.

### Alternative direction C — Role-adaptive task workspace

Possible concepts: My work, Hiring, My team/People, Workforce, Insights, Admin,
with default queues adjusted for recruiter, manager, owner, or payroll user.

**Strengths:**

- reduces noise for occasional users;
- aligns with permissions;
- surfaces approvals and exceptions directly.

**Weaknesses:**

- navigation can appear inconsistent between users;
- support/training becomes harder;
- incorrect role configuration has larger UX consequences.

### Alternative direction D — Small fixed navigation plus contextual subviews

Possible concepts: Home, Hiring, People, Workforce, Insights, Settings; module
capabilities become tabs/views inside each hub.

**Strengths:**

- compact and learnable;
- partial-module companies remain intentional;
- related queues can share context and filters.

**Weaknesses:**

- hubs can become dense mega-pages;
- deep links and selected subview state must be reliable;
- expert users may need shortcuts.

**Product decision:** Which matters more: fastest expert queue access, easiest
first-use comprehension, or consistent cross-role navigation?

---

## 7. Visual-system critique

### What is already visually strong

**Observed facts:**

- consistent warm neutral palette;
- restrained accent color;
- reusable Card, Button, Badge, Input, Select, Textarea components;
- consistent rounded surfaces;
- clear basic focus styling on form controls;
- Lucide icon set;
- dangerous actions use confirmation and red treatment;
- many empty states use plain, calm copy.

### What makes it look crowded or generic

**Expert judgment:**

- nearly every section is a rounded card inside another rounded surface;
- cards, pills, badges, subtle borders, glass backgrounds, blur, and shadows are
  used so frequently that hierarchy flattens;
- uppercase 10–11px labels with wide tracking appear everywhere;
- large 4xl/5xl page headings consume vertical space without adding task value;
- metric-card grids precede many operational tables;
- similar cards represent metrics, filters, actions, evidence, settings, and
  warnings, so visual form does not communicate semantic importance;
- warm beige glass styling is distinctive but repeated enough to feel like a
  template rather than a task-specific product.

### Spacing and density

- Global spacing is generous, but content density inside tables/drawers is high.
- Pages often combine large headers and large gaps with very wide tables, so
  they feel both spacious and cramped.
- Candidate and interview drawers contain many vertically stacked bordered
  sections, creating long scan paths.

### Typography

- The core type scale is readable on desktop.
- Excessive uppercase microcopy and letter spacing reduce readability,
  especially in Arabic.
- The interface uses Inter/system fonts with no Arabic-specific font strategy.
- English title casing generated from machine values can produce awkward HR
  terminology.

### Cards and borders

- Card primitives are consistent.
- Nested cards and nested borders are overused.
- Shadows and translucent backgrounds create polish but reduce contrast between
  primary, secondary, and diagnostic content.

### Tables

- Header styling is consistent.
- Most operational pages use tables even when mobile cards or exception lists
  would better preserve identity/action context.
- Horizontal overflow is the dominant responsive strategy.
- Many tables put actions in the far-right column, separated from identity on
  small screens.

### Filters

- Filters frequently use unlabeled selects whose first option acts as the label.
- Candidates has too many advanced filters for a default surface.
- Saved views are useful but displayed as another row of buttons, adding visual
  noise as the count grows.
- “Apply” suggests filters are not live, while some nearby controls update
  local state immediately; interaction expectations are mixed.

### Status badges

- Badges create quick recognition.
- Too many independent status systems use the same few tones.
- “Success” green can mean enabled, grounded, active, ready, completed, live, or
  merely not held.
- A user cannot infer whether a badge is a lifecycle state, data quality state,
  or action requirement from color alone.

### Modals and drawers

- Confirm dialogs provide useful safety.
- Custom dialogs do not visibly implement standard dialog semantics, focus trap,
  Escape handling, or focus restoration.
- Several overlays close on backdrop click, which is risky for long forms.
- Drawers are always right-anchored and visually LTR.
- Full-height drawers become very long pages on mobile.
- Several post-hire workflows use native `window.prompt` for status reasons,
  document dates/rejection reasons, activation references, and attendance
  mapping names. This provides weak validation, poor context, and especially
  poor mobile/RTL usability.

### Empty/loading/error states

**Good:**

- Post-hire has reusable loading and empty states.
- Several empty states explain what will appear and what to do next.
- Post-hire maps raw backend errors to friendly copy and detects technical
  messages.

**Weak:**

- loading is usually a spinner/text rather than preserving page shape;
- error handling is not equally mature across pre-hire;
- “Could not load governed candidate profile” and Intake Operations language
  remain product-internal;
- empty states often assume the user should “share a job link,” which is not
  relevant to general candidates.

---

## 8. English/Arabic terminology problems

### Mixed-language product

**Observed fact:** Arabic translations exist for many application stages,
recruiting actions, overview copy, jobs copy, and some interview copy.
Post-hire pages and the sidebar remain English.

**Expert judgment:** A locale toggle inside individual pages is the wrong scope.
Language is a workspace/user preference and should apply consistently.

### English terms that are too technical

- Wathefni Pre-Hiring Control Center
- Intake Operations
- Talent Pool
- authority
- grounded contact
- sender provenance
- extraction completeness
- immutable extraction snapshot
- fact path
- taxonomy node
- tenant scope
- dead letter
- calibration
- item bank
- norms
- deterministic scoring
- fit profile
- stored score
- delivery truth / provider accepted

### Arabic translation risks

Some existing translations are understandable but formal or system-like:

- `في القائمة المختصرة` is accurate but long; HR teams may use
  `القائمة المختصرة` or `مرشح مختار`.
- `تم التجاوز عمداً` for intentionally skipped can sound accusatory or
  machine-translated.
- `أقدمية` for seniority can be interpreted as tenure rather than job level in
  GCC HR contexts.
- `نطاق خبرة` is understandable but needs user testing against
  `سنوات الخبرة`.

### Terminology consistency issues

- Job / role / opening / position are used interchangeably.
- Candidate / applicant / Talent Pool record are used interchangeably.
- Status / stage / state / review state appear in the same workflows.
- Assessment / evaluation / analysis / screening are not sharply separated.
- Alerts / notifications / delivery / follow-up overlap.
- Employees / people / workforce / post-hire overlap.

**Product decision:** Establish one bilingual product glossary before any broad
UI redesign.

---

## 9. Responsive and RTL findings

### Desktop

**Expert judgment:** Desktop is the intended and most viable experience. It is
still overly wide and information-dense on laptop screens, particularly with a
260px sidebar and 1100–1180px tables.

### Tablet

- Below `lg`, the shell loses the two-column sidebar layout.
- The entire navigation is rendered above content rather than becoming a
  drawer, rail, or compact bar.
- Many forms change to one/two columns reasonably.
- Wide tables require horizontal scroll.
- Drawers use full width and can obscure context.

### Mobile

- Minimum body width is 320px, but the experience is not designed around mobile
  tasks.
- Long navigation comes before every page.
- Horizontal tables separate candidate/employee identity from actions.
- Dense filter controls and saved-view chips create long setup sections.
- Full-height profile drawers contain many nested sections.
- Several action rows wrap, but wrapped buttons do not create a clear mobile
  priority order.

### RTL

**Observed facts:**

- Overview, Jobs, Candidates, Interviews, selected drawers, and Arabic job
  fields set `dir=rtl`.
- Post-hire has no locale/RTL implementation.
- The sidebar and global page chrome remain English/LTR.
- Drawers use `ml-auto` and `border-l`.
- many tables use `text-left`;
- many menus use `right-0`;
- lists use physical `pl-*`;
- the drawer animation translates from the right.

**Expert judgment:** Setting `dir=rtl` on a container is not sufficient. Visual
order, drawer edge, icon direction, table alignment, date/number formatting,
breadcrumbs, action placement, and navigation must all be mirrored or
localized.

---

## 10. What is already good and should be preserved

1. **Module-aware visibility.** Disabled modules are generally hidden rather
   than left as broken destinations.
2. **Candidate actions are server-authoritative.** `allowed_actions` protects
   workflow actions instead of relying only on frontend role assumptions.
3. **Dangerous actions are confirmed.** Hiring, rejecting, role changes,
   deactivation, exports, and external sends receive deliberate confirmation.
4. **The overview is action-oriented.** It tries to direct HR to the next useful
   task rather than showing vanity metrics alone.
5. **One Candidates destination is the right discoverability goal.**
6. **Scheduled and video interviews remain distinct but share one Interviews
   area.**
7. **AI is often labelled advisory.** Missing evidence and human decision
   responsibility are visible.
8. **Post-hire error sanitization is thoughtful.** Raw codes and technical
   messages are mapped to calmer copy.
9. **Empty states often explain the next step.**
10. **Permissions affect actions and audit visibility.**
11. **Bilingual job content is modeled explicitly.**
12. **Employee directory is relatively restrained and understandable.**
13. **Leave has a coherent pending/upcoming/history model.**
14. **Reports clearly state that daily work belongs elsewhere.**
15. **Employee App is correctly excluded from normal HR navigation.**

---

## 11. Questions requiring product-owner decisions

1. Is the primary recruiting record a person or an application?
2. Should “Talent Pool” be visible product terminology, or only an internal
   capability?
3. What is the canonical HR term for a candidate with no assigned job in
   English and Arabic?
4. Is AI “Expertise” a suggestion, an HR-confirmed category, or both?
5. Which five facts must a recruiter see before opening a candidate?
6. Should Ranking be a top-level work area, a Jobs view, or a Candidates view?
7. Should Intake Operations be visible to recruiters, admins only, or platform
   support only?
8. Does the product need one universal action center or separate domain alerts?
9. Are scheduled and video interviews one operational team’s responsibility?
10. Does Wathefni calculate payroll or prepare data for payroll?
11. Is Compliance intended to grow beyond document expiry?
12. Should Hiring Reports and Workforce Analytics become one Insights mental
    model?
13. Should language be a user preference, a company default, or both?
14. Which Arabic dialect/register should the product use: formal MSA, GCC
    business Arabic, or configurable terminology?
15. Should hiring managers receive the same navigation as recruiters with fewer
    actions, or a manager-focused workspace?
16. Should a two-module company use the same suite shell or a compact workspace?
17. Which technical/governance details are appropriate for HR admins versus
    platform support?
18. What is the intended mobile use: full operations, approvals only, or
    read-only triage?
19. Is Wathefni Assistant a destination, a global command surface, or contextual
    help?
20. Should Team Access and Integrations remain inside Settings or become
    explicit admin subsections?

---

## 12. Recommended priorities — no implementation yet

These are product priorities for decision and validation, not implementation
waves.

### Priority 1 — Define the product’s core objects and vocabulary

Decide candidate versus application hierarchy, no-job candidate terminology,
stage/state vocabulary, communication vocabulary, and the English/Arabic
glossary.

### Priority 2 — Reduce daily recruiter cognitive load

Identify the minimum default candidate list, the single primary state/next
action, and which specialist evidence belongs only in the profile.

### Priority 3 — Resolve navigation mental model

Choose whether the product optimizes for objects, lifecycle, roles, or compact
hubs. Validate with recruiters, HR operations, hiring managers, and
partial-module companies.

### Priority 4 — Make Arabic a whole-workspace requirement

Treat translation, RTL, font, dates, numbers, drawer direction, navigation, and
terminology as one product requirement.

### Priority 5 — Separate normal HR work from technical operations

Decide the audience for Intake Operations, assessment calibration/authoring,
candidate provenance/governance, recovery credentials, and integration details.

### Priority 6 — Establish responsive product scope

Decide which tasks must be genuinely usable on mobile and tablet. Do not assume
horizontal scrolling is an acceptable completion state.

### Priority 7 — Consolidate overlapping queues

Map every candidate/employee subset shown in Overview, Candidates, Ranking,
Assessments, Interviews, Alerts, Onboarding, Compliance, and Reports. Decide
which are destinations, saved views, profile sections, or exception queues.

### Priority 8 — Clarify role experiences

Define the intended workspace for recruiter, hiring manager, HR manager,
payroll/compliance specialist, and owner—not only their permission list.

### Priority 9 — Simplify visual hierarchy

Reserve cards, metrics, badges, borders, and accent color for distinct semantic
roles. Reduce decorative repetition before introducing a new visual direction.

### Priority 10 — Validate with real GCC HR tasks

Test at minimum:

- review a new Arabic CV received by WhatsApp;
- find a general candidate for a new opening;
- compare applicants for one job;
- schedule and complete an interview;
- approve a leave request as a manager;
- identify an expiring Civil ID;
- resolve a failed candidate message;
- use a two-module workspace;
- complete an approval on tablet/mobile;
- switch the entire workspace to Arabic.

---

## Final audit conclusion

**Expert judgment:** Wathefni has a credible functional foundation and several
good safety patterns, but the normal HR workspace is not yet a simple,
coherent, bilingual HR product. Its largest problem is not visual polish. It is
product editing: too many internal states, too many parallel work surfaces, and
too much backend truth presented without a clear hierarchy for the human task.

The next product discussion should begin with objects, terminology, user roles,
and task priorities—not with new screens or a cosmetic redesign.
