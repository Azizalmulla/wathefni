"""HR Mobile Assistant — thin client of the Wathefni Assistant spine.

Endpoints under /dashboard/mobile/assistant/* reuse tool_call_orchestrator +
action_registry + capability catalog. Channel metadata is hr_mobile (not
web_dashboard spoofing). Never touches legacy ai-recruiter.
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from typing import Any

from fastapi import Request

try:
    from pydantic import BaseModel, Field

    class MobileAssistantChatBody(BaseModel):
        message: str = Field(..., min_length=1, max_length=8000)
        conversation_id: str | None = None
        locale: str | None = None
        confirm: bool | None = None

except Exception:  # pragma: no cover - unit hosts without pydantic
    MobileAssistantChatBody = None  # type: ignore[misc, assignment]


def assistant_mobile_offerable(app_mod: Any, context: dict[str, Any]) -> bool:
    """Same gate spirit as assistant_dashboard_context — modules + permissions."""
    company = str(context.get("company_code") or "").strip().upper()
    if not company:
        return False
    modules = set(app_mod.configured_company_modules(company) or set())
    offerable_modules = getattr(
        app_mod,
        "ASSISTANT_OFFERABLE_MODULES",
        frozenset(
            {
                "pre_hiring",
                "assessments",
                "interviews",
                "video_interviews",
                "employment_offers",
                "calendar",
                "leave",
                "attendance",
                "onboarding",
                "shifts",
                "payroll",
                "compliance",
                "analytics",
            }
        ),
    )
    if not (modules & set(offerable_modules)):
        return False
    perms = (
        set(app_mod.context_permissions(context))
        if hasattr(app_mod, "context_permissions")
        else {str(p) for p in (context.get("permissions") or []) if str(p).strip()}
    )
    offerable_perms = getattr(
        app_mod,
        "ASSISTANT_OFFERABLE_PERMISSIONS",
        frozenset({"prehire.read", "leave.read", "attendance.read", "employees.read", "*:*"}),
    )
    return bool(perms & set(offerable_perms))


def _require_assistant_access(app_mod: Any, context: dict[str, Any]) -> None:
    from fastapi import HTTPException

    if not assistant_mobile_offerable(app_mod, context):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "assistant_unavailable",
                "message": "OctoHR Assistant is not available for this company or account.",
            },
        )


def _mobile_conversation_id(context: dict[str, Any], conversation_id: str | None) -> str:
    import re

    raw = str(conversation_id or "").strip()
    if raw:
        return re.sub(r"[^a-zA-Z0-9_.:@-]+", "_", raw)[:180]
    company = str(context.get("company_code") or "UNKNOWN").upper()
    actor = str(context.get("actor_user_id") or "mobile").strip() or "mobile"
    return f"mobile:{company}:{actor}:assistant:{uuid.uuid4().hex[:12]}"


def _run_mobile_assistant_turn(
    app_mod: Any,
    context: dict[str, Any],
    *,
    message: str,
    conversation_id: str,
    locale: str,
    on_progress: Any | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    from tool_call_orchestrator import handle_toolcall_whatsapp_turn

    company = str(context.get("company_code") or "").upper()
    hr_phone = app_mod.digits(context.get("hr_phone")) or app_mod.digits(
        (context.get("hr_user") or {}).get("phone")
    ) or "mobile"
    text = str(message or "").strip()
    # Conservative confirm: user tapped Confirm → send affirmative so pending token resumes.
    if text.lower() in {"__confirm__", "__confirm_yes__"}:
        text = "نعم" if locale == "ar" else "yes"

    class _Req:
        pass

    # Minimal request shape matching DashboardChatRequest fields used by artifacts.
    dash_req = _Req()
    dash_req.message = text
    dash_req.conversation_id = conversation_id
    dash_req.page = "mobile_assistant"
    dash_req.selected_app_key = None
    dash_req.locale = locale

    turn_request = app_mod.WhatsAppTurnRequest(
        account_id="default",
        conversation_id=conversation_id,
        sender_phone=hr_phone,
        sender_role="hr_admin",
        raw_text=text,
        metadata={
            "channel": "hr_mobile",
            "dashboard": False,
            "mobile": True,
            "company_code": company,
            "page": "mobile_assistant",
            "admin_user": context.get("hr_user") if isinstance(context.get("hr_user"), dict) else {},
            "access": context.get("access") if isinstance(context.get("access"), dict) else {},
            "permissions": context.get("permissions") or [],
            "assistant_entry": "toolcall_orchestrator",
            "legacy_regex_inference_enabled": False,
            "legacy_path_inactive": True,
            "locale": locale,
            "on_progress": on_progress,
            "cancel_event": cancel_event,
            "actor_user_id": context.get("actor_user_id"),
        },
    )
    result = handle_toolcall_whatsapp_turn(turn_request)
    artifacts = app_mod.dashboard_chat_artifacts(result, dash_req, company_code=company)
    audit = result.get("audit") if isinstance(result.get("audit"), dict) else {}
    return {
        "ok": True,
        "reply_text": str(result.get("reply_text") or ""),
        "intent": result.get("intent"),
        "turn_id": str(audit.get("turn_id") or ""),
        "conversation_id": conversation_id,
        "candidate_cards": artifacts.get("candidate_cards") or [],
        "navigation": artifacts.get("navigation") or [],
        "confirmation": artifacts.get("confirmation"),
        "workflow_card": artifacts.get("workflow_card"),
        "audit": {
            "turn_id": audit.get("turn_id"),
            "capability_offerable": (audit.get("capability_catalog") or {}).get("offerable")
            if isinstance(audit.get("capability_catalog"), dict)
            else None,
        },
        "channel": "hr_mobile",
    }


def register_mobile_assistant_routes(app_mod: Any, *, operator_mobile_context: Any) -> None:
    from fastapi import Depends, HTTPException
    from fastapi.responses import StreamingResponse

    if MobileAssistantChatBody is None:
        raise RuntimeError("MobileAssistantChatBody requires pydantic")

    @app_mod.app.get("/dashboard/mobile/assistant/capabilities")
    def mobile_assistant_capabilities(
        locale: str = "en",
        context: dict[str, Any] = Depends(operator_mobile_context),
    ):
        _require_assistant_access(app_mod, context)
        from tool_call_orchestrator import build_dashboard_assistant_capabilities

        loc = "ar" if str(locale or "").lower().startswith("ar") else "en"
        payload = build_dashboard_assistant_capabilities(
            company_code=str(context.get("company_code") or ""),
            permissions=context.get("permissions") or [],
            locale=loc,
            admin_user=context.get("hr_user") if isinstance(context.get("hr_user"), dict) else {},
            access=context.get("access") if isinstance(context.get("access"), dict) else {},
        )
        # Honesty: mobile never offers web-only spine deep links as executable chips
        # without a mobile destination — client filters further via destinationAvailable.
        payload["surface"] = "hr_mobile"
        payload["unsupported_messaging"] = ["sms", "telegram", "teams_chat", "push_send"]
        return app_mod.json_safe(payload)

    @app_mod.app.post("/dashboard/mobile/assistant/chat", response_model=None)
    def mobile_assistant_chat(
        body: MobileAssistantChatBody,
        context: dict[str, Any] = Depends(operator_mobile_context),
    ):
        _require_assistant_access(app_mod, context)
        app_mod.ensure_schema()
        locale = "ar" if str(body.locale or "").lower().startswith("ar") else "en"
        conversation_id = _mobile_conversation_id(context, body.conversation_id)
        message = str(body.message or "").strip()
        if body.confirm:
            message = "__confirm__"
        if not message:
            raise HTTPException(status_code=422, detail={"error": "message_required"})
        try:
            return app_mod.json_safe(
                _run_mobile_assistant_turn(
                    app_mod,
                    context,
                    message=message,
                    conversation_id=conversation_id,
                    locale=locale,
                )
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"error": "assistant_chat_failed", "message": str(exc)[:400]},
            ) from exc

    @app_mod.app.post("/dashboard/mobile/assistant/chat/stream", response_model=None)
    def mobile_assistant_chat_stream(
        body: MobileAssistantChatBody,
        http_request: Request,
        context: dict[str, Any] = Depends(operator_mobile_context),
    ):
        _require_assistant_access(app_mod, context)
        app_mod.ensure_schema()
        locale = "ar" if str(body.locale or "").lower().startswith("ar") else "en"
        conversation_id = _mobile_conversation_id(context, body.conversation_id)
        message = str(body.message or "").strip()
        if body.confirm:
            message = "__confirm__"
        if not message:
            raise HTTPException(status_code=422, detail={"error": "message_required"})

        progress_q: queue.Queue = queue.Queue()
        cancel_event = threading.Event()
        done_holder: dict[str, Any] = {}

        def on_progress(event: dict[str, Any]) -> None:
            progress_q.put(event)

        def worker() -> None:
            try:
                done_holder["payload"] = _run_mobile_assistant_turn(
                    app_mod,
                    context,
                    message=message,
                    conversation_id=conversation_id,
                    locale=locale,
                    on_progress=on_progress,
                    cancel_event=cancel_event,
                )
            except Exception as exc:
                done_holder["error"] = str(exc)[:400]
            finally:
                progress_q.put({"type": "__done__"})

        threading.Thread(target=worker, daemon=True).start()

        def event_stream():
            yield app_mod.dashboard_chat_stream_event(
                {"type": "typing", "conversation_id": conversation_id}
            )
            while True:
                if getattr(http_request, "is_disconnected", None):
                    pass
                try:
                    event = progress_q.get(timeout=0.5)
                except queue.Empty:
                    if cancel_event.is_set():
                        break
                    continue
                if event.get("type") == "__done__":
                    break
                yield app_mod.dashboard_chat_stream_event(app_mod.json_safe(event))
            if done_holder.get("error"):
                yield app_mod.dashboard_chat_stream_event(
                    {"type": "error", "message": done_holder["error"]}
                )
            else:
                payload = done_holder.get("payload") or {}
                text = str(payload.get("reply_text") or "")
                # Progressive reply deltas for mobile UX (same final text; chunked delivery).
                for chunk in _reply_stream_chunks(text, words_per_chunk=2):
                    yield app_mod.dashboard_chat_stream_event({"type": "delta", "text": chunk})
                    time.sleep(0.032)
                yield app_mod.dashboard_chat_stream_event({"type": "done", "message": payload})

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )


def _reply_stream_chunks(text: str, *, words_per_chunk: int = 2) -> list[str]:
    """Split final reply into small deltas so the mobile client can paint progressively.

    Does not invent wording — only chunks the completed spine reply_text.
    """
    raw = str(text or "")
    if not raw:
        return []
    parts = raw.split(" ")
    if len(parts) <= 1:
        size = 18
        return [raw[i : i + size] for i in range(0, len(raw), size)]
    chunks: list[str] = []
    buf: list[str] = []
    for index, word in enumerate(parts):
        buf.append(word)
        last = index == len(parts) - 1
        if len(buf) >= max(1, words_per_chunk) or last:
            piece = " ".join(buf)
            if not last:
                piece += " "
            chunks.append(piece)
            buf = []
    return chunks
