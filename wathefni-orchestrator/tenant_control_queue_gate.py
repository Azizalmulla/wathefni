"""Shared worker/queue claim gate for Wave 2/3 activation epochs + lifecycle."""

from __future__ import annotations

from typing import Any

import tenant_control_decision as decision
import tenant_control_surfaces as surfaces


def allow_queue_claim(
    cur: Any,
    *,
    company_code: str,
    module_key: str | None,
    queued_epoch: int | None,
    work_kind: str,
    work_ref: str | None = None,
    legacy_allow: bool = True,
    surface: str = "queue_claims",
) -> decision.DecisionResult:
    result = surfaces.observe_or_enforce(
        cur,
        company_code=company_code,
        surface=surface,
        module_key=module_key,
        legacy_allow=legacy_allow,
        queued_epoch=queued_epoch,
        work_kind=work_kind,
        work_ref=work_ref,
        record_block=True,
    )
    return result


def allow_worker_side_effect(
    cur: Any,
    *,
    company_code: str,
    module_key: str | None,
    queued_epoch: int | None,
    work_kind: str,
    work_ref: str | None = None,
    legacy_allow: bool = True,
) -> decision.DecisionResult:
    return allow_queue_claim(
        cur,
        company_code=company_code,
        module_key=module_key,
        queued_epoch=queued_epoch,
        work_kind=work_kind,
        work_ref=work_ref,
        legacy_allow=legacy_allow,
        surface="workers",
    )


def allow_intake(
    cur: Any,
    *,
    company_code: str,
    channel: str,
    legacy_allow: bool = True,
) -> decision.DecisionResult:
    return surfaces.observe_or_enforce(
        cur,
        company_code=company_code,
        surface="intake",
        module_key="pre_hiring",
        legacy_allow=legacy_allow,
        work_kind=f"intake:{channel}",
        record_block=True,
    )


def allow_webhook(
    cur: Any,
    *,
    company_code: str,
    provider: str,
    legacy_allow: bool = True,
) -> decision.DecisionResult:
    return surfaces.observe_or_enforce(
        cur,
        company_code=company_code,
        surface="webhooks",
        module_key=None,
        legacy_allow=legacy_allow,
        work_kind=f"webhook:{provider}",
        record_block=True,
    )


def stamp_activation_epoch(cur: Any, company_code: str, module_key: str | None = None) -> int:
    tenant = decision.load_tenant_state(cur, company_code)
    if not tenant:
        return 1
    if module_key:
        state = decision.load_module_state(cur, tenant["tenant_id"], module_key)
        if state and state.get("activation_epoch") is not None:
            return int(state["activation_epoch"])
    return int(tenant.get("activation_epoch") or 1)


def persist_work_epoch(
    cur: Any,
    *,
    company_code: str,
    work_kind: str,
    work_ref: str,
    module_key: str | None = None,
    activation_epoch: int | None = None,
) -> int:
    epoch = int(
        activation_epoch
        if activation_epoch is not None
        else stamp_activation_epoch(cur, company_code, module_key)
    )
    try:
        cur.execute(
            """
            INSERT INTO tc_worker_epoch_stamps (
              company_code, work_kind, work_ref, module_key, activation_epoch
            ) VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (company_code, work_kind, work_ref) DO UPDATE SET
              activation_epoch = EXCLUDED.activation_epoch,
              module_key = EXCLUDED.module_key
            """,
            (company_code.upper(), work_kind, str(work_ref), module_key, epoch),
        )
    except Exception:
        pass
    return epoch


def load_work_epoch(cur: Any, *, company_code: str, work_kind: str, work_ref: str) -> int | None:
    try:
        cur.execute(
            """
            SELECT activation_epoch
            FROM tc_worker_epoch_stamps
            WHERE company_code=%s AND work_kind=%s AND work_ref=%s
            LIMIT 1
            """,
            (company_code.upper(), work_kind, str(work_ref)),
        )
        row = cur.fetchone()
        if not row:
            return None
        return int(row["activation_epoch"] if isinstance(row, dict) else row[0])
    except Exception:
        return None


def gate_or_skip(
    cur: Any,
    *,
    company_code: str,
    module_key: str | None,
    work_kind: str,
    work_ref: str,
    queued_epoch: int | None = None,
    surface: str = "workers",
) -> tuple[bool, decision.DecisionResult]:
    """Return (allowed, decision). Skip side effects when authoritative deny."""
    epoch = queued_epoch
    if epoch is None:
        epoch = load_work_epoch(cur, company_code=company_code, work_kind=work_kind, work_ref=work_ref)
    result = allow_queue_claim(
        cur,
        company_code=company_code,
        module_key=module_key,
        queued_epoch=epoch,
        work_kind=work_kind,
        work_ref=work_ref,
        legacy_allow=True,
        surface=surface,
    )
    if result.mode == "authoritative" and not result.allow:
        return False, result
    return True, result
