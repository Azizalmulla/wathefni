# Workflow Execution Backbone

Wathefni uses the AI for conversation and decisions, and the workflow worker for slow or retryable execution.

## Core Tables

- `workflow_runs`: one business operation, such as hiring one candidate or sending an assessment batch.
- `workflow_steps`: auditable phases inside a run.
- `job_queue`: executable jobs claimed by workers with `FOR UPDATE SKIP LOCKED`.
- `outbox_events`: reliable outbound sends, including WhatsApp confirmations.

## Worker

Run once:

```bash
python -m app.worker --once
```

Run continuously:

```bash
python -m app.worker
```

Multiple workers can run at the same time. Postgres row locks prevent two workers from claiming the same job.

## First Workflow

`hire_candidate` is the first workflow wired into the HR engine. When HR asks to mark a candidate as hired, the app enqueues a background workflow instead of doing every slow step inside the chat turn.

The `initialize_post_hire` step creates or updates the employee record, default onboarding checklist, employee document records, and compliance document records. It is idempotent, so retries do not duplicate post-hire rows.

After post-hire records are initialized, the workflow runs:

- `sync_employee_sheet`: updates or appends the `Employees` tab by `Employee Key`.
- `sync_compliance_sheet`: updates or appends the `Compliance` tab by employee phone and document type.

When the hire workflow completes, it confirms setup to HR and asks whether to start onboarding. Employee onboarding is HR-confirmed by default. A later HR reply like `yes`, `go ahead`, or `start onboarding for Fouad` enqueues `start_onboarding`, sends the employee onboarding message, marks onboarding as started, completes the welcome checklist item, and resyncs the employee sheet.

After onboarding starts, employee replies are conversational. The webhook routes employee phone numbers to the post-hire handler before candidate handling. The handler detects Civil ID, passport, work permit, bank details, and employment contract from text, captions, filenames, or the next missing document when an image/document has no label. It updates employee document and compliance rows, queues sheet syncs, acknowledges the employee, and notifies HR.

Set these environment variables for sheet sync:

```bash
GOOGLE_SHEET_ID=1zMqYRGj0OSdoYYlMThAEfxoc1DQv-rRfHzpiAronwRM
GOOGLE_ACCOUNT=azizalmulla16@gmail.com
GOG_BIN=gog
EMPLOYEES_SHEET_NAME=Employees
COMPLIANCE_SHEET_NAME=Compliance
```

If `GOOGLE_SHEET_ID` is empty, sheet jobs are skipped instead of failing local development.

## Long-Term Pattern

Use workflows for:

- Bulk hire, shortlist, reject, and onboarding operations.
- Assessment campaigns and scoring.
- Google Sheets, Gmail, Calendar, Drive, and WhatsApp sends.
- Reminders, follow-ups, and compliance expiry alerts.

Keep simple reads inline:

- Candidate status questions.
- Profile summaries.
- Small database lookups.
- Clarifying questions.
