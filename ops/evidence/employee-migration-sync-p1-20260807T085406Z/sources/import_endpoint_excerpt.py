excerpt bytes 1930
_posthire_import_employees(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    start_onboarding: bool = Form(False),
    source_system: str | None = Form(None),
    idempotency_key: str | None = Form(None),
    batch_id: str | None = Form(None),
    context: dict[str, Any] = Depends(dashboard_context),
):
    """Production-safe migration import only (Migration Sync P1).

    Legacy CSV import that could seed compliance documents is removed. When the
    foundation flag/company allowlist is off, this endpoint refuses rather than
    falling back. start_onboarding=true is rejected (never silently ignored).
    """
    company = require_employee_roster_admin(context)
    import employee_migration_foundation as _emf

    _emf.reject_migration_onboarding_request(sys.modules[__name__], bool(start_onboarding))
    _emf.require_foundation(sys.modules[__name__], company)

    raw = await file.read()
    if len(raw) > EMPLOYEE_IMPORT_MAX_BYTES:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "file_too_large",
                "message": f"This file is too large. Please keep imports under {EMPLOYEE_IMPORT_MAX_BYTES // (1024 * 1024)} MB.",
            },
        )
    if dry_run:
        return json_safe(
            _emf.preview_or_replay_import(
                sys.modules[__name__],
                context,
                raw=raw,
                filename=file.filename or "import.csv",
                source_system=source_system,
                idempotency_key=idempotency_key,
            )
        )
    return json_safe(
        _emf.commit_import_batch(
            sys.modules[__name__],
            context,
            batch_id=batch_id,
            raw=raw,
            filename=file.filename or "import.csv",
            source_system=source_system,
            idempotency_key=idempotency_key,
        )
    )