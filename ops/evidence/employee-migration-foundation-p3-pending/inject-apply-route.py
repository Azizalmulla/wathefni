#!/usr/bin/env python3
from pathlib import Path

path = Path("/opt/wathefni/orchestrator/app.py")
text = path.read_text()
if "apply-approved-name-change" in text:
    print("already present")
    raise SystemExit(0)

anchor = '@app.get("/dashboard/posthire/employees/import-batches/{batch_id}")\ndef dashboard_posthire_import_batch_get('
idx = text.find(anchor)
if idx < 0:
    raise SystemExit("anchor not found")
if "approve-name-change" not in text[:idx]:
    raise SystemExit("approve route missing before get batch")

block = '''@app.post("/dashboard/posthire/employees/import-batches/{batch_id}/rows/{row_id}/apply-approved-name-change")
def dashboard_posthire_import_apply_approved_name_change(
    batch_id: str,
    row_id: str,
    context: dict[str, Any] = Depends(dashboard_context),
):
    import employee_migration_foundation as _emf

    return json_safe(
        _emf.apply_approved_name_change(
            sys.modules[__name__],
            context,
            batch_id=batch_id,
            row_id=row_id,
        )
    )


'''
text = text[:idx] + block + text[idx:]
path.write_text(text)
print("injected ok")
