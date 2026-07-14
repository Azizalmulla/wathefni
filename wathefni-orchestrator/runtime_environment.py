"""Fail-closed runtime and database environment binding.

The database URL remains private. Public status surfaces expose only stable,
truncated fingerprints and the declared environment.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlparse


SUPPORTED_ENVIRONMENTS = {"staging", "production", "test"}
IDENTITY_TABLE = "wathefni_environment_identity"


class RuntimeEnvironmentError(RuntimeError):
    """Raised when runtime/database identity is missing or contradictory."""


def fingerprint(value: str | None) -> str:
    text = str(value or "")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12] if text else "missing"


def read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeEnvironmentError("database_environment_file_missing")
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class RuntimeBinding:
    application_environment: str
    env_path: Path
    database_url: str
    expected_host: str
    expected_port: int
    expected_database: str
    expected_marker: str
    env_items: tuple[tuple[str, str], ...]

    def child_environment(self, base: Mapping[str, str]) -> dict[str, str]:
        child = dict(base)
        child.update(dict(self.env_items))
        child.update(
            {
                "WATHEFNI_ENV": self.application_environment,
                "WATHEFNI_POSTGRES_ENV": str(self.env_path),
                "WATHEFNI_EXPECTED_DATABASE_HOST": self.expected_host,
                "WATHEFNI_EXPECTED_DATABASE_PORT": str(self.expected_port),
                "WATHEFNI_EXPECTED_DATABASE_NAME": self.expected_database,
                "WATHEFNI_DATABASE_ENVIRONMENT_MARKER": self.expected_marker,
            }
        )
        return child

    def masked(self) -> dict[str, Any]:
        return {
            "application_environment": self.application_environment,
            "database_environment_marker": fingerprint(self.expected_marker),
            "database_logical_name": fingerprint(self.expected_database),
            "database_host": fingerprint(self.expected_host),
            "database_port": self.expected_port,
        }


@dataclass(frozen=True)
class RuntimeIdentity:
    application_environment: str
    database_environment: str
    marker_fingerprint: str
    database_fingerprint: str
    host_fingerprint: str
    match: bool

    def public(self) -> dict[str, Any]:
        return {
            "application_environment": self.application_environment,
            "database_environment": self.database_environment,
            "database_environment_marker": self.marker_fingerprint,
            "database_logical_name": self.database_fingerprint,
            "database_host": self.host_fingerprint,
            "match": self.match,
        }


def resolve_runtime_binding(environ: Mapping[str, str]) -> RuntimeBinding:
    application_environment = str(environ.get("WATHEFNI_ENV") or "").strip().lower()
    if application_environment not in SUPPORTED_ENVIRONMENTS:
        raise RuntimeEnvironmentError("application_environment_missing_or_invalid")

    env_path_value = str(environ.get("WATHEFNI_POSTGRES_ENV") or "").strip()
    if not env_path_value:
        raise RuntimeEnvironmentError("database_environment_file_not_configured")
    env_path = Path(env_path_value)
    file_values = read_env_file(env_path)
    database_url = str(file_values.get("WATHEFNI_DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeEnvironmentError("database_url_missing_from_environment_file")

    ambient_url = str(environ.get("WATHEFNI_DATABASE_URL") or "").strip()
    if ambient_url and ambient_url != database_url:
        raise RuntimeEnvironmentError("ambient_database_url_conflicts_with_environment_file")

    expected_host = str(environ.get("WATHEFNI_EXPECTED_DATABASE_HOST") or "").strip().lower()
    expected_database = str(environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "").strip()
    expected_marker = str(environ.get("WATHEFNI_DATABASE_ENVIRONMENT_MARKER") or "").strip()
    expected_port_raw = str(environ.get("WATHEFNI_EXPECTED_DATABASE_PORT") or "").strip()
    if not expected_host or not expected_database or not expected_marker or not expected_port_raw:
        raise RuntimeEnvironmentError("database_identity_configuration_incomplete")
    try:
        expected_port = int(expected_port_raw)
    except ValueError as exc:
        raise RuntimeEnvironmentError("database_identity_port_invalid") from exc

    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeEnvironmentError("database_url_scheme_invalid")
    configured_host = str(parsed.hostname or "").strip().lower()
    configured_port = int(parsed.port or 5432)
    configured_database = unquote(str(parsed.path or "").lstrip("/"))
    if not configured_host or not configured_database:
        raise RuntimeEnvironmentError("database_url_host_or_name_missing")
    if configured_host != expected_host:
        raise RuntimeEnvironmentError("database_host_mismatch")
    if configured_port != expected_port:
        raise RuntimeEnvironmentError("database_port_mismatch")
    if configured_database != expected_database:
        raise RuntimeEnvironmentError("database_name_mismatch")
    if application_environment == "staging" and configured_database == "wathefni":
        raise RuntimeEnvironmentError("staging_refuses_production_database")
    if application_environment == "production" and configured_database == "wathefni_staging":
        raise RuntimeEnvironmentError("production_refuses_staging_database")

    return RuntimeBinding(
        application_environment=application_environment,
        env_path=env_path,
        database_url=database_url,
        expected_host=expected_host,
        expected_port=expected_port,
        expected_database=expected_database,
        expected_marker=expected_marker,
        env_items=tuple(sorted(file_values.items())),
    )


def validate_database_identity(connection: Any, binding: RuntimeBinding) -> RuntimeIdentity:
    try:
        with connection.cursor() as cur:
            cur.execute(
                f"""
                SELECT current_database() AS database_name,
                       COALESCE(inet_server_addr()::text, 'local_socket') AS server_host,
                       environment,
                       marker
                FROM {IDENTITY_TABLE}
                WHERE identity_key='primary'
                """
            )
            row = cur.fetchone()
    except Exception as exc:
        raise RuntimeEnvironmentError("database_environment_marker_missing") from exc
    if not row:
        raise RuntimeEnvironmentError("database_environment_marker_missing")

    data = dict(row)
    database_name = str(data.get("database_name") or "")
    server_host = str(data.get("server_host") or "")
    database_environment = str(data.get("environment") or "").strip().lower()
    marker = str(data.get("marker") or "")
    if database_name != binding.expected_database:
        raise RuntimeEnvironmentError("connected_database_name_mismatch")
    if database_environment != binding.application_environment:
        raise RuntimeEnvironmentError("database_environment_mismatch")
    if marker != binding.expected_marker:
        raise RuntimeEnvironmentError("database_environment_marker_mismatch")

    return RuntimeIdentity(
        application_environment=binding.application_environment,
        database_environment=database_environment,
        marker_fingerprint=fingerprint(marker),
        database_fingerprint=fingerprint(database_name),
        host_fingerprint=fingerprint(server_host),
        match=True,
    )
