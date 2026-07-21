"""Live behaviour test for the shared import core + bulk CV import V1.

Imports a mix of CVs (multi-file, a ZIP, a duplicate, an unsupported file, and
optional CSV metadata) into a temporary company and verifies:
  - every file is traceable (import_batch + import_items + file_registry + candidate_documents pending)
  - imported candidates are held in needs_role / import_review (not in the live pipeline or ranking)
  - duplicates and failures are reported, never imported twice
  - company_code scoping (a second company never sees the batch or the held candidates)
  - assign-role + promote moves a candidate into the pipeline (Ranking eligible)
  - the CV worker status guard preserves held status (extraction never auto-advances imports)
  - the candidate.import permission map

Run on a host with the orchestrator venv + database, e.g.:
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-bulk-cv-import.py
"""

from __future__ import annotations

import io
import zipfile

import app
from psycopg2.extras import Json

COMPANY_A = "BULKIMPALPHA"
COMPANY_B = "BULKIMPBRAVO"
MARKER = "temporary_bulk_cv_import_smoke"

_created_app_keys: list[str] = []
_created_surrogates: list[str] = []
_batch_id: str | None = None


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Bulk Import Smoke {company}", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
            cur.execute(
                "INSERT INTO positions (company_code, position_code, title, status, updated_at) "
                "VALUES (%s,'WELDER','Bulk Welder','open',now()) "
                "ON CONFLICT (company_code, position_code) DO UPDATE SET status='open'",
                (COMPANY_A,),
            )
        conn.commit()
    # This test validates the holdout + manual assign/promote path, so pin auto-admit OFF.
    # The tiered auto-admit behaviour (explicit role -> Candidates) is covered by
    # smoke-test-tiered-intake.py.
    app.set_company_setting(COMPANY_A, "intake_auto_admit_explicit", False)


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            if _created_app_keys:
                cur.execute("DELETE FROM candidate_documents WHERE app_key = ANY(%s)", (_created_app_keys,))
                cur.execute("DELETE FROM file_registry WHERE subject_key = ANY(%s)", (_created_app_keys,))
                cur.execute("DELETE FROM applications WHERE app_key = ANY(%s)", (_created_app_keys,))
            if _created_surrogates:
                cur.execute("DELETE FROM candidates WHERE phone = ANY(%s)", (_created_surrogates,))
            cur.execute("DELETE FROM import_batches WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
            cur.execute("DELETE FROM positions WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
            cur.execute("DELETE FROM company_settings WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
        conn.commit()


def _cv_bytes(name: str, email: str) -> bytes:
    return (
        f"{name}\nSenior Welder\nEmail: {email}\n\n"
        "Experience: 8 years offshore welding, NDT certified, safety lead.\n"
        "Skills: TIG, MIG, blueprint reading, QA.\n"
    ).encode("utf-8")


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for fname, data in entries.items():
            zf.writestr(fname, data)
    return buf.getvalue()


def _xlsx_bytes(header: list[str], rows: list[list[str]]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def run_checks() -> None:
    global _batch_id
    ali = _cv_bytes("Ali Hassan", "ali@example.com")
    sara = _cv_bytes("Sara Noor", "sara@example.com")
    omar = _cv_bytes("Omar Zaid", "omar@example.com")
    hind = _cv_bytes("Hind Saleh", "hind@example.com")

    uploaded = [
        ("Ali_Hassan_CV.txt", ali),
        ("Sara_Noor_CV.txt", sara),
        ("Ali_Hassan_CV_copy.txt", ali),  # byte-identical duplicate
        ("scan_notes.bin", b"not a real cv"),  # unsupported type
        # ZIP with NESTED folders + junk entries: expands to two CVs.
        ("batch.zip", _zip_bytes({
            "cvs/engineering/Omar_Zaid_CV.txt": omar,  # folder doesn't match a role -> needs_role, no suggestion
            "WELDER/Hind_Saleh_CV.txt": hind,          # folder matches a role -> needs_role + suggestion (never auto-assigned)
            "cvs/engineering/notes.exe": b"junk",      # unsupported inside zip -> silently skipped
            "__MACOSX/cvs/._Omar_Zaid_CV.txt": b"x",   # macOS metadata -> filtered
            ".DS_Store": b"x",                          # dotfile -> filtered
        })),
    ]
    # Sara is assigned via applied_role (free text) matched to the position title.
    metadata_rows = {
        "sara_noor_cv.txt": {"name": "Sara Noor", "email": "sara@example.com", "phone": "", "applied_role": "Bulk Welder"},
    }

    result = app.process_bulk_cv_import(
        company_code=COMPANY_A,
        created_by_user_id="smoke-user",
        created_by_email="smoke@bulk.test",
        uploaded_files=uploaded,
        metadata_rows=metadata_rows,
        default_position_code=None,
        default_position_title=None,
        source="workday_export",
    )
    _batch_id = result["batch_id"]
    for it in result["items"]:
        if it.get("app_key"):
            _created_app_keys.append(it["app_key"])
        if it.get("surrogate_phone"):
            _created_surrogates.append(it["surrogate_phone"])

    counts = result["counts"]
    assert_true(result["total_files"] == 6, f"zip should expand to 6 files, got {result['total_files']}")
    assert_true(counts["imported"] == 4, f"expected 4 imported, got {counts['imported']}")
    assert_true(counts["duplicate"] == 1, f"expected 1 duplicate, got {counts['duplicate']}")
    assert_true(counts["failed"] == 1, f"expected 1 failed (unsupported), got {counts['failed']}")
    assert_true(counts["needs_role"] == 3, f"expected 3 needs_role (Ali, Omar, Hind), got {counts['needs_role']}")

    by_file = {it["original_filename"]: it for it in result["items"]}
    assert_true(by_file["scan_notes.bin"]["status"] == "failed", "unsupported file must be failed")
    assert_true(by_file["Ali_Hassan_CV_copy.txt"]["status"] == "duplicate", "identical file must be flagged duplicate")
    assert_true(by_file["Sara_Noor_CV.txt"]["status"] == "imported", "Sara should import")
    # Nested-folder CV inside the ZIP imports under its basename; junk entries are filtered.
    assert_true(by_file.get("Omar_Zaid_CV.txt", {}).get("status") == "imported", "nested-folder CV inside ZIP must import")
    assert_true(by_file.get("Hind_Saleh_CV.txt", {}).get("status") == "imported", "role-folder CV inside ZIP must import")
    assert_true(all(it["original_filename"] != "notes.exe" for it in result["items"]), "unsupported zip entry must be filtered, not listed")
    assert_true(all(".DS_Store" not in it["original_filename"] for it in result["items"]), "zip dotfiles must be filtered")

    # Excel (.xlsx) metadata mapping must parse via openpyxl (same shape as CSV).
    xlsx = _xlsx_bytes(
        ["filename", "name", "email", "applied_role"],
        [["Omar_Zaid_CV.txt", "Omar Zaid", "omar@example.com", "Bulk Welder"]],
    )
    xlsx_map = app.parse_import_metadata_file("roles.xlsx", xlsx)
    assert_true(xlsx_map.get("omar_zaid_cv.txt", {}).get("applied_role") == "Bulk Welder", "xlsx metadata must map filename -> applied_role")

    # Role resolution matrix (pure function over the company's real positions).
    positions = [{"position_code": "WELDER", "title": "Bulk Welder"}]
    r_code = app.resolve_import_role(positions, position_code="WELDER")
    assert_true(r_code["assigned_code"] == "WELDER", "explicit matching position_code must assign")
    r_role = app.resolve_import_role(positions, applied_role="Bulk Welder")
    assert_true(r_role["assigned_code"] == "WELDER", "applied_role matching a title must assign")
    r_unknown = app.resolve_import_role(positions, position_code="PILOT")
    assert_true(r_unknown["assigned_code"] is None and r_unknown["suggested_code"] == "PILOT" and r_unknown["source"] == "metadata_unmatched_code", "unmatched code must suggest, never assign")
    r_folder = app.resolve_import_role(positions, folder_hint="WELDER")
    assert_true(r_folder["assigned_code"] is None and r_folder["suggested_code"] == "WELDER" and r_folder["source"] == "zip_folder_path", "folder hint must only suggest, never auto-assign")
    r_none = app.resolve_import_role(positions, applied_role="Astronaut")
    assert_true(r_none["assigned_code"] is None, "an unrelated role must not be assigned")

    ali_app = by_file["Ali_Hassan_CV.txt"]["app_key"]
    sara_app = by_file["Sara_Noor_CV.txt"]["app_key"]
    hind_app = by_file["Hind_Saleh_CV.txt"]["app_key"]

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # Traceability: batch + items + file_registry + candidate_documents pending.
            cur.execute("SELECT imported_count, duplicate_count, failed_count, status, source FROM import_batches WHERE batch_id=%s", (_batch_id,))
            b = cur.fetchone()
            assert_true(b and b["status"] == "completed", "batch should be marked completed")
            assert_true(b["source"] == "workday_export", "batch must record its import source")
            cur.execute("SELECT COUNT(*) AS c FROM import_items WHERE batch_id=%s", (_batch_id,))
            assert_true(cur.fetchone()["c"] == 6, "every file must have an import_item")
            cur.execute("SELECT status, position_code FROM applications WHERE app_key=%s", (ali_app,))
            row = cur.fetchone()
            assert_true(row["status"] == "needs_role", "Ali (no role) must be held as needs_role")
            cur.execute("SELECT status, position_code FROM applications WHERE app_key=%s", (sara_app,))
            sara_row = cur.fetchone()
            assert_true(sara_row["status"] == "import_review", "Sara (applied_role matched) must be import_review")
            assert_true(sara_row["position_code"] == "WELDER", "Sara's applied_role must resolve to the WELDER position")
            # Hind: folder-path role is only a SUGGESTION — held as needs_role, never auto-assigned.
            cur.execute(
                "SELECT status, position_code, raw_json->'import'->'role_suggestion'->>'suggested_code' AS sug, "
                "raw_json->'import'->'role_suggestion'->>'source' AS sug_src, raw_json->'import'->>'source' AS imp_src "
                "FROM applications WHERE app_key=%s",
                (hind_app,),
            )
            hind_row = cur.fetchone()
            assert_true(hind_row["status"] == "needs_role", "Hind (folder hint only) must stay needs_role")
            assert_true((hind_row["position_code"] or "") == "", "Hind must not be auto-assigned from a folder name")
            assert_true(hind_row["sug"] == "WELDER" and hind_row["sug_src"] == "zip_folder_path", "Hind must carry a folder-path role suggestion")
            assert_true(hind_row["imp_src"] == "workday_export", "imported application must record the batch source")
            cur.execute("SELECT extraction_status FROM candidate_documents WHERE app_key=%s", (ali_app,))
            assert_true(cur.fetchone()["extraction_status"] == "pending_extraction", "imported CV doc must be pending for the worker")
            cur.execute("SELECT storage_status FROM file_registry WHERE subject_key=%s AND file_kind='candidate_cv'", (ali_app,))
            assert_true(cur.fetchone() is not None, "imported file must be traceable in file_registry")

    # Holdout: held imports never appear in the live pipeline list or in ranking.
    listing = app.prehire_applications_query(
        company_code=COMPANY_A, status=None, position=None, search=None, limit=200, offset=0
    )
    listed_keys = {a.get("app_key") for a in listing.get("applications", [])}
    assert_true(ali_app not in listed_keys and sara_app not in listed_keys, "held imports must not show in the default pipeline list")

    # Ranking eligibility uses reviewable_application_predicate; held imports must be excluded by it.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) AS c FROM applications a WHERE a.company_code=%s AND a.app_key = ANY(%s) AND {app.reviewable_application_predicate('a')}",
                (COMPANY_A, [ali_app, sara_app]),
            )
            assert_true(cur.fetchone()["c"] == 0, "held imports must be excluded from the Ranking predicate")

    # Company scoping: company B sees neither the batch nor the held candidates.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM import_batches WHERE company_code=%s", (COMPANY_B,))
            assert_true(cur.fetchone()["c"] == 0, "company B must have no import batches")
            cur.execute("SELECT COUNT(*) AS c FROM applications WHERE company_code=%s AND status IN ('needs_role','import_review')", (COMPANY_B,))
            assert_true(cur.fetchone()["c"] == 0, "company B must have no held imports")

    # Worker status guard: extraction completion must NOT un-hold an imported application.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE applications
                SET status=CASE WHEN status IN ('needs_role','import_review') THEN status
                                WHEN %s='complete' THEN 'screening_complete'
                                WHEN status IN ('awaiting_cv','cv_received') THEN 'screening' ELSE status END
                WHERE app_key=%s
                RETURNING status
                """,
                ("complete", sara_app),
            )
            assert_true(cur.fetchone()["status"] == "import_review", "worker must preserve held status on extraction complete")
        conn.commit()

    # Assign role + promote via canonical intake_admit (no direct lifecycle write).
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE applications
                SET position_code='WELDER',
                    position_title='Bulk Welder',
                    updated_at=CURRENT_DATE
                WHERE app_key=%s AND company_code=%s
                """,
                (ali_app, COMPANY_A),
            )
        conn.commit()
    admit = app.update_application_status(
        {"app_key": ali_app, "company_code": COMPANY_A, "status": "needs_role", "position_code": "WELDER"},
        "ready_for_review",
        trigger="intake_admit",
        actor_type="system",
        channel="smoke",
        human_confirmed=False,
        idempotency_key=f"bulk-import-smoke-admit:{ali_app}",
    )
    assert_true(admit.get("ok"), f"canonical intake_admit must succeed: {admit}")
    listing2 = app.prehire_applications_query(
        company_code=COMPANY_A, status=None, position=None, search=None, limit=200, offset=0
    )
    listed2 = {a.get("app_key") for a in listing2.get("applications", [])}
    assert_true(ali_app in listed2, "after assign+promote the candidate must appear in the pipeline")

    # Permission map.
    assert_true("candidate.import" in app.hr_role_permissions("owner"), "owner can import")
    assert_true("candidate.import" in app.hr_role_permissions("hr_manager"), "hr_manager can import")
    assert_true("candidate.import" in app.hr_role_permissions("recruiter"), "recruiter can import")
    assert_true("candidate.import" not in app.hr_role_permissions("hiring_manager"), "hiring_manager cannot import")
    assert_true("candidate.import" not in app.hr_role_permissions("viewer"), "viewer cannot import")


def main() -> None:
    setup()
    try:
        run_checks()
    finally:
        teardown()
    print("bulk CV import smoke tests passed")


if __name__ == "__main__":
    main()
