#!/usr/bin/env python3
"""Focused, DB-free checks for the contained candidate WhatsApp cleanup."""

from __future__ import annotations

import json
import os

os.environ.setdefault("WATHEFNI_CANONICAL_LIFECYCLE", "true")
os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")

import app
import candidate_messages
import recruiting_lifecycle


positive = 0
negative = 0
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "", *, negative_path: bool = False) -> None:
    global positive, negative
    if condition:
        if negative_path:
            negative += 1
        else:
            positive += 1
        return
    failures.append(f"{name}: {detail}")


def main() -> int:
    inventory = candidate_messages.inventory()
    required = {
        "welcome",
        "role_resolved_cv_request",
        "file_received_checking",
        "cv_accepted",
        "cv_invalid",
        "ambiguous_application",
        "no_active_application",
        "cv_replacement_requested",
        "cv_updated_accepted",
        "application_status",
        "assessment_invitation",
        "interview_invitation",
        "interview_update",
        "offer_invitation",
        "withdrawal_confirm_prompt",
        "withdrawal_confirmation",
        "hr_handoff_confirmation",
    }
    check("required inventory", {row["template_key"] for row in inventory} == required)
    check("one catalog version", {row["template_version"] for row in inventory} == {"candidate_flow_v1"})
    check("English parity", all(row.get("en", "").strip() for row in inventory))
    check("Arabic parity", all(row.get("ar", "").strip() for row in inventory))
    check(
        "no text-only CV instruction",
        all("clear text" not in f"{row['en']} {row['ar']}".lower() for row in inventory),
        negative_path=True,
    )

    for locale in ("en", "ar"):
        rendered = candidate_messages.render("application_status", locale, role="Engineer", status="with HR")
        check(f"{locale} rendering", bool(rendered["text"]) and rendered["locale"] == locale)

    check("Arabic status intent", app.is_candidate_status_intent("وين وصل طلبي؟"))
    check("Arabic replace intent", app.is_candidate_cv_replace_intent("أبي أستبدل سيرتي الذاتية"))
    check("Arabic withdrawal intent", app.is_candidate_withdraw_intent("أريد سحب طلبي"))
    check("Arabic HR handoff intent", app.is_candidate_hr_handoff_intent("أبي أتكلم مع الموارد البشرية"))

    for heading in ("CV", "Resume", "Curriculum Vitae", "السيرة الذاتية", "المعلومات الشخصية"):
        check(f"generic heading rejected: {heading}", app.candidate_name_is_generic_heading(heading), negative_path=True)
    check("real English name accepted", not app.candidate_name_is_generic_heading("Mariam Al Salem"))
    check("real Arabic name accepted", not app.candidate_name_is_generic_heading("مريم السالم"))

    check("valid E.164-like recipient", app.valid_whatsapp_recipient("96550000000"))
    for recipient in ("", "abc", "123", "+"):
        check(
            f"invalid recipient rejected: {recipient!r}",
            not app.valid_whatsapp_recipient(recipient),
            negative_path=True,
        )

    unsupported = app.handle_candidate_file_turn(
        app.WhatsAppTurnRequest(
            sender_phone="96550000000",
            conversation_id="cleanup-smoke",
            raw_text="CV",
            media={"type": "text/plain", "path": "/tmp/candidate.txt"},
            metadata={"locale": "en"},
        )
    )
    check(
        "text attachment rejected",
        bool(unsupported and unsupported.get("error") == "unsupported_candidate_cv_media"),
        str(unsupported),
        negative_path=True,
    )
    check(
        "empty permissions fail closed",
        recruiting_lifecycle.allowed_actions_for_stage("ready_for_review", set()) == [],
        negative_path=True,
    )

    payload = {
        "ok": not failures,
        "positive": positive,
        "negative": negative,
        "total": positive + negative,
        "failures": failures,
        "template_version": candidate_messages.CATALOG_VERSION,
        "template_count": len(inventory),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
