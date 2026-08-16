
# --- Employees 360 Wave 4: org authority / migration / bulk (flag-gated) ---


class DashboardEmployeeOrgPolicyPatch(BaseModel):
    tier: str | None = None
    require_change_reason: bool | None = None
    require_dual_approval: bool | None = None
    allow_future_dated_changes: bool | None = None
    fail_on_overlap: bool | None = None
    migration_auto_create_org_units: bool | None = None
    bulk_max_rows: int | None = None


class DashboardEmployeeOrgUnitUpsert(BaseModel):
    unit_type: str
    name: str
    unit_key: str | None = None
    parent_org_unit_id: str | None = None
    attributes: dict[str, Any] | None = None
    effective_from: str | None = None
    status: str = "active"


class DashboardEmployeeOrgChangeRequest(BaseModel):
    employee_key: str
    change_type: str
    effective_on: str
    reason: str = Field(min_length=1, max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=200)
    designated_approver_user_id: str | None = None


class DashboardEmployeeMigrationBatchCreate(BaseModel):
    filename: str
    rows: list[dict[str, Any]]
    idempotency_key: str = Field(min_length=8, max_length=200)
    column_mapping: dict[str, str] | None = None


class DashboardEmployeeBulkAssign(BaseModel):
    employee_keys: list[str]
    effective_from: str
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=200)
    department_unit_id: str | None = None
    team_unit_id: str | None = None
    location_unit_id: str | None = None
    manager_employee_key: str | None = None


@app.get("/dashboard/posthire/employee-org/policy")
def dashboard_employee_org_policy_get(context: dict[str, Any] = Depends(dashboard_context)):
    company = require_employee_roster_admin(context, "employees.manage")
    import employee_org_wave4 as _w4

    if not _w4.org_v4_enabled(company):
        raise HTTPException(status_code=403, detail={"error": "org_v4_disabled"})
    return json_safe({"ok": True, "policy": _w4.get_or_create_org_policy(sys.modules[__name__], company_code=company)})


@app.patch("/dashboard/posthire/employee-org/policy")
def dashboard_employee_org_policy_patch(
    body: DashboardEmployeeOrgPolicyPatch,
    context: dict[str, Any] = Depends(dashboard_context),
):
    require_employee_roster_admin(context, "employees.manage")
    import employee_org_wave4 as _w4

    return json_safe(
        {
            "ok": True,
            "policy": _w4.upsert_org_policy(
                sys.modules[__name__], context, patch=body.model_dump(exclude_none=True)
            ),
        }
    )


@app.get("/dashboard/posthire/employee-org/units")
def dashboard_employee_org_units_list(
    unit_type: str | None = None,
    context: dict[str, Any] = Depends(dashboard_context),
):
    company = require_employee_roster_admin(context, "employees.manage")
    import employee_org_wave4 as _w4

    if not _w4.org_v4_enabled(company):
        raise HTTPException(status_code=403, detail={"error": "org_v4_disabled"})
    return json_safe({"ok": True, "units": _w4.list_org_units(sys.modules[__name__], company_code=company, unit_type=unit_type)})


@app.post("/dashboard/posthire/employee-org/units")
def dashboard_employee_org_units_upsert(
    body: DashboardEmployeeOrgUnitUpsert,
    context: dict[str, Any] = Depends(dashboard_context),
):
    require_employee_roster_admin(context, "employees.manage")
    import employee_org_wave4 as _w4
    from datetime import date as _date

    eff = None
    if body.effective_from:
        eff = _date.fromisoformat(str(body.effective_from)[:10])
    return json_safe(
        _w4.upsert_org_unit(
            sys.modules[__name__],
            context,
            unit_type=body.unit_type,
            name=body.name,
            unit_key=body.unit_key,
            parent_org_unit_id=body.parent_org_unit_id,
            attributes=body.attributes,
            effective_from=eff,
            status=body.status,
        )
    )


@app.get("/dashboard/posthire/employees/{employee_key}/org-history")
def dashboard_employee_org_history_get(
    employee_key: str,
    context: dict[str, Any] = Depends(dashboard_context),
):
    company = require_employee_roster_admin(context, "employees.manage")
    require_employee_mutation_scope(context, employee_key, company_code=company, action="org_history_read")
    import employee_org_wave4 as _w4

    if not _w4.org_v4_enabled(company):
        raise HTTPException(status_code=403, detail={"error": "org_v4_disabled"})
    return json_safe({"ok": True, "history": _w4.list_assignment_history(sys.modules[__name__], company_code=company, employee_key=employee_key)})


@app.post("/dashboard/posthire/employee-org/change-requests")
def dashboard_employee_org_change_request(
    body: DashboardEmployeeOrgChangeRequest,
    context: dict[str, Any] = Depends(dashboard_context),
):
    require_employee_roster_admin(context, "employees.manage")
    import employee_org_wave4 as _w4
    from datetime import date as _date

    return json_safe(
        _w4.create_org_change_request(
            sys.modules[__name__],
            context,
            employee_key=body.employee_key,
            change_type=body.change_type,
            effective_on=_date.fromisoformat(str(body.effective_on)[:10]),
            reason=body.reason,
            payload=body.payload or {},
            idempotency_key=body.idempotency_key,
            designated_approver_user_id=body.designated_approver_user_id,
        )
    )


@app.post("/dashboard/posthire/employee-org/migration-batches")
def dashboard_employee_org_migration_create(
    body: DashboardEmployeeMigrationBatchCreate,
    context: dict[str, Any] = Depends(dashboard_context),
):
    require_employee_roster_admin(context, "employees.manage")
    import employee_org_wave4 as _w4

    return json_safe(
        _w4.create_migration_batch(
            sys.modules[__name__],
            context,
            filename=body.filename,
            rows=body.rows,
            idempotency_key=body.idempotency_key,
            column_mapping=body.column_mapping,
        )
    )


@app.post("/dashboard/posthire/employee-org/migration-batches/{batch_id}/dry-run")
def dashboard_employee_org_migration_dry_run(
    batch_id: str,
    context: dict[str, Any] = Depends(dashboard_context),
):
    require_employee_roster_admin(context, "employees.manage")
    import employee_org_wave4 as _w4

    return json_safe(_w4.dry_run_migration_batch(sys.modules[__name__], context, batch_id=batch_id))


@app.post("/dashboard/posthire/employee-org/migration-batches/{batch_id}/commit")
def dashboard_employee_org_migration_commit(
    batch_id: str,
    resume: bool = False,
    max_rows: int | None = None,
    context: dict[str, Any] = Depends(dashboard_context),
):
    require_employee_roster_admin(context, "employees.manage")
    import employee_org_wave4 as _w4

    return json_safe(
        _w4.commit_migration_batch(
            sys.modules[__name__], context, batch_id=batch_id, resume=resume, max_rows=max_rows
        )
    )


@app.post("/dashboard/posthire/employee-org/migration-batches/{batch_id}/pause")
def dashboard_employee_org_migration_pause(
    batch_id: str,
    context: dict[str, Any] = Depends(dashboard_context),
):
    require_employee_roster_admin(context, "employees.manage")
    import employee_org_wave4 as _w4

    return json_safe(_w4.pause_migration_batch(sys.modules[__name__], context, batch_id=batch_id))


@app.post("/dashboard/posthire/employee-org/migration-batches/{batch_id}/rollback")
def dashboard_employee_org_migration_rollback(
    batch_id: str,
    idempotency_key: str,
    context: dict[str, Any] = Depends(dashboard_context),
):
    require_employee_roster_admin(context, "employees.manage")
    import employee_org_wave4 as _w4

    return json_safe(
        _w4.rollback_migration_batch(
            sys.modules[__name__], context, batch_id=batch_id, idempotency_key=idempotency_key
        )
    )


@app.post("/dashboard/posthire/employee-org/bulk-assign")
def dashboard_employee_org_bulk_assign(
    body: DashboardEmployeeBulkAssign,
    context: dict[str, Any] = Depends(dashboard_context),
):
    require_employee_roster_admin(context, "employees.manage")
    import employee_org_wave4 as _w4
    from datetime import date as _date

    return json_safe(
        _w4.create_bulk_assign_job(
            sys.modules[__name__],
            context,
            employee_keys=body.employee_keys,
            effective_from=_date.fromisoformat(str(body.effective_from)[:10]),
            reason=body.reason,
            idempotency_key=body.idempotency_key,
            department_unit_id=body.department_unit_id,
            team_unit_id=body.team_unit_id,
            location_unit_id=body.location_unit_id,
            manager_employee_key=body.manager_employee_key,
        )
    )


@app.get("/dashboard/posthire/employee-org/export")
def dashboard_employee_org_export(
    as_of: str | None = None,
    context: dict[str, Any] = Depends(dashboard_context),
):
    company = require_employee_roster_admin(context, "employees.manage")
    import employee_org_wave4 as _w4
    from datetime import date as _date

    if not _w4.org_v4_enabled(company):
        raise HTTPException(status_code=403, detail={"error": "org_v4_disabled"})
    as_of_date = _date.fromisoformat(str(as_of)[:10]) if as_of else None
    return json_safe(_w4.export_org_reconciliation(sys.modules[__name__], company_code=company, as_of=as_of_date))


@app.get("/dashboard/posthire/employees/{employee_key}/org-as-of")
def dashboard_employee_org_as_of(
    employee_key: str,
    as_of: str | None = None,
    context: dict[str, Any] = Depends(dashboard_context),
):
    company = require_employee_roster_admin(context, "employees.manage")
    require_employee_mutation_scope(context, employee_key, company_code=company, action="org_as_of_read")
    import employee_org_wave4 as _w4
    from datetime import date as _date

    if not _w4.org_v4_enabled(company):
        raise HTTPException(status_code=403, detail={"error": "org_v4_disabled"})
    as_of_date = _date.fromisoformat(str(as_of)[:10]) if as_of else _date.today()
    return json_safe(
        _w4.get_current_org_projection(
            sys.modules[__name__], company_code=company, employee_key=employee_key, as_of=as_of_date
        )
    )


@app.get("/dashboard/posthire/employee-org/reconcile")
def dashboard_employee_org_reconcile(
    as_of: str | None = None,
    context: dict[str, Any] = Depends(dashboard_context),
):
    company = require_employee_roster_admin(context, "employees.manage")
    import employee_org_wave4 as _w4
    from datetime import date as _date

    if not _w4.org_v4_enabled(company):
        raise HTTPException(status_code=403, detail={"error": "org_v4_disabled"})
    as_of_date = _date.fromisoformat(str(as_of)[:10]) if as_of else None
    return json_safe(_w4.reconcile_org_authority(sys.modules[__name__], company_code=company, as_of=as_of_date))


@app.post("/dashboard/posthire/employee-org/activate-due")
def dashboard_employee_org_activate_due(
    as_of: str | None = None,
    context: dict[str, Any] = Depends(dashboard_context),
):
    company = require_employee_roster_admin(context, "employees.manage")
    import employee_org_wave4 as _w4
    from datetime import date as _date

    if not _w4.org_v4_enabled(company):
        raise HTTPException(status_code=403, detail={"error": "org_v4_disabled"})
    as_of_date = _date.fromisoformat(str(as_of)[:10]) if as_of else None
    return json_safe(_w4.activate_due_assignment_slices(sys.modules[__name__], company_code=company, as_of=as_of_date))


def _parse_employee_import_file(raw: bytes, filename: str) -> tuple[list[dict[str, str]], str | None]:
    """Parse a CSV or XLSX upload into normalized {name, phone, email, ...} dicts.
    Returns (rows, error). Numbers from XLSX (e.g. a phone read as a float) are
    coerced back to integer strings before normalization."""
    name = str(filename or "").lower()
    try:
        if name.endswith(".xlsx") or name.endswith(".xlsm"):
            import openpyxl  # available in the orchestrator venv

            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            ws = wb.active
            if ws is None:
                return [], "We couldn't read this spreadsheet."
            iterator = ws.iter_rows(values_only=True)
            try:
                header = next(iterator)
            except StopIteration:
                return [], "The file is empty."
            mapped = [EMPLOYEE_IMPORT_HEADER_ALIASES.get(_normalize_import_header(h)) for h in header]
            if "name" not in mapped or "phone" not in mapped:
                return [], "The file needs a 'name' and a 'phone' column."
            rows: list[dict[str, str]] = []
            for values in iterator:
                if not values:
                    continue
                rec: dict[str, str] = {}
                for key, val in zip(mapped, values):
                    if not key or val is None:
                        continue
                    if isinstance(val, float) and val.is_integer():
                        val = int(val)
                    text = str(val).strip()
                    if text:
                        rec[key] = text
                if rec:
                    rows.append(rec)
            return rows, None
        # default: CSV
        text = raw.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return [], "The file is empty or missing a header row."
        field_map = {fn: EMPLOYEE_IMPORT_HEADER_ALIASES.get(_normalize_import_header(fn)) for fn in reader.fieldnames}
        if "name" not in field_map.values() or "phone" not in field_map.values():
            return [], "The file needs a 'name' and a 'phone' column."
        rows = []
        for raw_rec in reader:
            rec = {}
            for fn, key in field_map.items():
                if not key:
                    continue
                value = str(raw_rec.get(fn) or "").strip()
                if value:
                    rec[key] = value
            if rec:
                rows.append(rec)
        return rows, None
    except Exception:
        logger.warning("employee import parse failed", exc_info=True)
        return [], "We couldn't read this file. Please upload a CSV or XLSX with name and phone columns."


@app.post("/dashboard/posthire/employees/import")
async def dashboard_posthire_import_employees(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    start_onboarding: bool = Form(False),
    context: dict[str, Any] = Depends(dashboard_context),
):
    company = require_employee_roster_admin(context)
    seed = company_has_module(company, "compliance")
    raw = await file.read()
    if len(raw) > EMPLOYEE_IMPORT_MAX_BYTES:
        raise HTTPException(status_code=422, detail={"error": "file_too_large", "message": f"This file is too large. Please keep imports under {EMPLOYEE_IMPORT_MAX_BYTES // (1024 * 1024)} MB."})
    rows, parse_error = _parse_employee_import_file(raw, file.filename or "")
    if parse_error:
        raise HTTPException(status_code=422, detail={"error": "unreadable_file", "message": parse_error})
    if len(rows) > EMPLOYEE_IMPORT_MAX_ROWS:
        raise HTTPException(status_code=422, detail={"error": "too_many_rows", "message": f"Please import up to {EMPLOYEE_IMPORT_MAX_ROWS} employees per file."})

    summary: dict[str, list[dict[str, Any]]] = {"created": [], "skipped": [], "needs_review": [], "failed": []}
    seen_phones: dict[str, int] = {}
    for idx, rec in enumerate(rows, start=1):
        clean_name = str(rec.get("name") or "").strip()
        # Canonicalize so a local 8-digit number de-dupes against the stored 965 form.
        phone_digits = canonical_employee_phone(rec.get("phone"))
        row_label = clean_name or str(rec.get("phone") or "").strip() or f"Row {idx}"
        if not phone_digits:
            summary["failed"].append({"row": idx, "name": row_label, "reason": "Missing or invalid phone number."})
            continue
        if not clean_name:
            summary["failed"].append({"row": idx, "name": row_label, "reason": "Missing name."})
            continue
        if phone_digits in seen_phones:
            summary["needs_review"].append({"row": idx, "name": row_label, "reason": f"Duplicate phone in this file (also row {seen_phones[phone_digits]})."})
            continue
        seen_phones[phone_digits] = idx
        # Each row is created in its own transaction (create_company_employee owns
        # its connection/commit). Guard per row so one bad row becomes a 'failed'
        # entry instead of aborting the whole import and discarding the summary.
        try:
            existing = find_employee_by_phone(phone_digits, company_code=company)
            if existing:
                existing_name = str(existing.get("name") or "").strip()
                if existing_name and existing_name.lower() != clean_name.lower():
                    summary["needs_review"].append({"row": idx, "name": row_label, "reason": f"Already exists as '{existing_name}' with a different name."})
                else:
                    summary["skipped"].append({"row": idx, "name": row_label, "reason": "Already in the workforce."})
                continue
            if dry_run:
                summary["created"].append({"row": idx, "name": row_label, "reason": "Will be added."})
                continue
            result = create_company_employee(
                company,
                name=clean_name,
                phone=phone_digits,
                email=rec.get("email"),
                position_title=rec.get("position_title"),
                department=rec.get("department"),
                start_date=rec.get("start_date"),
                seed_compliance=seed,
                start_onboarding=start_onboarding,
            )
            status = result.get("status")
            if status == "created":
                summary["created"].append({"row": idx, "name": row_label})
            elif status == "exists":
                summary["skipped"].append({"row": idx, "name": row_label, "reason": "Already in the workforce."})
            else:
                summary["failed"].append({"row": idx, "name": row_label, "reason": result.get("reason") or "Could not be added."})
        except Exception:
            logger.warning("employee import row failed", exc_info=True)
            summary["failed"].append({"row": idx, "name": row_label, "reason": "Could not be added right now."})

    counts = {key: len(value) for key, value in summary.items()}
    if not dry_run and counts["created"]:
        record_admin_audit(
            context,
            "employees_imported",
            summary=f"Imported {counts['created']} employees ({counts['skipped']} skipped, {counts['needs_review']} need review, {counts['failed']} failed).",
            target_type="company",
            target=company,
            details=counts,
        )
    return {"ok": True, "dry_run": dry_run, "total_rows": len(rows), "counts": counts, "results": summary}


# onboarding_status buckets, kept in one place so the paged query, the summary
# counts and the frontend split all agree on what "still onboarding" means.
_ONBOARDING_IN_PROGRESS_SQL = "lower(coalesce(e.onboarding_status,'not_started')) IN ('in_progress','not_started','pending')"
_ONBOARDING_DONE_SQL = "lower(coalesce(e.onboarding_status,'')) IN ('complete','completed','done')"


def onboarding_counts_by_employee(company_code: str | None, employee_keys: list[str] | None = None) -> dict[str, dict[str, int]]:
    """One-query rollup of required-item pending/received counts per employee, so
    the onboarding list can show progress without an N+1 fan-out. When
    `employee_keys` is given the rollup is limited to just those employees (the
    current page), avoiding a full-company scan when only a page is displayed."""
    company = (company_code or "WATHEFNI").upper()
    out: dict[str, dict[str, int]] = {}
    params: list[Any] = [company]
    key_clause = ""
    if employee_keys is not None:
        if not employee_keys:
            return out
        key_clause = "AND oi.employee_key = ANY(%s)"
        params.append(list(employee_keys))
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT oi.employee_key,
                       COUNT(*) FILTER (WHERE oi.required IS TRUE AND lower(oi.status) NOT IN ('received','complete','completed','verified')) AS pending,
                       COUNT(*) FILTER (WHERE oi.required IS TRUE AND lower(oi.status) IN ('received','complete','completed','verified')) AS received
                FROM onboarding_items oi
                JOIN employees e ON e.employee_key = oi.employee_key AND e.company_code=%s
                WHERE TRUE {key_clause}
                GROUP BY oi.employee_key
                """,
                params,
            )
            for r in cur.fetchall():
                out[str(r.get("employee_key"))] = {
                    "pending_count": int(r.get("pending") or 0),
                    "received_count": int(r.get("received") or 0),
                }
    return out


def list_onboarding_page(
    company_code: str | None,
    *,
    viewer_phone: str | None = None,
    dashboard_user_id: str | None = None,
    actor_role: str | None = None,
    search: str | None = None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Paged read of employees who are STILL ONBOARDING (the onboarding list's
    primary view), scope- and search-aware in SQL so a large intake isn't
    truncated and search reaches the whole in-progress set. Stable PK tiebreaker
    keeps OFFSET paging deterministic."""
    where_sql, params = _employee_scope_where(
        company_code,
        viewer_phone,
        dashboard_user_id=dashboard_user_id,
        actor_role=actor_role,
    )
    where_sql = f"{where_sql} AND {_ONBOARDING_IN_PROGRESS_SQL}"
    search_clause, search_params = _employee_search_clause(search)
    if search_clause:
        where_sql = f"{where_sql} AND {search_clause}"
        params.extend(search_params)
    params.extend([limit, offset])
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT e.*, COUNT(*) OVER() AS _total_count
                FROM employees e
                WHERE {where_sql}
                ORDER BY e.name NULLS LAST, e.phone, e.employee_key
                LIMIT %s OFFSET %s
                """,
                params,
            )
            rows = [dict(row) for row in cur.fetchall()]
    total_count = int(rows[0]["_total_count"]) if rows else 0
    for row in rows:
        row.pop("_total_count", None)
    has_more = (offset + len(rows)) < total_count
    return {"rows": rows, "total_count": total_count, "limit": limit, "offset": offset, "has_more": has_more}


def onboarding_directory_counts(
    company_code: str | None,
    *,
    viewer_phone: str | None = None,
    dashboard_user_id: str | None = None,
    actor_role: str | None = None,
) -> dict[str, int]:
    """Scope-aware onboarding headline counts over the WHOLE workforce (total +
    completed), so the summary numbers stay correct regardless of paging."""
    where_sql, params = _employee_scope_where(
        company_code,
        viewer_phone,
        dashboard_user_id=dashboard_user_id,
        actor_role=actor_role,
    )
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE {_ONBOARDING_DONE_SQL}) AS completed,
                       count(*) FILTER (WHERE {_ONBOARDING_IN_PROGRESS_SQL}) AS in_progress
                FROM employees e
                WHERE {where_sql}
                """,
                params,
            )
            row = dict(cur.fetchone() or {})
    return {
        "total": int(row.get("total") or 0),
        "completed_count": int(row.get("completed") or 0),
        "in_progress_count": int(row.get("in_progress") or 0),
    }


@app.get("/dashboard/posthire/onboarding")
def dashboard_posthire_onboarding(
    offset: int = 0,
    limit: int = 100,
    search: str = "",
    context: dict[str, Any] = Depends(dashboard_context),
):
    company = _posthire_read_context(context, "onboarding")
    # Page the "still onboarding" list so a large intake isn't silently truncated,
    # and search it in SQL so HR can find anyone across the whole set. Headline
    # counts (total/completed) stay workforce-wide, independent of the page/search.
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    viewer_phone = context.get("hr_phone")
    page = list_onboarding_page(
        company,
        viewer_phone=viewer_phone,
        dashboard_user_id=context.get("actor_user_id"),
        actor_role=context.get("actor_role"),
        search=search,
        limit=limit,
        offset=offset,
    )
    cards = [posthire_employee_card(row) for row in page["rows"]]
    counts = onboarding_counts_by_employee(company, [c["employee_key"] for c in cards])
    for card in cards:
        c = counts.get(card["employee_key"]) or {"pending_count": 0, "received_count": 0}
        card["pending_count"] = c["pending_count"]
        card["received_count"] = c["received_count"]
    summary = onboarding_directory_counts(
        company,
        viewer_phone=viewer_phone,
        dashboard_user_id=context.get("actor_user_id"),
        actor_role=context.get("actor_role"),
    )
    return {
        "company_code": company,
        "in_progress": cards,
        "completed_count": summary["completed_count"],
        "total": summary["total"],
        "total_count": page["total_count"],
        "limit": page["limit"],
        "offset": page["offset"],
        "has_more": page["has_more"],
        "hr_mutate_enabled": onboarding_hr_mutate_enabled(),
    }


@app.get("/dashboard/posthire/onboarding/{employee_key}")
def dashboard_posthire_onboarding_detail(employee_key: str, context: dict[str, Any] = Depends(dashboard_context)):
    company = _posthire_read_context(context, "onboarding")
    employee = find_employee_by_key(employee_key, company_code=company)
    if not employee:
        raise HTTPException(status_code=404, detail={"error": "employee_not_found", "message": "We couldn't find that employee."})
    viewer_phone = context.get("hr_phone")
    if not context_manager_allows_employee(context, employee, company_code=company):
        raise HTTPException(status_code=404, detail={"error": "employee_not_found", "message": "We couldn't find that employee."})
    summary = employee_onboarding_summary(employee)
    document_index = employee_document_index(company, str(employee.get("employee_key")))
    return json_safe({
        "company_code": company,
        "hr_mutate_enabled": onboarding_hr_mutate_enabled(),
        "doc_upload_enabled": doc_upload_enabled(),
        "document_index": document_index,
        **summary,
    })


def _attendance_range(start_date: str | None, end_date: str | None) -> tuple[date, date]:
    """Resolve the requested attendance window, defaulting to today and clamping
    to a 92-day span so a date-range read/export can never scan unbounded history."""
    today = kuwait_today()
    start = parse_shift_date_value(start_date) or today
    end = parse_shift_date_value(end_date) or start
    if end < start:
        start, end = end, start
    if (end - start).days > 92:
        start = end - timedelta(days=92)
    return start, end


ALLOWED_ATTENDANCE_STATUS_FILTERS = frozenset({"present", "late", "absent", "completed", "pending"})


def normalize_attendance_status_filter(status: str | None) -> str | None:
    """Return a canonical attendance status filter, or None when unset.

    Invalid non-empty values raise HTTP 400 with a deterministic error contract —
    they must never silently widen or ignore the filter on the HTTP route.

    Direct Python calls of the FastAPI route (smoke harnesses) may receive the
    ``Query(None)`` default object instead of ``None``; treat that as unset.
    """
    if status is None or not isinstance(status, str):
        return None
    raw = status.strip()
    if not raw:
        return None
    normalized = normalize_text(raw)
    if normalized not in ALLOWED_ATTENDANCE_STATUS_FILTERS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_attendance_status",
                "message": "That attendance status filter is not valid.",
                "allowed": sorted(ALLOWED_ATTENDANCE_STATUS_FILTERS),
                "received": raw,
            },
        )
    return normalized


@app.get("/dashboard/posthire/attendance")
def dashboard_posthire_attendance(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    status: str | None = Query(None),
    offset: int = Query(0),
    limit: int = Query(1000),
    context: dict[str, Any] = Depends(dashboard_context),
):
    company = _posthire_read_context(context, "attendance")
    start, end = _attendance_range(start_date, end_date)
    today = kuwait_today().isoformat()
    status_filter = normalize_attendance_status_filter(status)
    # Paged so a busy company/window (>1000 records over up to 92 days) isn't
    # silently truncated: the table pages via limit/offset with an accurate
    # total_count + has_more, same pattern as shifts/leave/payroll.
    result = list_attendance(
        {
            "company_code": company,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "viewer_phone": context.get("hr_phone"),
            "viewer_user_id": context.get("actor_user_id"),
            "actor_role": context.get("actor_role"),
            "status": status_filter,
            "limit": limit,
            "offset": offset,
        },
        company_code=company,
    )
    return json_safe({
        "company_code": company,
        "date": today,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "is_today": start == end == kuwait_today(),
        "import_enabled": attendance_import_enabled(),
        **result,
    })


def build_attendance_csv(rows: list[dict[str, Any]]) -> str:
    """Render attendance rows to CSV text (header + one row each). Pure/no I/O so
    the export endpoint and smoke test share the exact same column contract."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Employee", "Date", "Status", "Check-in", "Check-out", "Late minutes", "Notes"])
    for row in rows or []:
        status = str(row.get("status") or "").replace("_", " ").strip().title()
        writer.writerow([
            row.get("employee_name") or "",
            row.get("attendance_date") or "",
            status,
            format_attendance_time(row.get("check_in_at")),
            format_attendance_time(row.get("check_out_at")),
            row.get("late_minutes") if row.get("late_minutes") is not None else "",
            row.get("notes") or "",
        ])
    return buffer.getvalue()


@app.get("/dashboard/posthire/attendance/export.csv")
def dashboard_posthire_attendance_export(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    context: dict[str, Any] = Depends(dashboard_context),
):
    company = _posthire_read_context(context, "attendance")
    start, end = _attendance_range(start_date, end_date)
    result = list_attendance(
        {
            "company_code": company,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "viewer_phone": context.get("hr_phone"),
            "viewer_user_id": context.get("actor_user_id"),
            "actor_role": context.get("actor_role"),
            "limit": 5000,
        },
        company_code=company,
    )
    rows = result.get("attendance") or []
    csv_text = build_attendance_csv(rows)

    record_admin_audit(
        context,
        "attendance_exported",
        summary=f"Exported {len(rows)} attendance record(s) for {start.isoformat()} to {end.isoformat()}.",
        target_type="company",
        target=company,
        details={"start_date": start.isoformat(), "end_date": end.isoformat(), "row_count": len(rows)},
    )
    filename = f"attendance-{company}-{start.isoformat()}-to-{end.isoformat()}.csv"
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


