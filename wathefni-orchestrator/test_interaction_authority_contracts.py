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


def function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"Missing function {name} in {path}")


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
        self.assertIn("create_employee_account_deletion_request", body)
        authority = function_source(ROOT / "app.py", "create_employee_account_deletion_request")
        self.assertIn("pg_advisory_xact_lock", authority)
        self.assertIn("task_type='account_deletion_request'", authority)

    def test_public_account_deletion_converges_on_tenant_scoped_authority(self) -> None:
        routes = route_functions(ROOT / "app.py")
        _, body = routes["/public/account-deletion/request"]
        self.assertIn("create_employee_account_deletion_request", body)
        self.assertIn("SELECT 1 FROM companies WHERE company_code=%s", body)
        self.assertIn("WHERE company_code=%s", body)
        self.assertIn("FROM employee_app_invites", body)
        self.assertIn("FROM employee_sessions", body)
        self.assertIn("len(matches) == 1", body)
        self.assertIn("_PUBLIC_ACCOUNT_DELETION_GENERIC", body)
        self.assertNotIn("_employee_app_company_gate", body)
        self.assertNotIn("_employee_app_runtime_access", body)
        self.assertNotIn("employee_app_activate", body)
        self.assertNotIn("INSERT INTO employee_sessions", body)


if __name__ == "__main__":
    unittest.main()
