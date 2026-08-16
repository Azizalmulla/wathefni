# Leave Wave 0 — codebase inventory notes

From explore pass 3ec37485-3860-470c-943c-4d1f6d777351 (read-only).

## Extra findings merged into REPORT addendum
- leave-type drift (vacation/time_off vs annual/sick)
- declined_lifecycle / pending vs primary statuses
- manager lacks leave.request (intentional)
- employee_leave_balances stale canary name
- no Leave freeze doc yet
- payroll leave_policy knob is not leave-module unpaid

## Key files
- wathefni-orchestrator/app.py (schema + workflow + balances)
- wathefni-orchestrator/action_registry.py (executors)
- wathefni-orchestrator/leave-accrual-worker.py
- wathefni-orchestrator/operator_mobile_data.py
- wathefni-orchestrator/employee_lifecycle_wave3c.py (decline_open_leave)
- apps/wathefni-dashboard/src/posthire/PostHire.tsx (LeavePage)
- apps/wathefni-employee-mobile/app/(tabs)/leave.tsx
- apps/wathefni-hr-mobile/src/features/leave/LeaveApprovalView.tsx
