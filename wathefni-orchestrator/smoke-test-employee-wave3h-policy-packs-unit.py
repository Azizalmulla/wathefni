"""Wave 3H jurisdiction policy-pack unit tests (no DB)."""

from __future__ import annotations

import copy

import employee_policy_packs_wave3h as packs
import employee_lifecycle_wave3c as w3c

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def main() -> int:
    check("schema wave3h", packs.SCHEMA_VERSION.startswith("employees360-wave3h"))
    check("lifecycle schema wave3h", w3c.SCHEMA_VERSION.startswith("employees360-wave3h"), w3c.SCHEMA_VERSION)
    check("only KW verified", packs.VERIFIED_PACKS == frozenset({"KW_PRIVATE_SECTOR"}))
    check("reserved includes SA", "SA_PRIVATE_SECTOR" in packs.RESERVED_PACKS)
    check("reserved includes KW domestic", "KW_DOMESTIC_WORKERS" in packs.RESERVED_PACKS)

    kw = packs.get_pack("KW_PRIVATE_SECTOR")
    check("kw pack enabled", bool(kw and kw.get("enabled")))
    check("kw pack version", kw.get("policy_version") == "1.0.0")
    check("kw content hash stable", len(str(kw.get("content_hash") or "")) == 64)
    h1 = kw["content_hash"]
    kw2 = packs.get_pack("KW_PRIVATE_SECTOR")
    check("kw hash immutable across loads", kw2["content_hash"] == h1)

    ok = packs.resolve_pack_code(jurisdiction_code="KW", worker_category="private_sector")
    check("resolve KW private", ok.get("ok") is True and ok.get("pack_code") == "KW_PRIVATE_SECTOR", ok)

    missing_cat = packs.resolve_pack_code(jurisdiction_code="KW", worker_category=None)
    check("missing category fail-closed", missing_cat.get("ok") is False and missing_cat.get("error") == "missing_worker_category", missing_cat)

    missing_jur = packs.resolve_pack_code(jurisdiction_code=None, worker_category="private_sector")
    check("missing jurisdiction fail-closed", missing_jur.get("ok") is False and missing_jur.get("error") == "missing_jurisdiction", missing_jur)

    reserved = packs.resolve_pack_code(jurisdiction_code="SA", worker_category="private_sector")
    check("SA reserved not implemented", reserved.get("ok") is False and reserved.get("error") == "pack_not_implemented", reserved)

    unsupported = packs.resolve_pack_code(jurisdiction_code="AE", worker_category="private_sector")
    check("AE unsupported fail-closed", unsupported.get("ok") is False and unsupported.get("error") == "unsupported_jurisdiction", unsupported)

    domestic = packs.resolve_pack_code(jurisdiction_code="KW", worker_category="domestic_workers")
    check("KW domestic reserved", domestic.get("ok") is False and domestic.get("pack_code") == "KW_DOMESTIC_WORKERS", domestic)

    # Tenant override cannot weaken mandatory floors
    merged = packs.merge_tenant_override(kw, {"require_last_working_day": False, "document_retention_floor_days": 30})
    check("reject weaken LWD", any(r["key"] == "require_last_working_day" for r in merged.get("tenant_override_rejected") or []), merged.get("tenant_override_rejected"))
    check("reject lower retention", any(r["key"] == "document_retention_floor_days" for r in merged.get("tenant_override_rejected") or []), merged.get("tenant_override_rejected"))
    check("mandatory LWD still true", (merged.get("mandatory_rules") or {}).get("require_last_working_day") is True)

    raised = packs.merge_tenant_override(kw, {"document_retention_floor_days": 730})
    check("allow raise retention", (raised.get("mandatory_rules") or {}).get("document_retention_floor_days") == 730, raised.get("mandatory_rules"))

    reject_money = packs.merge_tenant_override(kw, {"monetary_calculations_owner": "employees360"})
    check("reject money owner change", any(r["key"] == "monetary_calculations_owner" for r in reject_money.get("tenant_override_rejected") or []))

    overlay = packs.pack_as_company_policy_overlay(kw)
    check("overlay payroll owner", overlay.get("monetary_calculations_owner") == "payroll")
    check("overlay reinstate off", overlay.get("allow_reinstate_after_effective") is False)
    check("overlay wave3h", overlay.get("wave") == "wave3h")

    notice_hidden = packs.notice_guidance_from_pack(
        pack=kw,
        company_show_notice_hints=False,
        contract_type="unlimited",
        pay_frequency="monthly",
        probation_status="completed",
        termination_case_class="resignation",
    )
    check("notice hidden by default", notice_hidden["eligible"] is False)

    notice_ok = packs.notice_guidance_from_pack(
        pack=kw,
        company_show_notice_hints=True,
        contract_type="unlimited",
        pay_frequency="monthly",
        probation_status="completed",
        termination_case_class="resignation",
    )
    check("notice eligible KW unlimited", notice_ok["eligible"] is True and notice_ok["hint_days"] == 90, notice_ok)

    notice_ft = packs.notice_guidance_from_pack(
        pack=kw,
        company_show_notice_hints=True,
        contract_type="fixed_term",
        pay_frequency="monthly",
        probation_status="completed",
        termination_case_class="end_of_fixed_term",
    )
    check("notice hidden fixed_term", notice_ft["eligible"] is False)

    # Historical freeze identity: mutating a copy does not change catalog hash
    mutated = copy.deepcopy(kw)
    mutated["notice_rules"] = {**(mutated.get("notice_rules") or {}), "monthly_hint_days": 999}
    check("mutated copy does not alter catalog", packs.get_pack("KW_PRIVATE_SECTOR")["content_hash"] == h1)
    check("mutated hash differs locally", packs._pack_hash({k: v for k, v in mutated.items() if k != "content_hash"}) != h1)

    # Wave 3C defaults still KW-compatible
    check("default counsel gate off", w3c.DEFAULT_POLICY["require_counsel_gate"] is False)
    check("default jurisdiction policy_pack", w3c.DEFAULT_POLICY["jurisdiction_mode"] == "policy_pack")
    check("kuwait only mode removed as default", w3c.DEFAULT_POLICY["jurisdiction_mode"] != "kuwait_private_sector_only")

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
