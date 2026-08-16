#!/usr/bin/env python3
"""Fail-closed HTTP stubs for unreleased Wave 4/6 product surfaces (R5A).

Until a module's R5 surface slice passes, requests to its reserved namespaces
return 404 / capability_not_released. They must not call domain libraries.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

import capability_readiness as _ready

_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def register_unreleased_capability_failclosed(app_mod: Any) -> None:
    app = getattr(app_mod, "app", app_mod)

    def _bind(capability_key: str, path: str):
        def handler(request: Request) -> None:
            _ = request
            raise HTTPException(status_code=404, detail=_ready.unavailable_http_detail(capability_key))

        safe = path.strip("/").replace("/", "_").replace("-", "_") or "root"
        handler.__name__ = f"r5a_unreleased_{capability_key}_{safe}"
        return handler

    def _bind_rest(capability_key: str, path: str):
        def handler(request: Request, rest: str) -> None:
            _ = request, rest
            raise HTTPException(status_code=404, detail=_ready.unavailable_http_detail(capability_key))

        safe = path.strip("/").replace("/", "_").replace("-", "_") or "root"
        handler.__name__ = f"r5a_unreleased_{capability_key}_{safe}_rest"
        return handler

    seen: set[str] = set()
    for capability_key, path in _ready.all_http_namespaces():
        if path in seen:
            continue
        seen.add(path)
        app.api_route(
            path,
            methods=list(_METHODS),
            include_in_schema=False,
            name=f"r5a_unreleased_{capability_key}_{path.strip('/').replace('/', '_')}",
        )(_bind(capability_key, path))
        app.api_route(
            f"{path}/{{rest:path}}",
            methods=list(_METHODS),
            include_in_schema=False,
            name=f"r5a_unreleased_{capability_key}_{path.strip('/').replace('/', '_')}_rest",
        )(_bind_rest(capability_key, path))
