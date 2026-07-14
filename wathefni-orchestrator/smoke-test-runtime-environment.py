#!/usr/bin/env python3
"""Focused fail-closed runtime/database environment contract tests."""

from __future__ import annotations

from pathlib import Path
import tempfile

from runtime_environment import (
    RuntimeEnvironmentError,
    resolve_runtime_binding,
    validate_database_identity,
)


PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"PASS: {label}")
    else:
        FAIL += 1
        print(f"FAIL: {label}")


def rejects(label: str, expected: str, fn) -> None:
    try:
        fn()
    except RuntimeEnvironmentError as exc:
        check(label, str(exc) == expected)
    else:
        check(label, False)


class FakeCursor:
    def __init__(self, row=None, error: Exception | None = None):
        self.row = row
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _sql):
        if self.error:
            raise self.error

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row=None, error: Exception | None = None):
        self.row = row
        self.error = error

    def cursor(self):
        return FakeCursor(self.row, self.error)


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    staging_file = root / "staging.env"
    production_file = root / "production.env"
    staging_url = "postgresql://user:secret@127.0.0.1:5432/wathefni_staging"
    production_url = "postgresql://user:secret@127.0.0.1:5432/wathefni"
    staging_file.write_text(f"WATHEFNI_DATABASE_URL={staging_url}\n")
    production_file.write_text(f"WATHEFNI_DATABASE_URL={production_url}\n")

    def env(environment: str, path: Path, database: str, marker: str) -> dict[str, str]:
        return {
            "WATHEFNI_ENV": environment,
            "WATHEFNI_POSTGRES_ENV": str(path),
            "WATHEFNI_EXPECTED_DATABASE_HOST": "127.0.0.1",
            "WATHEFNI_EXPECTED_DATABASE_PORT": "5432",
            "WATHEFNI_EXPECTED_DATABASE_NAME": database,
            "WATHEFNI_DATABASE_ENVIRONMENT_MARKER": marker,
        }

    staging_env = env("staging", staging_file, "wathefni_staging", "staging-marker")
    production_env = env("production", production_file, "wathefni", "production-marker")
    staging = resolve_runtime_binding(staging_env)
    production = resolve_runtime_binding(production_env)
    check("staging binding resolves", staging.expected_database == "wathefni_staging")
    check("production binding resolves", production.expected_database == "wathefni")

    rejects(
        "staging refuses production database before connect",
        "database_name_mismatch",
        lambda: resolve_runtime_binding(env("staging", production_file, "wathefni_staging", "staging-marker")),
    )
    rejects(
        "production refuses staging database before connect",
        "database_name_mismatch",
        lambda: resolve_runtime_binding(env("production", staging_file, "wathefni", "production-marker")),
    )
    rejects(
        "missing application environment refuses startup",
        "application_environment_missing_or_invalid",
        lambda: resolve_runtime_binding({}),
    )
    rejects(
        "missing environment marker refuses startup",
        "database_identity_configuration_incomplete",
        lambda: resolve_runtime_binding(
            {
                key: value
                for key, value in staging_env.items()
                if key != "WATHEFNI_DATABASE_ENVIRONMENT_MARKER"
            }
        ),
    )
    conflict = dict(staging_env, WATHEFNI_DATABASE_URL=production_url)
    rejects(
        "ambient URL cannot override env file",
        "ambient_database_url_conflicts_with_environment_file",
        lambda: resolve_runtime_binding(conflict),
    )

    identity_row = {
        "database_name": "wathefni_staging",
        "server_host": "127.0.0.1",
        "environment": "staging",
        "marker": "staging-marker",
    }
    identity = validate_database_identity(FakeConnection(identity_row), staging)
    check("matching marker validates", identity.match is True)
    rejects(
        "missing database marker row refuses",
        "database_environment_marker_missing",
        lambda: validate_database_identity(FakeConnection(None), staging),
    )
    rejects(
        "missing database marker table refuses",
        "database_environment_marker_missing",
        lambda: validate_database_identity(FakeConnection(error=RuntimeError("undefined table")), staging),
    )
    rejects(
        "mismatched database marker refuses",
        "database_environment_marker_mismatch",
        lambda: validate_database_identity(
            FakeConnection(dict(identity_row, marker="wrong-marker")),
            staging,
        ),
    )
    rejects(
        "mismatched database environment refuses",
        "database_environment_mismatch",
        lambda: validate_database_identity(
            FakeConnection(dict(identity_row, environment="production")),
            staging,
        ),
    )

    child = staging.child_environment({"WATHEFNI_DATABASE_URL": production_url, "OTHER": "kept"})
    check("child database URL is authoritative staging URL", child["WATHEFNI_DATABASE_URL"] == staging_url)
    check("child receives environment marker", child["WATHEFNI_DATABASE_ENVIRONMENT_MARKER"] == "staging-marker")
    check("unrelated child environment retained", child["OTHER"] == "kept")

root = Path(__file__).resolve().parent
app_source = (root / "app.py").read_text()
check("app has no production database env fallback", "/root/.openclaw/secrets/postgres.env" not in app_source[:6000])
check("pool uses validated binding URL", "binding.database_url" in app_source[:9000])
check("direct DB fallback removed", "falls back to a direct connection" not in app_source[:9000])
check("workspace tool always uses validated child environment", "binding.child_environment(os.environ)" in app_source)
for worker in (
    "delivery-sweep-worker.py",
    "document-storage-reconcile-worker.py",
    "leave-accrual-worker.py",
    "video-interview-worker.py",
):
    check(f"{worker} validates environment before work", "app.assert_runtime_environment_binding()" in (root / worker).read_text())

print(f"\nruntime environment contract: {PASS} passed, {FAIL} failed")
raise SystemExit(1 if FAIL else 0)
