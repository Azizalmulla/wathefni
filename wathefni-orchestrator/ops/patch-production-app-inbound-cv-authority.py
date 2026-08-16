#!/usr/bin/env python3
"""Apply durable scan + identity authority onto production app.py.

Production still runs the legacy sync Postmark importer. This patcher:
- adds durable_email_ingress + inbound_cv_authority imports/schema;
- replaces Postmark receive with durable receipt;
- inserts identity resolution / accepted preparation / durable worker handlers;
- replaces register_imported_cv / _import_process_one_file / run_mailbox_sync;
- fail-closes live Gmail/mailbox sync;
- gates document-current promotion on durable scan+identity authority;
- upgrades the Postmark webhook to durable fail-closed semantics.

Does not enable inbound email, workers, timers, or mailbox sync.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


MARKER = "INBOUND_CV_SCAN_IDENTITY_AUTHORITY_V1"
REPLACE_CORE = (
    "register_imported_cv",
    "_import_process_one_file",
    "run_mailbox_sync",
)
INSERT_BEFORE_VERIFY = (
    "durable_email_ingress_config",
    "process_postmark_inbound",
    "_resolve_clean_intake_document_identity",
    "_prepare_accepted_intake_document",
    "process_durable_email_ingress_job",
    "run_durable_email_ingress_worker",
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def function_span(source: str, name: str) -> tuple[int, int]:
    tree = ast.parse(source)
    node = next(
        (
            item
            for item in tree.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == name
        ),
        None,
    )
    if node is None or node.end_lineno is None:
        raise RuntimeError(f"function missing: {name}")
    lines = source.splitlines(keepends=True)
    start = sum(len(line) for line in lines[: node.lineno - 1])
    end = sum(len(line) for line in lines[: node.end_lineno])
    return start, end


def function_source(source: str, name: str) -> str:
    start, end = function_span(source, name)
    text = source[start:end]
    if not text.endswith("\n"):
        text += "\n"
    return text


def replace_function(target: str, reference: str, name: str) -> str:
    start, end = function_span(target, name)
    return target[:start] + function_source(reference, name) + target[end:]


def count_functions(source: str, name: str) -> int:
    tree = ast.parse(source)
    return sum(
        1
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
    )


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: patch-production-app-inbound-cv-authority.py "
            "<production-app.py> <local-reference-app.py> <output.py>"
        )
    source_path = Path(sys.argv[1])
    reference_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3])
    source = source_path.read_text()
    reference = reference_path.read_text()

    if MARKER not in source:
        source = replace_once(
            source,
            "import cv_extraction as _cv_extraction  # noqa: E402\n",
            "import cv_extraction as _cv_extraction  # noqa: E402\n"
            "import durable_email_ingress as _durable_email_ingress  # noqa: E402\n"
            "import inbound_cv_authority as _inbound_cv_authority  # "
            f"{MARKER}\n",
            "authority imports",
        )
        source = replace_once(
            source,
            "            _cv_extraction.ensure_cv_extraction_schema(_cv_schema_exec)\n"
            "            import unified_candidates as _unified_candidates  # UNIFIED_CANDIDATES_PRODUCTION_DARK_PATCH\n",
            "            _cv_extraction.ensure_cv_extraction_schema(_cv_schema_exec)\n"
            "            _durable_email_ingress.ensure_schema(cur)\n"
            "            _inbound_cv_authority.ensure_schema(cur)\n"
            "            import unified_candidates as _unified_candidates  # UNIFIED_CANDIDATES_PRODUCTION_DARK_PATCH\n",
            "authority schema",
        )

    for name in REPLACE_CORE:
        source = replace_function(source, reference, name)

    # Remove legacy sync Postmark importer before inserting durable handlers.
    if count_functions(source, "process_postmark_inbound") == 1:
        old_start, old_end = function_span(source, "process_postmark_inbound")
        source = source[:old_start] + source[old_end:]

    if count_functions(source, "durable_email_ingress_config") == 0:
        verify_start, _ = function_span(source, "_verify_postmark_token")
        inserted = "".join(
            function_source(reference, name) + "\n\n" for name in INSERT_BEFORE_VERIFY
        )
        source = source[:verify_start] + inserted + source[verify_start:]

    if count_functions(source, "process_postmark_inbound") != 1:
        raise RuntimeError(
            "expected exactly one process_postmark_inbound after durable insert"
        )
    if count_functions(source, "_resolve_clean_intake_document_identity") != 1:
        raise RuntimeError("identity handler missing after insert")
    if count_functions(source, "process_durable_email_ingress_job") != 1:
        raise RuntimeError("durable job dispatcher missing after insert")

    source = replace_function(source, reference, "webhook_postmark_inbound")

    guard = """\
            governed_intake_document_id = str(
                document_metadata.get("intake_document_id")
                or document_cv.get("intake_document_id")
                or ""
            )
            if document_metadata.get("identity_resolution_id"):
                content_sha = str(
                    ((document_cv.get("storage") or {}).get("sha256"))
                    if isinstance(document_cv.get("storage"), dict)
                    else ""
                )
                if not _inbound_cv_authority.binding_is_authorized(
                    cur,
                    company_code=company_code,
                    intake_document_id=governed_intake_document_id,
                    content_sha256=content_sha,
                    candidate_phone=str(app.get("phone") or "") or None,
                    app_key=str(app.get("app_key") or "") or None,
                ):
                    return {
                        "ok": False,
                        "error": "document_current_authority_not_proven",
                        "document_id": document_id,
                    }
"""
    if "document_current_authority_not_proven" not in source:
        source = replace_once(
            source,
            """\
            if not company_code:
                return {"ok": False, "error": "tenant_scope_required", "document_id": document_id}
            db_exec = _cv_db_execute_factory(cur)
""",
            """\
            if not company_code:
                return {"ok": False, "error": "tenant_scope_required", "document_id": document_id}
"""
            + guard
            + "            db_exec = _cv_db_execute_factory(cur)\n",
            "document-current authority",
        )

    ast.parse(source)
    required = [
        MARKER,
        "durable_scan_and_identity_authority_required",
        "cv_identity_resolution",
        "document_current_authority_not_proven",
        "inbound_disabled",
    ]
    missing = [item for item in required if item not in source]
    if missing:
        raise RuntimeError(f"patched source missing required markers: {missing}")
    output_path.write_text(source)
    print(
        {
            "ok": True,
            "marker": MARKER,
            "source": str(source_path),
            "reference": str(reference_path),
            "output": str(output_path),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
