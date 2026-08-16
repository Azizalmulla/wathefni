"""Wave 3 additive channel adapters for unified inbound CV intake.

Manual dashboard, unsolicited WhatsApp, and job-specific WhatsApp adapters
dual-write into the shared envelope and observe shared processing authorities.
Live email remains authoritative. Live WhatsApp/manual outcome paths remain
authoritative until an explicit cutover (not this wave).

No Job application is created from these adapters without exact Job selection
and confirmation upstream (Stage B / intake_admit).
"""

from __future__ import annotations

import os
from typing import Any

import inbound_cv_intake as intake
import inbound_cv_processing as processing
import inbound_cv_wave4 as wave4

ADAPTER_VERSION = "unified-inbound-cv-adapters-v1"
FEATURE_ADAPTERS = "WATHEFNI_UNIFIED_INBOUND_CV_ADAPTERS"
FEATURE_SHARED_PROCESSING = "WATHEFNI_UNIFIED_ADAPTER_SHARED_PROCESSING"

ADAPTERS = ("manual_upload", "whatsapp_unsolicited", "whatsapp_job")


def _env(environ: dict[str, str] | None = None) -> dict[str, str]:
    return environ if environ is not None else os.environ


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def adapters_enabled(environ: dict[str, str] | None = None) -> bool:
    """Master Wave 3 adapter dual-write. Default OFF."""

    return _truthy(_env(environ).get(FEATURE_ADAPTERS)) or intake.dual_write_enabled(environ)


def shared_processing_enabled(environ: dict[str, str] | None = None) -> bool:
    """When ON, adapters record shared stage observations / provider plans."""

    return _truthy(_env(environ).get(FEATURE_SHARED_PROCESSING)) or processing.processing_feature_enabled(
        environ
    )


def assert_no_job_without_exact_confirmation(
    *,
    job_selected: bool,
    human_confirmed: bool,
    create_application: bool,
) -> dict[str, Any]:
    """Hard gate: adapters must not invent Job applications."""

    if create_application and not (job_selected and human_confirmed):
        return {
            "allowed": False,
            "error": "exact_job_confirmation_required",
            "job_selected": bool(job_selected),
            "human_confirmed": bool(human_confirmed),
        }
    return {
        "allowed": True,
        "job_selected": bool(job_selected),
        "human_confirmed": bool(human_confirmed),
        "create_application": bool(create_application),
    }


def talent_pool_visibility_for_unsolicited() -> dict[str, Any]:
    return {
        "hr_visible": True,
        "actionable": False,
        "job_ranking_allowed": False,
        "lifecycle_mutation_allowed": False,
        "contact_allowed": False,
        "held_state": "unsolicited_whatsapp_intake",
        "requires_exact_job_confirmation": True,
    }


def manual_held_by_default(*, auto_admit_enabled: bool, explicit_role: bool) -> dict[str, Any]:
    """Unified manual imports remain held unless explicit policy + role."""

    auto_admit = bool(auto_admit_enabled and explicit_role)
    return {
        "held_by_default": True,
        "auto_admit": auto_admit,
        "status": "review_pending" if auto_admit else ("import_review" if explicit_role else "needs_role"),
    }


def observe_shared_stages_for_document(
    cur: Any,
    *,
    company_code: str,
    subject_id: str,
    content_sha256: str | None,
    mime_or_suffix: str,
    local_text_ok: bool,
    needs_ocr: bool,
    channel: str,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Record acceptance/validation/provider-plan stages without cutting over live extract."""

    if not shared_processing_enabled(environ):
        return {"ok": True, "skipped": True, "reason": "adapter_shared_processing_disabled"}

    processing.require_schema(cur)
    plan = processing.plan_extraction_providers(
        mime_or_suffix=mime_or_suffix,
        local_text_ok=local_text_ok,
        needs_ocr=needs_ocr,
        environ=environ,
    )
    ledger_env = dict(_env(environ))
    ledger_env.setdefault(processing.FEATURE_STAGE_LEDGER, "1")
    stages = [
        ("document_acceptance", "completed"),
        ("mime_content_validation", "completed"),
        ("local_extraction", "completed" if plan.local_first else "pending"),
    ]
    if plan.mistral_ocr_eligible:
        stages.append(("mistral_ocr", "pending"))
    elif "mistral_ocr_disabled" in plan.reason_codes:
        stages.append(("mistral_ocr", "killed"))
    if plan.gpt_vision_rescue_eligible:
        stages.append(("gpt_vision_rescue", "pending"))

    runs = []
    for stage, status in stages:
        runs.append(
            processing.record_stage_run(
                cur,
                company_code=company_code,
                stage=stage,
                status=status,
                subject_id=subject_id,
                content_sha256=content_sha256,
                metadata={
                    "adapter_version": ADAPTER_VERSION,
                    "channel": channel,
                    "provider_plan": {
                        "local_first": plan.local_first,
                        "mistral_ocr_eligible": plan.mistral_ocr_eligible,
                        "gpt_vision_rescue_eligible": plan.gpt_vision_rescue_eligible,
                        "reason_codes": list(plan.reason_codes),
                    },
                    "authoritative_path": "live_channel_wrapper",
                },
                environ=ledger_env,
            )
        )
    return {
        "ok": True,
        "skipped": False,
        "provider_plan": {
            "local_first": plan.local_first,
            "mistral_ocr_eligible": plan.mistral_ocr_eligible,
            "gpt_vision_rescue_eligible": plan.gpt_vision_rescue_eligible,
            "reason_codes": list(plan.reason_codes),
        },
        "runs": runs,
    }


def adapt_manual_import(
    cur: Any,
    *,
    company_code: str,
    batch_id: str,
    content_sha256: str,
    filename: str | None,
    document_id: str | None,
    app_key: str | None,
    held_status: str | None,
    mime_or_suffix: str | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not adapters_enabled(environ):
        return {"ok": True, "skipped": True, "reason": "adapters_disabled"}
    try:
        import tenant_control_queue_gate as _tc_qg

        work_ref = str(batch_id or content_sha256 or "manual")
        queued_epoch = _tc_qg.persist_work_epoch(
            cur,
            company_code=str(company_code or "").upper(),
            work_kind="manual_intake",
            work_ref=work_ref,
            module_key="pre_hiring",
        )
        allowed, decision = _tc_qg.gate_or_skip(
            cur,
            company_code=str(company_code or "").upper(),
            module_key="pre_hiring",
            work_kind="manual_intake",
            work_ref=work_ref,
            queued_epoch=queued_epoch,
            surface="intake",
        )
        if not allowed:
            return {
                "ok": False,
                "held": True,
                "reason": decision.reason_code,
                "correlation_id": decision.audit_correlation_id,
                "adapter": "manual_upload",
            }
    except Exception:
        pass
    intake.require_schema(cur)
    receipt = intake.dual_write_manual_receipt(
        cur,
        company_code=company_code,
        batch_id=batch_id,
        content_sha256=content_sha256,
        filename=filename,
        document_id=document_id,
        app_key=app_key,
        held_status=held_status,
        environ=environ,
    )
    observed = {"skipped": True}
    wave4_result = {"skipped": True}
    if not receipt.get("skipped") and receipt.get("item_ids"):
        observed = observe_shared_stages_for_document(
            cur,
            company_code=company_code,
            subject_id=str(receipt["item_ids"][0]),
            content_sha256=content_sha256,
            mime_or_suffix=mime_or_suffix or (filename or ""),
            local_text_ok=True,
            needs_ocr=False,
            channel="manual_upload",
            environ=environ,
        )
        wave4_result = wave4.after_intake_receipt(
            cur,
            company_code=company_code,
            subject_id=str(receipt.get("subject_id") or receipt["item_ids"][0]),
            content_sha256=content_sha256,
            document_id=document_id,
            legacy_app_key=app_key,
            actionable=False,
            channel="manual_upload",
            environ=environ,
        )
    return {
        "ok": True,
        "adapter": "manual_upload",
        "receipt": receipt,
        "shared_processing": observed,
        "wave4": wave4_result,
        "held_by_default": True,
        "creates_job_application": False,
    }


def adapt_whatsapp_unsolicited(
    cur: Any,
    *,
    company_code: str,
    provider_message_id: str,
    phone: str | None,
    account_id: str | None,
    conversation_id: str | None,
    pending_id: str | None,
    content_sha256: str | None = None,
    filename: str | None = None,
    mime_or_suffix: str | None = None,
    needs_ocr: bool = True,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not adapters_enabled(environ):
        return {"ok": True, "skipped": True, "reason": "adapters_disabled"}
    try:
        import tenant_control_queue_gate as _tc_qg

        work_ref = str(provider_message_id or pending_id or "whatsapp_unsolicited")
        queued_epoch = _tc_qg.persist_work_epoch(
            cur,
            company_code=str(company_code or "").upper(),
            work_kind="whatsapp_unsolicited_intake",
            work_ref=work_ref,
            module_key="pre_hiring",
        )
        allowed, decision = _tc_qg.gate_or_skip(
            cur,
            company_code=str(company_code or "").upper(),
            module_key="pre_hiring",
            work_kind="whatsapp_unsolicited_intake",
            work_ref=work_ref,
            queued_epoch=queued_epoch,
            surface="intake",
        )
        if not allowed:
            return {
                "ok": False,
                "held": True,
                "reason": decision.reason_code,
                "correlation_id": decision.audit_correlation_id,
                "adapter": "whatsapp_unsolicited",
            }
    except Exception:
        pass
    gate = assert_no_job_without_exact_confirmation(
        job_selected=False,
        human_confirmed=False,
        create_application=False,
    )
    intake.require_schema(cur)
    receipt = intake.dual_write_whatsapp_receipt(
        cur,
        company_code=company_code,
        provider_message_id=provider_message_id,
        phone=phone,
        account_id=account_id,
        conversation_id=conversation_id,
        pending_id=pending_id,
        content_sha256=content_sha256,
        filename=filename,
        job_bound=False,
        environ=environ,
    )
    visibility = talent_pool_visibility_for_unsolicited()
    observed = {"skipped": True}
    wave4_result = {"skipped": True}
    if not receipt.get("skipped") and receipt.get("item_ids"):
        observed = observe_shared_stages_for_document(
            cur,
            company_code=company_code,
            subject_id=str(receipt["item_ids"][0]),
            content_sha256=content_sha256,
            mime_or_suffix=mime_or_suffix or (filename or "application/pdf"),
            local_text_ok=False,
            needs_ocr=needs_ocr,
            channel="whatsapp",
            environ=environ,
        )
        wave4_result = wave4.after_intake_receipt(
            cur,
            company_code=company_code,
            subject_id=str(receipt.get("subject_id") or receipt["item_ids"][0]),
            phone=phone,
            content_sha256=content_sha256,
            document_id=pending_id,
            actionable=False,
            channel="whatsapp_unsolicited",
            environ=environ,
        )
    return {
        "ok": True,
        "adapter": "whatsapp_unsolicited",
        "receipt": receipt,
        "talent_pool": visibility,
        "shared_processing": observed,
        "wave4": wave4_result,
        "job_gate": gate,
        "creates_job_application": False,
    }


def adapt_whatsapp_job(
    cur: Any,
    *,
    company_code: str,
    provider_message_id: str,
    phone: str | None,
    account_id: str | None,
    conversation_id: str | None,
    pending_id: str | None = None,
    document_id: str | None = None,
    content_sha256: str | None = None,
    filename: str | None = None,
    app_key: str | None = None,
    apply_code: str | None = None,
    human_confirmed: bool = False,
    mime_or_suffix: str | None = None,
    needs_ocr: bool = False,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not adapters_enabled(environ):
        return {"ok": True, "skipped": True, "reason": "adapters_disabled"}
    job_selected = bool(apply_code and app_key)
    # Adapter itself never creates the application; Stage B already did when confirmed.
    gate = assert_no_job_without_exact_confirmation(
        job_selected=job_selected,
        human_confirmed=human_confirmed,
        create_application=False,
    )
    intake.require_schema(cur)
    receipt = intake.dual_write_whatsapp_receipt(
        cur,
        company_code=company_code,
        provider_message_id=provider_message_id,
        phone=phone,
        account_id=account_id,
        conversation_id=conversation_id,
        pending_id=pending_id,
        document_id=document_id,
        content_sha256=content_sha256,
        filename=filename,
        app_key=app_key,
        job_bound=True,
        apply_code=apply_code,
        environ=environ,
    )
    observed = {"skipped": True}
    wave4_result = {"skipped": True}
    if not receipt.get("skipped") and receipt.get("item_ids"):
        observed = observe_shared_stages_for_document(
            cur,
            company_code=company_code,
            subject_id=str(receipt["item_ids"][0]),
            content_sha256=content_sha256,
            mime_or_suffix=mime_or_suffix or (filename or "application/pdf"),
            local_text_ok=not needs_ocr,
            needs_ocr=needs_ocr,
            channel="whatsapp",
            environ=environ,
        )
        wave4_result = wave4.after_intake_receipt(
            cur,
            company_code=company_code,
            subject_id=str(receipt.get("subject_id") or receipt["item_ids"][0]),
            phone=phone,
            content_sha256=content_sha256,
            document_id=document_id or pending_id,
            legacy_app_key=app_key,
            actionable=False,
            channel="whatsapp_job",
            environ=environ,
        )
    return {
        "ok": True,
        "adapter": "whatsapp_job",
        "receipt": receipt,
        "shared_processing": observed,
        "wave4": wave4_result,
        "job_gate": gate,
        "creates_job_application": False,
        "links_existing_application": bool(app_key),
    }


__all__ = [
    "ADAPTER_VERSION",
    "FEATURE_ADAPTERS",
    "FEATURE_SHARED_PROCESSING",
    "ADAPTERS",
    "adapters_enabled",
    "shared_processing_enabled",
    "assert_no_job_without_exact_confirmation",
    "talent_pool_visibility_for_unsolicited",
    "manual_held_by_default",
    "observe_shared_stages_for_document",
    "adapt_manual_import",
    "adapt_whatsapp_unsolicited",
    "adapt_whatsapp_job",
]
