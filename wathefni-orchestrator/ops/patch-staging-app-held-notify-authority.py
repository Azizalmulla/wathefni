#!/usr/bin/env python3
"""Surgically patch staging app.py with held-record communication authority gates.

Idempotent. Does not touch classification or Unified Candidates markers beyond
shared HELD_IMPORT_STATUSES constants already present.
"""
from __future__ import annotations

import pathlib
import sys

MARKER = "HELD_COMMUNICATION_AUTHORITY_STAGING_PATCH"

IMPORT_LINE = f"import candidate_communication_authority as _candidate_communication_authority  # {MARKER}\n"

HELPERS = f'''
CandidateCommunicationAuthorityError = _candidate_communication_authority.CandidateCommunicationAuthorityError  # {MARKER}


def load_candidate_communication_governance(company_code: str | None, app_key: str | None) -> dict[str, Any] | None:  # {MARKER}
    company = str(company_code or "").strip().upper()
    key = str(app_key or "").strip()
    if not company or not key:
        return None
    try:
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM candidate_record_governance
                    WHERE company_code=%s AND app_key=%s
                    LIMIT 1
                    """,
                    (company, key),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception:
        return None


def evaluate_application_communication_authority(  # {MARKER}
    application: dict[str, Any] | None,
    *,
    kind: str | None = None,
    expected_company_code: str | None = None,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gov = governance
    if gov is None and isinstance(application, dict):
        gov = load_candidate_communication_governance(application.get("company_code"), application.get("app_key"))
    return _candidate_communication_authority.evaluate_candidate_communication_authority(
        application,
        governance=gov,
        expected_company_code=expected_company_code,
        kind=kind,
    )


def assert_application_communication_allowed(  # {MARKER}
    application: dict[str, Any] | None,
    *,
    kind: str | None = None,
    expected_company_code: str | None = None,
    governance: dict[str, Any] | None = None,
    raise_http: bool = False,
) -> dict[str, Any]:
    try:
        gov = governance
        if gov is None and isinstance(application, dict):
            gov = load_candidate_communication_governance(application.get("company_code"), application.get("app_key"))
        return _candidate_communication_authority.assert_candidate_communication_allowed(
            application,
            governance=gov,
            expected_company_code=expected_company_code,
            kind=kind,
        )
    except CandidateCommunicationAuthorityError as exc:
        if raise_http:
            raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
        raise


def require_live_candidate_communication(  # {MARKER}
    application: dict[str, Any] | None,
    *,
    kind: str,
    expected_company_code: str | None = None,
) -> dict[str, Any]:
    return assert_application_communication_allowed(
        application,
        kind=kind,
        expected_company_code=expected_company_code,
        raise_http=True,
    )

'''


def _insert_once(src: str, anchor: str, insertion: str, *, after: bool = True) -> str:
    if insertion.strip() in src:
        return src
    if anchor not in src:
        raise RuntimeError(f"missing anchor: {anchor[:80]}")
    if after:
        return src.replace(anchor, anchor + insertion, 1)
    return src.replace(anchor, insertion + anchor, 1)


def patch(src: str) -> str:
    if MARKER in src and "require_live_candidate_communication" in src and "assert_application_communication_allowed(app, kind=\"notify\")" in src:
        return src
    out = src

    # Import near candidate_messages if present
    if "import candidate_communication_authority" not in out:
        msg_anchor = None
        for candidate in (
            "import candidate_messages as _candidate_messages  # noqa: E402\n",
            "import candidate_messages as _candidate_messages\n",
        ):
            if candidate in out:
                msg_anchor = candidate
                break
        if msg_anchor:
            out = _insert_once(out, msg_anchor, IMPORT_LINE)
        else:
            out = _insert_once(out, "from __future__ import annotations\n", "\n" + IMPORT_LINE)

    if "def require_live_candidate_communication(" not in out:
        anchor = "INTAKE_REVIEW_STATUSES = (\"needs_role\", \"import_review\")\n"
        if anchor not in out:
            anchor = "HELD_IMPORT_STATUSES = (\"needs_role\", \"import_review\", \"import_archived\")\n"
        out = _insert_once(out, anchor, "\n" + HELPERS)

    # Transport helpers
    replacements = [
        (
            "def notify_candidate(app: dict[str, Any], account_id: str | None, message: str | None = None) -> dict[str, Any]:\n    contact = candidate_contact(app)\n",
            "def notify_candidate(app: dict[str, Any], account_id: str | None, message: str | None = None) -> dict[str, Any]:\n"
            "    try:\n"
            "        assert_application_communication_allowed(app, kind=\"notify\")  # "
            + MARKER
            + "\n"
            "    except CandidateCommunicationAuthorityError as exc:\n"
            "        return {**exc.as_result(), \"candidate\": candidate_contact(app) if isinstance(app, dict) else {}}\n"
            "    contact = candidate_contact(app)\n",
        ),
        (
            "def send_email(app: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:\n    contact = candidate_contact(app)\n",
            "def send_email(app: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:\n"
            "    try:\n"
            "        assert_application_communication_allowed(app, kind=\"email\")  # "
            + MARKER
            + "\n"
            "    except CandidateCommunicationAuthorityError as exc:\n"
            "        return {**exc.as_result(), \"candidate\": candidate_contact(app) if isinstance(app, dict) else {}}\n"
            "    contact = candidate_contact(app)\n",
        ),
        (
            "def candidate_communication_router(\n    app: dict[str, Any],\n    *,\n    account_id: str | None,\n    kind: str,\n    message: str | None = None,\n    action: dict[str, Any] | None = None,\n) -> dict[str, Any]:\n    action = dict(action or {})\n    contact = candidate_contact(app)\n",
            "def candidate_communication_router(\n    app: dict[str, Any],\n    *,\n    account_id: str | None,\n    kind: str,\n    message: str | None = None,\n    action: dict[str, Any] | None = None,\n) -> dict[str, Any]:\n"
            "    try:\n"
            "        assert_application_communication_allowed(app, kind=str(kind or \"generic\"))  # "
            + MARKER
            + "\n"
            "    except CandidateCommunicationAuthorityError as exc:\n"
            "        contact = candidate_contact(app) if isinstance(app, dict) else {}\n"
            "        return {**exc.as_result(), \"kind\": kind, \"candidate\": contact, \"policy\": {}, \"attempts\": [], \"successful_channels\": [], \"failed_channels\": [], \"last_successful_channel\": None, \"fallback_used\": False, \"message\": message}\n"
            "    action = dict(action or {})\n"
            "    contact = candidate_contact(app)\n",
        ),
        (
            "def send_assessment(\n    app: dict[str, Any],\n    account_id: str | None,\n    *,\n    note: str | None = None,\n    requested_by: str | None = None,\n    battery_key: str | None = None,\n    expires_days: int | None = None,\n) -> dict[str, Any]:\n    attempt_result = create_or_resume_assessment_attempt(\n",
            "def send_assessment(\n    app: dict[str, Any],\n    account_id: str | None,\n    *,\n    note: str | None = None,\n    requested_by: str | None = None,\n    battery_key: str | None = None,\n    expires_days: int | None = None,\n) -> dict[str, Any]:\n"
            "    try:\n"
            "        assert_application_communication_allowed(app, kind=\"assessment\")  # "
            + MARKER
            + "\n"
            "    except CandidateCommunicationAuthorityError as exc:\n"
            "        return exc.as_result()\n"
            "    attempt_result = create_or_resume_assessment_attempt(\n",
        ),
        (
            "def deliver_assessment_invitation(\n    app: dict[str, Any],\n    attempt: dict[str, Any],\n    account_id: str | None,\n    *,\n    note: str | None,\n    message_kind: str,\n    requested_by: str | None,\n) -> dict[str, Any]:\n    import assessment_lifecycle as _assessment_lifecycle\n",
            "def deliver_assessment_invitation(\n    app: dict[str, Any],\n    attempt: dict[str, Any],\n    account_id: str | None,\n    *,\n    note: str | None,\n    message_kind: str,\n    requested_by: str | None,\n) -> dict[str, Any]:\n"
            "    try:\n"
            "        assert_application_communication_allowed(app, kind=\"assessment_resend\" if message_kind == \"assessment_resend\" else \"assessment\")  # "
            + MARKER
            + "\n"
            "    except CandidateCommunicationAuthorityError as exc:\n"
            "        return exc.as_result()\n"
            "    import assessment_lifecycle as _assessment_lifecycle\n",
        ),
        (
            "def send_interview_invite(\n    application: dict[str, Any],\n    *,\n    account_id: str | None,\n    interview_id: str | None = None,\n    preferred_channel: str | None = None,\n) -> dict[str, Any]:\n    company = str(application.get(\"company_code\") or \"\").strip().upper()\n",
            "def send_interview_invite(\n    application: dict[str, Any],\n    *,\n    account_id: str | None,\n    interview_id: str | None = None,\n    preferred_channel: str | None = None,\n) -> dict[str, Any]:\n"
            "    try:\n"
            "        assert_application_communication_allowed(application, kind=\"interview_invite\")  # "
            + MARKER
            + "\n"
            "    except CandidateCommunicationAuthorityError as exc:\n"
            "        return exc.as_result()\n"
            "    company = str(application.get(\"company_code\") or \"\").strip().upper()\n",
        ),
        (
            "def send_async_video_interview_invite(\n    application: dict[str, Any],\n    interview: dict[str, Any],\n    public_link: str,\n    *,\n    account_id: str | None,\n    preferred_channel: str | None = None,\n    actor_context: dict[str, Any] | None = None,\n    note: str | None = None,\n) -> dict[str, Any]:\n    subject = \"Video Interview Invitation\"\n",
            "def send_async_video_interview_invite(\n    application: dict[str, Any],\n    interview: dict[str, Any],\n    public_link: str,\n    *,\n    account_id: str | None,\n    preferred_channel: str | None = None,\n    actor_context: dict[str, Any] | None = None,\n    note: str | None = None,\n) -> dict[str, Any]:\n"
            "    try:\n"
            "        assert_application_communication_allowed(application, kind=\"video_interview\")  # "
            + MARKER
            + "\n"
            "    except CandidateCommunicationAuthorityError as exc:\n"
            "        return exc.as_result()\n"
            "    subject = \"Video Interview Invitation\"\n",
        ),
        (
            "def schedule_interview(app: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:\n    contact = candidate_contact(app)\n",
            "def schedule_interview(app: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:\n"
            "    try:\n"
            "        assert_application_communication_allowed(app, kind=\"calendar_invite\")  # "
            + MARKER
            + "\n"
            "    except CandidateCommunicationAuthorityError as exc:\n"
            "        return {**exc.as_result(), \"candidate\": candidate_contact(app) if isinstance(app, dict) else {}}\n"
            "    contact = candidate_contact(app)\n",
        ),
        (
            "def schedule_candidate_meeting(app: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:\n    contact = candidate_contact(app)\n",
            "def schedule_candidate_meeting(app: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:\n"
            "    try:\n"
            "        assert_application_communication_allowed(app, kind=\"calendar_invite\")  # "
            + MARKER
            + "\n"
            "    except CandidateCommunicationAuthorityError as exc:\n"
            "        return {**exc.as_result(), \"candidate\": candidate_contact(app) if isinstance(app, dict) else {}}\n"
            "    contact = candidate_contact(app)\n",
        ),
        (
            "def notify_candidate_cv_validation(\n    application: dict[str, Any],\n    *,\n    document_id: str,\n    accepted: bool,\n) -> dict[str, Any]:\n    app_key = str(application.get(\"app_key\") or \"\")\n",
            "def notify_candidate_cv_validation(\n    application: dict[str, Any],\n    *,\n    document_id: str,\n    accepted: bool,\n) -> dict[str, Any]:\n"
            "    try:\n"
            "        assert_application_communication_allowed(application, kind=\"cv_validation\")  # "
            + MARKER
            + "\n"
            "    except CandidateCommunicationAuthorityError as exc:\n"
            "        return {**exc.as_result(), \"skipped\": \"held_or_non_live_application\"}\n"
            "    app_key = str(application.get(\"app_key\") or \"\")\n",
        ),
        (
            "def send_company_whatsapp_message(\n    company_code: str,\n    phone: str,\n    text: str,\n    *,\n    account_id: str | None = None,\n    subject_key: str | None = None,\n    message_kind: str = \"text\",\n    metadata: dict[str, Any] | None = None,\n) -> dict[str, Any]:\n    result = send_octopus_whatsapp(\n",
            "def send_company_whatsapp_message(\n    company_code: str,\n    phone: str,\n    text: str,\n    *,\n    account_id: str | None = None,\n    subject_key: str | None = None,\n    message_kind: str = \"text\",\n    metadata: dict[str, Any] | None = None,\n) -> dict[str, Any]:\n"
            "    app_key = str(subject_key or \"\").strip()\n"
            "    company = str(company_code or \"\").strip().upper()\n"
            "    if app_key and company:\n"
            "        application = find_application_by_key(app_key, company_code=company)\n"
            "        try:\n"
            "            assert_application_communication_allowed(application, kind=\"whatsapp\" if message_kind != \"employment_offer\" else \"offer\", expected_company_code=company)  # "
            + MARKER
            + "\n"
            "        except CandidateCommunicationAuthorityError as exc:\n"
            "            return {**exc.as_result(), \"send\": {\"ok\": False, \"error\": exc.code}}\n"
            "    result = send_octopus_whatsapp(\n",
        ),
        (
            "def send_company_whatsapp_message(\n    company_code: str,\n    phone: str,\n    text: str,\n    *,\n    account_id: str | None = None,\n    subject_key: str | None = None,\n    message_kind: str = \"text\",\n    metadata: dict[str, Any] | None = None,\n    audit_text: str | None = None,\n) -> dict[str, Any]:\n    result = send_octopus_whatsapp(\n",
            "def send_company_whatsapp_message(\n    company_code: str,\n    phone: str,\n    text: str,\n    *,\n    account_id: str | None = None,\n    subject_key: str | None = None,\n    message_kind: str = \"text\",\n    metadata: dict[str, Any] | None = None,\n    audit_text: str | None = None,\n) -> dict[str, Any]:\n"
            "    app_key = str(subject_key or \"\").strip()\n"
            "    company = str(company_code or \"\").strip().upper()\n"
            "    if app_key and company:\n"
            "        application = find_application_by_key(app_key, company_code=company)\n"
            "        try:\n"
            "            assert_application_communication_allowed(application, kind=\"whatsapp\" if message_kind != \"employment_offer\" else \"offer\", expected_company_code=company)  # "
            + MARKER
            + "\n"
            "        except CandidateCommunicationAuthorityError as exc:\n"
            "            return {**exc.as_result(), \"send\": {\"ok\": False, \"error\": exc.code}}\n"
            "    result = send_octopus_whatsapp(\n",
        ),
    ]
    for old, new in replacements:
        if MARKER in new and old in out:
            out = out.replace(old, new, 1)

    # Dashboard HTTP routes
    route_replacements = [
        (
            "    application = dashboard_application_or_404(app_key, company)\n    payload = request or DashboardCandidateMessage()\n    if _prehire_registry_enabled(\"notify_candidate\"):\n",
            "    application = dashboard_application_or_404(app_key, company)\n"
            "    require_live_candidate_communication(application, kind=\"notify\", expected_company_code=company)  # "
            + MARKER
            + "\n"
            "    payload = request or DashboardCandidateMessage()\n"
            "    if _prehire_registry_enabled(\"notify_candidate\"):\n",
        ),
        (
            "    application = dashboard_application_or_404(app_key, company)\n    payload = request or DashboardCandidateMessage()\n    selected_battery_key = str(payload.battery_key or \"\").strip() or None\n",
            "    application = dashboard_application_or_404(app_key, company)\n"
            "    require_live_candidate_communication(application, kind=\"assessment\", expected_company_code=company)  # "
            + MARKER
            + "\n"
            "    payload = request or DashboardCandidateMessage()\n"
            "    selected_battery_key = str(payload.battery_key or \"\").strip() or None\n",
        ),
        (
            "    application = dashboard_application_or_404(app_key, company)\n    payload = request or DashboardVideoInterviewRequest()\n    # The registry executor always sends the invite",
            "    application = dashboard_application_or_404(app_key, company)\n"
            "    payload = request or DashboardVideoInterviewRequest()\n"
            "    if payload.send_invite:\n"
            "        require_live_candidate_communication(application, kind=\"video_interview\", expected_company_code=company)  # "
            + MARKER
            + "\n"
            "    # The registry executor always sends the invite",
        ),
        (
            "    application = dashboard_application_or_404(str(attempt.get(\"app_key\") or \"\"), company)\n    payload = request or DashboardCandidateMessage()\n    result = resend_assessment(\n",
            "    application = dashboard_application_or_404(str(attempt.get(\"app_key\") or \"\"), company)\n"
            "    require_live_candidate_communication(application, kind=\"assessment_resend\", expected_company_code=company)  # "
            + MARKER
            + "\n"
            "    payload = request or DashboardCandidateMessage()\n"
            "    result = resend_assessment(\n",
        ),
    ]
    for old, new in route_replacements:
        if old in out and "require_live_candidate_communication(application, kind=\"notify\"" not in out[out.find(old) : out.find(old) + 300] if "notify_candidate" in old else True:
            if new not in out:
                out = out.replace(old, new, 1)

    if MARKER not in out:
        raise RuntimeError("held communication authority patch failed to insert markers")
    if "require_live_candidate_communication" not in out:
        raise RuntimeError("require_live_candidate_communication missing after patch")
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: patch-staging-app-held-notify-authority.py <app.py.in> <app.py.out>", file=sys.stderr)
        return 2
    src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
    out = patch(src)
    pathlib.Path(sys.argv[2]).write_text(out, encoding="utf-8")
    print("patched", sys.argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
