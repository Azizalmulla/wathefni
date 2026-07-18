"""Delivery-mode safety smoke test.

Proves that with WATHEFNI_DELIVERY_MODE=dry_run the candidate-facing send paths
(email + WhatsApp) never perform a real send: no Gmail subprocess, no Octopus HTTP
call. Runs in-process and stubs the real transports so a regression that actually
tries to send is caught immediately.

Run on a host with the orchestrator venv:
  WATHEFNI_DELIVERY_MODE=dry_run /opt/wathefni/orchestrator/.venv/bin/python smoke-test-delivery-mode.py
"""

from __future__ import annotations

import os
import sys

os.environ["WATHEFNI_DELIVERY_MODE"] = "dry_run"

import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    assert_true(app.delivery_is_dry_run(), "delivery mode must report dry_run")

    sends: list[str] = []

    # Any attempt to actually send must blow up the test.
    def boom_gog(*args, **kwargs):
        sends.append("gmail")
        raise AssertionError("run_gog must not be called in dry_run")

    def boom_urlopen(*args, **kwargs):
        sends.append("http")
        raise AssertionError("network send must not happen in dry_run")

    # Keep the test DB-free and transport-free.
    app.run_gog = boom_gog  # type: ignore[assignment]
    app.urllib.request.urlopen = boom_urlopen  # type: ignore[assignment]
    app.record_outbound_delivery_event = lambda *a, **k: None  # type: ignore[assignment]
    app.compose_email_content = lambda *a, **k: {"subject": "Test subject", "body": "Test body"}  # type: ignore[assignment]

    # Email path.
    email_app = {"app_key": "DRYRUN-APP", "candidate_name": "Dry Run", "candidate_email": "dryrun@example.com", "phone": "96500000000"}
    email_result = app.send_email(email_app, {"action_type": "send_email", "prompt_text": "send email"})
    assert_true(email_result.get("ok") is True and email_result.get("dry_run") is True, "email send must return simulated dry_run success")

    # WhatsApp text path.
    wa_result = app.send_octopus_whatsapp(account_id="default", phone="96500000000", text="hello", subject_type="candidate", subject_key="DRYRUN-APP")
    assert_true(wa_result.get("ok") is True and wa_result.get("dry_run") is True, "whatsapp send must return simulated dry_run success")

    # WhatsApp image path.
    img_result = app.send_octopus_whatsapp_image(account_id="default", phone="96500000000", image_url="https://example.com/x.png", caption="c", subject_type="candidate", subject_key="DRYRUN-APP")
    assert_true(img_result.get("ok") is True and img_result.get("dry_run") is True, "whatsapp image send must return simulated dry_run success")

    assert_true(not sends, f"no real transport may be invoked in dry_run, but saw: {sends}")
    print("delivery mode dry_run smoke test passed (no real email/WhatsApp sent)")


if __name__ == "__main__":
    main()
