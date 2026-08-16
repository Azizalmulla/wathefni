"""Capability contracts registry — HARD / OPTIONAL / ENHANCEMENT classifications.

Machine-readable module integration contracts for Phase A + Wave 1.
Does not enable product UI. Evaluation is entitlement-aware and fail-closed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

DependencyClass = Literal["HARD_DEPENDENCY", "OPTIONAL_INTEGRATION", "ENHANCEMENT"]


@dataclass(frozen=True)
class CapabilityContract:
    contract_id: str
    dependency_class: DependencyClass
    requires_modules: tuple[str, ...]
    company_setting: str | None
    default_when_both_enabled: bool | None
    description: str
    writer_enabled_flag: str | None = None  # env kill-switch for mutating side


CAPABILITY_CONTRACTS: tuple[CapabilityContract, ...] = (
    CapabilityContract(
        contract_id="requisitions.gate_job_publish",
        dependency_class="OPTIONAL_INTEGRATION",
        requires_modules=("requisitions", "pre_hiring"),
        company_setting="jobs_require_approved_requisition",
        default_when_both_enabled=True,
        description="When both modules on, job publish may require an approved requisition.",
    ),
    CapabilityContract(
        contract_id="preboarding.auto_create_on_offer_accept",
        dependency_class="OPTIONAL_INTEGRATION",
        requires_modules=("preboarding", "employment_offers"),
        company_setting="preboarding.auto_create_on_offer_accept",
        default_when_both_enabled=True,
        description="Auto-create preboard assignment when an offer is accepted.",
    ),
    CapabilityContract(
        contract_id="preboarding.link_application",
        dependency_class="ENHANCEMENT",
        requires_modules=("preboarding", "pre_hiring"),
        company_setting=None,
        default_when_both_enabled=None,
        description="Traceability link from preboard assignment to application_id.",
    ),
    CapabilityContract(
        contract_id="preboarding.handoff_onboarding",
        dependency_class="OPTIONAL_INTEGRATION",
        requires_modules=("preboarding", "onboarding"),
        company_setting=None,
        default_when_both_enabled=None,
        description="Deduplicate checklist items across preboard and onboarding when both on.",
    ),
    CapabilityContract(
        contract_id="onboarding.auto_start_on_hire",
        dependency_class="OPTIONAL_INTEGRATION",
        requires_modules=("onboarding",),
        company_setting="onboarding.auto_start_on_hire",
        default_when_both_enabled=False,
        description="Hire TX may start onboarding assignment when setting true and module enabled.",
        writer_enabled_flag="WATHEFNI_ONBOARDING_AUTO_START_WRITERS",
    ),
    CapabilityContract(
        contract_id="probation.auto_plan_on_hire",
        dependency_class="OPTIONAL_INTEGRATION",
        requires_modules=("probation",),
        company_setting="probation.auto_plan_on_hire",
        default_when_both_enabled=True,
        description="Create probation plan from template on hire when probation enabled.",
    ),
    CapabilityContract(
        contract_id="probation.sync_from_offer",
        dependency_class="OPTIONAL_INTEGRATION",
        requires_modules=("probation", "employment_offers"),
        company_setting=None,
        default_when_both_enabled=None,
        description="Offer probation_days may seed employment probation terms.",
        writer_enabled_flag="WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS",
    ),
    CapabilityContract(
        contract_id="employment.joining_date_from_offer",
        dependency_class="OPTIONAL_INTEGRATION",
        requires_modules=("employment_offers",),
        company_setting=None,
        default_when_both_enabled=None,
        description="Offer proposed_start_date may seed employment joining/start date (dry-run first).",
        writer_enabled_flag="WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS",
    ),
    CapabilityContract(
        contract_id="probation.fail_opens_lifecycle",
        dependency_class="OPTIONAL_INTEGRATION",
        requires_modules=("probation",),
        company_setting=None,
        default_when_both_enabled=None,
        description="Failed probation may open a lifecycle termination case when lifecycle path available.",
    ),
    CapabilityContract(
        contract_id="requisitions.approval_n_step",
        dependency_class="HARD_DEPENDENCY",
        requires_modules=("requisitions",),
        company_setting=None,
        default_when_both_enabled=None,
        description="N-step requisition approval uses platform workflow_approvals authority.",
    ),
    CapabilityContract(
        contract_id="wave1.tasks_ontology",
        dependency_class="HARD_DEPENDENCY",
        requires_modules=(),
        company_setting=None,
        default_when_both_enabled=None,
        description="Wave 1 entity tasks use unified hr_tasks ontology (platform foundation).",
    ),
    CapabilityContract(
        contract_id="wave1.sla_policy",
        dependency_class="ENHANCEMENT",
        requires_modules=(),
        company_setting=None,
        default_when_both_enabled=None,
        description="SLA clocks enhance Wave 1 queues when company enables workflow SLA.",
    ),
)

CONTRACT_BY_ID = {c.contract_id: c for c in CAPABILITY_CONTRACTS}


def _env_on(name: str | None, default: str = "off") -> bool:
    if not name:
        return False
    import os

    return str(os.environ.get(name, default) or default).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def contract_payload() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in CAPABILITY_CONTRACTS:
        item = asdict(c)
        item["requires_modules"] = list(c.requires_modules)
        out.append(item)
    return out


def evaluate_contract(
    contract_id: str,
    *,
    enabled_modules: set[str] | frozenset[str] | list[str],
    company_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate whether a contract is active for a tenant entitlement set."""
    contract = CONTRACT_BY_ID.get(contract_id)
    if not contract:
        return {"ok": False, "active": False, "error": "contract_not_found"}

    enabled = {str(m).strip() for m in enabled_modules if str(m).strip()}
    missing = [m for m in contract.requires_modules if m not in enabled]
    if missing:
        return {
            "ok": True,
            "active": False,
            "contract_id": contract_id,
            "dependency_class": contract.dependency_class,
            "reason": "modules_missing",
            "missing_modules": missing,
            "writers_enabled": False,
        }

    settings = company_settings or {}
    setting_key = contract.company_setting
    setting_value = None
    if setting_key:
        if setting_key in settings:
            setting_value = bool(settings[setting_key])
        elif contract.default_when_both_enabled is not None:
            setting_value = bool(contract.default_when_both_enabled)
        else:
            setting_value = False
        if not setting_value:
            return {
                "ok": True,
                "active": False,
                "contract_id": contract_id,
                "dependency_class": contract.dependency_class,
                "reason": "company_setting_off",
                "company_setting": setting_key,
                "writers_enabled": False,
            }

    writers = True
    if contract.writer_enabled_flag:
        writers = _env_on(contract.writer_enabled_flag, "off")

    return {
        "ok": True,
        "active": True,
        "contract_id": contract_id,
        "dependency_class": contract.dependency_class,
        "company_setting": setting_key,
        "company_setting_value": setting_value,
        "writers_enabled": writers,
        "reason": "active" if writers or not contract.writer_enabled_flag else "active_dry_run_only",
    }


def active_contracts_for_modules(
    enabled_modules: set[str] | frozenset[str] | list[str],
    *,
    company_settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        evaluate_contract(c.contract_id, enabled_modules=enabled_modules, company_settings=company_settings)
        for c in CAPABILITY_CONTRACTS
        if evaluate_contract(
            c.contract_id, enabled_modules=enabled_modules, company_settings=company_settings
        ).get("active")
    ]
