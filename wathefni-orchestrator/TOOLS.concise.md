# TOOLS.md - Wathefni Operational Tool Contract

This is a concise fallback copy. The live OpenClaw workspace TOOLS.md is preferred when available. Keep this file aligned with the same contracts.

## Runtime

- Workspace: `/root/.openclaw/workspaces/company-wathefni`
- Company: `WATHEFNI`, timezone `Asia/Kuwait`
- WhatsApp/apply number: `+96597453460`
- Preferred live prompt doc: `/root/.openclaw/workspaces/company-wathefni/TOOLS.md`
- Fallback copy: `wathefni-orchestrator/TOOLS.concise.md`

## Truth Contract

- Postgres is operational truth for candidates, applications, employees, onboarding, compliance, attendance, shifts, leave, payroll, timesheets, delivery events, pending actions, audit records, and action results.
- Normalized ActionResult is truth for user-visible operational claims. Do not say an action was sent, failed, approved, rejected, synced, completed, or blocked unless ActionResult or stored action history says so.
- Google Sheets is dashboard/export only. It mirrors HR state; it is not the source of truth.
- OpenClaw memory and chat history may help with continuity, but they never override Postgres, ActionResult, audit logs, pending action state, offered follow-up state, or delivery records.
- No operational claims may come from broad LLM fallback.

## Wathefni Orchestrator

- Service: `wathefni-orchestrator.service`
- Health: `GET /health`
- Prompt debug: `GET /orchestrator/debug/prompt-context`
- Turn endpoint: `POST /orchestrator/whatsapp-turn`
- Audit endpoints: `/orchestrator/audit/turns`, `/orchestrator/audit/pending-actions`, `/orchestrator/audit/action-results`

The Wathefni FastAPI orchestrator owns routing, context resolution, state changes, pending confirmations, offered follow-ups, ActionResult storage, and authoritative HR replies. If it returns an authoritative reply, send that reply directly and do not summarize it through a general LLM.

## Routing Priority Contract

1. pending confirmation or clarification
2. explicit operational follow-up, verification, or action-history question
3. offered follow-up acceptance
4. explicit new action request
5. domain-specific analytical request
6. safe general fallback

Do not let stale chat context or broad analytics steal a more specific candidate/action-history route.

## Current Backend-Owned Actions

Communication and pre-hiring:
- `send_email`
- `notify_candidate`
- `send_assessment`
- `schedule_interview`
- `hire_candidate`
- `shortlist_candidate`
- `start_onboarding`
- `retry_last_failed_action`

Grounded read-only pre-hiring:
- `candidate_cv_evaluation`
- `compare_candidates`
- `rank_candidates`
- `check_assessment_config`
- candidate email/detail/status lookups

Workforce and reports:
- `workforce_analytics`
- attendance actions
- leave actions
- shift, availability, and shift-swap actions
- payroll hours, preview, export, and policy actions
- timesheet list/review/approve/reject actions

Conversation reliability:
- action-history follow-ups: `did you send it?`, `what did you send?`, `who did you email?`
- verification follow-ups: `are you sure?`, `did it go through?`
- pending action / pending operation handling
- offered follow-up handling
- pure greeting and small-talk opener handling

## Normalized ActionResult Contract

Every operation should normalize into a result with enough truth for reply rendering:

- `action_type`
- `status`
- `ok`
- `target_type`, `target_id`, `target_name`
- `error_code`
- `safe_user_message`
- `payload`
- exact artifacts when available, such as email subject/body, recipient, message ID, Meet link, dashboard sync status, or delivery result

Replies must be derived from this normalized result or stored action history, not from model assumptions.

## Reply Behavior

- Mutation actions require strict success/failure consistency with ActionResult.
- Read-only analytical actions may be naturally phrased from grounded payloads, but must preserve evidence, missing-data caveats, and recommendations.
- Do not flatten CV evaluation, comparison, ranking, analytics, or reports into generic success lines.
- Avoid generic backend phrases such as `completed successfully for the target`.
- If the action failed, explain the safe blocker without exposing stack traces, paths, raw auth errors, or internal implementation details.
- If no action history exists for `did you send it?`, say so plainly and do not resend.
- Safe fallback may ask for a narrow clarification or say the answer must come from Wathefni stored records. It must not invent operational truth.

## External Systems

- Gmail and Calendar use `gog`; do not ask HR for sender account.
- Postgres and the dashboard are the single source of truth; there is no Google Sheets mirror.
- Store exact sent email/message content in action history so follow-up questions can answer from backend truth.
