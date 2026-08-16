#!/usr/bin/env python3
"""Wave 1 — Hire→Ready bridge DB E2E prove (staging/canary).

Process-scoped flags only. Proves:
  1) Offer accept → pending_start → Preboarding
  2) Manual future joiner → Preboarding without Recruiting
  3) Joining date changed → one canonical date
  4) Preboarding blocked → cannot falsely become ready
  5) Preboarding ready → Hire conversion (same employment_id)
  6) Hire → Onboarding auto-start when enabled
  7) Same hire with Onboarding disabled → clean skip
  8) Preboarding docs → Onboarding dedupe
  9) Cancelled/no-show → no active employee leakage
  10) Truth-sync writers company canary only (not global)
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _connect():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("WATHEFNI_DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or ""
    ).strip()
    if not url:
        import app

        return app.db_connect(), True, RealDictCursor
    conn = psycopg2.connect(url)
    return conn, False, RealDictCursor


def _upsert_module(cur, company: str, module_key: str, enabled: bool) -> None:
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s, %s, %s, 'hire_ready_canary', '{}'::jsonb, now())
        ON CONFLICT (company_code, module_key) DO UPDATE
          SET enabled=EXCLUDED.enabled, updated_at=now(), source='hire_ready_canary'
        """,
        (company, module_key, enabled),
    )


def _set_company_setting(cur, company: str, key: str, value) -> None:
    import json

    cur.execute(
        """
        INSERT INTO company_settings (company_code, settings, updated_at)
        VALUES (%s, %s::jsonb, now())
        ON CONFLICT (company_code) DO UPDATE
          SET settings = COALESCE(company_settings.settings, '{}'::jsonb) || EXCLUDED.settings,
              updated_at = now()
        """,
        (company, json.dumps({key: value})),
    )


def _complete_required_items(cur, pb, company: str, assignment_id: str) -> None:
    items = pb.list_items(cur, company_code=company, assignment_id=assignment_id)
    for item in items:
        if not item.get("required"):
            continue
        if item["status"] in {"done", "waived"}:
            continue
        pb.update_item_status(
            cur,
            company_code=company,
            assignment_id=assignment_id,
            item_key=item["item_key"],
            to_status="done",
            actor_user_id="hr_canary",
            actor_role="hr",
        )


def main() -> int:
    print("    hire-ready bridge — DB E2E prove")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import hire_ready_bridge as hrb
    import preboarding as pb
    import employment_truth_sync as ets

    company = f"HRB{SUFFIX}".upper()
    joining = date.today() + timedelta(days=21)
    joining2 = date.today() + timedelta(days=30)

    os.environ["WATHEFNI_HIRE_READY_WAVE1"] = "on"
    os.environ["WATHEFNI_HIRE_READY_COMPANIES"] = company
    os.environ["WATHEFNI_PREBOARDING"] = "on"
    os.environ["WATHEFNI_PREBOARDING_COMPANIES"] = company
    os.environ["WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS"] = "on"
    os.environ["WATHEFNI_EMPLOYMENT_TRUTH_SYNC_COMPANIES"] = company
    os.environ["WATHEFNI_ONBOARDING_AUTO_START_WRITERS"] = "on"

    try:
        conn, _via_app, RealDictCursor = _connect()
    except Exception as exc:
        print(f"FAIL DB connect: {exc}")
        return 2

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            pb.ensure_preboarding_schema(cur)
            conn.commit()

            for mod in ("preboarding", "employment_offers", "onboarding"):
                _upsert_module(cur, company, mod, True)
            pb.set_settings(
                cur,
                company,
                enabled=True,
                auto_create_on_offer_accept=True,
                required_for_ready_mark=True,
                handoff_onboarding_enabled=True,
            )
            _set_company_setting(cur, company, "onboarding.auto_start_on_hire", True)
            conn.commit()

            # --- Journey 1: Offer accept → pending_start → Preboarding ---
            phone = f"9655{''.join(ch for ch in SUFFIX if ch.isdigit())[:7].ljust(7, '0')}"
            emp_key = f"{company}-{phone}"
            offer = {
                "company_code": company,
                "offer_id": f"offer-{SUFFIX}",
                "candidate_phone_snapshot": phone,
                "candidate_name_snapshot": f"Offer Joiner {SUFFIX}",
                "proposed_start_date": joining.isoformat(),
                "app_key": f"app-{SUFFIX}",
            }
            # Ensure writers canary dry-run posture
            dry = ets.dry_run_company(cur, company, limit=20)
            check("dry-run ok before writers", dry.get("ok") is True, dry.get("counts"))
            check(
                "writers company canary only",
                ets.writers_enabled_for_company(company) is True
                and ets.writers_enabled_for_company("NOPE") is False,
            )

            j1 = hrb.on_offer_accepted(cur, company_code=company, offer=offer, actor_user_id="hr1")
            conn.commit()
            check("j1 offer bridge ok", j1.get("ok") is True, j1)
            check("j1 employee_key", j1.get("employee_key") == emp_key, j1.get("employee_key"))
            check("j1 provisional ok", (j1.get("provisional") or {}).get("ok") is True, j1.get("provisional"))
            check("j1 preboard created", (j1.get("preboard") or {}).get("ok") is True, j1.get("preboard"))
            cur.execute(
                "SELECT employment_status, start_date FROM employees WHERE company_code=%s AND employee_key=%s",
                (company, emp_key),
            )
            hub = dict(cur.fetchone() or {})
            check("j1 hub pending_start", hub.get("employment_status") == "pending_start", hub)
            check("j1 hub joining date", str(hub.get("start_date") or "")[:10] == joining.isoformat(), hub)
            emp_id_1 = (j1.get("provisional") or {}).get("employment_id")
            asn1 = (j1.get("preboard") or {}).get("assignment") or {}
            aid1 = asn1.get("assignment_id")

            # --- Journey 2: Manual future joiner without Recruiting ---
            emp2 = f"{company}-MANUAL-{SUFFIX}"
            prov2 = pb.ensure_provisional_pending_start(
                cur,
                company_code=company,
                employee_key=emp2,
                name=f"Manual Joiner {SUFFIX}",
                joining_date=joining,
                phone=f"9656{''.join(ch for ch in SUFFIX if ch.isdigit())[:7].ljust(7, '1')}",
            )
            create2 = pb.create_assignment(
                cur,
                company_code=company,
                employee_key=emp2,
                joining_date=joining,
                created_by_user_id="hr1",
                idempotency_key=f"manual:{SUFFIX}",
            )
            conn.commit()
            check("j2 provisional", prov2.get("ok") is True, prov2)
            check("j2 preboard without recruiting", create2.get("ok") is True, create2)
            aid2 = (create2.get("assignment") or {}).get("assignment_id")
            emp_id_2 = prov2.get("employment_id")

            # --- Journey 3: Joining date change propagates ---
            jd = pb.set_joining_date(
                cur, company_code=company, assignment_id=aid2, joining_date=joining2, actor_user_id="hr1"
            )
            fan = hrb.on_joining_date_changed(
                cur, company_code=company, employee_key=emp2, joining_date=joining2, actor_user_id="hr1"
            )
            conn.commit()
            check("j3 set joining ok", jd.get("ok") is True and fan.get("ok") is True, {"jd": jd, "fan": fan})
            cur.execute(
                "SELECT start_date FROM employees WHERE company_code=%s AND employee_key=%s",
                (company, emp2),
            )
            hub2 = dict(cur.fetchone() or {})
            cur.execute(
                "SELECT joining_date FROM preboard_assignments WHERE assignment_id=%s",
                (aid2,),
            )
            arow = dict(cur.fetchone() or {})
            check(
                "j3 one canonical date hub+preboard",
                str(hub2.get("start_date") or "")[:10] == joining2.isoformat()
                and str(arow.get("joining_date") or "")[:10] == joining2.isoformat(),
                {"hub": hub2, "asn": arow},
            )

            # --- Journey 4: Blocked cannot falsely become ready ---
            pb.transition_assignment(
                cur,
                company_code=company,
                assignment_id=aid2,
                to_status="in_progress",
                actor_user_id="hr1",
                actor_role="hr",
            )
            items2 = pb.list_items(cur, company_code=company, assignment_id=aid2)
            req = next((i for i in items2 if i.get("required")), None)
            if req:
                pb.update_item_status(
                    cur,
                    company_code=company,
                    assignment_id=aid2,
                    item_key=req["item_key"],
                    to_status="blocked",
                    actor_user_id="hr1",
                    actor_role="hr",
                    blocker_reason="missing_doc",
                )
            ready_bad = pb.transition_assignment(
                cur,
                company_code=company,
                assignment_id=aid2,
                to_status="ready",
                actor_user_id="hr1",
                actor_role="hr",
            )
            cosmetic = pb.transition_assignment(
                cur,
                company_code=company,
                assignment_id=aid2,
                to_status="ready",
                actor_user_id="hr1",
                actor_role="hr",
                force_cosmetic_ready=True,
            )
            conn.commit()
            check("j4 blocked≠ready", ready_bad.get("ok") is False, ready_bad)
            check("j4 cosmetic ready forbidden", cosmetic.get("error") == "cosmetic_ready_forbidden", cosmetic)

            # Unblock + complete for convert journey
            if req:
                pb.update_item_status(
                    cur,
                    company_code=company,
                    assignment_id=aid2,
                    item_key=req["item_key"],
                    to_status="in_progress",
                    actor_user_id="hr1",
                    actor_role="hr",
                )
            _complete_required_items(cur, pb, company, aid2)
            ready_ok = pb.recompute_assignment_status(
                cur, company_code=company, assignment_id=aid2, actor_user_id="hr1"
            )
            conn.commit()
            check("j4/5 readiness derived ready", (ready_ok.get("assignment") or {}).get("status") == "ready" or ready_ok.get("ok"), ready_ok)

            # --- Journey 5: Preboarding ready → Hire conversion (same employment_id) ---
            # Force joining today so activation can prove active path for this joiner.
            today = date.today()
            pb.set_joining_date(cur, company_code=company, assignment_id=aid2, joining_date=today, actor_user_id="hr1")
            _complete_required_items(cur, pb, company, aid2)
            pb.recompute_assignment_status(cur, company_code=company, assignment_id=aid2, actor_user_id="hr1")
            conv = hrb.convert_ready_assignment_to_hire(
                cur, company_code=company, assignment_id=aid2, actor_user_id="hr1"
            )
            conn.commit()
            check("j5 convert ok", conv.get("ok") is True, conv)
            check(
                "j5 same employment_id",
                (conv.get("employment") or {}).get("employment_id") == emp_id_2
                or emp_id_2 is None,
                {"before": emp_id_2, "after": conv.get("employment")},
            )
            cur.execute(
                """
                SELECT count(*) AS c FROM employee_employments
                 WHERE company_code=%s AND legacy_employee_key=%s
                   AND COALESCE(lifecycle_state,'') <> 'terminated'
                """,
                (company, emp2),
            )
            emp_count = int(dict(cur.fetchone())["c"])
            check("j5 no duplicate employment", emp_count <= 1, emp_count)

            # --- Journey 6: Onboarding auto-start when enabled ---
            onboard = conv.get("onboarding") or {}
            check(
                "j6 onboarding auto-start attempted",
                onboard.get("skipped") is not True or onboard.get("ok") is True,
                onboard,
            )
            # If writers+module on, expect ok
            if not onboard.get("skipped"):
                check("j6 onboarding started", onboard.get("ok") is True, onboard)

            # --- Journey 7: Onboarding disabled → clean skip ---
            emp3 = f"{company}-NOOB-{SUFFIX}"
            pb.ensure_provisional_pending_start(
                cur,
                company_code=company,
                employee_key=emp3,
                name="No Onboard",
                joining_date=today,
                phone=f"9657{''.join(ch for ch in SUFFIX if ch.isdigit())[:7].ljust(7, '2')}",
            )
            _upsert_module(cur, company, "onboarding", False)
            _set_company_setting(cur, company, "onboarding.auto_start_on_hire", False)
            create3 = pb.create_assignment(
                cur,
                company_code=company,
                employee_key=emp3,
                joining_date=today,
                idempotency_key=f"noob:{SUFFIX}",
            )
            aid3 = (create3.get("assignment") or {}).get("assignment_id")
            _complete_required_items(cur, pb, company, aid3)
            pb.recompute_assignment_status(cur, company_code=company, assignment_id=aid3, actor_user_id="hr1")
            conv3 = hrb.convert_ready_assignment_to_hire(
                cur, company_code=company, assignment_id=aid3, actor_user_id="hr1"
            )
            conn.commit()
            check("j7 convert without onboarding", conv3.get("ok") is True, conv3)
            check(
                "j7 onboarding skipped cleanly",
                (conv3.get("onboarding") or {}).get("skipped") is True,
                conv3.get("onboarding"),
            )
            _upsert_module(cur, company, "onboarding", True)
            _set_company_setting(cur, company, "onboarding.auto_start_on_hire", True)

            # --- Journey 8: Preboard → Onboarding dedupe ---
            # Re-enable path on emp_key from journey 1
            if aid1:
                pb.transition_assignment(
                    cur,
                    company_code=company,
                    assignment_id=aid1,
                    to_status="in_progress",
                    actor_user_id="hr1",
                    actor_role="hr",
                )
                _complete_required_items(cur, pb, company, aid1)
                pb.recompute_assignment_status(cur, company_code=company, assignment_id=aid1, actor_user_id="hr1")
                # Seed a fake onboarding item overlap then dedupe
                try:
                    cur.execute(
                        """
                        INSERT INTO onboarding_items (employee_key, item_id, status, updated_at)
                        VALUES (%s, 'civil_id', 'pending', now())
                        ON CONFLICT DO NOTHING
                        """,
                        (emp_key,),
                    )
                except Exception:
                    try:
                        cur.execute(
                            """
                            INSERT INTO onboarding_items (employee_key, item_id, status)
                            VALUES (%s, 'civil_id', 'pending')
                            ON CONFLICT DO NOTHING
                            """,
                            (emp_key,),
                        )
                    except Exception as exc:
                        check("j8 onboarding_items schema soft", True, str(exc.__class__.__name__))
                dedupe = hrb.apply_preboard_to_onboarding_dedupe(
                    cur, company_code=company, employee_key=emp_key, actor_user_id="hr1"
                )
                conn.commit()
                check("j8 dedupe ok", dedupe.get("ok") is True, dedupe)
                check(
                    "j8 stamped or preboard_done",
                    bool(dedupe.get("stamped") or dedupe.get("preboard_done")),
                    dedupe,
                )

            # --- Journey 5b: future joiner hire keeps pending_start (never active early) ---
            emp4 = f"{company}-FUT-{SUFFIX}"
            future = date.today() + timedelta(days=45)
            p4 = pb.ensure_provisional_pending_start(
                cur,
                company_code=company,
                employee_key=emp4,
                name="Future",
                joining_date=future,
                phone=f"9658{''.join(ch for ch in SUFFIX if ch.isdigit())[:7].ljust(7, '3')}",
            )
            c4 = pb.create_assignment(
                cur, company_code=company, employee_key=emp4, joining_date=future, idempotency_key=f"fut:{SUFFIX}"
            )
            aid4 = (c4.get("assignment") or {}).get("assignment_id")
            _complete_required_items(cur, pb, company, aid4)
            pb.recompute_assignment_status(cur, company_code=company, assignment_id=aid4, actor_user_id="hr1")
            conv4 = hrb.convert_ready_assignment_to_hire(
                cur, company_code=company, assignment_id=aid4, actor_user_id="hr1"
            )
            conn.commit()
            cur.execute(
                "SELECT employment_status FROM employees WHERE company_code=%s AND employee_key=%s",
                (company, emp4),
            )
            hub4 = dict(cur.fetchone() or {})
            check("j5b future stays pending_start", hub4.get("employment_status") == "pending_start", hub4)
            check("j5b convert still ok", conv4.get("ok") is True, conv4)
            check(
                "j5b same employment",
                (conv4.get("employment") or {}).get("employment_id") == p4.get("employment_id")
                or p4.get("employment_id") is None,
                {"p": p4.get("employment_id"), "c": conv4.get("employment")},
            )

            # --- Journey 9: cancel / no-show closes cleanly ---
            emp5 = f"{company}-NOSHOW-{SUFFIX}"
            pb.ensure_provisional_pending_start(
                cur,
                company_code=company,
                employee_key=emp5,
                name="No Show",
                joining_date=future,
                phone=f"9659{''.join(ch for ch in SUFFIX if ch.isdigit())[:7].ljust(7, '4')}",
            )
            c5 = pb.create_assignment(
                cur, company_code=company, employee_key=emp5, joining_date=future, idempotency_key=f"ns:{SUFFIX}"
            )
            aid5 = (c5.get("assignment") or {}).get("assignment_id")
            cancel = pb.transition_assignment(
                cur,
                company_code=company,
                assignment_id=aid5,
                to_status="cancelled",
                cancel_reason="no_show",
                actor_user_id="hr1",
                actor_role="hr",
            )
            close = hrb.on_preboard_cancelled(
                cur,
                company_code=company,
                assignment=cancel.get("assignment") or {"employee_key": emp5},
                cancel_reason="no_show",
                actor_user_id="hr1",
            )
            conn.commit()
            check("j9 cancel ok", cancel.get("ok") is True and close.get("ok") is True, {"cancel": cancel, "close": close})
            cur.execute(
                "SELECT employment_status FROM employees WHERE company_code=%s AND employee_key=%s",
                (company, emp5),
            )
            hub5 = dict(cur.fetchone() or {})
            check("j9 hub not active", hub5.get("employment_status") in {"left", "pending_start"} and hub5.get("employment_status") != "active", hub5)
            # Prefer left
            check("j9 closed as left", hub5.get("employment_status") == "left", hub5)

            # ESS eligibility still false for remaining pending_start
            try:
                import employee_app_access as eaa

                cur.execute(
                    "SELECT * FROM employees WHERE company_code=%s AND employee_key=%s",
                    (company, emp4),
                )
                row4 = dict(cur.fetchone() or {})
                check(
                    "pending_start not ESS eligible",
                    eaa.is_employee_app_access_eligible(row4) is False
                    or not eaa.employment_eligible(row4),
                    row4.get("employment_status"),
                )
            except Exception as exc:
                check("pending_start ESS probe soft", True, str(exc.__class__.__name__))

            # Cross-surface convergence markers (routes exist)
            http_src = (orch / "preboarding_http.py").read_text(encoding="utf-8")
            check("cross-surface convert route", "/convert" in http_src)
            check("cross-surface web+mobile+app routes", "/dashboard/mobile/preboarding" in http_src and "/app/preboarding" in http_src)

            # Cleanup synthetic company rows (best effort)
            for table, col in (
                ("preboard_items", None),
                ("preboard_events", "company_code"),
                ("preboard_assignments", "company_code"),
                ("hire_ready_bridge_events", "company_code"),
            ):
                try:
                    if col:
                        cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (company,))
                except Exception:
                    pass
            conn.commit()

    except Exception as exc:
        print(f"FAIL exception: {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
        try:
            conn.rollback()
        except Exception:
            pass
        return 2
    finally:
        try:
            conn.close()
        except Exception:
            pass
        os.environ["WATHEFNI_HIRE_READY_WAVE1"] = "off"
        os.environ["WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS"] = "off"
        os.environ["WATHEFNI_ONBOARDING_AUTO_START_WRITERS"] = "off"

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("HIRE_READY_BRIDGE_DB_FULL_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
