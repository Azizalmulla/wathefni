# Attendance Wave 4 — page-by-page audit decisions

| Surface | Decision | Rationale |
|---|---|---|
| Attendance overview | **Refine in place** | Keep PostHire Attendance shell; add life-state QuietStats (captured/late/absent/needs review/payroll excluded) |
| Daily attendance table | **Enrich columns** | Scheduled, actual, worked, late/early, life-state pills; day-detail expand for sessions/breaks/payroll exclusion |
| Exception queue | **New `AttendanceOpsPanel`** | True queue from `/dashboard/attendance/ops/*` with owner, due, next action |
| Employee day detail | **Inline expand** | Under-table day detail (no new route) |
| Correction review | **Ops Corrections tab** | Before/after snapshots; Approve ≠ Apply; dual-approval strip |
| Disputes / reopen | **Ops Disputes + reopen** | Raise/resolve dispute; reopen requires evidence |
| Approval / dual-approval | **Visible case states** | Status labels + ApprovalStrip when second approver required |
| Payroll lock / exclusion | **BlockedReason + Locked tab** | Customer-facing exclusion copy |
| Capture connector health | **Polish CaptureOpsPanel** | Retitle **Connector health**; remove dark/wave jargon; ingest-off banner kept |
| EN/AR + RTL | **`useEmployees360Locale`** | Same locale rail as E360 / pre-hire |
| Loading / empty / error / stale / permission | **Covered** | Ops + capture + attendance page states |

Frozen modules (Employees 360, Onboarding, pre-hire): **not edited** beyond Attendance PostHire surfaces and shared ops API list enrichment.
