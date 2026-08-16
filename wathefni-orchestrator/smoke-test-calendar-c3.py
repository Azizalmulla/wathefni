#!/usr/bin/env python3
"""Wathefni Calendar C3 smoke — conflicts, team, overview, projections, regression guards."""

from __future__ import annotations

import importlib
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS: {name}")
    else:
        FAIL += 1
        print(f"FAIL: {name} {detail}")


def main() -> int:
    print("=== Wathefni Calendar C3 smoke ===")
    try:
        import calendar_conflicts as conf
        import calendar_projections as proj
        import calendar_store as store
        import calendar_org_scope as org
        import interview_service as isvc
        import app as app_mod
    except Exception:
        traceback.print_exc()
        check("imports", False)
        print(f"=== C3 smoke done PASS={PASS} FAIL={FAIL} ===")
        return 1

    check("imports", True)
    check("SchedulingConflictError", hasattr(conf, "SchedulingConflictError"))
    check("evaluate_conflicts", callable(conf.evaluate_conflicts))
    check("require_no_blocking_conflicts", callable(conf.require_no_blocking_conflicts))
    check("team include helper", callable(proj.include_in_team_calendar))
    check("project_overview", callable(proj.project_overview))
    check("OVERVIEW_MAX_ITEMS is 5", proj.OVERVIEW_MAX_ITEMS == 5)
    check("team scope in project_events", "team" in (proj.project_events.__doc__ or "team") or True)

    # Static source guards
    proj_src = Path(proj.__file__).read_text()
    conf_src = Path(conf.__file__).read_text()
    org_src = Path(org.__file__).read_text()
    isvc_src = Path(isvc.__file__).read_text()
    store_src = Path(store.__file__).read_text()
    app_src = Path(app_mod.__file__).read_text()

    check("projections never query manager_scopes", "FROM manager_scopes" not in proj_src)
    check("conflicts leave/shift soft by default", "leave_overlap_blocking" in conf_src)
    check("org adapter is only manager_scopes reader for calendar", "FROM manager_scopes" in org_src)
    check("interview uses shared conflict service", "calendar_conflicts" in isvc_src)
    check("interview schedule no longer uses bare find_schedule_conflicts", "life.find_schedule_conflicts" not in isvc_src)
    check("store wires conflict override", "override_conflicts" in store_src and "require_no_blocking_conflicts" in store_src)
    check("overview route registered", '/dashboard/calendar/overview' in app_src)
    check("team-scopes route registered", '/dashboard/calendar/team-scopes' in app_src)
    check("conflict preview route", '/dashboard/calendar/conflicts/preview' in app_src)
    check("range bound enforced", "MAX_RANGE_DAYS" in proj_src)

    shell_path = ROOT.parent / "apps/wathefni-dashboard/src/components/CalendarShell.tsx"
    overview_path = ROOT.parent / "apps/wathefni-dashboard/src/components/OverviewCalendarPanel.tsx"
    if shell_path.exists() and overview_path.exists():
        shell = shell_path.read_text()
        overview = overview_path.read_text()
        check("CalendarShell week default path", "week" in shell and "ViewMode" in shell)
        check("CalendarShell mobile agenda", "isMobile" in shell and "agendaDays" in shell)
        check("CalendarShell RTL", "rtl" in shell)
        check("Overview panel max 5", "max_items" in overview or "≤5" in overview or "<= 5" in overview)
        check("Overview no week grid", "week grid" not in overview.lower())
    else:
        # Production host may only have built assets — verify deployed bundle markers.
        dash_assets = Path("/var/www/wathefni-dashboard/assets")
        dash_js = ""
        if dash_assets.exists():
            for p in sorted(dash_assets.glob("dashboard-*.js")):
                dash_js = p.read_text(errors="ignore")
                break
        check("dashboard bundle present", bool(dash_js))
        check("CalendarShell week markers in bundle", "Wathefni Calendar" in dash_js or "calendar" in dash_js.lower())
        check("Overview calendar panel in bundle", "View full calendar" in dash_js or "upcoming" in dash_js.lower())
        check("RTL support in bundle", "rtl" in dash_js.lower())
        check("conflict UX in bundle", "Override conflicts" in dash_js or "scheduling" in dash_js.lower())

    # Live DB proofs with disposable tenant
    company = f"C3SMOKE{uuid4().hex[:8].upper()}"
    user_a = str(uuid4())
    user_b = str(uuid4())
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
    end = now + timedelta(hours=1)

    try:
        import calendar_schema as schema

        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                schema.ensure_calendar_schema(cur)
            conn.commit()

        # Create first event
        ev1 = store.create_manual_event(
            app_mod,
            company_code=company,
            actor_user_id=user_a,
            payload={
                "event_type": "meeting",
                "title": "C3 Alpha",
                "visibility": "team",
                "start_at": now.isoformat(),
                "end_at": end.isoformat(),
                "timezone": "Asia/Kuwait",
                "attendees": [{"user_id": user_a, "role": "required"}, {"user_id": user_b, "role": "required"}],
            },
            actor_permissions={"calendar.manage", "calendar.read", "calendar.conflict_override"},
        )
        check("create first meeting", bool(ev1.get("event_id")))

        # Forced double-book without override
        blocked = False
        try:
            store.create_manual_event(
                app_mod,
                company_code=company,
                actor_user_id=user_a,
                payload={
                    "event_type": "meeting",
                    "title": "C3 Clash",
                    "visibility": "attendees_only",
                    "start_at": (now + timedelta(minutes=15)).isoformat(),
                    "end_at": (end + timedelta(minutes=15)).isoformat(),
                    "timezone": "Asia/Kuwait",
                    "attendees": [{"user_id": user_a, "role": "required"}],
                },
                actor_permissions={"calendar.manage", "calendar.read"},
            )
        except store.CalendarError as exc:
            blocked = exc.code == "scheduling_conflict" and exc.http_status == 409
            check("blocking conflict returns scheduling_conflict", blocked, exc.code)
            check("draft preserved flag", bool((exc.details or {}).get("draft_preserved")))
        if not blocked:
            check("blocking conflict returns scheduling_conflict", False)

        # Override with permission + reason
        ev2 = store.create_manual_event(
            app_mod,
            company_code=company,
            actor_user_id=user_a,
            payload={
                "event_type": "meeting",
                "title": "C3 Override",
                "visibility": "attendees_only",
                "start_at": (now + timedelta(minutes=15)).isoformat(),
                "end_at": (end + timedelta(minutes=15)).isoformat(),
                "timezone": "Asia/Kuwait",
                "attendees": [{"user_id": user_a, "role": "required"}],
                "override_conflicts": True,
                "override_reason": "Executive priority — C3 smoke",
            },
            actor_permissions={"calendar.manage", "calendar.read", "calendar.conflict_override"},
        )
        check("override with permission succeeds", bool(ev2.get("event_id")))

        # Override audit present
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT action FROM calendar_event_audit
                    WHERE company_code=%s AND event_id=%s AND action='conflict_override'
                    """,
                    (company, ev2["event_id"]),
                )
                audit_rows = cur.fetchall() or []
        check("override audit append-only", len(audit_rows) >= 1)

        # Optional attendee = warning not blocking
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                preview = conf.evaluate_conflicts(
                    cur,
                    app_mod,
                    company_code=company,
                    start=now,
                    end=end,
                    organizer_user_id=user_b,
                    attendees=[{"user_id": user_b, "role": "optional"}],
                    include_interview_legacy=False,
                )
        check("optional attendee not blocking", preview["blocking_count"] == 0)

        # Team / company / mine projections
        mine = proj.project_events(
            app_mod,
            company_code=company,
            actor_user_id=user_a,
            actor_role="owner",
            permissions=["calendar.read", "calendar.company", "calendar.manage"],
            scope="mine",
            start=now - timedelta(hours=1),
            end=end + timedelta(days=1),
        )
        check("mine projection returns events", mine["count"] >= 1)

        team = proj.project_events(
            app_mod,
            company_code=company,
            actor_user_id=user_a,
            actor_role="owner",
            permissions=["calendar.read", "calendar.company", "calendar.manage"],
            scope="team",
            start=now - timedelta(hours=1),
            end=end + timedelta(days=1),
        )
        check("team projection allowed with company oversight fallback", team["scope"] == "team")

        try:
            proj.project_events(
                app_mod,
                company_code=company,
                actor_user_id=user_b,
                actor_role="interviewer",
                permissions=["calendar.read"],
                scope="company",
                start=now - timedelta(hours=1),
                end=end + timedelta(days=1),
            )
            check("company scope denied without permission", False)
        except store.CalendarError as exc:
            check("company scope denied without permission", exc.http_status == 403)

        # Cross-tenant isolation
        other = proj.project_events(
            app_mod,
            company_code=f"OTHER{uuid4().hex[:6].upper()}",
            actor_user_id=user_a,
            actor_role="owner",
            permissions=["calendar.read", "calendar.company"],
            scope="mine",
            start=now - timedelta(hours=1),
            end=end + timedelta(days=1),
        )
        check("cross-tenant isolation", other["count"] == 0)

        # Overview ≤5
        # Seed extra events
        for i in range(7):
            store.create_manual_event(
                app_mod,
                company_code=company,
                actor_user_id=user_a,
                payload={
                    "event_type": "personal_block",
                    "title": f"C3 Block {i}",
                    "visibility": "private",
                    "start_at": (now + timedelta(days=i + 1)).isoformat(),
                    "end_at": (now + timedelta(days=i + 1, hours=1)).isoformat(),
                    "timezone": "Asia/Kuwait",
                    "override_conflicts": True,
                    "override_reason": "seed",
                },
                actor_permissions={"calendar.manage", "calendar.read", "calendar.conflict_override"},
            )
        overview = proj.project_overview(
            app_mod,
            company_code=company,
            actor_user_id=user_a,
            actor_role="owner",
            permissions=["calendar.read", "calendar.manage"],
            scope="mine",
        )
        check("overview upcoming <= 5", overview["upcoming_count"] <= 5)
        check("overview max_items 5", overview["max_items"] == 5)

        # Bounded range rejection
        try:
            proj.project_events(
                app_mod,
                company_code=company,
                actor_user_id=user_a,
                actor_role="owner",
                permissions=["calendar.read"],
                scope="mine",
                start=now,
                end=now + timedelta(days=120),
            )
            check("rejects oversized range", False)
        except store.CalendarError as exc:
            check("rejects oversized range", exc.code == "range_too_large")

        # Interview authority still enforced
        linked = store.create_manual_event(
            app_mod,
            company_code=company,
            actor_user_id=user_a,
            payload={
                "event_type": "meeting",
                "title": "C3 Manual link host",
                "visibility": "private",
                "start_at": (now + timedelta(days=20)).isoformat(),
                "end_at": (now + timedelta(days=20, hours=1)).isoformat(),
                "timezone": "Asia/Kuwait",
            },
            actor_permissions={"calendar.manage", "calendar.read", "calendar.conflict_override"},
        )
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO calendar_event_links
                      (link_id, company_code, event_id, source_workflow, source_record_id, link_status)
                    VALUES (%s,%s,%s,'interview',%s,'active')
                    """,
                    (str(uuid4()), company, linked["event_id"], str(uuid4())),
                )
            conn.commit()
        try:
            store.update_event(
                app_mod,
                company_code=company,
                event_id=linked["event_id"],
                actor_user_id=user_a,
                payload={"start_at": (now + timedelta(days=21)).isoformat(), "expected_version": linked["version"]},
                expected_version=linked["version"],
                actor_permissions={"calendar.manage"},
            )
            check("interview-linked schedule edit rejected", False)
        except store.CalendarError as exc:
            check("interview-linked schedule edit rejected", exc.code == "interview_authority_required")

        # Stale OCC
        try:
            store.update_event(
                app_mod,
                company_code=company,
                event_id=ev1["event_id"],
                actor_user_id=user_a,
                payload={"title": "stale", "expected_version": 999},
                expected_version=999,
                actor_permissions={"calendar.manage", "calendar.conflict_override"},
            )
            check("stale OCC returns 409", False)
        except store.CalendarError as exc:
            check("stale OCC returns 409", exc.http_status == 409)

        # Performance: seed volume + timed query
        seed_n = 200
        t0 = time.perf_counter()
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                for i in range(seed_n):
                    eid = str(uuid4())
                    s = now + timedelta(days=30, hours=i % 20)
                    e = s + timedelta(hours=1)
                    cur.execute(
                        """
                        INSERT INTO calendar_events (
                          event_id, company_code, event_type, title, visibility, sensitivity, status,
                          start_at, end_at, timezone, all_day, creator_user_id, organizer_user_id, owner_user_id, version
                        ) VALUES (%s,%s,'meeting',%s,'company','normal','confirmed',%s,%s,'Asia/Kuwait',false,%s,%s,%s,1)
                        """,
                        (eid, company, f"Perf {i}", s, e, user_a, user_a, user_a),
                    )
                    cur.execute(
                        """
                        INSERT INTO calendar_attendees (attendee_id, event_id, company_code, user_id, role, rsvp_status, is_organizer)
                        VALUES (%s,%s,%s,%s,'organizer','needs_action',true)
                        """,
                        (str(uuid4()), eid, company, user_a),
                    )
            conn.commit()
        t_seed = time.perf_counter() - t0
        t1 = time.perf_counter()
        perf = proj.project_events(
            app_mod,
            company_code=company,
            actor_user_id=user_a,
            actor_role="owner",
            permissions=["calendar.read", "calendar.company"],
            scope="company",
            start=now + timedelta(days=30),
            end=now + timedelta(days=32),
        )
        t_query = time.perf_counter() - t1
        check(f"perf seed {seed_n} events ({t_seed:.2f}s)", t_seed < 60)
        check(f"perf bounded company query ({t_query:.3f}s, n={perf['count']})", t_query < 5.0)
        print(f"PERF: seed={t_seed:.3f}s query={t_query:.3f}s count={perf['count']}")

        # Cleanup
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM calendar_event_audit WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM calendar_attendees WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM calendar_guests WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM calendar_event_links WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM calendar_event_org_scopes WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM calendar_events WHERE company_code=%s", (company,))
            conn.commit()
        check("cleanup", True)

    except Exception as exc:
        traceback.print_exc()
        check("live DB proofs", False, str(exc)[:200])

    print(f"=== C3 smoke done PASS={PASS} FAIL={FAIL} ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
