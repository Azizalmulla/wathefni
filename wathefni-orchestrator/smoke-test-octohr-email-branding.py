#!/usr/bin/env python3
"""Production customer-email branding contract for the OctoHR cutover."""

from __future__ import annotations

import json

import app
import outbound_delivery as delivery
import tenant_email_authority as authority


LEGACY = ("wathefni", "وظفني", "وظّفني", "وثفني", "وثّفني")


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS: {name}")


def clean(value: object) -> bool:
    text = json.dumps(value, ensure_ascii=False).lower()
    return all(marker not in text for marker in LEGACY)


def main() -> None:
    old_settings = authority.get_email_settings
    authority.get_email_settings = lambda _legacy, _company: {}  # type: ignore[assignment]
    try:
        sender = authority.resolve_outbound_sender(app, "BRANDTEST", purpose="app_activation")
    finally:
        authority.get_email_settings = old_settings  # type: ignore[assignment]

    check("canonical automated From address", sender["from_address"] == "no-reply@octo-hr.com")
    check("canonical sender display name", sender["display_name"] == "OctoHR")
    check("canonical support Reply-To", sender["reply_to"] == "support@octo-hr.com")
    check("canonical privacy mailbox", app.privacy_mailbox_address() == "privacy@octo-hr.com")
    check("legacy privacy mailbox remains inbound-only alias", "privacy@wathefni.ai" in app.privacy_mailbox_aliases())

    variables = {
        "employee_name": "Store Reviewer",
        "company_name": "OctoHR Store Review",
        "code": "123456",
        "expiry_hours": 24,
        "start_date": "2026-08-20",
        "end_date": "2026-08-21",
        "period": "August 2026",
    }
    rendered: list[dict[str, str]] = []
    for key in delivery.TEMPLATE_CATALOG:
        rendered.append(
            {
                "key": key,
                "subject_en": delivery.catalog_label(key, "en"),
                "subject_ar": delivery.catalog_label(key, "ar"),
                "body_en": delivery.render_body(key, variables, "en"),
                "body_ar": delivery.render_body(key, variables, "ar"),
            }
        )
    check("all employee email catalog subjects and bodies are legacy-brand free", clean(rendered))

    candidate_examples = []
    for purpose in ("shortlisted", "onboarding", "assessment", "interview", "general"):
        candidate_examples.append(
            app.compose_email_content(
                {"candidate_name": "Synthetic Candidate"},
                {"purpose": purpose, "prompt_text": purpose},
            )
        )
    check("all candidate email subjects and bodies are legacy-brand free", clean(candidate_examples))
    check("candidate email bodies identify OctoHR", all("OctoHR" in row["body"] for row in candidate_examples))
    check("activation subject is bilingual and OctoHR branded", "OctoHR" in delivery.activation_email_subject("en") and "OctoHR" in delivery.activation_email_subject("ar"))
    print("OCTOHR_EMAIL_BRANDING_PASS")


if __name__ == "__main__":
    main()
