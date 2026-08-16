import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def route_functions(path: Path) -> dict[str, tuple[str, str]]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    routes: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            method = decorator.func.attr.upper()
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"} or not decorator.args:
                continue
            route_node = decorator.args[0]
            if not isinstance(route_node, ast.Constant) or not isinstance(route_node.value, str):
                continue
            body = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            routes[route_node.value] = (method, body)
    return routes


class InteractionAuthorityContracts(unittest.TestCase):
    def test_attendance_ops_use_read_and_manage_permissions(self) -> None:
        routes = route_functions(ROOT / "attendance_ops_http.py")
        attendance = {
            route: details
            for route, details in routes.items()
            if route.startswith("/dashboard/attendance/ops/")
        }
        self.assertTrue(attendance)
        for route, (method, body) in attendance.items():
            permission = "attendance.read" if method == "GET" else "attendance.manage"
            self.assertIn(
                f'require_entitlement(context, "attendance", "{permission}")',
                body,
                route,
            )
            if method != "GET":
                self.assertTrue(
                    "_audit(" in body or "record_admin_audit(" in body,
                    f"{route} must emit an audit record",
                )

    def test_whatsapp_turn_requires_internal_auth(self) -> None:
        routes = route_functions(ROOT / "app.py")
        _, body = routes["/orchestrator/whatsapp-turn"]
        self.assertIn("Depends(require_internal_access)", body)

    def test_account_deletion_matches_capability_and_is_idempotent(self) -> None:
        routes = route_functions(ROOT / "app.py")
        _, body = routes["/app/account/request-deletion"]
        self.assertIn(
            'require_employee_app_feature(context, "settings", action="request_deletion")',
            body,
        )
        self.assertIn("pg_advisory_xact_lock", body)
        self.assertIn("task_type='account_deletion_request'", body)


if __name__ == "__main__":
    unittest.main()
