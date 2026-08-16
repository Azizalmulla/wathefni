#!/usr/bin/env python3
"""Apply the contained inbound scan/identity authority patch to staging app.py."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


MARKER = "INBOUND_CV_SCAN_IDENTITY_AUTHORITY_V1"
FUNCTIONS = (
    "register_imported_cv",
    "_import_process_one_file",
    "run_mailbox_sync",
    "_prepare_accepted_intake_document",
    "process_durable_email_ingress_job",
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
    while end < len(source) and source[end] == "\n":
        end += 1
    return start, end


def function_source(source: str, name: str) -> str:
    start, end = function_span(source, name)
    return source[start:end]


def replace_function(target: str, reference: str, name: str) -> str:
    start, end = function_span(target, name)
    replacement = function_source(reference, name)
    return target[:start] + replacement + target[end:]


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: patch-staging-app-inbound-cv-authority.py "
            "<staging-app.py> <local-reference-app.py> <output.py>"
        )
    source_path = Path(sys.argv[1])
    reference_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3])
    source = source_path.read_text()
    reference = reference_path.read_text()

    if MARKER not in source:
        source = replace_once(
            source,
            "import durable_email_ingress as _durable_email_ingress  # noqa: E402\n",
            "import durable_email_ingress as _durable_email_ingress  # noqa: E402\n"
            "import inbound_cv_authority as _inbound_cv_authority  # "
            f"{MARKER}\n",
            "authority import",
        )
        source = replace_once(
            source,
            "            _durable_email_ingress.ensure_schema(cur)\n",
            "            _durable_email_ingress.ensure_schema(cur)\n"
            "            _inbound_cv_authority.ensure_schema(cur)\n",
            "authority schema",
        )
    for name in FUNCTIONS:
        source = replace_function(source, reference, name)

    identity_handler = function_source(
        reference, "_resolve_clean_intake_document_identity"
    )
    try:
        handler_start, handler_end = function_span(
            source, "_resolve_clean_intake_document_identity"
        )
        source = source[:handler_start] + identity_handler + source[handler_end:]
    except RuntimeError:
        prepare_start, _ = function_span(source, "_prepare_accepted_intake_document")
        source = source[:prepare_start] + identity_handler + source[prepare_start:]

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

    unsafe_sender_meta = '                        meta={"email": _parse_email_address(sender)},\n'
    safe_sender_meta = (
        "                        # Sender is provenance only. Legacy mailbox sync cannot\n"
        "                        # bind a candidate until it enters the durable authority path.\n"
        "                        meta={},\n"
    )
    if unsafe_sender_meta in source:
        source = replace_once(
            source,
            unsafe_sender_meta,
            safe_sender_meta,
            "mailbox sender provenance",
        )

    ast.parse(source)
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
