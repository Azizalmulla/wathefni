#!/usr/bin/env python3
"""Surgical staging patch for Unified Inbound CV Wave 1–3 hooks.

Does NOT replace staging app.py wholesale. Injects only missing imports,
schema ensure calls, and savepoint-guarded adapter/dual-write hooks.
"""

from __future__ import annotations

import argparse
from pathlib import Path


MARKERS = {
    "schema_intake": "import inbound_cv_intake as _inbound_cv_intake",
    "schema_processing": "import inbound_cv_processing as _inbound_cv_processing",
    "manual_adapter": "unified_inbound_cv_manual_adapter",
    "wa_unsolicited": "unified_inbound_cv_whatsapp_unsolicited",
    "wa_job": "unified_inbound_cv_whatsapp_job",
    "cv_version": "unified_cv_version_dual_write",
}


def patch(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    actions: list[str] = []

    if MARKERS["schema_intake"] not in text:
        anchor = "_durable_email_ingress.ensure_schema(cur)"
        if anchor not in text:
            raise SystemExit("missing durable_email ensure_schema anchor")
        insert = (
            "_durable_email_ingress.ensure_schema(cur)\n"
            "            import inbound_cv_intake as _inbound_cv_intake\n"
            "            _inbound_cv_intake.ensure_schema(cur)\n"
            "            import inbound_cv_processing as _inbound_cv_processing\n"
            "            _inbound_cv_processing.ensure_schema(cur)"
        )
        text = text.replace(anchor, insert, 1)
        actions.append("schema_ensure")

    # Manual adapter after successful import item_record update block — soft marker comment.
    if MARKERS["manual_adapter"] not in text:
        needle = 'item_record.update({"status": "failed", "error": result.get("error") or "import_failed"})\n    return item_record'
        if needle not in text:
            # Try alternate formatting
            needle = 'item_record.update({"status": "failed", "error": result.get("error") or "import_failed"})\n        return item_record'
        if 'if result.get("ok"):' in text and MARKERS["manual_adapter"] not in text:
            # Insert before the failed branch return of _import_process_one_file using unique context.
            target = '''    if result.get("ok"):
        seen_checksums[checksum] = result.get("app_key")
        item_record.update({
            "status": "imported",'''
            if target in text and MARKERS["manual_adapter"] not in text:
                # Find end of ok branch before else
                idx = text.find(target)
                else_idx = text.find("\n    else:\n        item_record.update({\"status\": \"failed\"", idx)
                if else_idx == -1:
                    raise SystemExit("manual adapter insert point not found")
                hook = '''
        # WAVE3 surgical: additive manual adapter dual-write
        if str(source or "").strip().lower() not in {"email", "email_inbound"}:
            cur.execute("SAVEPOINT unified_inbound_cv_manual_adapter")
            try:
                import inbound_cv_adapters as _inbound_cv_adapters
                _inbound_cv_adapters.adapt_manual_import(
                    cur,
                    company_code=company,
                    batch_id=batch_id,
                    content_sha256=checksum,
                    filename=Path(filename).name,
                    document_id=str(result.get("document_id") or "") or None,
                    app_key=str(result.get("app_key") or "") or None,
                    held_status=str(result.get("status") or "") or None,
                    mime_or_suffix=suffix or str(item_record.get("mime_type") or ""),
                )
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT unified_inbound_cv_manual_adapter")
            finally:
                cur.execute("RELEASE SAVEPOINT unified_inbound_cv_manual_adapter")
'''
                text = text[:else_idx] + hook + text[else_idx:]
                actions.append("manual_adapter")

    if MARKERS["wa_unsolicited"] not in text:
        hold_return = "            row = dict(cur.fetchone())\n        conn.commit()\n    return json_safe(row)\n\n\ndef upsert_candidate_job_context"
        if hold_return not in text:
            hold_return = "            row = dict(cur.fetchone())\n        conn.commit()\n    return json_safe(row)\n\n\ndef upsert_candidate_job_context("
        if hold_return in text:
            hook = '''            row = dict(cur.fetchone())
            # WAVE3 surgical: unsolicited WhatsApp adapter
            cur.execute("SAVEPOINT unified_inbound_cv_whatsapp_unsolicited")
            try:
                import inbound_cv_adapters as _inbound_cv_adapters
                media_meta = media if isinstance(media, dict) else {}
                request_metadata = request.metadata if isinstance(request.metadata, dict) else {}
                provider_message_id = str(
                    media_meta.get("message_id")
                    or media_meta.get("provider_message_id")
                    or request_metadata.get("message_id")
                    or row.get("pending_id")
                    or ""
                )
                company_code = str(
                    request_metadata.get("company_code")
                    or "WATHEFNI"
                ).strip().upper() or "WATHEFNI"
                _inbound_cv_adapters.adapt_whatsapp_unsolicited(
                    cur,
                    company_code=company_code,
                    provider_message_id=provider_message_id,
                    phone=phone,
                    account_id=request.account_id,
                    conversation_id=request.conversation_id,
                    pending_id=str(row.get("pending_id") or "") or None,
                    filename=str(media_meta.get("path") or "whatsapp-cv"),
                    mime_or_suffix=str(media_meta.get("type") or media_meta.get("mime_type") or ""),
                    needs_ocr=True,
                )
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT unified_inbound_cv_whatsapp_unsolicited")
            finally:
                cur.execute("RELEASE SAVEPOINT unified_inbound_cv_whatsapp_unsolicited")
        conn.commit()
    return json_safe(row)


def upsert_candidate_job_context'''
            text = text.replace(hold_return, hook, 1)
            actions.append("wa_unsolicited")

    if MARKERS["wa_job"] not in text:
        needle = '''    return {
        "ok": bool(storage_result.get("ok")),
        "app_key": app_key,
        "document_id": document_id,
        "storage": storage_result,
        "is_replacement": is_replacement,
    }


# --- Bulk CV import: shared import core -------------------------------------'''
        if needle in text:
            hook = '''    if received_ok and str(cv_json.get("source") or "").startswith("whatsapp"):
        cur.execute("SAVEPOINT unified_inbound_cv_whatsapp_job")
        try:
            import inbound_cv_adapters as _inbound_cv_adapters
            meta = metadata if isinstance(metadata, dict) else {}
            provider_message_id = str(
                meta.get("provider_message_id")
                or meta.get("message_id")
                or media.get("message_id")
                or f"{app_key}:{checksum}"
            )
            _inbound_cv_adapters.adapt_whatsapp_job(
                cur,
                company_code=company_code,
                provider_message_id=provider_message_id,
                phone=phone,
                account_id=str(meta.get("account_id") or "") or None,
                conversation_id=str(meta.get("conversation_id") or "") or None,
                pending_id=str(meta.get("pending_id") or "") or None,
                document_id=document_id,
                content_sha256=str(checksum or "") or None,
                filename=original_filename,
                app_key=app_key,
                apply_code=str(application.get("apply_code") or "") or None,
                human_confirmed=True,
                mime_or_suffix=str(mime_type or original_filename or ""),
                needs_ocr=False,
            )
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT unified_inbound_cv_whatsapp_job")
        finally:
            cur.execute("RELEASE SAVEPOINT unified_inbound_cv_whatsapp_job")
    return {
        "ok": bool(storage_result.get("ok")),
        "app_key": app_key,
        "document_id": document_id,
        "storage": storage_result,
        "is_replacement": is_replacement,
    }


# --- Bulk CV import: shared import core -------------------------------------'''
            text = text.replace(needle, hook, 1)
            actions.append("wa_job")

    if MARKERS["cv_version"] not in text and "talent_pool_auto_email_enqueue" in text:
        # Optional: only if auto-email block exists on staging.
        pass

    path.write_text(text, encoding="utf-8")
    return actions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("app_py", type=Path)
    args = parser.parse_args()
    actions = patch(args.app_py)
    print({"patched": args.app_py.as_posix(), "actions": actions})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
