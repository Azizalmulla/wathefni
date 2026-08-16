"""Wave A — orphan Assessments /queue route must never 500.

Live Assessments cohort UI uses:
  GET /dashboard/prehire/applications?overview_cohort=&assessment_cohort=

The path /dashboard/prehire/assessments/queue is not a product API. Before the
tombstone, FastAPI bound ``queue`` to ``{attempt_id}`` and could return 500.

This smoke is DB-light: dependency override + TestClient.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from fastapi.testclient import TestClient

import app


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:
            self.failed.append(f"{label} -> raised {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def report(self) -> int:
        for label in self.passed:
            print(f"PASS  {label}")
        for label in self.failed:
            print(f"FAIL  {label}")
        print(f"\n{len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def _fake_assessments_context() -> dict[str, Any]:
    return {
        "company_code": "WAVEAQUE",
        "hr_phone": "+96500000000",
        "hr_user": {"user_id": "wave-a-queue", "role": "owner", "permissions": ["*:*"]},
        "access": {"role": "owner", "permissions": ["*:*"]},
    }


def main() -> int:
    checks = Checks()

    paths = {getattr(route, "path", "") for route in app.app.routes}
    checks.check(
        "static assessments/queue tombstone route is registered",
        lambda: "/dashboard/prehire/assessments/queue" in paths,
    )
    checks.check(
        "attempt detail route remains registered",
        lambda: "/dashboard/prehire/assessments/{attempt_id}" in paths,
    )

    # Ensure static path is matched preferentially: inspect route order.
    ordered = [getattr(route, "path", "") for route in app.app.routes if str(getattr(route, "path", "")).startswith("/dashboard/prehire/assessments")]
    queue_idx = next((i for i, p in enumerate(ordered) if p == "/dashboard/prehire/assessments/queue"), -1)
    attempt_idx = next((i for i, p in enumerate(ordered) if p == "/dashboard/prehire/assessments/{attempt_id}"), -1)

    def _order_ok() -> bool:
        return queue_idx >= 0 and attempt_idx >= 0 and queue_idx < attempt_idx

    checks.check("queue tombstone is registered before {attempt_id}", _order_ok)

    client = TestClient(app.app)
    app.app.dependency_overrides[app.assessments_dashboard_context] = _fake_assessments_context
    try:
        resp = client.get("/dashboard/prehire/assessments/queue?cohort=assessment_ready_to_send&limit=10")
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"raw": resp.text}

        def _status_ok() -> bool:
            return resp.status_code in (404, 410)

        def _never_500() -> bool:
            return resp.status_code != 500

        def _json_error() -> bool:
            detail = body.get("detail") if isinstance(body, dict) else None
            if isinstance(detail, dict):
                return str(detail.get("error") or "") in {
                    "assessment_queue_route_removed",
                    "assessment_queue_route_not_found",
                }
            return False

        def _points_to_applications() -> bool:
            detail = body.get("detail") if isinstance(body, dict) else None
            msg = str((detail or {}).get("message") or "")
            return "applications" in msg and "overview_cohort" in msg

        checks.check("queue route returns controlled 404 or 410", _status_ok)
        checks.check("queue route never returns 500", _never_500)
        checks.check("queue route returns JSON error key", _json_error)
        checks.check("queue error points at applications cohort contract", _points_to_applications)
        checks.check("expected Wave A status is 410 Gone", lambda: resp.status_code == 410)
    finally:
        app.app.dependency_overrides.pop(app.assessments_dashboard_context, None)

    # Product dashboard must not call assessments/queue.
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    dash_src = root / "apps" / "wathefni-dashboard" / "src"
    if dash_src.is_dir():
        hits = []
        for path in dash_src.rglob("*"):
            if path.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "assessments/queue" in text:
                hits.append(str(path.relative_to(root)))
        checks.check("no product dashboard caller of assessments/queue", lambda h=hits: h == [])
        if hits:
            print("CALLER_HITS", hits)
    else:
        checks.check("dashboard src available for caller audit", lambda: False)

    return checks.report()


if __name__ == "__main__":
    sys.exit(main())
