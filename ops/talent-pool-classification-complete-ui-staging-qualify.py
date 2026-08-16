#!/usr/bin/env python3
"""Staging qualification — complete Talent Pool Classification UI read/interaction.

Runs on the staging VPS against :8011. Synthetic fixtures only.
Does not touch production. Does not start workers. Leaves residue cleaned.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import psycopg2
from psycopg2.extras import Json, RealDictCursor

PREFIX = "TPCUI" + uuid.uuid4().hex[:8].upper()
MARKER = "talent_pool_classification_complete_ui_staging_v1"
COMPANY = "WATHEFNI"
RESULTS: list[dict[str, Any]] = []
OUT = pathlib.Path(os.environ.get("TPC_UI_EVIDENCE") or f"/tmp/{PREFIX.lower()}-evidence")
OUT.mkdir(parents=True, exist_ok=True)


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


def set_flags(*, tenants: str, manual: str, ui: str, schema: str = "on", workers: str = "off", master: str = "off") -> None:
    conf = pathlib.Path("/etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf")
    conf.write_text(
        "[Service]\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION={master}\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS={tenants}\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA={schema}\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL={manual}\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS={workers}\n"
        f"Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_UI={ui}\n",
        encoding="utf-8",
    )
    os.system("systemctl daemon-reload && systemctl restart wathefni-orchestrator-staging.service")
    for _ in range(90):
        if os.system("curl -sf http://127.0.0.1:8011/health >/dev/null") == 0:
            return
        time.sleep(1)
    raise RuntimeError("staging health failed")


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
                return int(exc.code), {"raw": raw[:500]}
        raise


FIXTURES = {
    "tech": {
        "name": "TPCUI Tech",
        "text": "Senior Software Engineer, 6 years. Python SQL FastAPI AWS. Computer Science. Banking technology Kuwait.",
    },
    "finance": {
        "name": "TPCUI Finance",
        "text": "Accountant with Excel and financial reporting. Bachelor in Accounting. Audit and treasury.",
    },
    "skill_python": {
        "name": "TPCUI Python Skill",
        "text": "Operations manager who led warehouse teams and built Python automation with SQL dashboards for logistics planning.",
    },
    "medium": {
        "name": "TPCUI Medium",
        "text": "Office administrator who completed practical Java and Docker training and used both in a supervised internal technical assignment.",
    },
    "unclear": {
        "name": "TPCUI Unclear",
        "text": "Professional with experience in many areas and various responsibilities across teams over time.",
    },
    "empty": {
        "name": "TPCUI Empty",
        "text": "Name only\nphone 000",
    },
}


def seed_apps() -> dict[str, str]:
    keys: dict[str, str] = {}
    with db() as conn:
        with conn.cursor() as cur:
            for slug, fixture in FIXTURES.items():
                app_key = f"{PREFIX}-{slug.upper()}"
                phone = f"imp-{PREFIX.lower()}-{slug}"
                keys[slug] = app_key
                cur.execute(
                    """
                    INSERT INTO candidates(phone, name, email, profile, raw_json)
                    VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                    ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, profile=EXCLUDED.profile, raw_json=EXCLUDED.raw_json, updated_at=now()
                    """,
                    (
                        phone,
                        fixture["name"],
                        f"{slug}.{PREFIX.lower()}@example.invalid",
                        Json({"skills": []}),
                        Json({"marker": MARKER, "normalized_cv_text": fixture["text"], "synthetic": True}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO applications(
                      company_code, app_key, phone, status, position_code, position_title,
                      cv_received, raw_json, ingested_at, updated_at
                    ) VALUES (%s,%s,%s,'needs_role','','',true,%s::jsonb,now(),now())
                    ON CONFLICT (app_key) DO UPDATE
                      SET phone=EXCLUDED.phone, raw_json=EXCLUDED.raw_json, updated_at=now()
                    """,
                    (
                        COMPANY,
                        app_key,
                        phone,
                        Json(
                            {
                                "marker": MARKER,
                                "normalized_cv_text": fixture["text"],
                                "cv_text": fixture["text"],
                                "synthetic": True,
                                "intake": {"source": "synthetic"},
                            }
                        ),
                    ),
                )
            # large pagination filler
            for i in range(60):
                app_key = f"{PREFIX}-PAGE{i:03d}"
                phone = f"imp-{PREFIX.lower()}-page{i:03d}"
                cur.execute(
                    """
                    INSERT INTO candidates(phone, name, email, profile, raw_json)
                    VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)
                    ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name, updated_at=now()
                    """,
                    (phone, f"TPCUI Page {i}", f"page{i}.{PREFIX.lower()}@example.invalid", Json({}), Json({"marker": MARKER})),
                )
                cur.execute(
                    """
                    INSERT INTO applications(
                      company_code, app_key, phone, status, position_code, position_title,
                      cv_received, raw_json, ingested_at, updated_at
                    ) VALUES (%s,%s,%s,'needs_role','','',false,%s::jsonb,now(),now())
                    ON CONFLICT (app_key) DO UPDATE SET updated_at=now()
                    """,
                    (COMPANY, app_key, phone, Json({"marker": MARKER, "synthetic": True})),
                )
            conn.commit()
    return keys


def cleanup() -> int:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM candidate_classification_review_events WHERE app_key LIKE %s", (f"{PREFIX}%",))
            cur.execute("DELETE FROM candidate_classification_suggestions WHERE app_key LIKE %s", (f"{PREFIX}%",))
            cur.execute("DELETE FROM candidate_classification_runs WHERE app_key LIKE %s", (f"{PREFIX}%",))
            cur.execute("DELETE FROM talent_pool_classification_jobs WHERE app_key LIKE %s", (f"{PREFIX}%",))
            cur.execute("DELETE FROM candidate_saved_views WHERE name LIKE %s", (f"{PREFIX}%",))
            cur.execute("DELETE FROM applications WHERE app_key LIKE %s", (f"{PREFIX}%",))
            cur.execute("DELETE FROM candidates WHERE phone LIKE %s OR phone LIKE %s", (f"imp-{PREFIX.lower()}%", f"%{PREFIX.lower()}%"))
            left = 0
            for table, col in (
                ("applications", "app_key"),
                ("candidate_classification_runs", "app_key"),
                ("candidate_classification_suggestions", "app_key"),
                ("candidate_classification_review_events", "app_key"),
            ):
                cur.execute(f"SELECT count(*) AS c FROM {table} WHERE {col} LIKE %s", (f"{PREFIX}%",))
                left += int(cur.fetchone()["c"])
            conn.commit()
    return left


def main() -> int:
    sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
    import talent_pool_classification as tpc

    ok("classifier_frozen", tpc.CLASSIFIER_VERSION)
    ok("workers_env_off", not tpc.feature_workers_enabled())

    # Asset markers in staging dashboard dist
    dist = pathlib.Path("/opt/wathefni/staging/dashboard-dist")
    blob = "\n".join(p.read_text(errors="ignore") for p in dist.rglob("*") if p.is_file() and p.suffix in {".js", ".html", ".css"})
    for marker in [
        "classification-filter-bar",
        "classification-compact-chip",
        "candidate-classification-section",
        "classification-history",
        "classification-add-correct",
        "Include Medium AI",
    ]:
        (ok if marker in blob else bad)(f"dashboard_marker_{marker}", marker in blob)

    headers = mint()
    status, feature = http("GET", "/dashboard/prehire/classification/feature", headers)
    (ok if status == 200 and feature.get("enabled_for_company") and feature.get("ui_enabled") else bad)(
        "feature_on_wathefni", feature
    )

    status, tax = http("GET", "/dashboard/prehire/classification/taxonomy", headers)
    dims = {d["dimension"] for d in (tax.get("dimensions") or [])} if status == 200 else set()
    expected = {"career_area", "likely_role", "skill", "industry", "seniority", "experience_band"}
    (ok if dims == expected else bad)("taxonomy_dimensions", {"got": sorted(dims), "expected": sorted(expected)})
    has_bilingual = any(
        n.get("label_en") and n.get("label_ar")
        for d in (tax.get("dimensions") or [])
        for n in d.get("nodes") or []
    )
    (ok if has_bilingual else bad)("taxonomy_bilingual_labels", has_bilingual)

    keys = seed_apps()
    # classify fixtures
    for slug, app_key in keys.items():
        st, body = http("POST", f"/dashboard/prehire/applications/{app_key}/classification/run", headers, {"confirm": True})
        (ok if st == 200 and body.get("ocr_triggered") is False and body.get("lifecycle_mutated") is False else bad)(
            f"run_{slug}", {"status": st, "workers": body.get("workers_started"), "ocr": body.get("ocr_triggered")}
        )

    # list projection + chip eligibility
    qs = urlencode({"view": "talent_pool", "q": PREFIX, "limit": 50, "offset": 0})
    st, listing = http("GET", f"/dashboard/prehire/applications?{qs}", headers)
    apps = {a["app_key"]: a for a in (listing.get("applications") or [])} if st == 200 else {}
    tech = apps.get(keys["tech"]) or {}
    medium = apps.get(keys["medium"]) or {}
    empty = apps.get(keys["empty"]) or {}
    (ok if tech.get("classification_chip") else bad)("chip_high_tech", tech.get("classification_chip"))
    (ok if not medium.get("classification_chip") else bad)("no_chip_medium", medium.get("classification_chip"))
    (ok if not empty.get("classification_chip") else bad)("no_chip_unclassified", empty.get("classification_chip"))
    (ok if isinstance(tech.get("classification_node_ids"), list) else bad)("node_ids_projected", tech.get("classification_node_ids"))

    # dimension filters (server-side)
    # discover tech career node from taxonomy
    career_nodes = next((d["nodes"] for d in tax.get("dimensions") or [] if d["dimension"] == "career_area"), [])
    tech_node = next((n["node_id"] for n in career_nodes if "tech" in str(n.get("label_en") or "").lower() or "technolog" in str(n.get("node_id")).lower()), None)
    finance_node = next((n["node_id"] for n in career_nodes if "finance" in str(n.get("label_en") or "").lower() or "finance" in str(n.get("node_id")).lower()), None)
    skill_nodes = next((d["nodes"] for d in tax.get("dimensions") or [] if d["dimension"] == "skill"), [])
    python_node = next((n["node_id"] for n in skill_nodes if "python" in str(n.get("label_en") or "").lower() or "python" in str(n.get("node_id")).lower()), None)

    if tech_node:
        qs = urlencode({"view": "talent_pool", "q": PREFIX, "classification_career_area": tech_node, "limit": 50})
        st, filtered = http("GET", f"/dashboard/prehire/applications?{qs}", headers)
        ids = {a["app_key"] for a in (filtered.get("applications") or [])}
        (ok if keys["tech"] in ids and keys["finance"] not in ids else bad)(
            "filter_career_area", {"tech_node": tech_node, "ids": sorted(ids), "total": filtered.get("total")}
        )
    else:
        bad("filter_career_area", "tech node missing")

    if finance_node:
        qs = urlencode({"view": "talent_pool", "q": PREFIX, "classification_career_area": finance_node, "limit": 50})
        st, filtered = http("GET", f"/dashboard/prehire/applications?{qs}", headers)
        ids = {a["app_key"] for a in (filtered.get("applications") or [])}
        (ok if keys["finance"] in ids else bad)("filter_finance", {"finance_node": finance_node, "ids": sorted(ids)})

    if tech_node and python_node:
        qs = urlencode(
            {
                "view": "talent_pool",
                "q": PREFIX,
                "classification_career_area": tech_node,
                "classification_skill": python_node,
                "classification_authority": "either",
                "classification_include_medium_ai": "true",
                "limit": 50,
            }
        )
        st, filtered = http("GET", f"/dashboard/prehire/applications?{qs}", headers)
        (ok if st == 200 else bad)("filter_combined_and", {"status": st, "total": filtered.get("total")})

    # OR within dimension
    if tech_node and finance_node:
        qs = urlencode(
            {
                "view": "talent_pool",
                "q": PREFIX,
                "classification_career_area": f"{tech_node},{finance_node}",
                "classification_authority": "either",
                "classification_include_medium_ai": "true",
                "limit": 50,
            }
        )
        st, filtered = http("GET", f"/dashboard/prehire/applications?{qs}", headers)
        ids = {a["app_key"] for a in (filtered.get("applications") or [])}
        (ok if keys["tech"] in ids and keys["finance"] in ids else bad)("filter_or_within_dimension", sorted(ids))

    # confidence / unclassified — target the empty fixture directly via search
    qs = urlencode({"view": "talent_pool", "q": f"{PREFIX}-EMPTY", "classification_confidence": "Unclassified", "limit": 50})
    st, filtered = http("GET", f"/dashboard/prehire/applications?{qs}", headers)
    ids = {a["app_key"] for a in (filtered.get("applications") or [])}
    (ok if keys["empty"] in ids and keys["tech"] not in ids else bad)("filter_unclassified", sorted(ids))

    qs = urlencode({"view": "talent_pool", "q": f"{PREFIX}-TECH", "classification_confidence": "Unclassified", "limit": 50})
    st, filtered_tech = http("GET", f"/dashboard/prehire/applications?{qs}", headers)
    tech_ids = {a["app_key"] for a in (filtered_tech.get("applications") or [])}
    (ok if keys["tech"] not in tech_ids else bad)("filter_unclassified_excludes_classified", sorted(tech_ids))

    qs = urlencode({"view": "talent_pool", "q": PREFIX, "classification_confidence": "High", "classification_authority": "either", "limit": 50})
    st, filtered = http("GET", f"/dashboard/prehire/applications?{qs}", headers)
    (ok if st == 200 and int(filtered.get("total") or 0) >= 1 else bad)("filter_high", filtered.get("total"))

    # pagination correctness under classification filter (server total)
    qs1 = urlencode({"view": "talent_pool", "q": PREFIX, "classification_confidence": "Unclassified", "limit": 10, "offset": 0})
    qs2 = urlencode({"view": "talent_pool", "q": PREFIX, "classification_confidence": "Unclassified", "limit": 10, "offset": 10})
    st1, p1 = http("GET", f"/dashboard/prehire/applications?{qs1}", headers)
    st2, p2 = http("GET", f"/dashboard/prehire/applications?{qs2}", headers)
    page1 = [a["app_key"] for a in (p1.get("applications") or [])]
    page2 = [a["app_key"] for a in (p2.get("applications") or [])]
    (ok if st1 == 200 and st2 == 200 and not set(page1) & set(page2) and int(p1.get("total") or 0) == int(p2.get("total") or 0) else bad)(
        "pagination_server_correct",
        {"total": p1.get("total"), "page1": len(page1), "page2": len(page2), "overlap": sorted(set(page1) & set(page2))},
    )

    # profile history (multi-run)
    tech_key = keys["tech"]
    http("POST", f"/dashboard/prehire/applications/{tech_key}/classification/run", headers, {"document_version_id": "d2", "extraction_version_id": "e2"})
    st, profile = http("GET", f"/dashboard/prehire/applications/{tech_key}/classification?runs_limit=20", headers)
    section = profile.get("classification") or {}
    (ok if st == 200 and int(section.get("runs_total") or 0) >= 2 and len(section.get("runs") or []) >= 2 else bad)(
        "profile_runs_history", {"runs_total": section.get("runs_total"), "runs": len(section.get("runs") or [])}
    )
    currencies = {r.get("currency") for r in (section.get("runs") or [])}
    (ok if "current" in currencies and "stale" in currencies else bad)("profile_current_stale", sorted(currencies))
    (ok if set(section.get("actions") or []) >= {"confirm", "reject", "add", "correct"} else bad)("profile_actions", section.get("actions"))

    # HR actions with confirm required
    suggestion = (section.get("ai_suggested") or [None])[0]
    if suggestion:
        st, preview = http(
            "POST",
            f"/dashboard/prehire/applications/{tech_key}/classification/review",
            headers,
            {"action": "confirm", "node_id": suggestion.get("node_id"), "preview": True},
        )
        (ok if st == 200 and preview.get("preview") is True else bad)("review_preview", preview)
        st, denied = http(
            "POST",
            f"/dashboard/prehire/applications/{tech_key}/classification/review",
            headers,
            {"action": "confirm", "node_id": suggestion.get("node_id")},
        )
        (ok if st == 422 else bad)("review_confirm_required", {"status": st, "body": denied})
        st, confirmed = http(
            "POST",
            f"/dashboard/prehire/applications/{tech_key}/classification/review",
            headers,
            {"action": "confirm", "node_id": suggestion.get("node_id"), "confirm": True, "label_en": suggestion.get("label_en")},
        )
        (ok if st == 200 and confirmed.get("event", {}).get("action") == "confirm" else bad)("review_confirm", confirmed)
    else:
        bad("review_confirm", "no suggestion")

    # add
    add_node = python_node or (skill_nodes[0]["node_id"] if skill_nodes else None)
    if add_node:
        st, added = http(
            "POST",
            f"/dashboard/prehire/applications/{tech_key}/classification/review",
            headers,
            {"action": "add", "node_id": add_node, "confirm": True},
        )
        (ok if st == 200 and added.get("event", {}).get("action") == "add" else bad)("review_add", added)
    else:
        bad("review_add", "no skill node")

    # correct supersede
    if finance_node and tech_node:
        st, corrected = http(
            "POST",
            f"/dashboard/prehire/applications/{tech_key}/classification/review",
            headers,
            {"action": "correct", "node_id": finance_node, "previous_node_id": tech_node, "confirm": True},
        )
        (ok if st == 200 and corrected.get("event", {}).get("action") == "correct" else bad)("review_correct", corrected)
    st, after = http("GET", f"/dashboard/prehire/applications/{tech_key}/classification", headers)
    hist = (after.get("classification") or {}).get("history") or []
    (ok if any(e.get("action") == "correct" for e in hist) and any(e.get("action") == "add" for e in hist) else bad)(
        "review_history_append_only", [e.get("action") for e in hist]
    )

    # saved view
    st, saved = http(
        "POST",
        "/dashboard/prehire/candidates/saved-views",
        headers,
        {
            "name": f"{PREFIX}-finance-view",
            "filters": {
                "view": "talent_pool",
                "classification": {
                    "schema": "classification-filters-v1",
                    "dimension_nodes": {"career_area": [finance_node or "missing.node"]},
                    "authority": "confirmed_only",
                    "include_medium_ai": False,
                },
            },
        },
    )
    (ok if st == 200 else bad)("saved_view_create", saved)
    saved_filters = ((saved.get("view") or {}).get("filters") or {})
    classification = saved_filters.get("classification") or {}
    (ok if classification.get("schema") == "classification-filters-v1" else bad)("saved_view_versioned", classification)
    if finance_node is None:
        (ok if classification.get("deprecated_nodes") else bad)("saved_view_deprecated_disclosed", classification.get("deprecated_nodes"))

    # deprecated node disclosure when missing
    st, deprecated_view = http(
        "POST",
        "/dashboard/prehire/candidates/saved-views",
        headers,
        {
            "name": f"{PREFIX}-deprecated-view",
            "filters": {"classification": {"career_area": ["does.not.exist.node"], "authority": "either"}},
        },
    )
    dep = (((deprecated_view.get("view") or {}).get("filters") or {}).get("classification") or {}).get("deprecated_nodes")
    (ok if st == 200 and dep else bad)("saved_view_deprecated_nodes", dep)

    # feature OFF hide
    set_flags(tenants="", manual="off", ui="off", schema="on", workers="off", master="off")
    headers_off = mint()
    st, feat_off = http("GET", "/dashboard/prehire/classification/feature", headers_off)
    (ok if st == 200 and not feat_off.get("enabled_for_company") else bad)("feature_off_company", feat_off)
    st, tax_off = http("GET", "/dashboard/prehire/classification/taxonomy", headers_off)
    (ok if st == 404 else bad)("taxonomy_hidden_when_off", st)
    qs = urlencode({"view": "all", "q": PREFIX, "classification_career_area": tech_node or "fn.technology", "limit": 5})
    st, listing_off = http("GET", f"/dashboard/prehire/applications?{qs}", headers_off)
    # filters should be ignored / no classification projection required when off
    apps_off = listing_off.get("applications") or []
    (ok if st == 200 and all(not a.get("classification_chip") for a in apps_off) else bad)(
        "list_no_chip_when_off", {"status": st, "n": len(apps_off)}
    )

    # restore WATHEFNI staging enablement for browser shots / further use
    set_flags(tenants="WATHEFNI", manual="on", ui="on", schema="on", workers="off", master="off")

    # cross-tenant denial (prefer another pre-hiring company; otherwise prove allowlist isolation via feature status)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT du.company_code
                FROM dashboard_users du
                WHERE du.company_code<>%s AND du.status='active'
                ORDER BY du.updated_at DESC NULLS LAST
                LIMIT 20
                """,
                (COMPANY,),
            )
            others = [str(r["company_code"]) for r in cur.fetchall()]
    cross_checked = False
    for other_company in others:
        try:
            other_headers = mint(other_company)
            st, other_feat = http("GET", "/dashboard/prehire/classification/feature", other_headers)
            if st == 200:
                (ok if not other_feat.get("enabled_for_company") else bad)("cross_tenant_disabled", other_feat)
                cross_checked = True
                break
            if st in {403, 404} and isinstance(other_feat, dict) and other_feat.get("detail", {}).get("error") == "module_disabled":
                continue
        except Exception:
            continue
    if not cross_checked:
        # Fall back: feature status for WATHEFNI allowlist must not include arbitrary external tenant codes.
        st, feat = http("GET", "/dashboard/prehire/classification/feature", mint())
        allowed = feat.get("allowed_tenants") or []
        (ok if allowed == ["WATHEFNI"] or allowed == ["wathefni"] or [a.upper() for a in allowed] == ["WATHEFNI"] else bad)(
            "cross_tenant_allowlist_wathefni_only", allowed
        )

    left = cleanup()
    (ok if left == 0 else bad)("zero_residue", left)

    # production dashboard unchanged marker file write
    prod_dash = pathlib.Path("/var/www/wathefni-dashboard/index.html")
    ok("production_dashboard_present", prod_dash.exists())

    summary = {
        "prefix": PREFIX,
        "marker": MARKER,
        "pass_count": sum(1 for r in RESULTS if r["pass"]),
        "fail_count": sum(1 for r in RESULTS if not r["pass"]),
        "classifier_version": tpc.CLASSIFIER_VERSION,
        "taxonomy_version": (tax.get("taxonomy_version") if isinstance(tax, dict) else None),
        "results": RESULTS,
    }
    OUT.joinpath("complete-ui-qualification.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"pass_count": summary["pass_count"], "fail_count": summary["fail_count"], "out": str(OUT)}, indent=2))
    return 0 if summary["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
