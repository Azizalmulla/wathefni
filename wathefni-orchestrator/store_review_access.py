"""Default-off, fixed-identity store reviewer access.

This adapter is deliberately outside normal customer authentication. It can only
resolve four server-configured identities in OCTOHR-STORE-REVIEW, then delegates
to the existing Employee or HR mobile session creators. No credential is stored
in Git, the database, or a mobile bundle.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

import operator_mobile
import security_rate_limit

REVIEW_COMPANY_CODE = "OCTOHR-STORE-REVIEW"
REVIEW_PRINCIPALS = frozenset({"employee", "hr"})
REVIEW_STORES = frozenset({"apple", "google"})
_ON = frozenset({"1", "true", "yes", "on", "enabled"})

# Valid PBKDF2 value used only to keep unknown-user verification timing close to
# known-user verification. It is not a usable reviewer credential.
_DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$180000$00000000000000000000000000000000$"
    "481f50a7dbf97d9df1710a10c0e1337d65cc61d7f7218cdeecff3970e20a6823"
)


class StoreReviewLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=512)
    platform: str | None = Field(default=None, max_length=32)


def enabled() -> bool:
    return (os.environ.get("OCTOHR_STORE_REVIEW_ACCESS_ENABLED") or "").strip().lower() in _ON


def _credentials_path() -> Path:
    raw = (os.environ.get("OCTOHR_STORE_REVIEW_CREDENTIALS_FILE") or "").strip()
    path = Path(raw)
    if not raw or not path.is_absolute():
        raise RuntimeError("review_credentials_not_configured")
    return path


def _load_credentials() -> list[dict[str, str]]:
    path = _credentials_path()
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RuntimeError("review_credentials_file_unsafe")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise RuntimeError("review_credentials_file_permissions")
    if info.st_uid not in {0, os.geteuid()}:
        raise RuntimeError("review_credentials_file_owner")
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if str(parsed.get("company_code") or "").strip().upper() != REVIEW_COMPANY_CODE:
        raise RuntimeError("review_credentials_wrong_tenant")
    rows = parsed.get("identities")
    if not isinstance(rows, list) or len(rows) != 4:
        raise RuntimeError("review_credentials_identity_count")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    for item in rows:
        row = item if isinstance(item, dict) else {}
        username = str(row.get("username") or "").strip().lower()
        principal = str(row.get("principal") or "").strip().lower()
        store = str(row.get("store") or "").strip().lower()
        subject_id = str(row.get("subject_id") or "").strip()
        password_hash = str(row.get("password_hash") or "").strip()
        if (
            not username
            or username in seen
            or principal not in REVIEW_PRINCIPALS
            or store not in REVIEW_STORES
            or (store, principal) in seen_pairs
            or not subject_id
            or not password_hash.startswith("pbkdf2_sha256$")
        ):
            raise RuntimeError("review_credentials_invalid_identity")
        seen.add(username)
        seen_pairs.add((store, principal))
        out.append(
            {
                "username": username,
                "principal": principal,
                "store": store,
                "subject_id": subject_id,
                "password_hash": password_hash,
            }
        )
    if seen_pairs != {(store, principal) for store in REVIEW_STORES for principal in REVIEW_PRINCIPALS}:
        raise RuntimeError("review_credentials_matrix_incomplete")
    return out


def _digest(value: str | None) -> str:
    return hashlib.sha256(str(value or "").strip().lower().encode("utf-8")).hexdigest()[:32]


def _audit(
    app_mod: Any,
    *,
    username: str,
    principal: str,
    source: str,
    result: str,
    store: str | None = None,
    error_code: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    safe = security_rate_limit.safe_detail(detail)
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO store_review_access_audit
                  (username_digest, requested_principal, store, result, error_code,
                   source_digest, company_code, detail)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    _digest(username),
                    principal,
                    store,
                    result,
                    error_code,
                    _digest(source),
                    REVIEW_COMPANY_CODE,
                    app_mod.Json(safe),
                ),
            )
        conn.commit()


def _generic_failure() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"error": "store_review_auth_failed", "message": "Access needs to be verified."},
    )


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": "store_review_access_unavailable", "message": "This sign-in method is unavailable."},
    )


def _service_error(code: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"error": code, "message": "Review access is temporarily unavailable."},
    )


def _http_error_code(exc: HTTPException) -> str:
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return str(detail.get("error") or f"http_{exc.status_code}")[:80]


def _identity(app_mod: Any, request: StoreReviewLoginRequest, principal: str, source: str) -> dict[str, str]:
    username = str(request.username or "").strip().lower()
    dimensions = {"source": source, "identity": f"{REVIEW_COMPANY_CODE}|{principal}|{username}"}
    route = f"/{'app' if principal == 'employee' else 'dashboard/mobile'}/auth/store-review-login"
    if not enabled():
        try:
            _audit(app_mod, username=username, principal=principal, source=source, result="denied", error_code="kill_switch_off")
        except Exception:
            pass
        raise _unavailable()
    security_rate_limit.guard(
        app_mod,
        "store_review_login",
        route=route,
        dimensions=dimensions,
        company_code=REVIEW_COMPANY_CODE,
    )
    try:
        _audit(app_mod, username=username, principal=principal, source=source, result="attempt")
    except Exception as exc:
        raise _service_error("store_review_audit_unavailable") from exc
    try:
        rows = _load_credentials()
    except Exception as exc:
        _audit(
            app_mod,
            username=username,
            principal=principal,
            source=source,
            result="error",
            error_code=str(exc)[:80],
        )
        raise _service_error("store_review_configuration_invalid") from exc
    row = next((item for item in rows if item["username"] == username), None)
    stored = row["password_hash"] if row else _DUMMY_PASSWORD_HASH
    password_ok = app_mod.dashboard_password_ok(request.password, stored)
    if not row or row["principal"] != principal or not password_ok:
        security_rate_limit.record_failure(
            app_mod,
            "store_review_login",
            route=route,
            dimensions=dimensions,
            company_code=REVIEW_COMPANY_CODE,
            denial_class="store_review_auth_failed",
        )
        _audit(
            app_mod,
            username=username,
            principal=principal,
            source=source,
            result="denied",
            store=(row or {}).get("store"),
            error_code="invalid_credentials",
        )
        raise _generic_failure()
    security_rate_limit.reset(app_mod, "store_review_login", dimensions=dimensions)
    return row


def _require_review_company(app_mod: Any) -> None:
    app_mod.require_active_company(REVIEW_COMPANY_CODE)


def register_store_review_routes(app_mod: Any) -> None:
    @app_mod.app.get("/auth/store-review-availability")
    def store_review_availability():
        # No identity or tenant discovery: this only controls whether the fixed
        # reviewer entry point is visible on unsigned mobile clients.
        return {"ok": True, "available": enabled()}

    @app_mod.app.post("/app/auth/store-review-login")
    def employee_store_review_login(body: StoreReviewLoginRequest, request: Request):
        source = security_rate_limit.client_source(request)
        row = _identity(app_mod, body, "employee", source)
        token: str | None = None
        try:
            _require_review_company(app_mod)
            if not app_mod.employee_app_enabled():
                raise RuntimeError("employee_app_disabled")
            employee = app_mod.find_employee_by_key(row["subject_id"], company_code=REVIEW_COMPANY_CODE)
            allowed, reason = app_mod._employee_app_runtime_access(employee)
            if not employee or not allowed:
                raise RuntimeError(reason or "employee_not_eligible")
            session = app_mod.create_employee_session(
                REVIEW_COMPANY_CODE,
                row["subject_id"],
                employee.get("phone"),
                platform=body.platform,
            )
            token = session["token"]
            _audit(
                app_mod,
                username=row["username"],
                principal="employee",
                source=source,
                result="success",
                store=row["store"],
                detail={"employee_key_digest": _digest(row["subject_id"])},
            )
            return app_mod.json_safe(
                {
                    "ok": True,
                    "token": session["token"],
                    "refresh_token": session["refresh_token"],
                    "expires_at": session["expires_at"],
                    "employee": app_mod.employee_app_public(employee, REVIEW_COMPANY_CODE),
                    "review_access": True,
                }
            )
        except HTTPException as exc:
            if token:
                app_mod.revoke_employee_session_token(token)
            try:
                _audit(
                    app_mod,
                    username=row["username"],
                    principal="employee",
                    source=source,
                    result="denied" if exc.status_code < 500 else "error",
                    store=row["store"],
                    error_code=_http_error_code(exc),
                )
            except Exception:
                pass
            raise
        except Exception as exc:
            if token:
                app_mod.revoke_employee_session_token(token)
            try:
                _audit(
                    app_mod,
                    username=row["username"],
                    principal="employee",
                    source=source,
                    result="error",
                    store=row["store"],
                    error_code=str(exc)[:80],
                )
            except Exception:
                pass
            raise _service_error("store_review_principal_unavailable") from exc

    @app_mod.app.post("/dashboard/mobile/auth/store-review-login")
    def hr_store_review_login(body: StoreReviewLoginRequest, request: Request):
        source = security_rate_limit.client_source(request)
        row = _identity(app_mod, body, "hr", source)
        access_token: str | None = None
        try:
            _require_review_company(app_mod)
            user = app_mod.dashboard_user_by_email(REVIEW_COMPANY_CODE, row["username"])
            if (
                not user
                or str(user.get("user_id") or "") != row["subject_id"]
                or app_mod.normalize_dashboard_user_status(user.get("status")) != "active"
            ):
                raise RuntimeError("hr_identity_unavailable")
            tokens = operator_mobile.create_operator_mobile_session(app_mod, user)
            access_token = tokens["access_token"]
            _audit(
                app_mod,
                username=row["username"],
                principal="hr",
                source=source,
                result="success",
                store=row["store"],
                detail={"user_id_digest": _digest(row["subject_id"])},
            )
            response = operator_mobile._auth_tokens_response(app_mod, user, tokens)
            response["review_access"] = True
            return response
        except HTTPException as exc:
            if access_token:
                operator_mobile.revoke_operator_mobile_access_token(
                    app_mod, access_token, reason="store_review_http_failure"
                )
            try:
                _audit(
                    app_mod,
                    username=row["username"],
                    principal="hr",
                    source=source,
                    result="denied" if exc.status_code < 500 else "error",
                    store=row["store"],
                    error_code=_http_error_code(exc),
                )
            except Exception:
                pass
            raise
        except Exception as exc:
            if access_token:
                operator_mobile.revoke_operator_mobile_access_token(
                    app_mod, access_token, reason="store_review_audit_failure"
                )
            try:
                _audit(
                    app_mod,
                    username=row["username"],
                    principal="hr",
                    source=source,
                    result="error",
                    store=row["store"],
                    error_code=str(exc)[:80],
                )
            except Exception:
                pass
            raise _service_error("store_review_principal_unavailable") from exc
