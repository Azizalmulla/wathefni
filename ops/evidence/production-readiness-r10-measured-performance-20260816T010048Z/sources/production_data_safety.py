"""R3 — Production data safety.

Fixture, seed, matrix, and other mutating ops tooling must never silently
target production. Missing environment or company configuration refuses to
run. Missing tenant context never resolves to the Wathefni canary tenant.

This module is imported by ops scripts *before* they import app.py, so it
must not import the orchestrator.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse, unquote

CONTRACT_VERSION = "r3-data-safety-v1"

NON_PRODUCTION_ACK = "non-production"
PRODUCTION_MAINTENANCE_ACK = "I_UNDERSTAND_THIS_MUTATES_PRODUCTION"

PRODUCTION_ENVS = frozenset({"production", "prod", "live"})
NON_PRODUCTION_ENVS = frozenset(
    {"staging", "stage", "local", "test", "testing", "dev", "development", "ci"}
)
KNOWN_ENVS = PRODUCTION_ENVS | NON_PRODUCTION_ENVS

# Exact production database name. Staging/test names are suffixes of this word
# on purpose (wathefni_staging) — equality, not startswith, is the check.
PRODUCTION_DB_NAMES = frozenset({"wathefni"})
PRODUCTION_MARKERS = frozenset({"wathefni-production-isolation-v1"})

# Identity of the internal canary tenant. Never a default, never a missing-company fallback.
CANARY_COMPANY = "WATHEFNI"

PROTECTED_EMPLOYEE_KEYS = frozenset(
    {
        "WATHEFNI-96599338566",  # Aziz qualification identity
        "WATHEFNI-96550252254",  # Talal qualification identity
    }
)
PROTECTED_PHONES = frozenset({"96599338566", "96550252254"})

# Prefixes that mark an isolated synthetic/test company. WATHEFNI itself is never synthetic.
SYNTHETIC_COMPANY_PREFIXES = (
    "R2",
    "R3",
    "R4",
    "R5",
    "R6",
    "R7",
    "R8",
    "R9",
    "KWDOC",
    "W5C",
    "W2B",
    "SYNTH",
    "TEST",
    "STG",
    "QA",
    "VISQA",
    "LOCAL",
    "CI",
    "SMOKE",
    "PRODBND",
    "HR0",
    "HR1",
    "HR2",
    "HR3",
    "C01",
)

SYNTHETIC_CONNECTOR_KINDS = frozenset({"deterministic_canary"})

_ON = frozenset({"1", "true", "yes", "on", "enabled"})

# Tables a freshly created company must not contain rows in.
CLEAN_BOOTSTRAP_ABSENT_TABLES = (
    "employees",
    "employee_messages",
    "employee_documents",
    "leave_policies",
    "leave_balances",
    "leave_requests",
    "payroll_runs",
    "payslips",
    "company_modules",
    "onboarding_items",
    "attendance_days",
    "shifts",
)


class DataSafetyError(SystemExit):
    """Process-level refusal. Ops scripts die with a clear REFUSE TO RUN message.

    `reason` is the stable machine code. Do not use `.code` — SystemExit.code is
    the exit payload and would overwrite the reason with the full message.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(f"REFUSE TO RUN [{reason}]: {message}")
        self.reason = reason


class MissingCompanyCode(ValueError):
    """Tenant-sensitive work was asked to proceed without a company."""

    def __init__(self, source: str = "") -> None:
        self.error = "company_required"
        self.source = source or ""
        detail = f"company_required:{source}" if source else "company_required"
        super().__init__(detail)


@dataclass(frozen=True)
class FixtureTarget:
    environment: str
    company_code: str
    extra_companies: tuple[str, ...]
    database_name: str
    destructive: bool


def _env(name: str) -> str:
    return str(os.environ.get(name) or "").strip()


def _on(name: str) -> bool:
    return _env(name).lower() in _ON


def normalize_company_code(value: str | None) -> str | None:
    company = str(value or "").strip().upper()
    return company or None


def require_company_code(company_code: str | None, *, source: str = "") -> str:
    """Fail closed. Never substitute WATHEFNI (or any other tenant) for a missing company."""
    company = normalize_company_code(company_code)
    if not company:
        raise MissingCompanyCode(source)
    return company


def require_explicit_environment() -> str:
    raw = _env("WATHEFNI_ENV")
    if not raw:
        raise DataSafetyError(
            "environment_required",
            "WATHEFNI_ENV is not set. Missing target configuration refuses to run; it never defaults to production.",
        )
    env = raw.lower()
    if env not in KNOWN_ENVS:
        raise DataSafetyError(
            "environment_unknown",
            f"WATHEFNI_ENV={raw!r} is not a recognised target. Set staging, local, test, or production explicitly.",
        )
    return env


def _database_name_from_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
        path = unquote(parsed.path or "").lstrip("/")
        return path.split("/")[0].split("?")[0].strip()
    except Exception:
        return ""


def configured_database_name() -> str:
    for key in ("WATHEFNI_EXPECTED_DATABASE_NAME", "PGDATABASE"):
        value = _env(key)
        if value:
            return value
    for key in ("DATABASE_URL", "WATHEFNI_DATABASE_URL", "POSTGRES_URL"):
        name = _database_name_from_url(_env(key))
        if name:
            return name
    return ""


def configured_marker() -> str:
    return _env("WATHEFNI_DATABASE_ENVIRONMENT_MARKER")


def configured_postgres_env_path() -> str:
    return _env("WATHEFNI_POSTGRES_ENV")


def is_production_postgres_env_path(path: str | None = None) -> bool:
    raw = str(path if path is not None else configured_postgres_env_path()).strip()
    if not raw:
        return False
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    lowered = name.lower()
    if "staging" in lowered or "test" in lowered or "local" in lowered or "dev" in lowered:
        return False
    return lowered in {"postgres.env", "wathefni-postgres.env"}


def is_production_shaped(*, environment: str | None = None) -> bool:
    """True when the configured target looks like the live production database."""
    env = (environment or _env("WATHEFNI_ENV")).strip().lower()
    if env in PRODUCTION_ENVS:
        return True
    db_name = configured_database_name()
    if db_name in PRODUCTION_DB_NAMES:
        return True
    if configured_marker() in PRODUCTION_MARKERS:
        return True
    if is_production_postgres_env_path():
        return True
    return False


def require_non_production_target() -> str:
    env = require_explicit_environment()
    if env in PRODUCTION_ENVS:
        raise DataSafetyError(
            "production_blocked",
            "Fixture/seed/matrix tooling is hard-blocked against production. Use an isolated staging or local target.",
        )
    if is_production_shaped(environment=env):
        raise DataSafetyError(
            "production_shaped_target",
            "Target database/marker/secrets path is production-shaped. Fixture tooling refuses to run.",
        )
    return env


def require_non_production_ack(ack: str | None = None) -> None:
    value = str(ack or _env("WATHEFNI_DATA_SAFETY_ACK")).strip()
    if value != NON_PRODUCTION_ACK:
        raise DataSafetyError(
            "non_production_ack_required",
            f"Set WATHEFNI_DATA_SAFETY_ACK={NON_PRODUCTION_ACK} (or --ack-non-production {NON_PRODUCTION_ACK}). "
            "There is no --force switch.",
        )


def require_non_production_ops(*, company_code: str | None = None) -> str:
    """Mutating canary/ops tooling: explicit env, never production, explicit ack.

    Unlike require_fixture_tooling, this allows a named canary tenant such as
    WATHEFNI when the operator also sets WATHEFNI_ALLOW_CANARY_FIXTURES=1.
    Missing company is still refused when company_code is passed.
    """
    env = require_non_production_target()
    require_non_production_ack()
    if company_code is not None:
        company = require_explicit_company(company_code)
        if company == CANARY_COMPANY and not canary_fixtures_allowed():
            raise DataSafetyError(
                "synthetic_company_required",
                "WATHEFNI is not an inferred fixture tenant. Set WATHEFNI_ALLOW_CANARY_FIXTURES=1 "
                "to mutate the isolated canary on a non-production target.",
            )
    return env


def require_production_maintenance(*, operation: str) -> None:
    """Deliberate production mutation. Not a fixture escape hatch."""
    env = require_explicit_environment()
    if env not in PRODUCTION_ENVS:
        raise DataSafetyError(
            "maintenance_not_production",
            "Production maintenance controls are only valid when WATHEFNI_ENV=production is set explicitly.",
        )
    named = str(operation or "").strip()
    if not named or named != _env("WATHEFNI_PRODUCTION_MAINTENANCE_OPERATION"):
        raise DataSafetyError(
            "maintenance_operation_required",
            "Set WATHEFNI_PRODUCTION_MAINTENANCE_OPERATION to the exact named operation. This is not --force.",
        )
    if _env("WATHEFNI_PRODUCTION_MAINTENANCE_ACK") != PRODUCTION_MAINTENANCE_ACK:
        raise DataSafetyError(
            "maintenance_ack_required",
            f"Set WATHEFNI_PRODUCTION_MAINTENANCE_ACK={PRODUCTION_MAINTENANCE_ACK} for operation {named!r}.",
        )


def is_synthetic_company(company_code: str | None) -> bool:
    company = normalize_company_code(company_code)
    if not company or company == CANARY_COMPANY:
        return False
    allowlist = {
        part.strip().upper()
        for part in _env("WATHEFNI_SYNTHETIC_COMPANIES").split(",")
        if part.strip()
    }
    if company in allowlist:
        return True
    if "SYNTH" in company or "TEST" in company:
        return True
    return any(company.startswith(prefix) for prefix in SYNTHETIC_COMPANY_PREFIXES)


def canary_fixtures_allowed() -> bool:
    return _on("WATHEFNI_ALLOW_CANARY_FIXTURES")


def require_explicit_company(company_code: str | None, *, source: str = "company") -> str:
    company = normalize_company_code(company_code)
    if not company:
        raise DataSafetyError(
            "company_required",
            f"An explicit {source} is required. There is no default company and WATHEFNI is never inferred.",
        )
    return company


def require_fixture_company(company_code: str | None, *, source: str = "company") -> str:
    company = require_explicit_company(company_code, source=source)
    if is_synthetic_company(company):
        return company
    if company == CANARY_COMPANY and canary_fixtures_allowed():
        return company
    raise DataSafetyError(
        "synthetic_company_required",
        f"{company} is not an isolated synthetic/test company. Fixture tooling will not write it.",
    )


def refuse_protected_identities(
    *,
    employee_keys: Iterable[str] = (),
    phones: Iterable[str] = (),
) -> None:
    for key in employee_keys:
        normalized = str(key or "").strip().upper()
        if normalized in PROTECTED_EMPLOYEE_KEYS:
            raise DataSafetyError(
                "protected_identity",
                f"Refusing to mutate qualification identity {normalized}.",
            )
    for phone in phones:
        digits = re.sub(r"\D+", "", str(phone or ""))
        if digits in PROTECTED_PHONES:
            raise DataSafetyError(
                "protected_identity",
                f"Refusing to mutate qualification phone {digits}.",
            )


def require_destructive_scope(companies: Iterable[str | None]) -> list[str]:
    scoped: list[str] = []
    for raw in companies:
        text = str(raw or "").strip()
        if not text or text in {"*", "%", "ALL", "all"}:
            raise DataSafetyError(
                "wildcard_tenant_forbidden",
                "Destructive fixture/matrix operations cannot target a wildcard tenant.",
            )
        company = require_fixture_company(text, source="destructive company")
        scoped.append(company)
    if not scoped:
        raise DataSafetyError(
            "destructive_scope_required",
            "Destructive operations require an explicit company list.",
        )
    return scoped


def scoped_delete_company_modules(companies: Iterable[str | None]) -> tuple[str, tuple[list[str]]]:
    """The only allowed company_modules DELETE shape for fixture/matrix tooling."""
    scoped = require_destructive_scope(companies)
    return "DELETE FROM company_modules WHERE company_code = ANY(%s)", (scoped,)


def require_fixture_tooling(
    *,
    company_code: str | None,
    extra_companies: Iterable[str | None] = (),
    destructive: bool = False,
    employee_keys: Iterable[str] = (),
    phones: Iterable[str] = (),
    ack: str | None = None,
) -> FixtureTarget:
    env = require_non_production_target()
    require_non_production_ack(ack)
    company = require_fixture_company(company_code)
    extras = tuple(require_fixture_company(item, source="extra company") for item in extra_companies if item)
    if destructive:
        require_destructive_scope((company,) + extras)
    refuse_protected_identities(employee_keys=employee_keys, phones=phones)
    return FixtureTarget(
        environment=env,
        company_code=company,
        extra_companies=extras,
        database_name=configured_database_name(),
        destructive=destructive,
    )


def _argv_value(flag: str, argv: list[str] | None = None) -> str | None:
    args = list(sys.argv if argv is None else argv)
    prefix = flag + "="
    for index, token in enumerate(args):
        if token == flag and index + 1 < len(args):
            return str(args[index + 1])
        if token.startswith(prefix):
            return str(token[len(prefix) :])
    return None


def activate_fixture_tooling_from_argv(
    *,
    extra_companies: Iterable[str | None] = (),
    employee_keys: Iterable[str] = (),
    phones: Iterable[str] = (),
) -> FixtureTarget:
    """Import-time hook for ops-seed scripts. Runs before app.py is imported."""
    if {"-h", "--help"} & set(sys.argv):
        return FixtureTarget(
            environment=_env("WATHEFNI_ENV") or "unset",
            company_code="HELP",
            extra_companies=(),
            database_name="",
            destructive=False,
        )
    company = _argv_value("--company") or _env("WATHEFNI_COMPANY_CODE")
    ack = _argv_value("--ack-non-production") or _env("WATHEFNI_DATA_SAFETY_ACK")
    if ack:
        os.environ["WATHEFNI_DATA_SAFETY_ACK"] = ack
    destructive = "--cleanup" in sys.argv
    target = require_fixture_tooling(
        company_code=company,
        extra_companies=extra_companies,
        destructive=destructive,
        employee_keys=employee_keys,
        phones=phones,
        ack=ack,
    )
    os.environ["WATHEFNI_COMPANY_CODE"] = target.company_code
    return target


def synthetic_connectors_allowed(company_code: str | None) -> bool:
    """Isolated test capability. Off by default in every environment, including canary."""
    if not _on("WATHEFNI_SYNTHETIC_CONNECTORS"):
        return False
    company = normalize_company_code(company_code)
    if not company:
        return False
    allowlist = {
        part.strip().upper()
        for part in _env("WATHEFNI_SYNTHETIC_CONNECTOR_COMPANIES").split(",")
        if part.strip()
    }
    if company in allowlist:
        return True
    return is_synthetic_company(company)


def require_synthetic_connector_kind(company_code: str | None, connector_kind: str | None) -> None:
    kind = str(connector_kind or "").strip()
    if kind not in SYNTHETIC_CONNECTOR_KINDS:
        return
    if synthetic_connectors_allowed(company_code):
        return
    raise DataSafetyError(
        "synthetic_connector_forbidden",
        "Synthetic fixture sources are disabled unless WATHEFNI_SYNTHETIC_CONNECTORS=1 "
        "and the company is an isolated synthetic/test tenant.",
    )


def classify_wathefni_fallback(snippet: str) -> str:
    """Classify a source occurrence of a WATHEFNI default for the R3 inventory."""
    text = " ".join(str(snippet or "").split())
    if "or \"WATHEFNI\"" in text or "or 'WATHEFNI'" in text:
        return "implicit_canary_fallback"
    if "WATHEFNI_DEFAULT_COMPANY" in text:
        return "env_default_company"
    if f'"{CANARY_COMPANY}"' in text or f"'{CANARY_COMPANY}'" in text:
        return "explicit_canary_identity"
    return "unknown"


def production_default_patterns() -> tuple[str, ...]:
    return (
        'setdefault("WATHEFNI_ENV", "production")',
        "setdefault('WATHEFNI_ENV', 'production')",
        'setdefault("WATHEFNI_ENVIRONMENT", "production")',
        'setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")',
        'setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")',
        'setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")',
        'setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")',
    )


def looks_like_unscoped_company_modules_delete(sql: str) -> bool:
    text = " ".join(str(sql or "").split())
    if "DELETE FROM company_modules" not in text:
        return False
    return "company_code" not in text.lower()
