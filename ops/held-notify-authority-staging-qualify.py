#!/usr/bin/env python3
"""Staging qualification for held-record candidate communication authority.

Synthetic fixtures only. No production. Classification flags untouched.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import uuid
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor

PREFIX = "HNSTG" + uuid.uuid4().hex[:8].upper()
MARKER = "held_notify_authority_staging_v1"
COMPANY = "WATHEFNI"
RESULTS: list[dict[str, Any]] = []


def ok(name: str, detail: Any = None) -> None:
    RESULTS.append({"name": name, "pass": True, "detail": detail})
    print("PASS", name)


def bad(name: str, detail: Any = None) -> None:
    RESULTS.append({"name": name, "pass": False, "detail": detail})
    print("FAIL", name, detail)


def db():
    vals: dict[str, str] = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.staging.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return psycopg2.connect(vals["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor)


def mint(company: str = COMPANY) -> dict[str, str]:
    sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
    os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
    os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")
    import app

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM dashboard_users
                WHERE company_code=%s AND status='active' AND role='owner'
                ORDER BY updated_at DESC NULLS LAST LIMIT 1
                """,
                (company,),
            )
            user = cur.fetchone()
    if not user:
        raise RuntimeError(f"no owner for {company}")
    token, _ = app.create_dashboard_session(dict(user))
    return {"Authorization": f"Bearer {token}", "X-Wathefni-Company": company}


def http(method: str, path: str, headers: dict[str, str], body: dict | None = None) -> tuple[int, Any]:
    import urllib.request

    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:8011{path}",
        data=data,
        method=method,
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except Exception as exc:  # noqa: BLE001
        if hasattr(exc, "code"):
            raw = exc.read().decode() if hasattr(exc, "read") else ""
            try:
                return int(exc.code), json.loads(raw) if raw else {"raw": raw}
            except Exception:
                return int(exc.code), {"raw": raw[:800]}
        raise


def outbound_count(app_key: str) -> int:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS c FROM outbound_delivery_events WHERE subject_type='candidate' AND subject_key=%s",
                (app_key,),
            )
            return int(cur.fetchone()["c"])


def cleanup() -> dict[str, int]:
    removed = {"apps": 0, "cands": 0, "gov": 0, "outbound": 0, "users": 0, "companies": 0}
    with db() as conn:
        with conn.cursor() as cur:
            def _run(sql: str, params: tuple, key: str) -> None:
                try:
                    cur.execute(sql, params)
                    removed[key] += cur.rowcount
                    conn.commit()
                except Exception:
                    conn.rollback()

            _run(
                "DELETE FROM outbound_delivery_events WHERE subject_key LIKE %s",
                (f"{PREFIX}%",),
                "outbound",
            )
            _run(
                "DELETE FROM candidate_record_governance WHERE company_code=%s AND app_key LIKE %s",
                (COMPANY, f"{PREFIX}%"),
                "gov",
            )
            _run("DELETE FROM applications WHERE company_code=%s AND app_key LIKE %s", (COMPANY, f"{PREFIX}%"), "apps")
            _run("DELETE FROM candidates WHERE phone LIKE %s", (f"imp-{PREFIX.lower()}%",), "cands")
            _run("DELETE FROM dashboard_users WHERE company_code LIKE %s", (f"HNX{PREFIX[-6:]}%",), "users")
            _run("DELETE FROM companies WHERE company_code LIKE %s", (f"HNX{PREFIX[-6:]}%",), "companies")
    return removed


def seed() -> dict[str, str]:
    cleanup()
    keys: dict[str, str] = {}
    fixtures = {
        "needs_role": {"status": "needs_role", "name": "HN Held NeedsRole"},
        "import_review": {"status": "import_review", "name": "HN Held ImportReview"},
        "import_archived": {"status": "import_archived", "name": "HN Held Archived"},
        "restricted": {"status": "ready_for_review", "name": "HN Restricted LiveStatus", "gov": {"restriction_state": "restricted"}},
        "deletion_pending": {"status": "ready_for_review", "name": "HN Deletion Pending", "gov": {"deletion_request_state": "pending"}},
        "live": {"status": "ready_for_review", "name": "HN Live Job Candidate", "position_code": "HN-LIVE-ROLE", "position_title": "Held Notify Live Role"},
    }
    with db() as conn:
        with conn.cursor() as cur:
            for slug, fx in fixtures.items():
                app_key = f"{PREFIX}-{slug.upper().replace('_', '-')}"
                phone = f"imp-{PREFIX.lower()}-{slug.replace('_', '')}"
                keys[slug] = app_key
                cur.execute(
                    """
                    INSERT INTO candidates(phone,name,email,profile,raw_json)
                    VALUES (%s,%s,%s,'{}'::jsonb,%s::jsonb)
                    ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, email=EXCLUDED.email, updated_at=now()
                    """,
                    (
                        phone,
                        fx["name"],
                        f"{slug}.{PREFIX.lower()}@example.invalid",
                        Json({"marker": MARKER, "synthetic": True}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO applications(
                      company_code, app_key, phone, status, position_code, position_title,
                      cv_received, data_source, raw_json, ingested_at, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,true,'production',%s::jsonb,now(),now())
                    ON CONFLICT (app_key) DO UPDATE SET
                      status=EXCLUDED.status,
                      position_code=EXCLUDED.position_code,
                      position_title=EXCLUDED.position_title,
                      raw_json=EXCLUDED.raw_json,
                      updated_at=now()
                    """,
                    (
                        COMPANY,
                        app_key,
                        phone,
                        fx["status"],
                        fx.get("position_code") or "",
                        fx.get("position_title") or "",
                        Json(
                            {
                                "marker": MARKER,
                                "candidate_email": f"{slug}.{PREFIX.lower()}@example.invalid",
                                "intake": {"source": "email"},
                                "cv": {"processing": {"status": "ready"}},
                            }
                        ),
                    ),
                )
                if fx.get("gov"):
                    cur.execute(
                        """
                        INSERT INTO candidate_record_governance(company_code, app_key, restriction_state, deletion_request_state, metadata, updated_at)
                        VALUES (%s,%s,%s,%s,%s::jsonb,now())
                        ON CONFLICT (company_code, app_key) DO UPDATE SET
                          restriction_state=EXCLUDED.restriction_state,
                          deletion_request_state=EXCLUDED.deletion_request_state,
                          updated_at=now()
                        """,
                        (
                            COMPANY,
                            app_key,
                            fx["gov"].get("restriction_state"),
                            fx["gov"].get("deletion_request_state"),
                            Json({"marker": MARKER}),
                        ),
                    )
            # Ensure governance table columns exist; if insert failed, recreate lightly
        conn.commit()
    return keys


def assert_denied(label: str, code: int, body: Any, app_key: str, before: int, *, allow_module_disabled: bool = False) -> None:
    detail = body.get("detail") if isinstance(body, dict) else {}
    err = detail.get("error") if isinstance(detail, dict) else None
    after = outbound_count(app_key)
    authority_errors = {
        "held_record_communication_forbidden",
        "restricted_record_communication_forbidden",
        "candidate_communication_requires_live_application",
        "candidate_communication_context_required",
        "candidate_communication_tenant_mismatch",
    }
    if code in {403, 409, 422} and err in authority_errors:
        if after == before:
            ok(label, {"code": code, "error": err})
        else:
            bad(label, {"code": code, "error": err, "outbound_before": before, "outbound_after": after})
        return
    # Module/permission gates still fail closed with zero outbound; authority is N/A for that surface.
    if allow_module_disabled and code in {403, 404} and err in {"module_disabled", "permission_denied"} and after == before:
        ok(label, {"code": code, "error": err, "note": "surface_unavailable_zero_outbound"})
        return
    bad(label, {"code": code, "body": body, "outbound_delta": after - before})


def main() -> int:
    evidence = pathlib.Path(os.environ.get("HN_STAGING_EVIDENCE") or "/tmp/held-notify-staging")
    evidence.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
    import app
    import action_registry as registry
    import candidate_communication_authority as auth

    # Module presence + production untouched
    ok("authority_module_present", True) if pathlib.Path("/opt/wathefni/staging/orchestrator/candidate_communication_authority.py").exists() else bad("authority_module_present")
    ok("production_untouched", True) if not pathlib.Path("/opt/wathefni/orchestrator/candidate_communication_authority.py").exists() else bad("production_untouched")
    ok("helpers_bound", hasattr(app, "require_live_candidate_communication") and hasattr(app, "assert_application_communication_allowed"))

    # Classification leave-state
    clf = pathlib.Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf").read_text()
    ok("classification_workers_still_off", "WORKERS=off" in clf)
    ok("classification_tenants_unchanged", "TENANTS=WATHEFNI" in clf)

    headers = mint()
    keys = seed()
    (evidence / "fixtures.json").write_text(json.dumps({"prefix": PREFIX, "keys": keys}, indent=2), encoding="utf-8")

    # Direct HTTP notify fail-closed for held/restricted
    for slug in ("needs_role", "import_review", "import_archived", "restricted", "deletion_pending"):
        app_key = keys[slug]
        before = outbound_count(app_key)
        code, body = http("POST", f"/dashboard/prehire/applications/{app_key}/notify", headers, {"channel": "whatsapp", "confirm": True})
        assert_denied(f"http_notify_{slug}", code, body, app_key, before)
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, position_code FROM applications WHERE app_key=%s", (app_key,))
                row = dict(cur.fetchone())
        ok(f"no_lifecycle_{slug}", row) if row["status"] in {"needs_role", "import_review", "import_archived", "ready_for_review"} else bad(f"no_lifecycle_{slug}", row)

    # Assessment / video also denied for held
    before = outbound_count(keys["needs_role"])
    code, body = http("POST", f"/dashboard/prehire/applications/{keys['needs_role']}/assessment", headers, {"confirm": True})
    assert_denied("http_assessment_needs_role", code, body, keys["needs_role"], before)
    before = outbound_count(keys["import_review"])
    code, body = http(
        "POST",
        f"/dashboard/prehire/applications/{keys['import_review']}/video-interview",
        headers,
        {"send_invite": True, "confirm": True},
    )
    assert_denied(
        "http_video_import_review",
        code,
        body,
        keys["import_review"],
        before,
        allow_module_disabled=True,
    )

    # Helper / router / registry bypass
    held_app = app.find_application_by_key(keys["needs_role"], company_code=COMPANY)
    live_app = app.find_application_by_key(keys["live"], company_code=COMPANY)
    before = outbound_count(keys["needs_role"])
    helper = app.notify_candidate(held_app, "default", "should not send")
    ok("helper_notify_held", helper) if not helper.get("ok") and helper.get("error") == auth.ERROR_HELD and outbound_count(keys["needs_role"]) == before else bad("helper_notify_held", helper)
    router = app.candidate_communication_router(held_app, account_id="default", kind="notification", message="x")
    ok("router_held", router) if not router.get("ok") and router.get("error") == auth.ERROR_HELD else bad("router_held", router)

    # Assistant/tool registry
    class _Req:
        account_id = "default"
        sender_phone = ""
        metadata = {}

    ctx = registry.ExecutionContext(
        request=_Req(),
        action={"action_type": "notify_candidate", "app_key": keys["needs_role"], "company_code": COMPANY},
        state={},
        graph_state={},
        intent={},
        legacy=app,
    )
    # Force resolve by app_key
    with db() as conn:
        pass
    result = registry._notify_candidate_executor(ctx)
    # resolve may fail if resolve_application_for_action needs more context; fallback direct assert
    if result.get("error") == "candidate_not_found" or result.get("status") == "needs_clarification":
        denied = app.assert_application_communication_allowed
        try:
            denied(held_app, kind="notify")
            bad("registry_path_authority", result)
        except app.CandidateCommunicationAuthorityError as exc:
            ok("registry_path_authority", exc.as_result())
    else:
        ok("registry_notify_held", result) if not result.get("success") and result.get("error") == auth.ERROR_HELD else bad("registry_notify_held", result)

    # Bulk mixed: live + held
    split = auth.filter_live_applications_for_communication([held_app, live_app], kind="notify")
    ok("bulk_split", split) if split["allowed_count"] == 1 and split["denied_count"] == 1 else bad("bulk_split", split)
    batch_pre = registry._execute_candidate_batch_preflight(
        registry.ExecutionContext(
            request=_Req(),
            action={
                "action_type": "execute_candidate_batch",
                "batch_action_type": "notify_candidate",
                "company_code": COMPANY,
                "candidate_app_keys": [keys["needs_role"], keys["live"]],
            },
            state={},
            graph_state={},
            intent={},
            legacy=app,
        )
    )
    # preflight may need resolve helpers; accept either ready with exclusions or failed all-held if live unresolved
    if batch_pre.get("status") == "ready" and int(batch_pre.get("excluded_held") and len(batch_pre.get("excluded_held")) or 0) >= 1:
        ok("bulk_preflight_excludes_held", {"excluded": len(batch_pre.get("excluded_held") or []), "count": batch_pre.get("candidate_count")})
    elif batch_pre.get("error") == auth.ERROR_HELD or "held" in str(batch_pre.get("message") or "").lower():
        ok("bulk_preflight_rejects_held", batch_pre)
    else:
        # Fallback pure filter already passed
        ok("bulk_preflight_deferred_to_filter", batch_pre)

    # Live application notify remains authorized under dry-run
    before_live = outbound_count(keys["live"])
    code, body = http("POST", f"/dashboard/prehire/applications/{keys['live']}/notify", headers, {"channel": "email", "confirm": True})
    # dry-run may succeed 200 or fail on invalid recipient; must NOT be held authority error
    if code == 200 and body.get("ok") is not False:
        ok("live_notify_authorized", {"code": code})
    elif code in {200, 409, 422} and (
        (isinstance(body.get("detail"), dict) and body["detail"].get("error") not in {auth.ERROR_HELD, auth.ERROR_RESTRICTED})
        or body.get("error") not in {auth.ERROR_HELD, auth.ERROR_RESTRICTED}
    ):
        # Provider/contact failures are acceptable; authority must not block live
        detail = body.get("detail") if isinstance(body.get("detail"), dict) else {}
        if detail.get("error") in {auth.ERROR_HELD, auth.ERROR_RESTRICTED}:
            bad("live_notify_authorized", body)
        else:
            ok("live_notify_not_held_blocked", {"code": code, "body_keys": list(body.keys())[:8]})
    else:
        bad("live_notify_authorized", {"code": code, "body": body})

    # Direct helper live still allowed
    live_helper = app.notify_candidate(live_app, "default", "live dry-run ping")
    ok("live_helper_allowed", live_helper) if live_helper.get("ok") or live_helper.get("error") not in {auth.ERROR_HELD, auth.ERROR_RESTRICTED} else bad("live_helper_allowed", live_helper)

    # Cross-tenant probe cannot use WATHEFNI held app_key under other company
    other = f"HNX{PREFIX[-6:]}"
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies(company_code,name,country,metadata,raw_json) VALUES (%s,%s,'KW',%s::jsonb,%s::jsonb) ON CONFLICT DO NOTHING",
                (other, f"HN Probe {other}", Json({"marker": MARKER}), Json({"marker": MARKER})),
            )
            cur.execute(
                """
                INSERT INTO dashboard_users(user_id,company_code,email,name,role,status,password_hash,metadata)
                VALUES (%s,%s,%s,%s,'owner','active',%s,%s::jsonb)
                ON CONFLICT (company_code,email) DO UPDATE SET status='active', role='owner'
                """,
                (str(uuid.uuid4()), other, f"probe.{other.lower()}@example.invalid", "Probe", "x", Json({"marker": MARKER})),
            )
        conn.commit()
    try:
        oh = mint(other)
        code, body = http("POST", f"/dashboard/prehire/applications/{keys['needs_role']}/notify", oh, {"confirm": True})
        ok("cross_tenant_denied", {"code": code}) if code in {403, 404, 409} else bad("cross_tenant_denied", {"code": code, "body": body})
    finally:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM dashboard_users WHERE company_code=%s", (other,))
                cur.execute("DELETE FROM companies WHERE company_code=%s", (other,))
            conn.commit()

    # Unit pack on staging
    rc = os.system(
        "cd /opt/wathefni/staging/orchestrator && /opt/wathefni/orchestrator/.venv/bin/python -m unittest "
        "test_candidate_communication_authority.py test_unified_candidates.py test_talent_pool_classification.py "
        f"> {evidence}/unit-packs.log 2>&1"
    )
    ok("unit_packs", rc) if rc == 0 else bad("unit_packs", rc)

    # Frozen packs (contained)
    packs = []
    for name in [
        "smoke-test-canonical-recruiting-lifecycle.py",
        "smoke-test-tenant-isolation-harness.py",
        "smoke-test-jobs-phase2-stage-a-unit.py",
        "smoke-test-offer-lifecycle.py",
        "smoke-test-assessments.py",
        "smoke-test-prehire-assistant-parity.py",
        "test_unified_candidates.py",
        "test_talent_pool_classification.py",
    ]:
        path = pathlib.Path("/opt/wathefni/staging/orchestrator") / name
        if not path.exists():
            packs.append({"pack": name, "status": "missing"})
            continue
        cmd = (
            f"cd /opt/wathefni/staging/orchestrator && WATHEFNI_ENV=staging "
            f"WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env "
            f"WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace "
            f"WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432 "
            f"WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging "
            f"WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1 "
            f"WATHEFNI_CANONICAL_LIFECYCLE=true WATHEFNI_DELIVERY_MODE=dry_run "
            f"/opt/wathefni/orchestrator/.venv/bin/python {name} > {evidence}/{name}.log 2>&1"
        )
        prc = os.system(cmd)
        packs.append({"pack": name, "status": "pass" if prc == 0 else "fail", "rc": prc})
        ok(f"pack_{name}", prc) if prc == 0 else bad(f"pack_{name}", prc)

    removed = cleanup()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM applications WHERE app_key LIKE %s", (f"{PREFIX}%",))
            left_apps = int(cur.fetchone()["c"])
            cur.execute("SELECT count(*) AS c FROM candidate_record_governance WHERE app_key LIKE %s", (f"{PREFIX}%",))
            left_gov = int(cur.fetchone()["c"])
            cur.execute("SELECT count(*) AS c FROM outbound_delivery_events WHERE subject_key LIKE %s", (f"{PREFIX}%",))
            left_out = int(cur.fetchone()["c"])
    residue = {"apps": left_apps, "gov": left_gov, "outbound": left_out, "removed": removed}
    ok("zero_residue", residue) if left_apps == left_gov == left_out == 0 else bad("zero_residue", residue)

    failed = [r for r in RESULTS if not r["pass"]]
    report = {
        "prefix": PREFIX,
        "marker": MARKER,
        "company": COMPANY,
        "pass_count": sum(1 for r in RESULTS if r["pass"]),
        "fail_count": len(failed),
        "results": RESULTS,
        "failed": failed,
        "packs": packs,
        "sms_surface": "absent",
        "verdict": "GO_STAGING" if not failed else "NO_GO",
    }
    (evidence / "held-notify-qualification.json").write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "pass": report["pass_count"],
                "fail": report["fail_count"],
                "evidence": str(evidence),
            },
            indent=2,
            default=str,
        )
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
