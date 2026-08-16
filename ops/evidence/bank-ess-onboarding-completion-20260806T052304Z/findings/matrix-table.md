## bank_ess

| case | verdict | detail |
|---|---|---|
| `employee_view_status_no_bank` | proven | `{"code": 200, "state": "none"}` |
| `next_step_present_when_empty` | proven | `"Add your bank details so salary can be paid to you."` |
| `draft_save` | proven | `{"code": 200, "state": "draft"}` |
| `masking_default_employee` | proven | `{"leaked": false}` |
| `proposal_sealed_at_rest` | proven | `{"sealed": true, "leaked": false}` |
| `duplicate_submit_protection` | proven | `{"code": 409, "error": "bank_request_already_active"}` |
| `retry_idempotency_create` | proven | `{"code": 200, "idempotent": true}` |
| `submit_draft_for_review` | proven | `{"code": 200, "state": "pending_review"}` |
| `change_under_review_flag` | proven | `null` |
| `unauthorized_employee_isolation` | proven | `{"code": 200, "leaked": false, "other_request_id": null, "draft_id_present": true}` |
| `unauthorized_employee_cannot_withdraw` | proven | `{"code": 403, "error": "not_request_owner"}` |
| `hr_review_compare_current_vs_proposed` | proven | `{"code": 200, "changed_fields": ["account_holder", "bank_name", "iban"], "first": true}` |
| `hr_view_masked_by_default` | proven | `{"leaked": false}` |
| `hr_sees_evidence_list` | proven | `null` |
| `hr_reject_requires_reason` | proven | `{"code": 422, "error": "decision_reason_required"}` |
| `hr_reject_with_reason` | proven | `{"state": "rejected", "reason": "QUAL: account holder name does not match your civil ID."}` |
| `employee_sees_rejection_next_step` | proven | `{"owner": "employee", "message": "Your submission was rejected. Review the reason, correct it and resubmit.", "message_en": "Your submission was rejected. Revie` |
| `can_resubmit_after_reject` | proven | `null` |
| `employee_correction_and_resubmit` | proven | `{"code": 200, "state": "pending_review"}` |
| `withdrawal` | proven | `{"code": 200, "state": "withdrawn"}` |
| `first_submission_live` | proven | `{"code": 200}` |
| `hr_approve_stage_1` | proven | `{"code": 200, "error": ""}` |
| `concurrent_hr_review_guard` | proven | `{"code": 409, "error": "stale_concurrency_version"}` |
| `payroll_effective_transition` | proven | `{"code": 200, "request_state": "applied", "effective_from": "2026-08-06", "bank_profile_version": 1}` |
| `retry_idempotency_apply` | proven | `{"code": 200, "current_effective_rows": 1}` |
| `authority_layers_separated` | proven | `{"verified_rows": 1, "current_effective_rows": 1}` |
| `payroll_effective_never_plaintext` | proven | `{"leaked": false}` |
| `notification_deduplication` | proven | `{"groups": 4, "dupes": []}` |
| `audit_history` | proven | `{"event_count": 9, "actions": ["apply", "create_draft", "decide_approve", "decide_reject", "submit", "withdraw"]}` |
| `onboarding_bank_item_synced_on_apply` | proven | `{"status": "accepted"}` |
| `existing_bank_change` | proven | `{"code": 200, "has_verified": true, "state": "pending_review"}` |
| `verified_separate_from_submitted` | proven | `{"verified_present": true, "submitted_present": true}` |
| `unreviewed_input_not_payroll_truth` | proven | `{"effective_fingerprint_matches_previous": true}` |
| `evidence_upload` | proven | `{"evidence_id": "abc7ef95-f48e-4e28-a11f-5540ec24f607"}` |
| `evidence_access_own` | proven | `{"code": 200}` |
| `evidence_access_denied_other_employee` | proven | `{"code": 404}` |
| `evidence_access_hr_authorized` | proven | `{"code": 200}` |
| `unauthorized_hr_access_denied` | proven | `{"code": 401, "error": "dashboard_auth_failed"}` |
| `cross_tenant_isolation_unknown_key` | proven | `{"code": 404}` |
| `cross_tenant_isolation_storage` | proven | `{"rows_outside_tenant": 0}` |
| `arabic_next_step` | proven | `{"message": "\u0627\u0644\u0645\u0648\u0627\u0631\u062f \u0627\u0644\u0628\u0634\u0631\u064a\u0629 \u062a\u0631\u0627\u062c\u0639 \u0637\u0644\u0628\u0643. \u06` |
| `masking_and_permitted_reveal_contract` | proven | `{"masking": {"masked_by_default": true, "reveal_requires_permission": "employees.ess.unmask", "reveal_is_audited": true}, "leaked": false}` |
| `payroll_lock_state_defined` | proven | `{"locked": false, "period_status": null, "period_end": null}` |

## onboarding_completion

| case | verdict | detail |
|---|---|---|
| `new_employee_no_progress` | proven | `"not_started"` |
| `partial_progress` | proven | `{"satisfied": 0, "open": 3}` |
| `waiting_on_employee` | proven | `"waiting_on_employee"` |
| `waiting_on_hr` | proven | `"waiting_on_hr"` |
| `rejected_item` | proven | `"waiting_on_employee"` |
| `corrected_item` | proven | `["qual_doc_a"]` |
| `waived_item` | proven | `{"waiting_hr": ["qual_doc_b"]}` |
| `not_applicable_item` | proven | `"completed"` |
| `completion` | proven | `"completed"` |
| `completion_evidence_recorded` | proven | `{"first_completed_at": "2026-08-06 05:24:44.994315+00:00", "evidence": 1}` |
| `legacy_columns_mirrored` | proven | `{"onboarding_status": "completed", "documents_pending": 0, "documents_complete": 1}` |
| `requirement_added_after_completion` | proven | `"reopened"` |
| `reopened_onboarding` | proven | `"reopened"` |
| `historical_evidence_preserved` | proven | `{"evidence": 1}` |
| `requirement_removed_after_progress` | proven | `"completed"` |
| `blocked_dependency_detected` | proven | `{"blocked": ["qual_dep_child"]}` |
| `accepted_satisfies_dependency` | proven | `{"blocked": []}` |
| `employee_transfer_new_requirement` | proven | `"reopened"` |
| `legacy_received_not_verified` | proven | `{"waiting_hr": ["qual_dep_child"]}` |
| `cross_surface_status_consistency` | proven | `{"employee_app": "reopened", "hr_completion_endpoint": "reopened", "hr_onboarding_web": "reopened", "contract": "reopened"}` |
| `reminder_covers_correction_state` | proven | `{"party": "employee", "items": ["qual_dep_child", "qual_transfer_req"], "dedup_key": "onboarding:reopened:employee:qual_dep_child,qual_transfer_req"}` |
| `reminder_deduplication` | proven | `{"key": "onboarding:reopened:employee:qual_dep_child,qual_transfer_req"}` |
| `retry_idempotency_recompute` | proven | `{"state": "reopened", "history_before": 9, "history_after": 9}` |
| `permissions_unauthenticated_denied` | proven | `{"code": 401}` |
| `tenant_isolation` | proven | `{"code": 404}` |
| `arabic_next_action` | proven | `"\u062a\u0645 \u0625\u0639\u0627\u062f\u0629 \u0641\u062a\u062d \u0627\u0644\u0627\u0644\u062a\u062d\u0627\u0642 \u2014 \u064a\u0644\u0632\u0645 \u0628\u0646\u0` |
| `mobile_projection_contract` | proven | `{"code": 200, "lifecycle_version": "2a"}` |
