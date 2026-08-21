#!/usr/bin/env python3
"""Workspace Work aggregation contract — My Work / Company Attention."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import workspace_work as ww  # noqa: E402


def check(label: str, cond: bool) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {label}")
    print(f"PASS: {label}")


def main() -> None:
    check("contract id", ww.CONTRACT == "workspace_work_v1")
    check("scopes", ww.SCOPES == frozenset({"mine", "attention"}))
    check("normalize mine", ww.normalize_work_scope("my_work") == "mine")
    check("normalize attention", ww.normalize_work_scope("company") == "attention")
    check("normalize empty", ww.normalize_work_scope("nope") == "")

    assigned = ww._item(
        work_id="prehire:person:A:ready_for_review",
        scope="mine",
        membership=ww.MEMBERSHIP_ASSIGNED,
        module="pre_hiring",
        source_key=ww.SOURCE_PREHIRE,
        authority_source="test",
        action_type="ready_for_review",
        title_en="Review candidate",
        title_ar="مراجعة المرشح",
        reason_en="ready",
        reason_ar="جاهز",
        destination={"page": "candidates", "filters": {"q": "A"}},
        owner_user_id="u1",
        due_state="overdue",
        priority=80,
        entity_type="person",
        entity_id="A",
    )
    dup = dict(assigned)
    dup["priority"] = 10
    dup["due_state"] = "open"
    merged = ww._dedupe([assigned, dup])
    check("dedupe keeps overdue", len(merged) == 1 and merged[0]["due_state"] == "overdue")

    inbox_mine, inbox_meta = ww.collect_action_inbox(
        scope="mine",
        actor_user_id="u1",
        load_inbox=lambda: {
            "ok": True,
            "items": [
                {"id": "leave:1", "what_en": "Leave", "what_ar": "إجازة", "source_module": "leave", "deep_link": {"page": "leave"}, "owner_role": "hr_ops"},
                {"id": "leave:2", "what_en": "Mine", "what_ar": "لي", "source_module": "leave", "assignee_user_id": "u1", "deep_link": {"page": "leave"}},
            ],
        },
    )
    check("inbox mine only assigned", len(inbox_mine) == 1 and inbox_mine[0]["membership"] == ww.MEMBERSHIP_ASSIGNED)
    inbox_att, _ = ww.collect_action_inbox(
        scope="attention",
        actor_user_id="u1",
        load_inbox=lambda: {
            "ok": True,
            "items": [
                {"id": "leave:1", "what_en": "Leave", "what_ar": "إجازة", "source_module": "leave", "owner_role": "hr_ops", "deep_link": {"page": "leave"}},
                {"id": "leave:2", "what_en": "Mine", "what_ar": "لي", "source_module": "leave", "assignee_user_id": "u1", "deep_link": {"page": "leave"}},
            ],
        },
    )
    check("inbox attention skips assigned-to-me", len(inbox_att) == 1 and inbox_att[0]["work_id"].endswith("leave:1"))

    check(
        "viewer cannot oversee",
        ww.can_view_attention(actor_role="viewer", permissions={"prehire.read"}, enabled={"pre_hiring"}, inbox_ok=False) is False,
    )
    check(
        "owner can oversee hiring",
        ww.can_view_attention(actor_role="owner", permissions={"prehire.read"}, enabled={"pre_hiring"}, inbox_ok=False) is True,
    )
    check(
        "leave decide unlocks attention",
        ww.can_view_attention(
            actor_role="viewer",
            permissions={"leave.decide"},
            enabled={"leave"},
        )
        is True,
    )
    check(
        "inbox does not unlock attention without entitled module",
        ww.can_view_attention(actor_role="viewer", permissions=set(), enabled=set(), inbox_ok=True)
        is False,
    )

    src = (ROOT / "workspace_work.py").read_text(encoding="utf-8")
    check("does not mutate", '"mutates_records": False' in src)
    check("wraps prehire personal work", "build_scoped_work_queue" in src)
    check("wraps action inbox", "action_inbox" in src)
    check("wraps requisitions surface", "requisitions_surfaces" in src)
    check("no second ranking formula beyond source due/priority", "pressure_score" not in src)

    http_src = (ROOT / "workspace_work_http.py").read_text(encoding="utf-8")
    check("http path", "/dashboard/work" in http_src)
    check("app register present", "register_workspace_work_http" in (ROOT / "app.py").read_text(encoding="utf-8"))
    check("http wraps leave queue", "list_leave_requests" in http_src)
    check("http wraps onboarding queue", "list_onboarding_hr_actionable_page" in http_src)
    check("http wraps shift swaps", "resolve_shift_swaps" in http_src)

    import workspace_work_contributions as contrib

    coverage = contrib.catalog_coverage_errors()
    check(f"catalog contribution coverage {coverage}", coverage == [])
    matrix = contrib.contribution_matrix()
    check("matrix covers 25 catalog modules", len(matrix) == 25)
    none_rows = [row for row in matrix if row["kind"] == "none"]
    check(
        "none rows have reasons",
        all(row["omit_reason"] for row in none_rows) and {row["module"] for row in none_rows}
        == {"calendar", "video_interviews", "talent", "payroll", "employee_app"},
    )
    mine_rows = [row for row in matrix if row["mine"]]
    check("mine rows declare assignee fields", all(row["assignee_fields"] for row in mine_rows))

    class NullCur:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args, **kwargs):
            raise RuntimeError("unexpected_sql")

        def fetchall(self):
            return []

        def fetchone(self):
            return None

    class NullConn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return NullCur()

        def commit(self):
            return None

    leave_payload = {
        "ok": True,
        "leave_requests": [
            {"leave_id": "L1", "employee_key": "E1", "employee_name": "Sam", "status": "requested"}
        ],
    }

    disabled = ww.compose_workspace_work(
        company="WATHEFNI",
        db_connect=lambda: NullConn(),
        actor_user_id="u1",
        actor_role="owner",
        actor_email="o@x",
        actor_phone="965000",
        enabled_modules={"pre_hiring"},
        permissions={"prehire.read", "candidates.read", "candidate.manage", "leave.decide"},
        scope="attention",
        load_leave=lambda: leave_payload,
        load_inbox=lambda: {
            "ok": True,
            "items": [
                {
                    "id": "leave:1",
                    "what_en": "Leave",
                    "what_ar": "إجازة",
                    "source_module": "leave",
                    "owner_role": "hr_ops",
                    "deep_link": {"page": "leave"},
                }
            ],
        },
    )
    check("disabled compose ok", disabled.get("ok") is True)
    leave_status = next(row for row in disabled["contributions"] if row["module"] == "leave")
    check("disabled leave is module_off", leave_status["status"] == "module_off")
    check("disabled leave count 0", leave_status["count"] == 0)
    check(
        "disabled leave contributes no items",
        all(item.get("module") != "leave" for item in disabled["items"]),
    )
    payroll_status = next(row for row in disabled["contributions"] if row["module"] == "payroll")
    check("payroll none even when omitted from enabled", payroll_status["status"] == "module_off")

    unauthorized = ww.compose_workspace_work(
        company="WATHEFNI",
        db_connect=lambda: NullConn(),
        actor_user_id="viewer-1",
        actor_role="viewer",
        actor_email="v@x",
        actor_phone="965111",
        enabled_modules={"leave", "payroll", "calendar"},
        permissions={"leave.read", "payroll.read"},
        scope="attention",
        load_leave=lambda: leave_payload,
    )
    leave_unauth = next(row for row in unauthorized["contributions"] if row["module"] == "leave")
    check("unauthorized leave is permission_denied", leave_unauth["status"] == "permission_denied")
    check("unauthorized leave contributes nothing", unauthorized["counts"]["total"] == 0)
    check("unauthorized can_view_attention false", unauthorized["can_view_attention"] is False)
    payroll_unauth = next(row for row in unauthorized["contributions"] if row["module"] == "payroll")
    check("payroll none reason preserved", payroll_unauth["status"] == "none" and payroll_unauth["omit_reason"] == "payroll_money_excluded")
    calendar_unauth = next(row for row in unauthorized["contributions"] if row["module"] == "calendar")
    check("calendar none reason preserved", calendar_unauth["omit_reason"] == "projection_only")

    entitled = ww.compose_workspace_work(
        company="WATHEFNI",
        db_connect=lambda: NullConn(),
        actor_user_id="hr-1",
        actor_role="owner",
        actor_email="hr@x",
        actor_phone="965222",
        enabled_modules={"leave"},
        permissions={"leave.decide"},
        scope="attention",
        load_leave=lambda: leave_payload,
    )
    leave_ok = next(row for row in entitled["contributions"] if row["module"] == "leave")
    check("entitled leave used", leave_ok["status"] == "used" and leave_ok["count"] == 1)
    check("entitled leave item preserved destination", entitled["items"][0]["destination"]["page"] == "leave")
    check("entitled leave allowed_actions from source", entitled["items"][0]["allowed_actions"] == ["decide"])

    mine_none = ww.compose_workspace_work(
        company="WATHEFNI",
        db_connect=lambda: NullConn(),
        actor_user_id="hr-1",
        actor_role="owner",
        actor_email="hr@x",
        actor_phone="965222",
        enabled_modules={"leave"},
        permissions={"leave.decide"},
        scope="mine",
        load_leave=lambda: leave_payload,
    )
    leave_mine = next(row for row in mine_none["contributions"] if row["module"] == "leave")
    check("leave has no mine contribution", leave_mine["status"] == "no_mine_contribution")
    check("leave mine items empty", mine_none["counts"]["total"] == 0)

    print("OK workspace-work")


if __name__ == "__main__":
    main()
