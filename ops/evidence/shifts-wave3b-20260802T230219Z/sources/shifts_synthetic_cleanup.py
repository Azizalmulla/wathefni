"""Shared dependency-aware synthetic cleanup for Shifts Wave 1 / Wave 2 canaries.

Contract version: 1.0.0

Safety rules:
  - Marker + phone-prefix scoped only. Never deletes real (non-marker) rows.
  - Protected shift IDs (production orphan quarantine allowlist) are never deleted.
  - Idempotent: safe to rerun after partial failure.
  - Optional Wave 2 tables use SAVEPOINT so missing tables never abort the txn.
  - Wave 1 and Wave 2 marker families cannot delete each other (distinct markers/phones).

Deletion order (children → parents):
  1. shift_reminder_queue
  2. shift_reconciliation_flags
  3. shift_assignment_versions
  4. shift_lifecycle_flags
  5. shift_orphan_quarantine  (synthetic only; never protected IDs)
  6. shift_swap_events
  7. shift_swap_requests
  8. shift_events
  9. employee_availability_requests
 10. shift_assignments         (excludes protected IDs)
 11. leave_requests            (known IDs + optional reason ILIKE)
 12. shift_seasonal_policies   (optional; name/metadata marker)
 13. employees                 (synthetic flag and/or marker+phone / explicit keys)

Real immutable audit rows outside the marker scope are never touched.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

CLEANUP_CONTRACT_VERSION = "1.0.0"

# Soft-cancelled Wave 1C orphans — immutable production quarantine; never hard-delete.
PRODUCTION_ORPHAN_ALLOWLIST: frozenset[str] = frozenset(
    {
        "0a6e73dd-9c6d-49a0-b253-39a9922ebd70",
        "6a84a671-eb7f-43ea-870e-af859a440467",
        "f9ebecf3-8838-456a-8124-c34c3c7600ca",
    }
)

DELETION_ORDER: tuple[str, ...] = (
    "shift_reminder_queue",
    "shift_reconciliation_flags",
    "shift_assignment_versions",
    "shift_lifecycle_flags",
    "shift_orphan_quarantine",
    "shift_swap_events",
    "shift_swap_requests",
    "shift_events",
    "employee_availability_requests",
    "shift_assignments",
    "leave_requests",
    "shift_seasonal_policies",
    "employees",
)


@dataclass(frozen=True)
class CleanupScope:
    """Marker-scoped synthetic cleanup target."""

    company_code: str
    markers: Sequence[str]
    phone_prefixes: Sequence[str]
    employee_json_flag: str = ""
    tag: str = ""
    extra_employee_keys: Sequence[str] = field(default_factory=tuple)
    leave_reason_ilike: str = ""
    seasonal_name_ilike: str = ""
    protected_shift_ids: frozenset[str] = PRODUCTION_ORPHAN_ALLOWLIST

    def __post_init__(self) -> None:
        if not self.markers:
            raise ValueError("CleanupScope.markers must be non-empty")
        if not self.phone_prefixes:
            raise ValueError("CleanupScope.phone_prefixes must be non-empty")


def wave1b_scope(*, company_code: str = "WATHEFNI", tag: str = "") -> CleanupScope:
    return CleanupScope(
        company_code=company_code,
        markers=("SHW1B", "SHW1B-SYNTH|"),
        phone_prefixes=("965529",),
        employee_json_flag="shw1b",
        tag=tag,
        leave_reason_ilike="%shw1b%",
    )


def wave2b_scope(
    *,
    company_code: str = "WATHEFNI",
    tag: str = "",
    extra_employee_keys: Sequence[str] = (),
) -> CleanupScope:
    return CleanupScope(
        company_code=company_code,
        markers=("SHW2B", "SHW2B-SYNTH|"),
        phone_prefixes=("965530",),
        employee_json_flag="shw2b",
        tag=tag,
        extra_employee_keys=tuple(extra_employee_keys),
        leave_reason_ilike="%shw2b%",
        seasonal_name_ilike="%SHW2B%",
    )


def wave3b_scope(
    *,
    company_code: str = "WATHEFNI",
    tag: str = "",
    extra_employee_keys: Sequence[str] = (),
) -> CleanupScope:
    return CleanupScope(
        company_code=company_code,
        markers=("SHW3B", "SHW3B-SYNTH|"),
        phone_prefixes=("965531",),
        employee_json_flag="shw3b",
        tag=tag,
        extra_employee_keys=tuple(extra_employee_keys),
        leave_reason_ilike="%shw3b%",
        seasonal_name_ilike="%SHW3B%",
    )


def _nil_uuid() -> str:
    return "00000000-0000-0000-0000-000000000000"


def _as_list(ids: Iterable[Any] | None) -> list[str]:
    out: list[str] = []
    for x in ids or []:
        s = str(x or "").strip()
        if s:
            out.append(s)
    return out or [_nil_uuid()]


def _marker_likes(markers: Sequence[str]) -> list[str]:
    return [f"%{m}%" for m in markers]


def _phone_likes(prefixes: Sequence[str]) -> list[str]:
    return [f"{p}%" for p in prefixes]


def _table_exists(cur: Any, table: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name=%s
        LIMIT 1
        """,
        (table,),
    )
    return cur.fetchone() is not None


def _exec_counted(cur: Any, sql: str, params: tuple[Any, ...] | list[Any]) -> int:
    cur.execute(sql, params)
    return int(cur.rowcount or 0)


def _exec_optional(cur: Any, table: str, sql: str, params: tuple[Any, ...] | list[Any]) -> int:
    if not _table_exists(cur, table):
        return 0
    cur.execute("SAVEPOINT sp_shifts_synth_cleanup")
    try:
        n = _exec_counted(cur, sql, params)
        cur.execute("RELEASE SAVEPOINT sp_shifts_synth_cleanup")
        return n
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT sp_shifts_synth_cleanup")
        return 0


def _collect_shift_ids(
    cur: Any,
    scope: CleanupScope,
    known_shift_ids: Sequence[str],
) -> list[str]:
    marker_likes = _marker_likes(scope.markers)
    phone_likes = _phone_likes(scope.phone_prefixes)
    known = _as_list(known_shift_ids)
    # Build OR clauses for markers / phones without accidentally matching sibling waves.
    cur.execute(
        """
        SELECT shift_id::text AS shift_id
        FROM shift_assignments
        WHERE company_code=%s
          AND (
            shift_id::text = ANY(%s)
            OR employee_key LIKE ANY(%s)
            OR coalesce(employee_phone,'') LIKE ANY(%s)
            OR coalesce(source_text,'') LIKE ANY(%s)
            OR coalesce(metadata::text,'') LIKE ANY(%s)
          )
        """,
        (
            scope.company_code,
            known,
            marker_likes,
            phone_likes,
            marker_likes,
            marker_likes,
        ),
    )
    sids = [dict(r)["shift_id"] for r in cur.fetchall()]
    protected = set(scope.protected_shift_ids)
    return [s for s in sids if s not in protected]


def count_synthetic_residuals(
    cur: Any,
    scope: CleanupScope,
    *,
    extra_employee_keys: Sequence[str] | None = None,
) -> dict[str, int]:
    """Count marker-scoped synthetic residuals. Does not mutate."""
    marker_likes = _marker_likes(scope.markers)
    phone_likes = _phone_likes(scope.phone_prefixes)
    protected = list(scope.protected_shift_ids) or [_nil_uuid()]
    extras = list(extra_employee_keys or scope.extra_employee_keys)

    def _count(sql: str, params: tuple[Any, ...] | list[Any], table: str | None = None) -> int:
        if table and not _table_exists(cur, table):
            return 0
        cur.execute(sql, params)
        return int(dict(cur.fetchone())["c"])

    residual = {
        "assignments": _count(
            """
            SELECT count(*) AS c FROM shift_assignments
            WHERE company_code=%s
              AND (employee_key LIKE ANY(%s) OR coalesce(employee_phone,'') LIKE ANY(%s)
                   OR coalesce(metadata::text,'') LIKE ANY(%s))
              AND shift_id::text <> ALL(%s)
            """,
            (scope.company_code, marker_likes, phone_likes, marker_likes, protected),
        ),
        "versions": _count(
            """
            SELECT count(*) AS c FROM shift_assignment_versions
            WHERE company_code=%s
              AND (employee_key LIKE ANY(%s) OR coalesce(previous_employee_key,'') LIKE ANY(%s))
            """,
            (scope.company_code, marker_likes, marker_likes),
            table="shift_assignment_versions",
        ),
        "reminders": _count(
            """
            SELECT count(*) AS c FROM shift_reminder_queue
            WHERE company_code=%s AND employee_key LIKE ANY(%s)
            """,
            (scope.company_code, marker_likes),
            table="shift_reminder_queue",
        ),
        "reconciliation_flags": _count(
            """
            SELECT count(*) AS c FROM shift_reconciliation_flags
            WHERE company_code=%s AND employee_key LIKE ANY(%s)
            """,
            (scope.company_code, marker_likes),
            table="shift_reconciliation_flags",
        ),
        "lifecycle_flags": _count(
            """
            SELECT count(*) AS c FROM shift_lifecycle_flags
            WHERE company_code=%s AND employee_key LIKE ANY(%s)
            """,
            (scope.company_code, marker_likes),
            table="shift_lifecycle_flags",
        ),
        "swaps": _count(
            """
            SELECT count(*) AS c FROM shift_swap_requests
            WHERE company_code=%s
              AND (requester_employee_key LIKE ANY(%s) OR target_employee_key LIKE ANY(%s)
                   OR coalesce(reason,'') LIKE ANY(%s))
            """,
            (scope.company_code, marker_likes, marker_likes, marker_likes),
        ),
        "availability": _count(
            """
            SELECT count(*) AS c FROM employee_availability_requests
            WHERE company_code=%s
              AND (employee_key LIKE ANY(%s) OR coalesce(employee_phone,'') LIKE ANY(%s)
                   OR employee_key = ANY(%s))
            """,
            (scope.company_code, marker_likes, phone_likes, extras or [_nil_uuid()]),
        ),
        "leave": 0,
        "seasonal_policies": 0,
        "employees": 0,
    }

    if scope.leave_reason_ilike:
        residual["leave"] = _count(
            """
            SELECT count(*) AS c FROM leave_requests
            WHERE company_code=%s AND coalesce(reason,'') ILIKE %s
            """,
            (scope.company_code, scope.leave_reason_ilike),
        )
    if scope.seasonal_name_ilike and _table_exists(cur, "shift_seasonal_policies"):
        residual["seasonal_policies"] = _count(
            """
            SELECT count(*) AS c FROM shift_seasonal_policies
            WHERE company_code=%s AND name ILIKE %s
            """,
            (scope.company_code, scope.seasonal_name_ilike),
            table="shift_seasonal_policies",
        )

    flag = scope.employee_json_flag
    if flag:
        residual["employees"] = _count(
            """
            SELECT count(*) AS c FROM employees
            WHERE company_code=%s AND (
              (coalesce(raw_json->>%s,'')='true'
                AND (employee_key LIKE ANY(%s) OR phone LIKE ANY(%s)))
              OR employee_key = ANY(%s)
            )
            """,
            (scope.company_code, flag, marker_likes, phone_likes, extras or [_nil_uuid()]),
        )
    else:
        residual["employees"] = _count(
            """
            SELECT count(*) AS c FROM employees
            WHERE company_code=%s AND (
              (employee_key LIKE ANY(%s) AND phone LIKE ANY(%s))
              OR employee_key = ANY(%s)
            )
            """,
            (scope.company_code, marker_likes, phone_likes, extras or [_nil_uuid()]),
        )

    residual["total"] = int(sum(residual.values()))
    return residual


def cleanup_synthetic_scope(
    db_connect: Callable[[], Any],
    scope: CleanupScope,
    *,
    known_ids: Mapping[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Delete marker-scoped synthetic rows in dependency order; return deleted + residual."""
    ids = dict(known_ids or {})
    known_shifts = _as_list(ids.get("shift_ids"))
    known_swaps = _as_list(ids.get("swap_ids"))
    known_avail = _as_list(ids.get("availability_ids"))
    known_leave = _as_list(ids.get("leave_ids"))
    known_policies = _as_list(ids.get("policy_ids"))
    extras = list(scope.extra_employee_keys) or _as_list(ids.get("extra_employee_keys"))
    # Also accept gate key from nested employee_keys.gate
    emp_keys = ids.get("employee_keys") or {}
    if isinstance(emp_keys, dict) and emp_keys.get("gate"):
        extras.append(str(emp_keys["gate"]))
    extras = [e for e in extras if e and e != _nil_uuid()]

    marker_likes = _marker_likes(scope.markers)
    phone_likes = _phone_likes(scope.phone_prefixes)
    deleted: dict[str, int] = {k: 0 for k in DELETION_ORDER}
    shift_ids: list[str] = []

    with db_connect() as conn:
        with conn.cursor() as cur:
            shift_ids = _collect_shift_ids(cur, scope, known_shifts)
            sids = shift_ids or [_nil_uuid()]

            if dry_run:
                residual = count_synthetic_residuals(cur, scope, extra_employee_keys=extras)
                conn.rollback()
                return {
                    "contract_version": CLEANUP_CONTRACT_VERSION,
                    "dry_run": True,
                    "markers": list(scope.markers),
                    "phone_prefixes": list(scope.phone_prefixes),
                    "would_delete_shift_ids": [s for s in shift_ids],
                    "residual": residual,
                    "residual_total": residual["total"],
                    "total": residual["total"],
                    "deletion_order": list(DELETION_ORDER),
                }

            # 1 reminders
            deleted["shift_reminder_queue"] = _exec_optional(
                cur,
                "shift_reminder_queue",
                """
                DELETE FROM shift_reminder_queue
                WHERE company_code=%s
                  AND (shift_id::text = ANY(%s) OR employee_key LIKE ANY(%s))
                """,
                (scope.company_code, sids, marker_likes),
            )
            # 2 recon flags
            deleted["shift_reconciliation_flags"] = _exec_optional(
                cur,
                "shift_reconciliation_flags",
                """
                DELETE FROM shift_reconciliation_flags
                WHERE company_code=%s
                  AND (shift_id::text = ANY(%s) OR employee_key LIKE ANY(%s))
                """,
                (scope.company_code, sids, marker_likes),
            )
            # 3 versions
            deleted["shift_assignment_versions"] = _exec_optional(
                cur,
                "shift_assignment_versions",
                """
                DELETE FROM shift_assignment_versions
                WHERE company_code=%s
                  AND (shift_id::text = ANY(%s)
                       OR employee_key LIKE ANY(%s)
                       OR coalesce(previous_employee_key,'') LIKE ANY(%s))
                """,
                (scope.company_code, sids, marker_likes, marker_likes),
            )
            # 4 lifecycle flags
            deleted["shift_lifecycle_flags"] = _exec_optional(
                cur,
                "shift_lifecycle_flags",
                """
                DELETE FROM shift_lifecycle_flags
                WHERE company_code=%s
                  AND (shift_id::text = ANY(%s) OR employee_key LIKE ANY(%s))
                """,
                (scope.company_code, sids, marker_likes),
            )
            # 5 orphan quarantine (synthetic only; never protected)
            deleted["shift_orphan_quarantine"] = _exec_optional(
                cur,
                "shift_orphan_quarantine",
                """
                DELETE FROM shift_orphan_quarantine
                WHERE company_code=%s
                  AND shift_id::text = ANY(%s)
                  AND shift_id::text <> ALL(%s)
                """,
                (scope.company_code, sids, list(scope.protected_shift_ids) or [_nil_uuid()]),
            )
            # 6 swap events
            deleted["shift_swap_events"] = _exec_optional(
                cur,
                "shift_swap_events",
                """
                DELETE FROM shift_swap_events WHERE swap_id IN (
                  SELECT swap_id FROM shift_swap_requests
                  WHERE company_code=%s
                    AND (requester_employee_key LIKE ANY(%s)
                         OR target_employee_key LIKE ANY(%s)
                         OR coalesce(reason,'') LIKE ANY(%s)
                         OR swap_id::text = ANY(%s))
                )
                """,
                (scope.company_code, marker_likes, marker_likes, marker_likes, known_swaps),
            )
            # 7 swaps
            deleted["shift_swap_requests"] = _exec_counted(
                cur,
                """
                DELETE FROM shift_swap_requests
                WHERE company_code=%s
                  AND (requester_employee_key LIKE ANY(%s)
                       OR target_employee_key LIKE ANY(%s)
                       OR coalesce(reason,'') LIKE ANY(%s)
                       OR swap_id::text = ANY(%s))
                """,
                (scope.company_code, marker_likes, marker_likes, marker_likes, known_swaps),
            )
            # 8 events
            deleted["shift_events"] = _exec_counted(
                cur,
                "DELETE FROM shift_events WHERE company_code=%s AND shift_id::text = ANY(%s)",
                (scope.company_code, sids),
            )
            # 9 availability
            deleted["employee_availability_requests"] = _exec_counted(
                cur,
                """
                DELETE FROM employee_availability_requests
                WHERE company_code=%s
                  AND (employee_key LIKE ANY(%s)
                       OR coalesce(employee_phone,'') LIKE ANY(%s)
                       OR availability_id::text = ANY(%s)
                       OR employee_key = ANY(%s))
                """,
                (
                    scope.company_code,
                    marker_likes,
                    phone_likes,
                    known_avail,
                    extras or [_nil_uuid()],
                ),
            )
            # 10 assignments
            deleted["shift_assignments"] = _exec_counted(
                cur,
                """
                DELETE FROM shift_assignments
                WHERE company_code=%s
                  AND shift_id::text = ANY(%s)
                  AND shift_id::text <> ALL(%s)
                """,
                (scope.company_code, sids, list(scope.protected_shift_ids) or [_nil_uuid()]),
            )
            # Also catch marker/phone leftovers not in sids snapshot (idempotent rerun)
            deleted["shift_assignments"] += _exec_counted(
                cur,
                """
                DELETE FROM shift_assignments
                WHERE company_code=%s
                  AND (employee_key LIKE ANY(%s) OR coalesce(employee_phone,'') LIKE ANY(%s)
                       OR coalesce(metadata::text,'') LIKE ANY(%s))
                  AND shift_id::text <> ALL(%s)
                """,
                (
                    scope.company_code,
                    marker_likes,
                    phone_likes,
                    marker_likes,
                    list(scope.protected_shift_ids) or [_nil_uuid()],
                ),
            )
            # 11 leave
            leave_n = 0
            if known_leave and known_leave != [_nil_uuid()]:
                leave_n += _exec_counted(
                    cur,
                    "DELETE FROM leave_requests WHERE company_code=%s AND leave_id::text = ANY(%s)",
                    (scope.company_code, known_leave),
                )
            if scope.leave_reason_ilike:
                leave_n += _exec_counted(
                    cur,
                    "DELETE FROM leave_requests WHERE company_code=%s AND coalesce(reason,'') ILIKE %s",
                    (scope.company_code, scope.leave_reason_ilike),
                )
            deleted["leave_requests"] = leave_n
            # 12 seasonal
            if scope.seasonal_name_ilike:
                deleted["shift_seasonal_policies"] = _exec_optional(
                    cur,
                    "shift_seasonal_policies",
                    """
                    DELETE FROM shift_seasonal_policies
                    WHERE company_code=%s
                      AND (name ILIKE %s OR policy_id::text = ANY(%s)
                           OR coalesce(metadata::text,'') LIKE ANY(%s))
                    """,
                    (
                        scope.company_code,
                        scope.seasonal_name_ilike,
                        known_policies,
                        marker_likes,
                    ),
                )
            # 13 employees
            flag = scope.employee_json_flag
            if flag:
                deleted["employees"] = _exec_counted(
                    cur,
                    """
                    DELETE FROM employees
                    WHERE company_code=%s AND (
                      (coalesce(raw_json->>%s,'')='true'
                        AND (employee_key LIKE ANY(%s) OR phone LIKE ANY(%s)))
                      OR employee_key = ANY(%s)
                    )
                    """,
                    (
                        scope.company_code,
                        flag,
                        marker_likes,
                        phone_likes,
                        extras or [_nil_uuid()],
                    ),
                )
            else:
                deleted["employees"] = _exec_counted(
                    cur,
                    """
                    DELETE FROM employees
                    WHERE company_code=%s AND (
                      (employee_key LIKE ANY(%s) AND phone LIKE ANY(%s))
                      OR employee_key = ANY(%s)
                    )
                    """,
                    (
                        scope.company_code,
                        marker_likes,
                        phone_likes,
                        extras or [_nil_uuid()],
                    ),
                )

            residual = count_synthetic_residuals(cur, scope, extra_employee_keys=extras)
            conn.commit()

    total = int(residual["total"])
    return {
        "contract_version": CLEANUP_CONTRACT_VERSION,
        "dry_run": False,
        "markers": list(scope.markers),
        "phone_prefixes": list(scope.phone_prefixes),
        "tag": scope.tag,
        "deleted_shift_ids": shift_ids,
        "deleted": deleted,
        "deletion_order": list(DELETION_ORDER),
        "residual": residual,
        "residual_total": total,
        "total": total,
        # Wave 1B legacy flat keys
        "residual_assignments": residual["assignments"],
        "residual_swaps": residual["swaps"],
        "residual_employees": residual["employees"],
    }
