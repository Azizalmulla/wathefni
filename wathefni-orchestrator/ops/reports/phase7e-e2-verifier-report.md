# Phase 7E E2 staging verifier report

- Result: **55/57 passed; 2 failed**
- Recommendation: **not-staging-green**
- Fixture: `P7ESTG01` (+ `P7ESTG02` for isolation)
- Outbound: mocked only; synthetic documents only
- Application remediation: none performed

## Exact case evidence

### PASS — C01a global flag OFF blocks authenticated app context
- Endpoint: `GET /app/me (employee_app_context)`
- Expected: `{"error": "employee_app_disabled", "status_code": 503}`
- Observed: `{"body": {"error": "employee_app_disabled", "message": "The employee app is not available right now."}, "returned": false, "status_code": 503}`

### PASS — C01b global flag OFF blocks activation
- Endpoint: `POST /app/auth/activate`
- Expected: `{"status_code": 503}`
- Observed: `{"body": {"error": "employee_app_disabled", "message": "The employee app is not available right now."}, "returned": false, "status_code": 503}`

### PASS — C02a module OFF blocks an existing session
- Endpoint: `GET /app/me (employee_app_context)`
- Expected: `{"error": "employee_app_not_enabled_for_company", "status_code": 403}`
- Observed: `{"body": {"error": "employee_app_not_enabled_for_company", "message": "The app is not enabled for your company."}, "returned": false, "status_code": 403}`

### PASS — C02b module OFF blocks HR invite
- Endpoint: `POST /dashboard/posthire/employees/{employee_key}/app-invite`
- Expected: `{"status_code": 403}`
- Observed: `{"body": {"error": "employee_app_not_enabled_for_company", "message": "The employee app module is not enabled for your company."}, "returned": false, "status_code": 403}`

### PASS — C03a mocked activation delivery exposes backend-owned delivered outcome
- Endpoint: `POST /dashboard/posthire/employees/{employee_key}/app-invite`
- Expected: `{"attempted": true, "channel": "whatsapp_session", "created": true, "status": "delivered_whatsapp"}`
- Observed: `{"attempted": true, "created": true, "semantic": "delivered", "server_channel": "whatsapp_session", "server_status": "delivered_whatsapp"}`

### PASS — C03b mocked activation delivery exposes backend-owned failed outcome
- Endpoint: `POST /dashboard/posthire/employees/{employee_key}/app-invite`
- Expected: `{"attempted": true, "channel": null, "created": true, "status": "failed"}`
- Observed: `{"attempted": true, "created": true, "semantic": "failed", "server_channel": null, "server_status": "failed"}`

### PASS — C03c mocked activation delivery exposes backend-owned suppressed outcome
- Endpoint: `POST /dashboard/posthire/employees/{employee_key}/app-invite`
- Expected: `{"attempted": true, "channel": null, "created": true, "status": "suppressed"}`
- Observed: `{"attempted": true, "created": true, "semantic": "suppressed", "server_channel": null, "server_status": "suppressed"}`

### PASS — C03d mocked activation delivery exposes backend-owned fallback outcome
- Endpoint: `POST /dashboard/posthire/employees/{employee_key}/app-invite`
- Expected: `{"attempted": true, "channel": "email", "created": true, "status": "sent_email_fallback"}`
- Observed: `{"attempted": true, "created": true, "semantic": "fallback", "server_channel": "email", "server_status": "sent_email_fallback"}`

### PASS — C03e real ladder persists created/attempted/delivered state
- Endpoint: `deliver_app_activation_code → outbound_delivery`
- Expected: `{"attempts": 1, "created_row": true, "status": "delivered_whatsapp", "terminal_event": true}`
- Observed: `{"event": [{"channel": "outbound_layer", "payload": {"attempt_reasons": [], "channel_used": "whatsapp_session", "delivery_status": "delivered_whatsapp", "employee_message_id": "b19faf1d-92a0-4418-b17e-1d275672a77a", "flow": "app_activation", "outbound_layer": true, "recipient_email": "p7e-app-a@synthetic.invalid", "template_key": "app_activation"}, "status": "sent"}], "message": [{"attempt_log": [{"at": "2026-07-12T09:35:13.413039+00:00", "attempt": 1, "channel": "whatsapp_session", "reasons": [], "status": "delivered_whatsapp"}], "attempts": 1, "channel_used": "whatsapp_session", "message_id": "b19faf1d-92a0-4418-b17e-1d275672a77a", "status": "delivered_whatsapp"}], "provider_calls": {"emai…`

### PASS — C03f real ladder records fallback as later-rung success plus reason trail
- Endpoint: `deliver_app_activation_code → outbound_delivery`
- Expected: `{"channel": "email", "prior_rung_reason": true, "status": "sent_email_fallback"}`
- Observed: `{"message": [{"attempt_log": [{"at": "2026-07-12T09:35:13.421709+00:00", "attempt": 1, "channel": "email", "reasons": ["session:conversation_closed", "template:template_unmapped"], "status": "sent_email_fallback"}], "attempts": 1, "channel_used": "email", "status": "sent_email_fallback"}], "provider_calls": {"email": 1, "session": 1, "template": 1}, "result": {"channel": "email", "delivery_status": "sent_email_fallback", "hr_task_id": null, "ok": true}}`

### PASS — C03g real ladder all-failed activation creates visible HR task
- Endpoint: `deliver_app_activation_code → outbound_delivery`
- Expected: `{"hr_task": "open", "status": "needs_hr_action"}`
- Observed: `{"hr_task_count": 1, "message": [{"attempt_log": [{"at": "2026-07-12T09:35:13.429164+00:00", "attempt": 1, "channel": null, "reasons": ["session:conversation_closed", "template:template_unmapped", "email:synthetic_email_failure"], "status": "needs_hr_action"}], "attempts": 1, "channel_used": null, "hr_task_id": "34be8500-9761-4ac3-9fe8-6cc3eb8e7988", "status": "needs_hr_action"}], "result": {"channel": null, "delivery_status": "needs_hr_action", "hr_task_id": "34be8500-9761-4ac3-9fe8-6cc3eb8e7988", "ok": false}}`

### PASS — C03h real ladder persists suppressed without provider calls or HR task
- Endpoint: `deliver_app_activation_code → outbound_delivery`
- Expected: `{"hr_task": null, "provider_calls": 0, "status": "suppressed"}`
- Observed: `{"message": [{"attempt_log": [{"at": "2026-07-12T09:35:13.439598+00:00", "attempt": 1, "channel": null, "reasons": ["push:suppressed_opt_out", "session:suppressed_opt_out", "template:suppressed_opt_out", "email:suppressed_opt_out"], "status": "suppressed"}], "attempts": 1, "channel_used": null, "hr_task_id": null, "status": "suppressed"}], "provider_calls": {"email": 0, "session": 0, "template": 0}, "result": {"channel": null, "delivery_status": "suppressed", "hr_task_id": null, "ok": false}}`

### PASS — C04a valid single-use invite activates the intended employee
- Endpoint: `POST /app/auth/activate`
- Expected: `{"employee_key": "p7e-app-a", "session": true, "status_code": 200}`
- Observed: `{"body": {"employee": {"company_code": "P7ESTG01", "department": "", "email": "p7e-app-a@synthetic.invalid", "employee_key": "p7e-app-a", "locale": "en", "name": "Synthetic Employee A", "onboarding_status": "in_progress", "phone": "96555557801", "position_title": ""}, "expires_at": "2026-07-19T09:35:13.452170+00:00", "ok": true, "refresh_token": "[redacted]", "token": "[redacted]"}, "returned": true, "status_code": 200}`

### PASS — C04b authenticated identity is self-scoped
- Endpoint: `GET /app/me`
- Expected: `{"company_code": "P7ESTG01", "employee_key": "p7e-app-a"}`
- Observed: `{"body": {"company_code": "P7ESTG01", "department": "", "email": "p7e-app-a@synthetic.invalid", "employee_key": "p7e-app-a", "enabled_modules": ["employee_app", "leave", "onboarding"], "leave_balances_enabled": false, "locale": "en", "name": "Synthetic Employee A", "ok": true, "onboarding_status": "in_progress", "phone": "96555557801", "position_title": ""}, "returned": true, "status_code": 200}`

### PASS — C05a superseded invite is rejected
- Endpoint: `POST /app/auth/activate`
- Expected: `{"status_code": 401}`
- Observed: `{"body": {"error": "app_activation_failed", "message": "That code didn't work. Ask your HR team for a new one."}, "returned": false, "status_code": 401}`

### PASS — C05b repeated invalid activation attempts trigger abuse protection
- Endpoint: `POST /app/auth/activate`
- Expected: `{"after_limit": 429, "first_invalid": 401, "max_attempts": 5}`
- Observed: `{"invalid_statuses": [401, 401, 401, 401, 401], "locked": {"body": {"error": "too_many_attempts", "message": "Too many attempts. Ask your HR team for a new code."}, "returned": false, "status_code": 429}}`

### PASS — C05c redeemed invite cannot be reused
- Endpoint: `POST /app/auth/activate`
- Expected: `{"first": 200, "second": 401}`
- Observed: `{"first": {"body": {"employee": {"company_code": "P7ESTG01", "department": "", "email": "p7e-app-b@synthetic.invalid", "employee_key": "p7e-app-b", "locale": "en", "name": "Synthetic Employee B", "onboarding_status": "in_progress", "phone": "96555557802", "position_title": ""}, "expires_at": "2026-07-19T09:35:13.580922+00:00", "ok": true, "refresh_token": "[redacted]", "token": "[redacted]"}, "returned": true, "status_code": 200}, "second": {"body": {"error": "app_activation_failed", "message": "That code didn't work. Ask your HR team for a new one."}, "returned": false, "status_code": 401}}`

### PASS — C05d expired invite is rejected
- Endpoint: `POST /app/auth/activate`
- Expected: `{"status_code": 401}`
- Observed: `{"body": {"error": "app_activation_failed", "message": "That code didn't work. Ask your HR team for a new one."}, "returned": false, "status_code": 401}`

### PASS — C05d2 explicitly revoked invite is rejected
- Endpoint: `POST /app/auth/activate`
- Expected: `{"status_code": 401}`
- Observed: `{"body": {"error": "app_activation_failed", "message": "That code didn't work. Ask your HR team for a new one."}, "returned": false, "status_code": 401}`

### PASS — C05e invite employee_key/phone mismatch cannot activate the wrong employee
- Endpoint: `POST /app/auth/activate`
- Expected: `{"new_sessions_for_wrong_employee": 0, "status_code": 401}`
- Observed: `{"response": {"body": {"error": "app_activation_failed", "message": "That code didn't work. Ask your HR team for a new one."}, "returned": false, "status_code": 401}, "sessions_after": 0, "sessions_before": 0}`

### PASS — C05f cross-company invite cannot activate an employee
- Endpoint: `POST /app/auth/activate`
- Expected: `{"status_code": 401}`
- Observed: `{"body": {"error": "app_activation_failed", "message": "That code didn't work. Ask your HR team for a new one."}, "returned": false, "status_code": 401}`

### PASS — C05g disabled company blocks invite and activation
- Endpoint: `POST /dashboard/.../app-invite + POST /app/auth/activate`
- Expected: `{"activation_denied": true, "invite_denied": true}`
- Observed: `{"activation": {"reason": "invite correctly denied", "skipped": true}, "invite": {"body": {"company_code": "P7ESTG01", "company_status": "disabled", "error": "company_disabled", "message": "This company workspace is not active. Contact the Wathefni platform operator."}, "returned": false, "status_code": 403}}`

### PASS — C05h archived company blocks invite and activation
- Endpoint: `POST /dashboard/.../app-invite + POST /app/auth/activate`
- Expected: `{"activation_denied": true, "invite_denied": true}`
- Observed: `{"activation": {"reason": "invite correctly denied", "skipped": true}, "invite": {"body": {"company_code": "P7ESTG01", "company_status": "archived", "error": "company_archived", "message": "This company workspace is not active. Contact the Wathefni platform operator."}, "returned": false, "status_code": 403}}`

### PASS — C05i already-activated employee does not receive an additional privileged session
- Endpoint: `POST /app/auth/activate`
- Expected: `{"active_session_count_growth": 0, "rejected_or_idempotent": true}`
- Observed: `{"response": {"body": {"error": "already_activated", "message": "This employee app account is already activated. Sign in or use account recovery."}, "returned": false, "status_code": 409}, "sessions_after": 1, "sessions_before": 1}`

### PASS — C06a unseeded employee does not crash, invent items, or appear completed
- Endpoint: `GET /app/onboarding`
- Expected: `{"items": [], "required_total": 0, "status_not_complete": true}`
- Observed: `{"body": {"can_upload": true, "next_item": null, "ok": true, "pending": [], "pending_count": 0, "received": [], "received_count": 0, "required_total": 0, "status": "in_progress"}, "returned": true, "status_code": 200}`

### PASS — C06b Option A exposes exactly four manually provisioned canonical items
- Endpoint: `GET /app/onboarding`
- Expected: `{"onboarding_seed": false, "pending_item_ids": ["bank_details", "civil_id", "employment_contract", "personal_photo"]}`
- Observed: `{"response": {"body": {"can_upload": true, "next_item": {"document_type": "civil_id", "item_id": "civil_id", "item_type": "document", "label": "Civil ID", "status": "pending"}, "ok": true, "pending": [{"document_type": "civil_id", "drive_url": null, "escalated_at": null, "file_id": null, "item_id": "civil_id", "item_type": "document", "label": "Civil ID", "last_reminded_at": null, "reminder_count": 0, "required": true, "status": "pending", "storage_provider": null, "storage_status": null, "storage_url": null, "updated_at": "2026-07-12T09:35:13.717835+00:00", "value": null}, {"document_type": "personal_photo", "drive_url": null, "escalated_at": null, "file_id": null, "item_id": "personal_phot…`

### PASS — C07a valid synthetic upload creates canonical Document Hub linkage
- Endpoint: `POST /app/onboarding/documents`
- Expected: `{"employee_documents": true, "file_registry": true, "onboarding_item": "received"}`
- Observed: `{"canonical": {"employee_documents": [{"company_code": "P7ESTG01", "document_type": "civil_id", "employee_key": "p7e-app-a", "item_id": "civil_id", "metadata": {"item_id": "civil_id", "label": "Civil ID", "received_at": "2026-07-12T09:35:13Z", "storage": {"content_sha256": "761955553e6b9cf0f8926d05ddc9e56e775d8ac48146c51453f2bc7e4b42db4a", "drive_file_id": null, "drive_url": null, "external_file_id": null, "metadata": {"company_code": "P7ESTG01", "local_path": "/opt/wathefni/staging/workspace/data/companies/P7ESTG01/employees/96555557801/documents/civil_id/civil_id-761955553e6b.pdf"}, "mime_type": "application/pdf", "ok": true, "provider": "local", "storage_object_key": "data/companies/P7EST…`

### PASS — C07b successful upload is auditable
- Endpoint: `POST /app/onboarding/documents`
- Expected: `{"action_type": "employee_document_uploaded", "status": "completed"}`
- Observed: `[{"action_type": "employee_document_uploaded", "actor_user_id": "employee_app:p7e-app-a", "company_code": "P7ESTG01", "status": "completed"}]`

### PASS — C07c cross-employee item upload is denied
- Endpoint: `POST /app/onboarding/documents`
- Expected: `{"status_code": 404}`
- Observed: `{"body": {"error": "item_not_found", "message": "We couldn't find that document on your checklist."}, "returned": false, "status_code": 404}`

### PASS — C07d cross-tenant item upload is denied
- Endpoint: `POST /app/onboarding/documents`
- Expected: `{"status_code": 404}`
- Observed: `{"body": {"error": "item_not_found", "message": "We couldn't find that document on your checklist."}, "returned": false, "status_code": 404}`

### PASS — C07e cross-tenant document read is denied
- Endpoint: `GET /app/documents/{file_id}`
- Expected: `{"status_code": 404}`
- Observed: `{"body": {"error": "document_not_found", "message": "We couldn't find that document."}, "returned": false, "status_code": 404}`

### PASS — C07f cross-employee document read is denied
- Endpoint: `GET /app/documents/{file_id}`
- Expected: `{"status_code": 404}`
- Observed: `{"body": {"error": "document_not_found", "message": "We couldn't find that document."}, "returned": false, "status_code": 404}`

### PASS — C07g server rejects disallowed extension
- Endpoint: `POST /app/onboarding/documents`
- Expected: `{"error": "unsupported_file_type", "status_code": 400}`
- Observed: `{"body": {"error": "unsupported_file_type", "message": "Upload a PDF or an image."}, "returned": false, "status_code": 400}`

### PASS — C07h server rejects file over 15 MiB cap
- Endpoint: `POST /app/onboarding/documents`
- Expected: `{"error": "file_too_large", "status_code": 400}`
- Observed: `{"body": {"error": "file_too_large", "message": "Files must be 15 MB or smaller."}, "returned": false, "status_code": 400}`

### PASS — C07i server rejects extension/MIME mismatch
- Endpoint: `POST /app/onboarding/documents`
- Expected: `{"error": "mime_mismatch_or_invalid_content", "status_code": "400/415"}`
- Observed: `{"body": {"error": "mime_mismatch_or_invalid_content", "message": "The file content does not match an allowed PDF or image type."}, "returned": false, "status_code": 415}`

### PASS — C07j failed storage does not create canonical rows or mark item received
- Endpoint: `POST /app/onboarding/documents`
- Expected: `{"database_state_unchanged": true, "status_code": 502}`
- Observed: `{"after": {"docs": 0, "files": 0, "status": "pending"}, "before": {"docs": 0, "files": 0, "status": "pending"}, "response": {"body": {"error": "storage_failed", "message": "We couldn't store that document. Please try again."}, "returned": false, "status_code": 502}}`

### FAIL — C07k DB failure after successful storage leaves no permanent orphan
- Endpoint: `POST /app/onboarding/documents`
- Expected: `{"database_state_unchanged": true, "permanent_orphans": [], "request_failed": true}`
- Observed: `{"database_after": {"docs": 0, "files": 0, "status": "pending"}, "database_before": {"docs": 0, "files": 0, "status": "pending"}, "permanent_orphans": ["/opt/wathefni/staging/workspace/data/companies/P7ESTG01/employees/96555557801/documents/employment_contract/employment_contract-1564384d80b7.pdf"], "response": {"body": "synthetic_db_failure_after_storage", "exception": "RuntimeError", "returned": false, "status_code": 500}}`

### FAIL — C07l rejected employee upload is auditable
- Endpoint: `POST /app/onboarding/documents`
- Expected: `{"rejection_audit_growth": 1, "request_denied": true}`
- Observed: `{"audit_after": 0, "audit_before": 0, "response": {"body": {"error": "unsupported_file_type", "message": "Upload a PDF or an image."}, "returned": false, "status_code": 400}}`

### PASS — C08 leave request/cancel remains employee-owned
- Endpoint: `POST /app/leave/request + POST /app/leave/{id}/cancel`
- Expected: `{"create": 200, "cross_employee_cancel": 404, "own_cancel": 200}`
- Observed: `{"create": {"body": {"leave": {"company_code": "P7ESTG01", "created_at": "2026-07-12T09:35:13.895138+00:00", "decided_at": null, "decided_by_phone": null, "decision_note": null, "employee_key": "p7e-app-a", "employee_name": "Synthetic Employee A", "employee_phone": "96555557801", "end_date": "2099-01-12", "leave_id": "df0aa128-ac39-40b7-9f51-15c7aba65ee3", "leave_type": "annual", "metadata": {"action": {"end_date": "2099-01-12", "leave_type": "annual", "reason": null, "start_date": "2099-01-10", "subject_phone": "96555557801"}, "shift_conflicts": [], "source": "whatsapp"}, "reason": null, "requested_at": "2026-07-12T09:35:13.895138+00:00", "requested_by_phone": "96555557801", "source_text": …`

### PASS — C09 inbox exposes backend-owned status without push
- Endpoint: `GET /app/notifications + POST /app/notifications/{id}/read`
- Expected: `{"push_enabled": false, "read_marked": true, "server_status": "pending"}`
- Observed: `{"item": {"body": "Synthetic onboarding reminder", "created_at": "2026-07-12T09:35:13.909991+00:00", "flow": "onboarding", "id": "7158e86a-927c-4d75-ab0c-19f89709512b", "read": false, "status": "pending", "title": "Onboarding reminder"}, "mark": {"body": {"ok": true}, "returned": true, "status_code": 200}, "push_enabled": false}`

### PASS — C10a global flag OFF blocks a previously valid bearer
- Endpoint: `GET /app/me (employee_app_context)`
- Expected: `{"status_code": 503}`
- Observed: `{"body": {"error": "employee_app_disabled", "message": "The employee app is not available right now."}, "returned": false, "status_code": 503}`

### PASS — C10a2 global flag OFF blocks refresh
- Endpoint: `POST /app/auth/refresh`
- Expected: `{"status_code": 503}`
- Observed: `{"body": {"error": "employee_app_disabled", "message": "The employee app is not available right now."}, "returned": false, "status_code": 503}`

### PASS — C10b company module removal blocks a previously valid bearer
- Endpoint: `GET /app/me (employee_app_context)`
- Expected: `{"status_code": 403}`
- Observed: `{"body": {"error": "employee_app_not_enabled_for_company", "message": "The app is not enabled for your company."}, "returned": false, "status_code": 403}`

### PASS — C10c company module removal blocks refresh
- Endpoint: `POST /app/auth/refresh`
- Expected: `{"status_code": "401/403"}`
- Observed: `{"body": {"error": "app_auth_failed", "message": "Please sign in again."}, "returned": false, "status_code": 401}`

### PASS — C10d company disabled blocks subsequent authenticated API access
- Endpoint: `GET /app/me (employee_app_context)`
- Expected: `{"company_status": "disabled", "status_code": "401/403"}`
- Observed: `{"body": {"error": "company_disabled", "message": "Your company workspace is not active."}, "returned": false, "status_code": 403}`

### PASS — C10d2 company disabled blocks refresh
- Endpoint: `POST /app/auth/refresh`
- Expected: `{"company_status": "disabled", "status_code": "401/403"}`
- Observed: `{"body": {"error": "app_auth_failed", "message": "Please sign in again."}, "returned": false, "status_code": 401}`

### PASS — C10e company archived blocks subsequent authenticated API access
- Endpoint: `GET /app/me (employee_app_context)`
- Expected: `{"company_status": "archived", "status_code": "401/403"}`
- Observed: `{"body": {"error": "company_archived", "message": "Your company workspace is not active."}, "returned": false, "status_code": 403}`

### PASS — C10e2 company archived blocks refresh
- Endpoint: `POST /app/auth/refresh`
- Expected: `{"company_status": "archived", "status_code": "401/403"}`
- Observed: `{"body": {"error": "app_auth_failed", "message": "Please sign in again."}, "returned": false, "status_code": 401}`

### PASS — C10f per-employee revoke blocks subsequent authenticated API access
- Endpoint: `GET /app/me (employee_app_context)`
- Expected: `{"status_code": "401/403"}`
- Observed: `{"body": {"error": "app_auth_failed", "message": "Please sign in again."}, "returned": false, "status_code": 401}`

### PASS — C10f2 per-employee revoke blocks refresh
- Endpoint: `POST /app/auth/refresh`
- Expected: `{"status_code": "401/403"}`
- Observed: `{"body": {"error": "app_auth_failed", "message": "Please sign in again."}, "returned": false, "status_code": 401}`

### PASS — C10g revoked employee cannot download a previously owned document
- Endpoint: `GET /app/documents/{file_id}`
- Expected: `{"status_code": "401/403"}`
- Observed: `{"body": {"error": "app_auth_failed", "message": "Please sign in again."}, "returned": false, "status_code": 401}`

### PASS — C10h rollback does not require company channel routing or live delivery
- Endpoint: `shared send helper (dry-run)`
- Expected: `{"company_route": false, "dry_run": true, "shared_account": "default"}`
- Observed: `{"account_id": "default", "dry_run": true, "ok": true, "phone": "96555557801", "simulated": true, "status": 200}`

### PASS — C11a production protected flags remained OFF
- Endpoint: `systemd wathefni-orchestrator.service`
- Expected: `{"WATHEFNI_COMPANY_CHANNEL_ACCOUNTS": "off/unset", "WATHEFNI_EMPLOYEE_APP": "off/unset", "WATHEFNI_ONBOARDING_SEED": "off/unset"}`
- Observed: `{"WATHEFNI_COMPANY_CHANNEL_ACCOUNTS": "off", "WATHEFNI_EMPLOYEE_APP": "off", "WATHEFNI_ONBOARDING_SEED": "off"}`

### PASS — C11b staging systemd protected flags remained OFF
- Endpoint: `systemd wathefni-orchestrator-staging.service`
- Expected: `{"WATHEFNI_COMPANY_CHANNEL_ACCOUNTS": "off/unset", "WATHEFNI_EMPLOYEE_APP": "off/unset", "WATHEFNI_ONBOARDING_SEED": "off/unset"}`
- Observed: `{"WATHEFNI_COMPANY_CHANNEL_ACCOUNTS": "off", "WATHEFNI_EMPLOYEE_APP": "off", "WATHEFNI_ONBOARDING_SEED": "off"}`

### PASS — C11c production WATHEFNI data snapshot remained unchanged
- Endpoint: `production DB read-only fingerprint`
- Expected: `{"before": "df7c817b569012e99244222451f1d0fe024a61f943212fc830a6b797a9f5f663", "unchanged": true}`
- Observed: `{"after": "df7c817b569012e99244222451f1d0fe024a61f943212fc830a6b797a9f5f663", "unchanged": true}`

### PASS — C11d staging WATHEFNI protected tenant remained unchanged
- Endpoint: `staging DB protected-tenant fingerprint`
- Expected: `{"before": "053af662b49776d2896bbd125cbcfed05319e64a4dac0f28696328ec2e5c1445", "unchanged": true}`
- Observed: `{"after": "053af662b49776d2896bbd125cbcfed05319e64a4dac0f28696328ec2e5c1445", "unchanged": true}`

### PASS — C11e throwaway staging fixtures were removed after evidence capture
- Endpoint: `staging DB cleanup`
- Expected: `{"remaining_fixture_companies": 0}`
- Observed: `{"remaining_fixture_companies": 0}`

## Blockers

### C07k — DB failure after successful storage leaves no permanent orphan
- Endpoint: `POST /app/onboarding/documents`
- Observed: `{"database_after": {"docs": 0, "files": 0, "status": "pending"}, "database_before": {"docs": 0, "files": 0, "status": "pending"}, "permanent_orphans": ["/opt/wathefni/staging/workspace/data/companies/P7ESTG01/employees/96555557801/documents/employment_contract/employment_contract-1564384d80b7.pdf"], "response": {"body": "synthetic_db_failure_after_storage", "exception": "RuntimeError", "returned": false, "status_code": 500}}`
- Expected: `{"database_state_unchanged": true, "permanent_orphans": [], "request_failed": true}`
- Smallest durable remediation: Add compensating deletion for the stored local/Drive object when the post-storage database transaction fails, or make storage finalization transactional.

### C07l — rejected employee upload is auditable
- Endpoint: `POST /app/onboarding/documents`
- Observed: `{"audit_after": 0, "audit_before": 0, "response": {"body": {"error": "unsupported_file_type", "message": "Upload a PDF or an image."}, "returned": false, "status_code": 400}}`
- Expected: `{"rejection_audit_growth": 1, "request_denied": true}`
- Smallest durable remediation: Write an HR-safe, company/employee-scoped audit event for rejected upload attempts without recording document bytes or secrets.

## Rollback evidence

- **PASS** C01a — global flag OFF blocks authenticated app context: `{"body": {"error": "employee_app_disabled", "message": "The employee app is not available right now."}, "returned": false, "status_code": 503}`
- **PASS** C01b — global flag OFF blocks activation: `{"body": {"error": "employee_app_disabled", "message": "The employee app is not available right now."}, "returned": false, "status_code": 503}`
- **PASS** C02a — module OFF blocks an existing session: `{"body": {"error": "employee_app_not_enabled_for_company", "message": "The app is not enabled for your company."}, "returned": false, "status_code": 403}`
- **PASS** C10a — global flag OFF blocks a previously valid bearer: `{"body": {"error": "employee_app_disabled", "message": "The employee app is not available right now."}, "returned": false, "status_code": 503}`
- **PASS** C10a2 — global flag OFF blocks refresh: `{"body": {"error": "employee_app_disabled", "message": "The employee app is not available right now."}, "returned": false, "status_code": 503}`
- **PASS** C10b — company module removal blocks a previously valid bearer: `{"body": {"error": "employee_app_not_enabled_for_company", "message": "The app is not enabled for your company."}, "returned": false, "status_code": 403}`
- **PASS** C10c — company module removal blocks refresh: `{"body": {"error": "app_auth_failed", "message": "Please sign in again."}, "returned": false, "status_code": 401}`
- **PASS** C10d — company disabled blocks subsequent authenticated API access: `{"body": {"error": "company_disabled", "message": "Your company workspace is not active."}, "returned": false, "status_code": 403}`
- **PASS** C10d2 — company disabled blocks refresh: `{"body": {"error": "app_auth_failed", "message": "Please sign in again."}, "returned": false, "status_code": 401}`
- **PASS** C10e — company archived blocks subsequent authenticated API access: `{"body": {"error": "company_archived", "message": "Your company workspace is not active."}, "returned": false, "status_code": 403}`
- **PASS** C10e2 — company archived blocks refresh: `{"body": {"error": "app_auth_failed", "message": "Please sign in again."}, "returned": false, "status_code": 401}`
- **PASS** C10f — per-employee revoke blocks subsequent authenticated API access: `{"body": {"error": "app_auth_failed", "message": "Please sign in again."}, "returned": false, "status_code": 401}`
- **PASS** C10f2 — per-employee revoke blocks refresh: `{"body": {"error": "app_auth_failed", "message": "Please sign in again."}, "returned": false, "status_code": 401}`
- **PASS** C10g — revoked employee cannot download a previously owned document: `{"body": {"error": "app_auth_failed", "message": "Please sign in again."}, "returned": false, "status_code": 401}`
- **PASS** C10h — rollback does not require company channel routing or live delivery: `{"account_id": "default", "dry_run": true, "ok": true, "phone": "96555557801", "simulated": true, "status": 200}`
- **PASS** C11a — production protected flags remained OFF: `{"WATHEFNI_COMPANY_CHANNEL_ACCOUNTS": "off", "WATHEFNI_EMPLOYEE_APP": "off", "WATHEFNI_ONBOARDING_SEED": "off"}`
- **PASS** C11b — staging systemd protected flags remained OFF: `{"WATHEFNI_COMPANY_CHANNEL_ACCOUNTS": "off", "WATHEFNI_EMPLOYEE_APP": "off", "WATHEFNI_ONBOARDING_SEED": "off"}`
- **PASS** C11e — throwaway staging fixtures were removed after evidence capture: `{"remaining_fixture_companies": 0}`

## Production protection

- Flags before: `{"WATHEFNI_COMPANY_CHANNEL_ACCOUNTS": "off", "WATHEFNI_EMPLOYEE_APP": "off", "WATHEFNI_ONBOARDING_SEED": "off"}`
- Flags after: `{"WATHEFNI_COMPANY_CHANNEL_ACCOUNTS": "off", "WATHEFNI_EMPLOYEE_APP": "off", "WATHEFNI_ONBOARDING_SEED": "off"}`
- Production snapshot unchanged: `True`
- Staging protected-company snapshot unchanged: `True`

