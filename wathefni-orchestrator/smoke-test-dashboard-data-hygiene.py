from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    smoke_request = SimpleNamespace(account_id="default", conversation_id="cleanup-candidate-smoke")
    source, detail = app.data_source_from_request(smoke_request)
    assert_true(source == "smoke_test", "smoke conversation ids must be tagged as smoke_test")
    assert_true(detail == "cleanup-candidate-smoke", "smoke data source detail must keep the conversation id")

    production_request = SimpleNamespace(account_id="default", conversation_id="real-whatsapp-conversation")
    source, detail = app.data_source_from_request(production_request)
    assert_true(source == "production", "normal conversations must default to production data source")
    assert_true(detail is None, "production data should not get smoke detail")

    assert_true(
        app.clean_extracted_email("fslalmulla@gmail.comlocation") == "fslalmulla@gmail.com",
        "email cleanup must remove concatenated field labels after common TLDs",
    )
    assert_true(
        app.application_lead_quality({"status": "awaiting_cv", "phone": "96555550136", "cv_received": False, "raw_json": {}})
        == "incomplete_lead",
        "phone-only awaiting-CV rows must be marked as incomplete leads",
    )
    assert_true(
        app.application_lead_quality({"status": "screening", "candidate_name": "Hamad", "cv_received": True, "raw_json": {}})
        == "candidate_record",
        "named CV-backed rows must be normal candidate records",
    )

    app_source = Path(app.__file__).read_text(encoding="utf-8")
    cleanup_source = (Path(app.__file__).resolve().parent / "cleanup-production-data.py").read_text(encoding="utf-8")
    assert_true("production_application_predicate(\"a\")" in app_source, "dashboard queries must use production data predicate")
    assert_true("data_source='smoke_test'" in cleanup_source, "cleanup path must quarantine smoke rows instead of exposing them")

    print("dashboard data hygiene smoke tests passed")


if __name__ == "__main__":
    main()
