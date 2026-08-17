#!/usr/bin/env python3
"""Customer-visible Employee activation email branding contract."""

from __future__ import annotations

import inspect

import outbound_delivery as delivery
import tenant_email_authority as email_authority


LEGACY_MARKERS = ("wathefni", "وظفني", "وظّفني", "وثفني", "وثّفني")


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS: {name}")


def has_no_legacy_brand(value: str) -> bool:
    lowered = value.lower()
    return all(marker not in lowered for marker in LEGACY_MARKERS)


def main() -> None:
    variables = {"employee_name": "Store Reviewer", "code": "123456", "expiry_hours": 24}
    subject_en = delivery.activation_email_subject("en")
    subject_ar = delivery.activation_email_subject("ar")
    body_en = delivery.render_body("app_activation", variables, "en")
    body_ar = delivery.render_body("app_activation", variables, "ar")

    for label, value in (
        ("English subject", subject_en),
        ("Arabic subject", subject_ar),
        ("English body", body_en),
        ("Arabic body", body_ar),
    ):
        check(f"{label} uses OctoHR", "OctoHR" in value)
        check(f"{label} has no legacy customer brand", has_no_legacy_brand(value))

    check("English and Arabic subjects differ", subject_en != subject_ar)
    check("English and Arabic bodies differ", body_en != body_ar)
    check("activation code renders in English", "123456" in body_en)
    check("activation code renders in Arabic", "123456" in body_ar)

    original_get_settings = email_authority.get_email_settings
    email_authority.get_email_settings = lambda _legacy, _company: {  # type: ignore[assignment]
        "outbound_mode": "wathefni",
        "display_name": "Example Company HR",
    }
    try:
        class Legacy:
            @staticmethod
            def outbound_postmark_config() -> dict[str, str]:
                return {"from_address": "notifications@example.test", "reply_to": ""}

        resolved = email_authority.resolve_outbound_sender(
            Legacy(), "REVIEW", purpose="app_activation", for_send=True
        )
    finally:
        email_authority.get_email_settings = original_get_settings  # type: ignore[assignment]

    check("activation sender display resolves to OctoHR", resolved.get("display_name") == "OctoHR")

    resolver_source = inspect.getsource(email_authority.resolve_outbound_sender)
    check(
        "activation sender display is forced to OctoHR",
        'purpose or ""' in resolver_source
        and '== "app_activation"' in resolver_source
        and 'display_name = "OctoHR"' in resolver_source,
    )

    print("EMPLOYEE_APP_ACTIVATION_BRANDING_PASS")


if __name__ == "__main__":
    main()
