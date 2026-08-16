"""Wave 4 orchestration: Person Registry + Talent Pool + owned CV dual-write.

Called after envelope receipts. Does not create Job applications or rewrite
Ranking evidence. Flags default OFF.
"""

from __future__ import annotations

import os
from typing import Any

import inbound_cv_person_registry as person_registry
import inbound_cv_processing as processing
import job_binding_authority as job_binding
import talent_pool_authority as talent_pool
import verified_job_binding_gate as gate

WAVE4_VERSION = "unified-inbound-cv-wave4-v1"
FEATURE_WAVE4 = "WATHEFNI_UNIFIED_INBOUND_CV_WAVE4"


def _env(environ: dict[str, str] | None = None) -> dict[str, str]:
    return environ if environ is not None else os.environ


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def wave4_enabled(environ: dict[str, str] | None = None) -> bool:
    env = _env(environ)
    if _truthy(env.get(FEATURE_WAVE4)):
        return True
    return (
        person_registry.enabled(env)
        or talent_pool.enabled(env)
        or job_binding.enabled(env)
        or gate.gate_enabled(env)
    )


def after_intake_receipt(
    cur: Any,
    *,
    company_code: str,
    subject_id: str | None,
    phone: str | None = None,
    email: str | None = None,
    display_name: str | None = None,
    content_sha256: str | None = None,
    document_id: str | None = None,
    legacy_app_key: str | None = None,
    actionable: bool = False,
    channel: str = "unknown",
    force_identity_review: bool = False,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Link subject → person (safe), upsert Talent Pool, optionally own cv_version."""

    if not wave4_enabled(environ):
        return {"ok": True, "skipped": True, "reason": "wave4_disabled"}

    env = dict(_env(environ))
    person_result = {"skipped": True}
    if subject_id and person_registry.enabled(env):
        person_result = person_registry.ensure_or_link_person_for_subject(
            cur,
            company_code=company_code,
            subject_id=subject_id,
            phone=phone,
            email=email,
            display_name=display_name,
            source=f"intake:{channel}",
            force_identity_review=force_identity_review,
            environ=env,
        )

    person_id = person_result.get("person_id") if isinstance(person_result, dict) else None
    membership_id = person_result.get("membership_id") if isinstance(person_result, dict) else None
    subject_status = str(person_result.get("status") or "")
    # Identity-review / provisional subjects stay non-actionable.
    pool_actionable = bool(actionable and person_id and membership_id and subject_status == "linked")

    tp_result = {"skipped": True}
    if subject_id and talent_pool.enabled(env):
        tp_result = talent_pool.upsert_talent_pool_entry(
            cur,
            company_code=company_code,
            subject_id=subject_id,
            person_id=person_id,
            membership_id=membership_id,
            actionable=pool_actionable,
            status="identity_review" if subject_status == "identity_review" else "active",
            provenance={"channel": channel, "wave": WAVE4_VERSION},
            environ=env,
        )

    cv_result = {"skipped": True}
    if (
        content_sha256
        and document_id
        and processing.cv_version_dual_write_enabled(env)
        and (person_id or subject_id)
    ):
        cv_result = processing.dual_write_cv_version(
            cur,
            company_code=company_code,
            content_sha256=content_sha256,
            legacy_document_id=document_id,
            legacy_app_key=legacy_app_key,
            person_id=person_id,
            subject_id=subject_id,
            provenance={"channel": channel, "wave": WAVE4_VERSION},
            environ=env,
        )
        if (
            not cv_result.get("skipped")
            and tp_result.get("entry_id")
            and cv_result.get("cv_version_id")
            and talent_pool.enabled(env)
        ):
            talent_pool.pin_current_cv_version(
                cur,
                company_code=company_code,
                entry_id=str(tp_result["entry_id"]),
                cv_version_id=str(cv_result["cv_version_id"]),
                environ=env,
            )

    return {
        "ok": True,
        "skipped": False,
        "wave": WAVE4_VERSION,
        "person": person_result,
        "talent_pool": tp_result,
        "cv_version": cv_result,
        "creates_job_application": False,
    }


def promote_with_verified_job_binding(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    position_code: str,
    apply_code: str | None = None,
    job_id: str | None = None,
    human_confirmed: bool = False,
    subject_id: str | None = None,
    person_id: str | None = None,
    membership_id: str | None = None,
    cv_version_id: str | None = None,
    actor_type: str = "hr",
    actor_id: str | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Record consent + verified bindings. Does not invent the application row."""

    if not job_binding.enabled(environ):
        return {"ok": True, "skipped": True, "reason": "job_binding_authority_disabled"}
    if not human_confirmed:
        return {"ok": False, "error": "exact_job_confirmation_required"}

    job_binding.ensure_schema(cur)
    consent_id = job_binding.record_consent(
        cur,
        company_code=company_code,
        consent_kind="exact_job_apply",
        actor_type=actor_type,
        actor_id=actor_id,
        subject_id=subject_id,
        person_id=person_id,
        evidence={
            "app_key": app_key,
            "position_code": position_code,
            "apply_code": apply_code,
            "human_confirmed": True,
        },
    )
    bound = job_binding.bind_application_to_job(
        cur,
        company_code=company_code,
        app_key=app_key,
        position_code=position_code,
        apply_code=apply_code,
        job_id=job_id,
        human_confirmed=True,
        consent_id=consent_id,
        person_id=person_id,
        membership_id=membership_id,
        subject_id=subject_id,
        cv_version_id=cv_version_id,
        environ=environ,
    )
    return {"ok": bool(bound.get("ok")), "consent_id": consent_id, "binding": bound}


def check_downstream_action(
    cur: Any | None,
    *,
    company_code: str,
    app_key: str,
    action: str,
    application: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    decision = gate.assert_verified_job_binding(
        cur,
        company_code=company_code,
        app_key=app_key,
        action=action,
        application=application,
        environ=environ,
    )
    return decision.to_dict()


__all__ = [
    "WAVE4_VERSION",
    "FEATURE_WAVE4",
    "wave4_enabled",
    "after_intake_receipt",
    "promote_with_verified_job_binding",
    "check_downstream_action",
]
