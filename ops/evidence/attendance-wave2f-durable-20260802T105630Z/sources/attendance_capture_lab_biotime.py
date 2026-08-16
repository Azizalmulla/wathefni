#!/usr/bin/env python3
"""Attendance Wave 2C — lab BioTime HTTP fixture (synthetic identities only).

Serves /iclock/api/transactions/ for the production canary. Refuses to start if
any emp_code matches a real WATHEFNI employee phone/key fragment.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

FOUR_REAL_PHONES = frozenset({"96550252254", "96599411617", "96597727743", "96566363363"})
SYNTHETIC_EMP_RE = re.compile(r"^W2C\d{4,}$|^9\d{3,}$")  # lab device user ids only


def assert_synthetic_only(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        emp = str(row.get("emp_code") or "").strip()
        if not emp:
            raise SystemExit(f"lab fixture missing emp_code: {row}")
        if emp in FOUR_REAL_PHONES or emp.startswith("965502") or emp.startswith("965994") or emp.startswith("965977") or emp.startswith("965663"):
            raise SystemExit(f"REFUSE: lab fixture contains real-looking emp_code={emp}")
        # Soft allow W2C* / numeric lab ids used by canary
        if emp in {"1001", "9999"} or emp.startswith("W2C") or emp.isdigit():
            continue
        raise SystemExit(f"REFUSE: lab fixture emp_code not in synthetic allow pattern: {emp}")


class LabBioTimeState:
    def __init__(self, rows: list[dict[str, Any]], *, username: str, password: str, token: str) -> None:
        assert_synthetic_only(rows)
        self.rows = list(rows)
        self.username = username
        self.password = password
        self.token = token
        self.lock = threading.Lock()

    def list_page(self, page: int, limit: int) -> dict[str, Any]:
        with self.lock:
            start = (page - 1) * limit
            chunk = self.rows[start : start + limit]
            return {"count": len(self.rows), "next": None, "previous": None, "results": chunk}


def make_handler(state: LabBioTimeState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # quieter; never log auth headers
            return

        def _auth_ok(self) -> bool:
            auth = self.headers.get("Authorization") or ""
            if auth == f"Token {state.token}":
                return True
            if auth.startswith("Basic "):
                import base64

                try:
                    raw = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
                    user, pw = raw.split(":", 1)
                    return user == state.username and pw == state.password
                except Exception:  # noqa: BLE001
                    return False
            return False

        def _json(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") + "/"
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                data = {}
            if path.endswith("api-token-auth/") or path.endswith("jwt-api-token-auth/") or path.endswith("api/token/"):
                if data.get("username") == state.username and data.get("password") == state.password:
                    self._json(200, {"token": state.token})
                else:
                    self._json(401, {"detail": "auth_failed"})
                return
            self._json(404, {"detail": "not_found"})

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") + "/"
            if not self._auth_ok():
                self._json(401, {"detail": "auth_failed"})
                return
            if path.endswith("iclock/api/transactions/"):
                qs = parse_qs(parsed.query)
                page = int((qs.get("page") or ["1"])[0])
                limit = int((qs.get("limit") or ["50"])[0])
                self._json(200, state.list_page(page, limit))
                return
            self._json(404, {"detail": "not_found"})

    return Handler


def serve(host: str, port: int, state: LabBioTimeState) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def default_rows(device_user_id: str, terminal_sn: str) -> list[dict[str, Any]]:
    """Synthetic-only lab transactions used by the canary."""
    uid = device_user_id
    sn = terminal_sn
    return [
        {"id": 2101, "emp_code": uid, "punch_time": "2026-09-10 09:00:00", "punch_state": "0", "verify_type": 2, "terminal_sn": sn},
        {"id": 2102, "emp_code": uid, "punch_time": "2026-09-10 17:00:00", "punch_state": "1", "verify_type": 15, "terminal_sn": sn},
        {"id": 2201, "emp_code": uid, "punch_time": "2026-09-11 22:00:00", "punch_state": "0", "verify_type": 1, "terminal_sn": sn},
        {"id": 2202, "emp_code": uid, "punch_time": "2026-09-12 06:00:00", "punch_state": "1", "verify_type": 1, "terminal_sn": sn},
        # privacy poison row must be filtered by sanitizer when injected separately
    ]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=19199)
    ap.add_argument("--username", default="lab_synth")
    ap.add_argument("--password", default="lab_synth_only")
    ap.add_argument("--token", default="lab-token-synth-only")
    ap.add_argument("--emp", default="9001")
    ap.add_argument("--sn", default="LAB-W2C-SN")
    args = ap.parse_args()
    rows = default_rows(args.emp, args.sn)
    state = LabBioTimeState(rows, username=args.username, password=args.password, token=args.token)
    httpd = serve(args.host, args.port, state)
    print(json.dumps({"ok": True, "url": f"http://{args.host}:{args.port}/", "rows": len(rows), "emp_codes": sorted({r["emp_code"] for r in rows})}))
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        httpd.shutdown()
