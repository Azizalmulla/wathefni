#!/usr/bin/env python3
"""HR Tasks — open follow-up queue + Mark done contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT.parents[1] / "wathefni-orchestrator"

queue = (ROOT / "src/hr/features/tasks/HRTasksQueueView.tsx").read_text(encoding="utf-8")
detail = (ROOT / "src/hr/features/tasks/HRTaskDetailView.tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/tasks/tasksComposition.ts").read_text(encoding="utf-8")
gate = (ROOT / "src/hr/features/tasks/tasksDemoGate.ts").read_text(encoding="utf-8")
index = (ROOT / "app/hr/tasks/index.tsx").read_text(encoding="utf-8")
detail_route = (ROOT / "app/hr/tasks/[taskId].tsx").read_text(encoding="utf-8")
api = (ROOT / "src/hr/api/mobile.ts").read_text(encoding="utf-8")
types = (ROOT / "src/hr/api/types.ts").read_text(encoding="utf-8")
norm = (ROOT / "src/hr/api/normalize.ts").read_text(encoding="utf-8")
caps = (ROOT / "src/hr/capabilities.ts").read_text(encoding="utf-8")
ia = (ROOT / "src/hr/shell/ia.ts").read_text(encoding="utf-8")
config = (ROOT / "app.config.js").read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))
backend = (ORCH / "operator_mobile_data.py").read_text(encoding="utf-8")
mobile_caps = (ORCH / "operator_mobile.py").read_text(encoding="utf-8")
outbound = (ORCH / "outbound_delivery.py").read_text(encoding="utf-8")


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("queue route", "HRTasksQueueView" in index)
check("detail route", "HRTaskDetailView" in detail_route)
check("default open API", "status" in api and "open" in api.split("tasks:")[1].split("taskDetail")[0])
check("no due_at invent", "due_at" not in types.split("export type HRTask")[1].split("export type DocumentReview")[0])
check("normalize keeps type/priority/employee", "task_type" in norm.split("normalizeTask")[1].split("normalizeDocument")[0] and "priority" in norm.split("normalizeTask")[1].split("normalizeDocument")[0])
check("Mark done action present", "hrTasks.markDone" in detail)
check("editorial About + unboxed facts", "sectionAbout" in detail and "Fact" in detail)
check("ConfirmationSheet outside scroll", detail.rfind("ConfirmationSheet") > detail.rfind("PageScrollView"))
check("no dismiss/assign action keys", "hrTasks.dismiss" not in detail and "hrTasks.assign" not in detail)
check("destinationAvailable tasks", "path.startsWith('/tasks/')" in caps)
check("Inbox includes hr_tasks", "'hr_tasks'" in ia.split("INBOX_SECTION_TYPES")[1].split("HOME_SECTION_TYPES")[0])
check("demo gated", "tasksDemoEnabled" in gate and "__demo_task__" in gate)
check("demo multi types", "candidate_handoff" in comp and "delivery_failed" in comp and "app_activation_handoff" in comp)
check("app.config tasksDemo", "tasksDemo:" in config and "EXPO_PUBLIC_HR_TASKS_DEMO" in config)
check("backend resolve + scope load", "mobile_hr_task_resolve" in backend and "_load_hr_task" in backend)
check("capability advertises resolve", '"resolve"' in mobile_caps.split('"hr_tasks"')[1].split('"leave_approvals"')[0] or "hr_task_actions.append(\"resolve\")" in mobile_caps)
check("get_hr_task scoped helper", "def get_hr_task" in outbound)
check("priorities use mobile_hr_tasks", "mobile_hr_tasks(" in backend.split('type": "hr_tasks"')[0][-400:])

keys = [
    "hrTasks.title",
    "hrTasks.queueHint",
    "hrTasks.markDone",
    "hrMore.tasksBody",
]
check("hrTasks keys EN+AR", all(k in en and k in ar for k in keys))
check("More body is follow-ups", "follow-up" in en.get("hrMore.tasksBody", "").lower() or "Open" in en.get("hrMore.tasksBody", ""))
print("hr-tasks-follow-ups: GREEN")
