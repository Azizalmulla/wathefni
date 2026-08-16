"""R8 HTTP adapters — client error ingest + delivery snapshot. No new domain."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Request
from pydantic import BaseModel

import observability
import security_rate_limit as rl


def _r2_denial_hook(event: dict[str, Any]) -> None:
    observability.structured_log("warning", "security_denial", **event)


class ClientErrorBody(BaseModel):
    surface: str = "hr_web"
    message: str = "unspecified_client_error"
    name: str | None = None
    release: str | None = None


def register_observability_http(app_mod: Any) -> None:
    app = app_mod.app

    rl.register_telemetry_hook(_r2_denial_hook)

    def _ingest(body: ClientErrorBody, request: Request, *, surface: str) -> dict[str, Any]:
        rl.consume(
            app_mod,
            "client_error_report",
            route="/telemetry/client-error",
            dimensions={"source": rl.client_source(request)},
        )
        event = observability.record_error_event(
            app_mod,
            surface=surface,
            message=body.message,
            detail={"name": body.name, "release": body.release},
        )
        return {"ok": True, "event_id": event["event_id"], "stored": event["stored"]}

    @app.post("/telemetry/client-error")
    def telemetry_client_error(body: ClientErrorBody, request: Request):
        return _ingest(body, request, surface=body.surface)

    @app.post("/dashboard/telemetry/error")
    def dashboard_telemetry_error(body: ClientErrorBody, request: Request):
        surface = body.surface if body.surface in {"hr_web", "setup_console"} else "hr_web"
        return _ingest(body, request, surface=surface)

    @app.post("/dashboard/mobile/telemetry/error")
    def hr_mobile_telemetry_error(body: ClientErrorBody, request: Request):
        return _ingest(body, request, surface="hr_mobile")

    @app.post("/app/telemetry/error")
    def employee_telemetry_error(body: ClientErrorBody, request: Request):
        return _ingest(body, request, surface="employee_mobile")

    @app.get("/dashboard/ops/delivery")
    def dashboard_delivery_ops(context: dict[str, Any] = Depends(app_mod.dashboard_context)):
        if not app_mod.dashboard_context_has_permission(context, "settings.manage"):
            raise app_mod.HTTPException(
                status_code=403,
                detail={"error": "permission_denied", "message": "You do not have access to do that."},
            )
        snapshot = observability.delivery_snapshot(app_mod)
        return {"ok": True, **snapshot}

    @app.middleware("http")
    async def r8_unhandled_exception(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            if isinstance(exc, app_mod.HTTPException):
                raise
            observability.record_error_event(
                app_mod,
                surface="backend",
                message=type(exc).__name__,
                detail={"path": request.url.path},
            )
            raise
