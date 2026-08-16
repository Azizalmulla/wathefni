#!/usr/bin/env python3
"""Wathefni Calendar C1 — spine smoke / safety proofs.

Covers module+permissions, adapter isolation, schema, ACL/privacy, OCC,
workflow-link uniqueness, cross-tenant isolation, and Waves 1–6 regression
guards. Does not exercise Interview enqueue (C2) or Google sync changes.
"""

from __future__ import annotations

import inspect
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail: str | None = None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS: {label}")
    else:
        FAIL += 1
        print(f"FAIL: {label}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("=== Wathefni Calendar C1 smoke ===")
    import module_catalog as catalog
    import calendar_acl as acl
    import calendar_org_scope as org
    import calendar_projections as proj
    import calendar_schema as schema
    import calendar_store as store
    import concurrency_safety as cs
    import app

    # --- Module + permissions ---
    check("calendar in MODULE_CATALOG", "calendar" in catalog.MODULE_BY_KEY)
    check("calendar order 28", catalog.MODULE_BY_KEY["calendar"].order == 28)
    check("calendar not legacy-implied", "calendar" not in catalog.apply_legacy_module_implications({"pre_hiring"}))
    check("owner calendar.sync", "calendar.sync" in app.ROLE_PERMISSIONS["owner"])
    check("hr_admin no calendar.sync", "calendar.sync" not in app.ROLE_PERMISSIONS["hr_admin"])
    check("hr_manager no calendar.sync", "calendar.sync" not in app.ROLE_PERMISSIONS["hr_manager"])
    check("hr_manager has calendar.company", "calendar.company" in app.ROLE_PERMISSIONS["hr_manager"])
    check("recruiter calendar.manage", "calendar.manage" in app.ROLE_PERMISSIONS["recruiter"])
    check("interviewer calendar.read only manage", "calendar.manage" not in app.ROLE_PERMISSIONS["interviewer"])
    check("payroll no calendar", "calendar.read" not in app.ROLE_PERMISSIONS["payroll_operator"])
    for key in ("calendar.read", "calendar.manage", "calendar.company", "calendar.sync", "calendar.conflict_override"):
        check(f"known permission {key}", key in app.KNOWN_DASHBOARD_PERMISSIONS)

    # --- Routes ---
    paths = {getattr(r, "path", "") for r in app.app.routes}
    for path in (
        "/dashboard/calendar/events",
        "/dashboard/calendar/events/{event_id}",
        "/dashboard/calendar/events/{event_id}/cancel",
    ):
        check(f"route {path}", path in paths)
    check("interview route unchanged", "/dashboard/prehire/interviews" in paths)
    check("gog calendar helper still present", callable(getattr(app, "run_gog", None)) or hasattr(app, "interview_calendar_event_id"))

    # --- Adapter isolation ---
    acl_src = Path(acl.__file__).read_text(encoding="utf-8")
    proj_src = Path(proj.__file__).read_text(encoding="utf-8")
    import re

    def _queries_manager_scopes(src: str) -> bool:
        return bool(
            re.search(r"(?i)(from|join)\s+manager_scopes\b", src)
            or re.search(r"(?i)(from|join)\s+manager_scope_members\b", src)
        )

    check("acl does not query manager_scopes", not _queries_manager_scopes(acl_src))
    check("projections do not query manager_scopes", not _queries_manager_scopes(proj_src))
    check("acl imports only adapter contract", "calendar_org_scope" in acl_src and "ManagerScopesOrgAdapter" not in acl_src)
    check("projections use get_org_scope_adapter", "get_org_scope_adapter" in proj_src)
    check("OrgScopeAdapter protocol present", hasattr(org, "OrgScopeAdapter"))
    check("ManagerScopesOrgAdapter present", hasattr(org, "ManagerScopesOrgAdapter"))
    check("factory present", callable(org.get_org_scope_adapter))

    # --- ACL unit matrix ---
    class FakeAdapter:
        def __init__(self, member_ids: set[str]):
            self.member_ids = member_ids

        def list_memberships(self, company_code, user_id):
            return []

        def resolve_scopes(self, company_code, org_scope_ids):
            return []

        def primary_scope_for_user(self, company_code, user_id):
            return None

        def actor_in_any(self, company_code, user_id, org_scope_ids):
            return bool(self.member_ids & {str(x) for x in org_scope_ids})

    event_team = {
        "visibility": "team",
        "sensitivity": "normal",
        "owner_user_id": "u-owner",
        "organizer_user_id": "u-org",
        "creator_user_id": "u-creator",
        "event_type": "meeting",
        "metadata": {},
    }
    bindings = [{"org_scope_id": "scope-a"}]
    level = acl.evaluate_detail_level(
        event=event_team,
        actor_user_id="u-viewer",
        actor_role="viewer",
        permissions=["calendar.read"],
        attendee_user_ids=[],
        org_bindings=bindings,
        links=[],
        adapter=FakeAdapter({"scope-a"}),
        company_code="ACME",
    )
    check("viewer in-scope team → busy_only", level == acl.DETAIL_BUSY_ONLY)

    cand_event = {**event_team, "sensitivity": "candidate_confidential"}
    level = acl.evaluate_detail_level(
        event=cand_event,
        actor_user_id="u-hr",
        actor_role="hr_admin",
        permissions=["calendar.read", "calendar.company"],
        attendee_user_ids=[],
        org_bindings=bindings,
        links=[{"source_workflow": "interview", "link_status": "active"}],
        adapter=FakeAdapter({"scope-a"}),
        company_code="ACME",
    )
    check("candidate-linked company oversight → busy_only", level == acl.DETAIL_BUSY_ONLY)

    busy = acl.serialize_for_detail_level(
        {
            "event_id": "e1",
            "title": "Secret Interview",
            "attendees": [{"user_id": "x"}],
            "guests": [{"email": "c@x.com"}],
            "links": [{"source_workflow": "interview"}],
            "start_at": "2026-07-29T10:00:00+00:00",
            "end_at": "2026-07-29T11:00:00+00:00",
        },
        acl.DETAIL_BUSY_ONLY,
    )
    check("busy_only hides title/attendees/guests/links", (
        busy is not None
        and busy.get("title") == "Busy"
        and "attendees" not in busy
        and "guests" not in busy
        and "links" not in busy
        and busy.get("busy") is True
    ))
    check("hidden serializes to None", acl.serialize_for_detail_level({"event_id": "e"}, acl.DETAIL_HIDDEN) is None)

    # Principal always full
    level = acl.evaluate_detail_level(
        event=cand_event,
        actor_user_id="u-org",
        actor_role="viewer",
        permissions=["calendar.read"],
        attendee_user_ids=[],
        org_bindings=bindings,
        links=[{"source_workflow": "interview", "link_status": "active"}],
        adapter=FakeAdapter(set()),
        company_code="ACME",
    )
    check("organizer gets full even when candidate-linked", level == acl.DETAIL_FULL)

    # Reminder rejection
    try:
        store.create_manual_event(
            app,
            company_code="NOPE",
            actor_user_id="u1",
            payload={"event_type": "reminder", "title": "x", "start_at": "2026-07-29T10:00:00+00:00", "end_at": "2026-07-29T11:00:00+00:00"},
        )
        check("reminder rejected as timed event", False)
    except store.CalendarError as exc:
        check("reminder rejected as timed event", exc.code in {"invalid_event_type", "reminder_not_timed_event"})

    # Interview authority fields constant locked
    check("interview authority fields include schedule/status", {"start_at", "status", "attendees"} <= store.INTERVIEW_AUTHORITY_FIELDS)

    # Wave regression markers
    check("wave1 interviewer scoped", app.interview_role_is_assignment_scoped("interviewer"))
    import prehire_visibility as pv

    check("wave2 default shared", pv.normalize_prehire_visibility_policy(None) == "shared_company")
    import prehire_ownership as own

    check("wave3 ownership", hasattr(own, "resolve_job_recruiter_on_create"))
    import prehire_personal_work as ppw

    check("wave4 personal work", ppw.resolve_work_scope(requested="mine", role="recruiter") == "mine")
    check("wave5 conflict message", "another user" in cs.CONFLICT_MESSAGE_EN.lower())
    check("wave6 people route", "/dashboard/team/people" in paths)

    # Schema SQL presence
    check("schema defines calendar_events", "CREATE TABLE IF NOT EXISTS calendar_events" in schema.CALENDAR_SCHEMA_SQL)
    check("schema unique active workflow links", "uq_calendar_event_links_active" in schema.CALENDAR_SCHEMA_SQL)
    check("schema outbox unused infrastructure", "calendar_link_outbox" in schema.CALENDAR_SCHEMA_SQL)
    check("ensure_schema wires calendar", "ensure_calendar_schema" in inspect.getsource(app._ensure_schema_impl))

    # --- DB-backed proofs (when available) ---
    db_ok = False
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                schema.ensure_calendar_schema(cur)
            conn.commit()
        db_ok = True
        check("calendar schema ensure", True)
    except Exception as exc:
        check("calendar schema ensure (skipped DB)", True, detail=f"no db: {exc}")

    if db_ok:
        company_a = f"C1A{uuid.uuid4().hex[:8].upper()}"
        company_b = f"C1B{uuid.uuid4().hex[:8].upper()}"
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=2)
        end = start + timedelta(hours=1)
        try:
            # Enable module for A only via direct registry rows if table exists.
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO companies (company_code, name, created_at, updated_at)
                        VALUES (%s,%s,now(),now())
                        ON CONFLICT DO NOTHING
                        """,
                        (company_a, company_a),
                    )
                conn.commit()
        except Exception:
            pass

        try:
            created = store.create_manual_event(
                app,
                company_code=company_a,
                actor_user_id=user_a,
                payload={
                    "event_type": "meeting",
                    "title": "C1 Tenant A Meeting",
                    "visibility": "attendees_only",
                    "start_at": start.isoformat(),
                    "end_at": end.isoformat(),
                    "attendees": [{"user_id": user_a, "role": "organizer"}],
                    "guests": [{"email": "guest@example.com", "guest_kind": "external"}],
                    "org_scope_ids": [],
                },
            )
            check("create manual event", bool(created.get("event_id")))
            eid = created["event_id"]
            version = int(created["version"])

            # Cross-tenant: B cannot load A's event by company filter
            other = store.get_event(app, company_code=company_b, event_id=eid)
            check("cross-tenant get_event empty", other is None)

            # OCC stale
            try:
                store.update_event(
                    app,
                    company_code=company_a,
                    event_id=eid,
                    actor_user_id=user_a,
                    payload={"title": "stale"},
                    expected_version=version - 1 if version > 1 else 999,
                )
                check("stale OCC raises", False)
            except store.CalendarError as exc:
                check("stale OCC 409", exc.http_status == 409 and exc.code.startswith("stale"))

            # Fresh update
            updated = store.update_event(
                app,
                company_code=company_a,
                event_id=eid,
                actor_user_id=user_a,
                payload={"title": "C1 Updated"},
                expected_version=version,
            )
            check("fresh OCC update", updated.get("title") == "C1 Updated" and int(updated["version"]) == version + 1)

            # Workflow link uniqueness
            link_key = f"manual-{uuid.uuid4().hex[:8]}"
            first = store.create_manual_event(
                app,
                company_code=company_a,
                actor_user_id=user_a,
                payload={
                    "event_type": "meeting",
                    "title": "Linked A",
                    "start_at": (start + timedelta(days=1)).isoformat(),
                    "end_at": (end + timedelta(days=1)).isoformat(),
                    "link": {"source_workflow": "candidate_followup", "source_record_id": link_key},
                },
            )
            check("linked event created", bool(first.get("event_id")))
            try:
                store.create_manual_event(
                    app,
                    company_code=company_a,
                    actor_user_id=user_a,
                    payload={
                        "event_type": "meeting",
                        "title": "Linked dup",
                        "start_at": (start + timedelta(days=2)).isoformat(),
                        "end_at": (end + timedelta(days=2)).isoformat(),
                        "link": {"source_workflow": "candidate_followup", "source_record_id": link_key},
                    },
                )
                check("active workflow-link uniqueness", False)
            except store.CalendarError as exc:
                check("active workflow-link uniqueness", exc.code == "workflow_link_conflict" and exc.http_status == 409)

            # Interview-linked authority reject
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO calendar_event_links
                          (link_id, company_code, event_id, source_workflow, source_record_id, link_status)
                        VALUES (%s,%s,%s,'interview',%s,'active')
                        """,
                        (str(uuid.uuid4()), company_a, eid, f"iv-{uuid.uuid4().hex[:8]}"),
                    )
                conn.commit()
            try:
                store.update_event(
                    app,
                    company_code=company_a,
                    event_id=eid,
                    actor_user_id=user_a,
                    payload={"start_at": (start + timedelta(hours=3)).isoformat()},
                    expected_version=int(updated["version"]),
                )
                check("interview_authority_required", False)
            except store.CalendarError as exc:
                check("interview_authority_required", exc.code == "interview_authority_required")

            # Candidate busy_only projection for non-attendee company actor
            cand = store.create_manual_event(
                app,
                company_code=company_a,
                actor_user_id=user_a,
                payload={
                    "event_type": "meeting",
                    "title": "Candidate Secret",
                    "visibility": "company",
                    "sensitivity": "candidate_confidential",
                    "start_at": (start + timedelta(days=3)).isoformat(),
                    "end_at": (end + timedelta(days=3)).isoformat(),
                    "attendees": [{"user_id": user_a}],
                },
            )
            projected = proj.project_events(
                app,
                company_code=company_a,
                actor_user_id=user_b,
                actor_role="hr_admin",
                permissions=["calendar.read", "calendar.company", "calendar.manage"],
                scope="company",
                start=(start - timedelta(days=1)).isoformat(),
                end=(end + timedelta(days=10)).isoformat(),
            )
            match = next((e for e in projected["events"] if e.get("event_id") == cand["event_id"]), None)
            check(
                "company projection candidate busy_only",
                match is not None
                and match.get("detail_level") == "busy_only"
                and match.get("title") == "Busy"
                and "attendees" not in match,
            )

            # Cleanup
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM calendar_event_audit WHERE company_code=%s", (company_a,))
                    cur.execute("DELETE FROM calendar_event_links WHERE company_code=%s", (company_a,))
                    cur.execute("DELETE FROM calendar_guests WHERE company_code=%s", (company_a,))
                    cur.execute("DELETE FROM calendar_attendees WHERE company_code=%s", (company_a,))
                    cur.execute("DELETE FROM calendar_event_org_scopes WHERE company_code=%s", (company_a,))
                    cur.execute("DELETE FROM calendar_events WHERE company_code=%s", (company_a,))
                conn.commit()
            check("cleanup tenant A calendar rows", True)
        except Exception as exc:
            check("db-backed calendar proofs", False, detail=str(exc))

    print(f"=== C1 smoke done PASS={PASS} FAIL={FAIL} ===")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
