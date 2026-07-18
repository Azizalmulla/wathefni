"""Live behaviour test for the tiered CV intake model (V1).

Tiering rule:
  - Explicit role signal (position_code that maps to an open position, or an exact
    applied_role match)  -> AUTO-ADMIT into Candidates (review_pending), labelled +
    auditable + reversible, BUT never auto-messaged and never auto-decided.
  - Inferred/guessed role (folder hint, fuzzy/unmatched code, general inbox) -> held in
    the Intake queue for group-level bulk confirm.
  - No role signal -> needs_role (Intake, "unclear").

This test verifies:
  - explicit imports auto-admit (in Candidates + Ranking-eligible), inferred/none are held
  - auto-admitted candidates carry the import label (so the CV worker never messages them)
  - the per-company "auto-admit explicit imports" setting flips behaviour (OFF -> hold)
  - the Intake workspace groups held imports by suggested role / source / confidence
  - bulk confirm / assign / archive move or drop held candidates, company-scoped
  - archived imports leave the Intake queue and never enter Ranking

Run on a host with the orchestrator venv + database, e.g.:
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-tiered-intake.py
"""

from __future__ import annotations

import io
import zipfile

import app
from psycopg2.extras import Json

COMPANY = "TIEREDINTK"
MARKER = "temporary_tiered_intake_smoke"

_created_app_keys: list[str] = []
_created_surrogates: list[str] = []


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _context() -> dict:
    # A fully-formed owner context that satisfies require_entitlement so we can drive
    # the real dashboard endpoint functions directly (no HTTP layer needed).
    return {
        "company_code": COMPANY,
        "actor_user_id": "smoke-tiered-user",
        "permission_authority": "backend_current",
        "permission_subject_user_id": "smoke-tiered-user",
        "permission_subject_company": COMPANY,
        "actor_email": "smoke@tiered.test",
        "actor_role": "owner",
        "hr_user": {"role": "owner", "status": "active"},
        "permissions": app.hr_role_permissions("owner"),
    }


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                (COMPANY, "Tiered Intake Smoke", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
            )
            for code, title in (("WELDER", "Bulk Welder"), ("DRIVER", "Delivery Driver")):
                cur.execute(
                    "INSERT INTO positions (company_code, position_code, title, status, updated_at) "
                    "VALUES (%s,%s,%s,'open',now()) "
                    "ON CONFLICT (company_code, position_code) DO UPDATE SET status='open'",
                    (COMPANY, code, title),
                )
            cur.execute(
                "INSERT INTO company_modules (company_code, module_key, enabled, source, updated_at) "
                "VALUES (%s,'pre_hiring',true,'smoke',now()) "
                "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true",
                (COMPANY,),
            )
        conn.commit()
    # Auto-admit ON for the first phase (this is the product default).
    app.set_company_setting(COMPANY, "intake_auto_admit_explicit", True)


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            if _created_app_keys:
                cur.execute("DELETE FROM candidate_documents WHERE app_key = ANY(%s)", (_created_app_keys,))
                cur.execute("DELETE FROM file_registry WHERE subject_key = ANY(%s)", (_created_app_keys,))
                cur.execute("DELETE FROM applications WHERE app_key = ANY(%s)", (_created_app_keys,))
            if _created_surrogates:
                cur.execute("DELETE FROM candidates WHERE phone = ANY(%s)", (_created_surrogates,))
            cur.execute("DELETE FROM import_batches WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM positions WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM company_modules WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM company_settings WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
        conn.commit()


def _cv_bytes(name: str, summary: str) -> bytes:
    return (
        f"{name}\n{summary}\n\n"
        "Experience: 6 years relevant experience, certified, references available.\n"
        "Skills: teamwork, safety, quality.\n"
    ).encode("utf-8")


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for fname, data in entries.items():
            zf.writestr(fname, data)
    return buf.getvalue()


def _track(result: dict) -> None:
    for it in result.get("items", []):
        if it.get("app_key"):
            _created_app_keys.append(it["app_key"])
        if it.get("surrogate_phone"):
            _created_surrogates.append(it["surrogate_phone"])


def _passes_ranking(app_keys: list[str]) -> int:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) AS c FROM applications a "
                f"WHERE a.company_code=%s AND a.app_key = ANY(%s) AND {app.reviewable_application_predicate('a')}",
                (COMPANY, app_keys),
            )
            return int(cur.fetchone()["c"])


def _status(app_key: str) -> dict:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, position_code, raw_json->'import'->>'auto_admitted' AS auto_admitted, "
                "raw_json->'import'->>'held' AS held, raw_json->'import'->>'admit_reason' AS admit_reason, "
                "(raw_json->'import') IS NOT NULL AS has_import "
                "FROM applications WHERE app_key=%s",
                (app_key,),
            )
            return dict(cur.fetchone())


def run_checks() -> None:
    welder = _cv_bytes("Ali Welder", "Senior Welder")
    role_text = _cv_bytes("Sara Role", "Welding specialist")
    folder_cv = _cv_bytes("Omar Folder", "General technician")
    pilot = _cv_bytes("Hind Pilot", "Aviation background")
    norole = _cv_bytes("Noor None", "General applicant")

    uploaded = [
        ("Ali_Welder_CV.txt", welder),       # explicit position_code -> auto-admit
        ("Sara_Role_CV.txt", role_text),     # exact applied_role -> auto-admit
        ("No_Role_CV.txt", norole),          # no signal -> needs_role (unclear)
        ("Hind_Pilot_CV.txt", pilot),        # unmatched code PILOT -> suggested, held
        ("batch.zip", _zip_bytes({           # folder hint -> suggested, held
            "WELDER/Omar_Folder_CV.txt": folder_cv,
        })),
    ]
    metadata_rows = {
        "ali_welder_cv.txt": {"name": "Ali Welder", "email": "ali.w@example.com", "position_code": "WELDER"},
        "sara_role_cv.txt": {"name": "Sara Role", "email": "sara.r@example.com", "applied_role": "Bulk Welder"},
        "hind_pilot_cv.txt": {"name": "Hind Pilot", "email": "hind.p@example.com", "position_code": "PILOT"},
    }

    result = app.process_bulk_cv_import(
        company_code=COMPANY,
        created_by_user_id="smoke-tiered-user",
        created_by_email="smoke@tiered.test",
        uploaded_files=uploaded,
        metadata_rows=metadata_rows,
        default_position_code=None,
        default_position_title=None,
        source="bulk_upload",
    )
    _track(result)

    counts = result["counts"]
    assert_true(counts["imported"] == 5, f"expected 5 imported, got {counts['imported']}")
    assert_true(counts.get("auto_admitted") == 2, f"expected 2 auto-admitted (explicit code + exact role), got {counts.get('auto_admitted')}")
    assert_true(counts.get("needs_role") == 3, f"expected 3 held in Intake (folder hint, unmatched code, no role), got {counts.get('needs_role')}")

    by_file = {it["original_filename"]: it for it in result["items"]}
    welder_app = by_file["Ali_Welder_CV.txt"]["app_key"]
    role_app = by_file["Sara_Role_CV.txt"]["app_key"]
    folder_app = by_file["Omar_Folder_CV.txt"]["app_key"]
    pilot_app = by_file["Hind_Pilot_CV.txt"]["app_key"]
    norole_app = by_file["No_Role_CV.txt"]["app_key"]

    # Explicit position_code -> auto-admitted into Candidates.
    s = _status(welder_app)
    assert_true(s["status"] == "review_pending", f"explicit code import must auto-admit (review_pending), got {s['status']}")
    assert_true(s["position_code"] == "WELDER", "explicit code import must keep its role")
    assert_true(s["auto_admitted"] == "true" and s["held"] == "false", "explicit import must be labelled auto_admitted + not held")
    assert_true(s["admit_reason"] == "metadata_position_code", f"auto-admit reason must be audited, got {s['admit_reason']}")

    # Exact applied_role -> auto-admitted.
    s = _status(role_app)
    assert_true(s["status"] == "review_pending", "exact applied_role import must auto-admit")
    assert_true(s["position_code"] == "WELDER" and s["auto_admitted"] == "true", "exact applied_role must resolve + auto-admit")
    assert_true(s["admit_reason"] == "metadata_applied_role", "applied_role auto-admit reason must be audited")

    # Inferred / none -> held in Intake.
    for app_key, label in ((folder_app, "folder hint"), (pilot_app, "unmatched code"), (norole_app, "no role")):
        s = _status(app_key)
        assert_true(s["status"] == "needs_role", f"{label} import must stay held (needs_role), got {s['status']}")
        assert_true(s["has_import"], f"{label} import must carry the import label")

    # Safety: auto-admitted candidates are in Candidates + Ranking-eligible...
    assert_true(_passes_ranking([welder_app, role_app]) == 2, "auto-admitted explicit imports must be Ranking-eligible")
    listing = app.prehire_applications_query(company_code=COMPANY, status=None, position=None, search=None, limit=200, offset=0)
    listed = {a.get("app_key") for a in listing.get("applications", [])}
    assert_true(welder_app in listed and role_app in listed, "auto-admitted imports must appear in the Candidates list")
    # ...but held imports are NOT.
    assert_true(_passes_ranking([folder_app, pilot_app, norole_app]) == 0, "held imports must be excluded from Ranking")
    assert_true(folder_app not in listed and pilot_app not in listed, "held imports must not appear in the Candidates list")

    # Safety: auto-admitted candidates carry the import label so the CV worker never
    # messages them (the worker forces send_screening=False for any imported application).
    assert_true(_status(welder_app)["has_import"], "auto-admitted import must keep the import label (no auto-message)")

    # --- Intake workspace grouping ------------------------------------------------
    ctx = _context()
    intake = app.dashboard_prehire_import_intake(limit=500, context=ctx)
    assert_true(intake["total"] == 3, f"Intake must show only the 3 held imports, got {intake['total']}")
    assert_true(intake["auto_admitted_total"] == 2, f"Intake summary must report 2 auto-admitted, got {intake['auto_admitted_total']}")
    assert_true(intake["auto_admit_explicit_imports"] is True, "Intake must report the auto-admit setting state")
    group_keys = {g["key"] for g in intake["groups"]}
    assert_true("WELDER" in group_keys, "folder-hint suggestion must group under WELDER")
    assert_true("PILOT" in group_keys, "unmatched-code suggestion must group under PILOT")
    assert_true("__unclear__" in group_keys, "no-role import must group as unclear")
    welder_group = next(g for g in intake["groups"] if g["key"] == "WELDER")
    assert_true(welder_group["kind"] == "suggested", "folder-hint group must be a suggestion, never explicit")

    # --- Bulk confirm: trust the suggested role for the folder-hint group ---------
    res = app.dashboard_prehire_import_bulk(request={"action": "confirm", "app_keys": [folder_app]}, context=ctx)
    assert_true(res["promoted"] == 1, f"bulk confirm must promote the folder-hint candidate, got {res}")
    s = _status(folder_app)
    assert_true(s["status"] == "review_pending" and s["position_code"] == "WELDER", "confirmed candidate must enter the pipeline with the suggested role")
    assert_true(_passes_ranking([folder_app]) == 1, "confirmed candidate must become Ranking-eligible")

    # --- Bulk assign: give the unclear candidate an explicit role -----------------
    res = app.dashboard_prehire_import_bulk(request={"action": "assign", "app_keys": [norole_app], "position_code": "DRIVER", "position_title": "Delivery Driver"}, context=ctx)
    assert_true(res["promoted"] == 1, "bulk assign must promote the selected candidate")
    s = _status(norole_app)
    assert_true(s["status"] == "review_pending" and s["position_code"] == "DRIVER", "assigned candidate must enter the pipeline with the chosen role")

    # --- Bulk archive: drop the noisy PILOT import --------------------------------
    res = app.dashboard_prehire_import_bulk(request={"action": "archive", "app_keys": [pilot_app]}, context=ctx)
    assert_true(res["archived"] == 1, "bulk archive must archive the selected candidate")
    s = _status(pilot_app)
    assert_true(s["status"] == "import_archived", "archived candidate must be import_archived")
    assert_true(_passes_ranking([pilot_app]) == 0, "archived candidate must never enter Ranking")

    # Intake is now empty (all three resolved).
    intake2 = app.dashboard_prehire_import_intake(limit=500, context=ctx)
    assert_true(intake2["total"] == 0, f"Intake must be empty after bulk actions, got {intake2['total']}")

    # --- Setting OFF: explicit imports must now be HELD, not auto-admitted --------
    res = app.dashboard_prehire_import_settings_update(request={"auto_admit_explicit_imports": False}, context=ctx)
    assert_true(res["auto_admit_explicit_imports"] is False, "settings update must persist auto-admit OFF")
    assert_true(app.company_auto_admit_imports(COMPANY) is False, "company setting must read back OFF")

    cautious = _cv_bytes("Cautious Carl", "Senior Welder")
    result2 = app.process_bulk_cv_import(
        company_code=COMPANY,
        created_by_user_id="smoke-tiered-user",
        created_by_email="smoke@tiered.test",
        uploaded_files=[("Cautious_Carl_CV.txt", cautious)],
        metadata_rows={"cautious_carl_cv.txt": {"name": "Cautious Carl", "email": "carl@example.com", "position_code": "WELDER"}},
        default_position_code=None,
        default_position_title=None,
        source="bulk_upload",
    )
    _track(result2)
    assert_true(result2["counts"].get("auto_admitted", 0) == 0, "with auto-admit OFF, explicit imports must not auto-admit")
    carl_app = result2["items"][0]["app_key"]
    s = _status(carl_app)
    assert_true(s["status"] == "import_review", f"with auto-admit OFF, explicit import must be held for review, got {s['status']}")
    assert_true(s["position_code"] == "WELDER" and s["auto_admitted"] in (None, "false"), "held explicit import keeps role but is not auto-admitted")
    assert_true(_passes_ranking([carl_app]) == 0, "with auto-admit OFF, the explicit import must not be Ranking-eligible until confirmed")


def main() -> None:
    setup()
    try:
        run_checks()
    finally:
        teardown()
    print("tiered intake smoke tests passed")


if __name__ == "__main__":
    main()
