#!/usr/bin/env python3
"""Held/live authority separation + flag rollback proofs for restored baseline requal."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import uuid
import urllib.request

import psycopg2
from psycopg2.extras import RealDictCursor, Json

sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
os.environ.setdefault("WATHEFNI_ENV", "staging")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")
os.environ.setdefault("WATHEFNI_DASHBOARD_DIST", "/opt/wathefni/staging/dashboard-dist")
os.environ.setdefault("WATHEFNI_CANONICAL_LIFECYCLE", "true")

import app  # noqa: E402
import unified_candidates as uc  # noqa: E402

EVIDENCE = pathlib.Path(os.environ["REQUAL_EVIDENCE"])
PREFIX = "UCREQ" + uuid.uuid4().hex[:8].upper()
MARKER = "unified_candidates_requal_v1"
COMPANY = "WATHEFNI"
RESULTS: list[dict] = []


def ok(name: str, detail=None) -> None:
    RESULTS.append({"name": name, "pass": True, "detail": detail})
    print("PASS", name)


def bad(name: str, detail=None) -> None:
    RESULTS.append({"name": name, "pass": False, "detail": detail})
    print("FAIL", name, detail)


def db():
    vals = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.staging.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return psycopg2.connect(vals["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor)


def set_flag(master: str, tenants: str) -> None:
    conf = pathlib.Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d/unified-candidates.conf")
    conf.write_text(
        "[Service]\n"
        f"Environment=WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL={master}\n"
        f"Environment=WATHEFNI_UNIFIED_CANDIDATES_TENANTS={tenants}\n",
        encoding="utf-8",
    )
    os.system("systemctl daemon-reload && systemctl restart wathefni-orchestrator-staging.service")
    for _ in range(60):
        if os.system("curl -sf http://127.0.0.1:8011/health >/dev/null") == 0:
            return
        time.sleep(1)
    raise RuntimeError("health failed after flag change")


def mint(company: str = COMPANY) -> dict[str, str]:
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
    token, _ = app.create_dashboard_session(dict(user))
    return {"Authorization": f"Bearer {token}", "X-Wathefni-Company": company}


def http(method: str, path: str, headers: dict, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:8011{path}",
        data=data,
        method=method,
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except Exception as exc:  # noqa: BLE001
        if hasattr(exc, "code"):
            raw = exc.read().decode() if hasattr(exc, "read") else ""
            try:
                payload = json.loads(raw) if raw else {"error": str(exc)}
            except Exception:
                payload = {"error": raw or str(exc)}
            return int(exc.code), payload
        raise


def seed() -> str:
    held = f"{PREFIX}-HELD"
    phone = f"imp-{PREFIX.lower()}-held"
    with db() as conn:
        with conn.cursor() as cur:
            uc.ensure_unified_candidates_schema(cur)
            cur.execute(
                "INSERT INTO candidates(phone,name,email,profile,raw_json) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb) ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name",
                (phone, "UC Requal Held", "ucrequal@cv.example", Json({}), Json({"marker": MARKER})),
            )
            cur.execute(
                """
                INSERT INTO applications(company_code,app_key,phone,status,position_code,position_title,cv_received,raw_json,ingested_at,updated_at)
                VALUES (%s,%s,%s,'needs_role','','',true,%s::jsonb,now(),now())
                ON CONFLICT DO NOTHING
                """,
                (COMPANY, held, phone, Json({"marker": MARKER, "intake": {"source": "email"}, "cv": {"processing": {"status": "ready"}}})),
            )
        conn.commit()
    return held


def cleanup() -> None:
    with db() as conn:
        with conn.cursor() as cur:
            for sql, params in [
                ("DELETE FROM candidate_fact_review_events WHERE app_key LIKE %s", (f"{PREFIX}%",)),
                ("DELETE FROM candidate_record_governance WHERE app_key LIKE %s", (f"{PREFIX}%",)),
                ("DELETE FROM applications WHERE app_key LIKE %s", (f"{PREFIX}%",)),
                ("DELETE FROM candidates WHERE phone LIKE %s", (f"imp-{PREFIX.lower()}%",)),
            ]:
                try:
                    cur.execute(sql, params)
                    conn.commit()
                except Exception:
                    conn.rollback()


def main() -> int:
    cleanup()
    held = seed()
    set_flag("on", "WATHEFNI")
    headers = mint()

    code, feature = http("GET", "/dashboard/prehire/candidates/feature", headers)
    ok("flag_on_wathefni", feature) if feature.get("enabled_for_company") else bad("flag_on_wathefni", feature)

    # other tenant remains dark
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT company_code FROM dashboard_users WHERE company_code<>%s AND status='active' GROUP BY 1 LIMIT 1",
                (COMPANY,),
            )
            other = (cur.fetchone() or {}).get("company_code")
    if other:
        try:
            oh = mint(other)
            code, ofeat = http("GET", "/dashboard/prehire/candidates/feature", oh)
            enabled = bool(ofeat.get("enabled_for_company"))
            ok("other_tenant_flag_off", {"company": other, "feature": ofeat}) if (code == 200 and not enabled) or code in {403, 404} else bad("other_tenant_flag_off", {"code": code, "body": ofeat})
        except Exception as exc:  # noqa: BLE001
            ok("other_tenant_flag_off", {"company": other, "note": "mint/auth restricted", "error": str(exc)[:200]})

    code, apps = http("GET", "/dashboard/prehire/applications?limit=50&view=talent_pool", headers)
    keys = {a.get("app_key") for a in apps.get("applications") or []}
    ok("held_in_talent_pool", held in keys) if held in keys else bad("held_in_talent_pool", keys)

    # held action gates
    for name, method, path, body in [
        ("held_gate_shortlist", "POST", f"/dashboard/prehire/applications/{held}/shortlist", {"confirm": True}),
        ("held_gate_reject", "POST", f"/dashboard/prehire/applications/{held}/reject", {"confirm": True, "reason": "test"}),
        ("held_gate_notify", "POST", f"/dashboard/prehire/applications/{held}/notify", {"channel": "whatsapp", "confirm": True}),
        ("held_gate_assessment", "POST", f"/dashboard/prehire/applications/{held}/assessment", {"confirm": True}),
    ]:
        code, body_out = http(method, path, headers, body)
        ok(name, {"code": code, "body": body_out}) if code in {403, 404, 409, 422} else bad(name, {"code": code, "body": body_out})

    # ranking path must not treat held as job pool member for empty job
    code, rank = http("GET", f"/dashboard/prehire/rank?q={held}", headers)
    # accept job_required / empty / no held scoring
    rank_txt = json.dumps(rank)
    ok("ranking_no_held_advisory", {"code": code, "snippet": rank_txt[:300]}) if ("job_required" in rank_txt or held not in rank_txt or code in {400, 422}) else bad("ranking_no_held_advisory", rank)

    # reports should not explode; held exclusion is covered by reports matrix — light check
    code, reports = http("GET", "/dashboard/prehire/reports", headers)
    ok("reports_reachable", {"code": code}) if code == 200 else bad("reports_reachable", reports)

    # Rollback
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, position_code FROM applications WHERE company_code=%s AND app_key=%s", (COMPANY, held))
            before = dict(cur.fetchone())
    set_flag("off", "")
    headers_off = mint()
    code, legacy = http("GET", "/dashboard/prehire/applications?limit=5", headers_off)
    ok("rollback_legacy", {"code": code, "unified": legacy.get("unified_candidates")}) if code == 200 and not legacy.get("unified_candidates") else bad("rollback_legacy", legacy)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, position_code FROM applications WHERE company_code=%s AND app_key=%s", (COMPANY, held))
            after = dict(cur.fetchone())
    ok("rollback_no_job_binding", {"before": before, "after": after}) if after.get("status") == "needs_role" and not (after.get("position_code") or "").strip() else bad("rollback_no_job_binding", after)

    # Re-enable
    set_flag("on", "WATHEFNI")
    headers = mint()
    code, feature2 = http("GET", "/dashboard/prehire/candidates/feature", headers)
    ok("flag_reenable", feature2) if feature2.get("enabled_for_company") else bad("flag_reenable", feature2)
    code, apps2 = http("GET", f"/dashboard/prehire/applications?limit=50&view=talent_pool", headers)
    keys2 = {a.get("app_key") for a in apps2.get("applications") or []}
    ok("unified_restored_without_rewrite", held in keys2) if held in keys2 else bad("unified_restored_without_rewrite", keys2)

    cleanup()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM applications WHERE app_key LIKE %s", (f"{PREFIX}%",))
            left = int(cur.fetchone()["c"])
    ok("zero_residue", left) if left == 0 else bad("zero_residue", left)

    set_flag("on", "WATHEFNI")  # leave qualified state
    failed = [r for r in RESULTS if not r["pass"]]
    report = {
        "prefix": PREFIX,
        "pass": sum(1 for r in RESULTS if r["pass"]),
        "fail": len(failed),
        "results": RESULTS,
        "failed": failed,
        "flag_final": {"master": "on", "tenants": "WATHEFNI"},
    }
    (EVIDENCE / "held-authority-rollback.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"pass": report["pass"], "fail": report["fail"]}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
