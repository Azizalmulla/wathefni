#!/usr/bin/env python3
"""Surgical production patch: WATHEFNI WhatsApp-unsolicited + manual cutover hooks.

Does not cut over email or Job Stage B. Does not enable ENFORCE.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKERS = {
    "helper": "def _reply_after_unsolicited_cv_hold(",
    "hold_cutover": "UNIFIED_INTAKE_AUTHORITY_WHATSAPP_UNSOLICITED_CUTOVER",
    "manual_prescan": "UNIFIED_INTAKE_AUTHORITY_MANUAL_PRESCAN",
    "manual_cutover": "UNIFIED_INTAKE_AUTHORITY_MANUAL_CUTOVER",
    "no_app_reply": "UNIFIED_INTAKE_AUTHORITY_NO_APP_REPLY",
    "resolve_reply": "UNIFIED_INTAKE_AUTHORITY_RESOLVE_REPLY",
}

HELPER = '''
def _reply_after_unsolicited_cv_hold(request, held, *, default_error: str | None = None):
    """Prefer Talent Pool confirmation when WhatsApp unsolicited cutover accepted."""
    cut = (held or {}).get("channel_cutover") if isinstance(held, dict) else None
    if isinstance(cut, dict) and cut.get("ok") and cut.get("authoritative") and not cut.get("skipped"):
        return {
            "ok": True,
            "error": None,
            **candidate_message_result("cv_received_talent_pool", request=request),
            "pending_media": held,
            "application_created": False,
            "talent_pool": cut.get("talent_pool"),
            "channel_cutover": cut,
            "intent": "candidate_cv_talent_pool_received",
        }
    if isinstance(cut, dict) and cut.get("rejected"):
        return {
            "ok": False,
            "error": cut.get("error") or "cv_rejected",
            **candidate_message_result("cv_invalid", request=request),
            "pending_media": held,
            "application_created": False,
            "channel_cutover": cut,
        }
    payload = {
        "ok": True,
        "pending_media": held,
        "application_created": False,
    }
    if default_error:
        payload["error"] = default_error
    payload.update(candidate_message_result("cv_held_needs_role", request=request))
    return payload

'''

HOLD_CUTOVER = '''
            # UNIFIED_INTAKE_AUTHORITY_WHATSAPP_UNSOLICITED_CUTOVER
            try:
                import inbound_cv_channel_cutover as _inbound_cv_cutover
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
                if _inbound_cv_cutover.wa_unsolicited_authority_enabled(company_code):
                    cut = _inbound_cv_cutover.accept_whatsapp_unsolicited(
                        cur,
                        company_code=company_code,
                        phone=phone,
                        provider_message_id=provider_message_id,
                        account_id=request.account_id,
                        conversation_id=request.conversation_id,
                        pending_id=str(row.get("pending_id") or "") or None,
                        media_path=str(media_meta.get("path") or "") or None,
                        mime_or_suffix=str(media_meta.get("type") or media_meta.get("mime_type") or ""),
                        filename=str(media_meta.get("filename") or media_meta.get("path") or "whatsapp-cv"),
                    )
                    row["channel_cutover"] = cut
            except Exception as _cut_exc:
                row["channel_cutover"] = {
                    "ok": False,
                    "error": "cutover_exception",
                    "detail": str(_cut_exc)[:300],
                }
'''


def patch(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    actions: list[str] = []

    if MARKERS["helper"] not in text:
        anchor = "\ndef hold_candidate_pending_media(request: WhatsAppTurnRequest) -> dict[str, Any]:"
        if anchor not in text:
            raise SystemExit("hold_candidate_pending_media anchor missing")
        text = text.replace(anchor, "\n" + HELPER + anchor, 1)
        actions.append("helper")

    if MARKERS["hold_cutover"] not in text:
        # Insert after WAVE3 unsolicited adapter finally/release block, before commit.
        needle = (
            "                cur.execute(\"RELEASE SAVEPOINT unified_inbound_cv_whatsapp_unsolicited\")\n"
            "        conn.commit()\n"
            "    return json_safe(row)\n"
            "\n"
            "\n"
            "def upsert_candidate_job_context"
        )
        if needle not in text:
            raise SystemExit("hold cutover insert point missing")
        replacement = (
            "                cur.execute(\"RELEASE SAVEPOINT unified_inbound_cv_whatsapp_unsolicited\")\n"
            + HOLD_CUTOVER
            + "        conn.commit()\n"
            "    return json_safe(row)\n"
            "\n"
            "\n"
            "def upsert_candidate_job_context"
        )
        text = text.replace(needle, replacement, 1)
        actions.append("hold_cutover")

    # Reply: resolve failure path
    if MARKERS["resolve_reply"] not in text:
        old = '''            held = hold_candidate_pending_media(request)
            return {
                "ok": True,
                "error": error,
                **candidate_message_result("cv_held_needs_role", request=request),
                "matches": resolved.get("matches") or [],
                "pending_media": held,
                "application_created": False,
            }'''
        new = '''            held = hold_candidate_pending_media(request)
            # UNIFIED_INTAKE_AUTHORITY_RESOLVE_REPLY
            reply = _reply_after_unsolicited_cv_hold(request, held, default_error=error)
            reply["matches"] = resolved.get("matches") or []
            return reply'''
        if old not in text:
            raise SystemExit("resolve reply block missing")
        text = text.replace(old, new, 1)
        actions.append("resolve_reply")

    if MARKERS["no_app_reply"] not in text:
        old = '''    if not application:
        held = hold_candidate_pending_media(request)
        return {
            "ok": True,
            "error": "no_active_application",
            **candidate_message_result("cv_held_needs_role", request=request),
            "pending_media": held,
            "application_created": False,
        }'''
        new = '''    if not application:
        held = hold_candidate_pending_media(request)
        # UNIFIED_INTAKE_AUTHORITY_NO_APP_REPLY
        return _reply_after_unsolicited_cv_hold(
            request, held, default_error="no_active_application"
        )'''
        if old not in text:
            raise SystemExit("no_app reply block missing")
        text = text.replace(old, new, 1)
        actions.append("no_app_reply")

    # Manual: force held + pre-scan when cutover on
    if MARKERS["manual_prescan"] not in text:
        old = '''    if suffix not in IMPORT_CV_EXTENSIONS:
        item_record.update({"status": "failed", "error": f"unsupported_file_type:{suffix or 'unknown'}"})
        return item_record'''
        new = '''    if suffix not in IMPORT_CV_EXTENSIONS:
        item_record.update({"status": "failed", "error": f"unsupported_file_type:{suffix or 'unknown'}"})
        return item_record
    # UNIFIED_INTAKE_AUTHORITY_MANUAL_PRESCAN
    if str(source or "").strip().lower() not in {"email", "email_inbound"}:
        try:
            import inbound_cv_channel_cutover as _inbound_cv_cutover
            if _inbound_cv_cutover.manual_authority_enabled(company):
                auto_admit = False
                admit_reason = None
                pre = _inbound_cv_cutover.pre_scan_manual_bytes(
                    company_code=company,
                    batch_id=batch_id,
                    filename=Path(filename).name,
                    data=data,
                )
                if pre.get("rejected") or (not pre.get("ok") and not pre.get("skipped")):
                    item_record.update({
                        "status": "failed",
                        "error": pre.get("error") or "manual_cutover_rejected",
                        "scan": pre.get("scan"),
                    })
                    return item_record
                item_record["durable_path"] = pre.get("durable_path")
                item_record["scan"] = pre.get("scan")
        except Exception as _pre_exc:
            item_record.update({"status": "failed", "error": f"manual_prescan_failed:{_pre_exc}"})
            return item_record'''
        if old not in text:
            raise SystemExit("manual prescan insert point missing")
        text = text.replace(old, new, 1)
        actions.append("manual_prescan")

    if MARKERS["manual_cutover"] not in text:
        old = '''        # WAVE3 surgical: additive manual adapter dual-write
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
        new = '''        # WAVE3 surgical: additive manual adapter dual-write
        if str(source or "").strip().lower() not in {"email", "email_inbound"}:
            cur.execute("SAVEPOINT unified_inbound_cv_manual_adapter")
            try:
                import inbound_cv_channel_cutover as _inbound_cv_cutover
                if _inbound_cv_cutover.manual_authority_enabled(company):
                    # UNIFIED_INTAKE_AUTHORITY_MANUAL_CUTOVER (fail-closed)
                    cut = _inbound_cv_cutover.accept_manual_upload(
                        cur,
                        company_code=company,
                        batch_id=batch_id,
                        content_sha256=checksum,
                        filename=Path(filename).name,
                        document_id=str(result.get("document_id") or "") or None,
                        source_path=item_record.get("durable_path"),
                        mime_or_suffix=suffix or str(item_record.get("mime_type") or ""),
                        app_key=str(result.get("app_key") or "") or None,
                        held_status=str(result.get("status") or "") or None,
                        source=str(source or "manual_upload"),
                    )
                    item_record["channel_cutover"] = cut
                    if cut.get("rejected") or not cut.get("ok"):
                        raise RuntimeError(cut.get("error") or "manual_cutover_failed")
                else:
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
                if str(source or "").strip().lower() not in {"email", "email_inbound"}:
                    try:
                        import inbound_cv_channel_cutover as _inbound_cv_cutover
                        if _inbound_cv_cutover.manual_authority_enabled(company):
                            item_record.update({"status": "failed", "error": "manual_cutover_failed"})
                    except Exception:
                        pass
            finally:
                cur.execute("RELEASE SAVEPOINT unified_inbound_cv_manual_adapter")
'''
        if old not in text:
            raise SystemExit("manual cutover block missing")
        text = text.replace(old, new, 1)
        actions.append("manual_cutover")

    path.write_text(text, encoding="utf-8")
    return actions


def main() -> int:
    app_py = Path(sys.argv[1] if len(sys.argv) > 1 else "app.py")
    actions = patch(app_py)
    print(json.dumps({"ok": True, "path": str(app_py), "actions": actions}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
