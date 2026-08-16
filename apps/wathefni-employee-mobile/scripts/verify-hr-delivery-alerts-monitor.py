#!/usr/bin/env python3
"""HR Delivery Alerts — quiet read-only More monitor contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT.parents[1] / "wathefni-orchestrator"

view = (ROOT / "src/hr/features/delivery-alerts/HRDeliveryAlertsMonitorView.tsx").read_text(encoding="utf-8")
comp = (ROOT / "src/hr/features/delivery-alerts/alertsComposition.ts").read_text(encoding="utf-8")
gate = (ROOT / "src/hr/features/delivery-alerts/alertsDemoGate.ts").read_text(encoding="utf-8")
route = (ROOT / "app/hr/delivery-alerts.tsx").read_text(encoding="utf-8")
ops = (ROOT / "src/hr/features/operations/routes.tsx").read_text(encoding="utf-8")
types = (ROOT / "src/hr/api/types.ts").read_text(encoding="utf-8")
norm = (ROOT / "src/hr/api/normalize.ts").read_text(encoding="utf-8")
caps = (ROOT / "src/hr/capabilities.ts").read_text(encoding="utf-8")
launcher = (ROOT / "src/hr/features/more/moreLauncher.ts").read_text(encoding="utf-8")
ia = (ROOT / "src/hr/shell/ia.ts").read_text(encoding="utf-8")
tasks_comp = (ROOT / "src/hr/features/tasks/tasksComposition.ts").read_text(encoding="utf-8")
config = (ROOT / "app.config.js").read_text(encoding="utf-8")
en = json.loads((ROOT / "src/i18n/en.json").read_text(encoding="utf-8"))
ar = json.loads((ROOT / "src/i18n/ar.json").read_text(encoding="utf-8"))
backend = (ORCH / "operator_mobile_data.py").read_text(encoding="utf-8")
mobile_caps = (ORCH / "operator_mobile.py").read_text(encoding="utf-8")
outbound = (ORCH / "outbound_delivery.py").read_text(encoding="utf-8")
app_py = (ORCH / "app.py").read_text(encoding="utf-8")


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


check("cream monitor view wired", "HRDeliveryAlertsMonitorView" in route)
check("ops route is thin re-export", "HRDeliveryAlertsMonitorView as DeliveryAlertsRoute" in ops)
check("no OperationalListView on alerts path", "OperationalListView" not in view)
check("read-only — no mutate APIs", "mobileApi." not in view or "mobileApi.alerts" in view)
check("no resolve/resend UI actions", "markDone" not in view and "Resend" not in view and "onResolve" not in view)
check("has_task client belt", "has_task" in view and "has_task" in comp)
check("normalize has_task + employee + channel", all(k in norm.split("normalizeAlert")[1].split("normalizeCandidate")[0] for k in ("has_task", "employee", "channel_used", "reason")))
check("types include has_task/kind/attempts", all(k in types.split("export type DeliveryAlert")[1].split("export type CandidateSummary")[0] for k in ("has_task", "kind", "attempts", "employee")))
check("More only destination", "deliveryAlerts" in launcher and "Delivery alerts lock" in launcher)
check("Inbox allowlist excludes delivery_alerts", "delivery_alerts" not in ia.split("INBOX_SECTION_TYPES")[1].split("]")[0])
check("Home allowlist excludes delivery_alerts", "delivery_alerts" not in ia.split("HOME_SECTION_TYPES")[1].split("]")[0])
check("demo gated", "alertsDemoEnabled" in gate and "__demo_alert__" in gate)
check("app.config deliveryAlertsDemo", "deliveryAlertsDemo:" in config and "EXPO_PUBLIC_HR_DELIVERY_ALERTS_DEMO" in config)
check("canonical delivery_failed vocab", "delivery_failed" in tasks_comp and "case 'delivery_failed'" in tasks_comp)
check("backend exclude_linked_tasks on mobile queue", "exclude_linked_tasks=True" in backend.split("def mobile_delivery_alert_queue")[1].split("def attendance_mobile_item")[0])
check("priorities omit delivery_alerts emit", '"type": "delivery_alerts"' not in backend.split("def build_mobile_priorities")[1].split("\ndef ")[0])
check("priorities comment present", "intentionally omitted from mobile priorities" in backend)
check("outbound SQL has_task dedupe", "exclude_linked_tasks" in outbound and "m.hr_task_id IS NULL" in outbound)
check("dashboard API pass-through", "exclude_linked_tasks" in app_py.split("dashboard_outbound_needs_follow_up")[1][:800])
alerts_feat = mobile_caps.split('"delivery_alerts": _feature(')[1].split("),")[0]
check("capability parity with hr_task_read", "enabled=hr_task_read" in alerts_feat)
check("delivery_alerts actions read-only", 'actions=["read"] if hr_task_read else []' in alerts_feat)
check("task type canonical delivery_failed", 'task_type: str = "delivery_failed"' in outbound)

keys = [
    "hrAlerts.title",
    "hrAlerts.subtitle",
    "hrAlerts.queueHint",
    "hrMore.deliveryAlertsBody",
]
check("hrAlerts keys EN+AR", all(k in en and k in ar for k in keys))
check("More body mentions non-task", "non-task" in en.get("hrMore.deliveryAlertsBody", "").lower())
print("hr-delivery-alerts-monitor: GREEN")
