"""Surface adapters that observe or enforce canonical decisions (Wave 2).

Default: shadow observe + persist.
Authoritative deny only when canary authority matches the surface/module.
"""

from __future__ import annotations

from typing import Any, Callable

import tenant_control_decision as decision


def observe_or_enforce(
    cur: Any | None,
    *,
    company_code: str,
    surface: str,
    module_key: str | None,
    legacy_allow: bool | None,
    queued_epoch: int | None = None,
    actor_permission_ok: bool | None = None,
    on_authoritative_deny: Callable[[decision.DecisionResult], None] | None = None,
    record_block: bool = True,
    work_kind: str | None = None,
    work_ref: str | None = None,
) -> decision.DecisionResult:
    result = decision.evaluate_decision(
        cur,
        company_code=company_code,
        surface=surface,
        module_key=module_key,
        legacy_allow=legacy_allow,
        queued_epoch=queued_epoch,
        actor_permission_ok=actor_permission_ok,
        persist=True,
    )
    if (
        result.mode == "authoritative"
        and not result.allow
        and cur is not None
        and record_block
    ):
        decision.record_blocked_work(
            cur,
            company_code=company_code,
            work_kind=work_kind or surface,
            reason_code=result.reason_code,
            surface=surface,
            module_key=module_key,
            capability_key=result.capability,
            work_ref=work_ref,
            disposition="reject" if surface in {"apis", "webhooks", "intake"} else "hold",
            queued_epoch=queued_epoch,
            live_epoch=result.activation_epoch,
            correlation_id=result.audit_correlation_id,
            detail=result.detail,
        )
        if on_authoritative_deny is not None:
            on_authoritative_deny(result)
    return result


def legacy_module_checker(checker: Callable[[str, str], bool]) -> Callable[[str, str], bool]:
    return checker
