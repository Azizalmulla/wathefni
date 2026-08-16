#!/usr/bin/env python3
"""Production-dark qualification for Unified Candidates (flag OFF, no synthetic tenants)."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.request

sys.path.insert(0, "/opt/wathefni/orchestrator")
import production_data_safety as _r3_data_safety
_r3_data_safety.require_explicit_environment()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")

import app  # noqa: E402
import psycopg2
from psycopg2.extras import RealDictCursor

EVIDENCE = pathlib.Path(os.environ.get("DARK_EVIDENCE", "/tmp/uc-dark"))
EVIDENCE.mkdir(parents=True, exist_ok=True)
RESULTS: list[dict] = []


def ok(name: str, detail=None) -> None:
    RESULTS.append({"name": name, "pass": True, "detail": detail})
    print("PASS", name)


def bad(name: str, detail=None) -> None:
    RESULTS.append({"name": name, "pass": False, "detail": detail})
    print("FAIL", name, detail)


def db():
    vals = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return psycopg2.connect(vals["WATHEFNI_DATABASE_URL"], cursor_factory=RealDictCursor)


def mint(company: str = "WATHEFNI") -> dict[str, str]:
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


def http(method: str, path: str, headers: dict, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:8010{path}",
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


def main() -> int:
    # health
    code, _ = http("GET", "/health", {})
    ok("prod_health", code) if code == 200 else bad("prod_health", code)

    # flag drop-in
    conf = pathlib.Path("/etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf").read_text()
    ok("flag_dropin_off", conf) if "TALENT_POOL=off" in conf and "TENANTS=\n" in conf.replace("TENANTS=\r\n", "TENANTS=\n") else bad("flag_dropin_off", conf)

    headers = mint("WATHEFNI")
    code, feature = http("GET", "/dashboard/prehire/candidates/feature", headers)
    # With master OFF, feature endpoint should report disabled for company
    enabled = bool(feature.get("enabled_for_company")) if isinstance(feature, dict) else True
    ok("feature_disabled_for_wathefni", {"code": code, "feature": feature}) if (code in {200, 404} and not enabled) or code in {403, 404, 501} else bad("feature_disabled_for_wathefni", {"code": code, "feature": feature})

    # legacy list unchanged shape
    code, apps = http("GET", "/dashboard/prehire/applications?limit=5", headers)
    unified = bool(apps.get("unified_candidates")) if isinstance(apps, dict) else True
    ok("legacy_list_not_unified", {"code": code, "unified": unified, "total": apps.get("total")}) if code == 200 and not unified else bad("legacy_list_not_unified", apps)

    # talent pool view must not activate dark read model
    code, tp = http("GET", "/dashboard/prehire/applications?limit=5&view=talent_pool", headers)
    # either ignored (legacy) or fail-closed / not unified
    tp_unified = bool(tp.get("unified_candidates")) if isinstance(tp, dict) else True
    ok("talent_pool_view_dark", {"code": code, "unified": tp_unified}) if (code == 200 and not tp_unified) or code in {403, 404, 422} else bad("talent_pool_view_dark", tp)

    # dark routes fail closed
    for name, path in [
        ("saved_views", "/dashboard/prehire/candidates/saved-views"),
        ("intake_ops", "/dashboard/prehire/intake-operations"),
        ("intake_attention", "/dashboard/prehire/intake-operations/attention"),
    ]:
        code, body = http("GET", path, headers)
        ok(f"dark_route_{name}", {"code": code, "body": body}) if code in {403, 404, 409, 501} or (code == 200 and body.get("enabled") is False) else bad(f"dark_route_{name}", {"code": code, "body": body})

    # no held talent-pool presentation in legacy list
    heldish = [
        a for a in (apps.get("applications") or [])
        if str(a.get("status") or "").lower() in {"needs_role", "import_review"}
        or str((a.get("job_display") or "")).lower() == "not linked"
        or str((a.get("status_label") or "")).lower() == "talent pool"
    ]
    ok("no_talent_pool_labels_in_legacy_sample", {"heldish": len(heldish)}) if not any(
        str((a.get("status_label") or "")).lower() == "talent pool" for a in (apps.get("applications") or [])
    ) else bad("no_talent_pool_labels_in_legacy_sample", heldish)

    # sidecar tables empty / no deploy-created rows
    with db() as conn:
        with conn.cursor() as cur:
            for t in ("candidate_record_governance", "candidate_fact_review_events", "candidate_saved_views"):
                cur.execute(f"SELECT count(*) AS c FROM {t}")
                c = int(cur.fetchone()["c"])
                ok(f"sidecar_empty_{t}", c) if c == 0 else bad(f"sidecar_empty_{t}", c)
            # no tenant enablement table rows if such exists
            cur.execute(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_name='company_feature_flags'
                """
            )
            if cur.fetchone():
                cur.execute(
                    "SELECT count(*) AS c FROM company_feature_flags WHERE feature_key ILIKE %s",
                    ("%unified%candidates%",),
                )
                c = int(cur.fetchone()["c"])
                ok("no_company_feature_flag_rows", c) if c == 0 else bad("no_company_feature_flag_rows", c)
            else:
                ok("no_company_feature_flag_table", True)

    # staging isolation
    st = pathlib.Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d/unified-candidates.conf").read_text()
    ok("staging_still_wathefni_only", st) if "TENANTS=WATHEFNI" in st and "TALENT_POOL=on" in st else bad("staging_still_wathefni_only", st)

    # multiple prod companies sampled: feature off
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT company_code FROM dashboard_users
                WHERE status='active' AND role='owner'
                GROUP BY company_code ORDER BY company_code LIMIT 5
                """
            )
            companies = [r["company_code"] for r in cur.fetchall()]
    disabled = []
    for company in companies:
        try:
            h = mint(company)
            code, feat = http("GET", "/dashboard/prehire/candidates/feature", h)
            disabled.append({"company": company, "code": code, "enabled": feat.get("enabled_for_company"), "master": feat.get("master_enabled")})
        except Exception as exc:  # noqa: BLE001
            disabled.append({"company": company, "error": str(exc)[:200]})
    all_dark = all(not (d.get("enabled") is True) for d in disabled)
    ok("all_sampled_tenants_dark", disabled) if all_dark else bad("all_sampled_tenants_dark", disabled)

    failed = [r for r in RESULTS if not r["pass"]]
    report = {
        "pass": sum(1 for r in RESULTS if r["pass"]),
        "fail": len(failed),
        "results": RESULTS,
        "failed": failed,
        "flag": {"master": "off", "tenants": ""},
    }
    (EVIDENCE / "dark-qualification.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"pass": report["pass"], "fail": report["fail"]}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
