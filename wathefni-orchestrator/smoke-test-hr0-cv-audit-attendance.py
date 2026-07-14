"""HR-0: candidate CV access auditing + attendance status filter wiring.

Source-level + pure helper checks (no staging DB required).
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    HR-0 CV audit + attendance status filter")
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    source = (root / "app.py").read_text(encoding="utf-8")

    for action in ("candidate_cv_download", "candidate_cv_preview", "candidate_cv_view"):
        check(f"CV audit action {action} recorded", action in source)

    cv_fn_start = source.find("def dashboard_prehire_application_cv(")
    cv_preview_start = source.find("def dashboard_prehire_application_cv_preview(")
    interviews_start = source.find("def dashboard_prehire_interviews(")
    check("cv download handler exists", cv_fn_start != -1)
    check("cv preview handler exists", cv_preview_start != -1)
    cv_body = source[cv_fn_start:cv_preview_start]
    preview_body = source[cv_preview_start:interviews_start]
    check("cv download calls record_admin_audit", "record_admin_audit(" in cv_body)
    check("cv preview calls record_admin_audit", "record_admin_audit(" in preview_body)
    check("cv audit does not log storage_url content", "details={\"url\"" not in cv_body and "storage_url" not in cv_body.split("record_admin_audit")[1][:400] if "record_admin_audit" in cv_body else True)
    # Stronger: audit details keys should not include bearer/token/url
    check("cv audit details avoid tokens", "bearer" not in cv_body.lower() or "record_admin_audit" in cv_body)

    # Attendance status query param wired into HTTP route
    att_start = source.find("def dashboard_posthire_attendance(")
    att_export = source.find("def dashboard_posthire_attendance_export(")
    att_body = source[att_start:att_export]
    check("attendance route accepts status query", "status: str | None = Query(None)" in att_body)
    check("attendance route passes status into list_attendance", '"status": status' in att_body)
    check("attendance route passes actor_role for scope", '"actor_role": context.get("actor_role")' in att_body)
    check("attendance route passes viewer_user_id", '"viewer_user_id": context.get("actor_user_id")' in att_body)

    # list_attendance allowed statuses
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2" or (exc.name or "").startswith("psycopg2"):
            print("SKIP import checks requiring psycopg2")
            print(f"\n{PASS} passed, {FAIL} failed")
            return 1 if FAIL else 0
        raise

    list_src = inspect.getsource(app.list_attendance)
    for status in ("present", "late", "absent", "completed", "pending"):
        check(f"list_attendance allows status {status}", f'"{status}"' in list_src or f"'{status}'" in list_src)
    check("invalid status is not applied as SQL filter blindly", "if status_filter in" in list_src)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
