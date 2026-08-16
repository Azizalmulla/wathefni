"""Reusable disposable fixtures for Interaction Assurance (IAX).

Contract: ops/INTERACTION_ASSURANCE_PROGRAM/CLEANUP_CONTRACT.md
Naming: ops/INTERACTION_ASSURANCE_PROGRAM/NAMING.md

Safety:
  - WATHEFNI in-tenant synthetics only by default
  - Marker + phone-prefix scoped create/cleanup
  - Never deletes non-marker employees
  - Idempotent cleanup
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

CONTRACT_VERSION = "iax-cleanup-1.0.0"
MARKER = "IAX-SYNTH|"
MARKERS: tuple[str, ...] = ("IAX", MARKER)
PHONE_PREFIX = "965542"
PHONE_PREFIXES: tuple[str, ...] = (PHONE_PREFIX,)
JSON_FLAG = "iax_synth"
DEFAULT_COMPANY = "WATHEFNI"


@dataclass(frozen=True)
class FixtureScope:
    company_code: str = DEFAULT_COMPANY
    tag: str = ""
    markers: Sequence[str] = field(default_factory=lambda: MARKERS)
    phone_prefixes: Sequence[str] = field(default_factory=lambda: PHONE_PREFIXES)
    employee_json_flag: str = JSON_FLAG

    def __post_init__(self) -> None:
        if not self.markers:
            raise ValueError("FixtureScope.markers must be non-empty")
        if not self.phone_prefixes:
            raise ValueError("FixtureScope.phone_prefixes must be non-empty")
        if self.company_code.upper() != DEFAULT_COMPANY and not self.company_code.upper().startswith("IAX"):
            raise ValueError("IAX fixtures refuse non-WATHEFNI companies unless code starts with IAX")


@dataclass
class SyntheticEmployee:
    company_code: str
    employee_key: str
    name: str
    phone: str
    tag: str
    raw_json: dict[str, Any]


def new_tag() -> str:
    return uuid.uuid4().hex[:8]


def _digit_suffix(tag: str, width: int = 5) -> str:
    digits = re.sub(r"\D", "", tag) or "0"
    # Mix hex → digits for uniqueness within the reserved prefix.
    mixed = "".join(str(int(ch, 16) % 10) for ch in tag.lower())
    return (digits + mixed + "00000")[:width]


def phone_for_tag(tag: str, *, slot: int = 0) -> str:
    base = _digit_suffix(tag, 4)
    return f"{PHONE_PREFIX}{slot}{base}"


def employee_key_for_tag(tag: str, *, role: str = "emp") -> str:
    return f"WATHEFNI-IAX-{role.upper()}-{tag.upper()}"


def display_name_for_tag(tag: str, *, role: str = "emp") -> str:
    return f"{MARKER} {role} {tag}"


def make_scope(*, company_code: str = DEFAULT_COMPANY, tag: str | None = None) -> FixtureScope:
    return FixtureScope(company_code=company_code.upper(), tag=tag or new_tag())


def create_synthetic_employee(
    legacy: Any,
    *,
    scope: FixtureScope,
    role: str = "emp",
    extra: Mapping[str, Any] | None = None,
) -> SyntheticEmployee:
    """Insert one disposable employee. Safe to re-run (upserts by key)."""
    tag = scope.tag or new_tag()
    key = employee_key_for_tag(tag, role=role)
    phone = phone_for_tag(tag, slot=0 if role == "emp" else 1)
    name = display_name_for_tag(tag, role=role)
    payload = {
        JSON_FLAG: True,
        "tag": tag,
        "program": "interaction_assurance",
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **dict(extra or {}),
    }
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s::jsonb, now(), now())
                ON CONFLICT (company_code, employee_key) DO UPDATE SET
                  name = EXCLUDED.name,
                  phone = EXCLUDED.phone,
                  raw_json = EXCLUDED.raw_json,
                  updated_at = now()
                """,
                (scope.company_code, key, name, phone, json.dumps(payload)),
            )
            cur.execute(
                """
                UPDATE employees
                SET employment_status = 'active'
                WHERE company_code = %s AND employee_key = %s
                """,
                (scope.company_code, key),
            )
        conn.commit()
    return SyntheticEmployee(
        company_code=scope.company_code,
        employee_key=key,
        name=name,
        phone=phone,
        tag=tag,
        raw_json=payload,
    )


def count_residuals(legacy: Any, scope: FixtureScope) -> dict[str, int]:
    marker_likes = [f"%{m}%" for m in scope.markers]
    phone_likes = [f"{p}%" for p in scope.phone_prefixes]
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM employees
                WHERE company_code = %s
                  AND (
                    coalesce(raw_json->>%s,'') IN ('true','1')
                    OR employee_key LIKE ANY(%s)
                    OR name LIKE ANY(%s)
                  )
                  AND phone LIKE ANY(%s)
                """,
                (scope.company_code, scope.employee_json_flag, marker_likes, marker_likes, phone_likes),
            )
            employees = int(cur.fetchone()["n"])
            # Open HR tasks tagged for this program (best-effort; table may vary).
            tasks = 0
            try:
                cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM hr_tasks
                    WHERE company_code = %s
                      AND (
                        coalesce(title,'') LIKE ANY(%s)
                        OR coalesce(details::text,'') LIKE ANY(%s)
                      )
                    """,
                    (scope.company_code, marker_likes, marker_likes),
                )
                tasks = int(cur.fetchone()["n"])
            except Exception:
                tasks = 0
                conn.rollback()
    return {"employees": employees, "hr_tasks": tasks, "total": employees + tasks}


def cleanup_scope(legacy: Any, scope: FixtureScope, *, allow_authority_cleanup: bool = True) -> dict[str, Any]:
    """Marker+phone scoped cleanup. Idempotent. Never touches non-marker rows."""
    if allow_authority_cleanup:
        try:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT set_config('wathefni.allow_authority_cleanup','1', true)")
                conn.commit()
        except Exception:
            pass

    marker_likes = [f"%{m}%" for m in scope.markers]
    phone_likes = [f"{p}%" for p in scope.phone_prefixes]
    deleted: dict[str, int] = {}

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            # Child tables that may reference synthetic employees (best-effort / optional).
            optional_child_deletes: list[tuple[str, str]] = [
                (
                    "hr_tasks",
                    """
                    DELETE FROM hr_tasks
                    WHERE company_code = %s
                      AND (
                        coalesce(title,'') LIKE ANY(%s)
                        OR coalesce(details::text,'') LIKE ANY(%s)
                      )
                    """,
                ),
                (
                    "leave_requests",
                    """
                    DELETE FROM leave_requests
                    WHERE company_code = %s
                      AND employee_key IN (
                        SELECT employee_key FROM employees
                        WHERE company_code = %s
                          AND phone LIKE ANY(%s)
                          AND (
                            coalesce(raw_json->>%s,'') IN ('true','1')
                            OR employee_key LIKE ANY(%s)
                            OR name LIKE ANY(%s)
                          )
                      )
                    """,
                ),
                (
                    "onboarding_items",
                    """
                    DELETE FROM onboarding_items
                    WHERE employee_key IN (
                      SELECT employee_key FROM employees
                      WHERE company_code = %s
                        AND phone LIKE ANY(%s)
                        AND (
                          coalesce(raw_json->>%s,'') IN ('true','1')
                          OR employee_key LIKE ANY(%s)
                          OR name LIKE ANY(%s)
                        )
                    )
                    """,
                ),
                (
                    "employee_onboarding_assignments",
                    """
                    DELETE FROM employee_onboarding_assignments
                    WHERE employee_key IN (
                      SELECT employee_key FROM employees
                      WHERE company_code = %s
                        AND phone LIKE ANY(%s)
                        AND (
                          coalesce(raw_json->>%s,'') IN ('true','1')
                          OR employee_key LIKE ANY(%s)
                          OR name LIKE ANY(%s)
                        )
                    )
                    """,
                ),
            ]
            for table, sql in optional_child_deletes:
                try:
                    if table == "hr_tasks":
                        cur.execute(sql, (scope.company_code, marker_likes, marker_likes))
                    elif table == "leave_requests":
                        cur.execute(
                            sql,
                            (
                                scope.company_code,
                                scope.company_code,
                                phone_likes,
                                scope.employee_json_flag,
                                marker_likes,
                                marker_likes,
                            ),
                        )
                    else:
                        cur.execute(
                            sql,
                            (
                                scope.company_code,
                                phone_likes,
                                scope.employee_json_flag,
                                marker_likes,
                                marker_likes,
                            ),
                        )
                    deleted[table] = int(cur.rowcount or 0)
                except Exception:
                    deleted[table] = 0
                    conn.rollback()
                    # Re-open transaction for remaining deletes
                    cur.execute("SELECT 1")

            cur.execute(
                """
                DELETE FROM employees
                WHERE company_code = %s
                  AND phone LIKE ANY(%s)
                  AND (
                    coalesce(raw_json->>%s,'') IN ('true','1')
                    OR employee_key LIKE ANY(%s)
                    OR name LIKE ANY(%s)
                  )
                """,
                (
                    scope.company_code,
                    phone_likes,
                    scope.employee_json_flag,
                    marker_likes,
                    marker_likes,
                ),
            )
            deleted["employees"] = int(cur.rowcount or 0)
        conn.commit()

    residual = count_residuals(legacy, scope)
    return {
        "contract_version": CONTRACT_VERSION,
        "company_code": scope.company_code,
        "tag": scope.tag,
        "markers": list(scope.markers),
        "phone_prefixes": list(scope.phone_prefixes),
        "deleted": deleted,
        "residual": residual,
        "residual_total": int(residual["total"]),
    }
