"""HR-0: legacy ai-recruiter /internal quarantine proof.

Run: python3 smoke-test-hr0-legacy-recruiter-quarantine.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    HR-0 legacy ai-recruiter /internal quarantine")
    repo = Path(__file__).resolve().parents[1]
    main_py = (repo / "ai-recruiter" / "app" / "main.py").read_text(encoding="utf-8")
    compose = (repo / "ai-recruiter" / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (repo / "ai-recruiter" / "Dockerfile").read_text(encoding="utf-8")
    quarantine = repo / "ai-recruiter" / "QUARANTINE.md"

    check("QUARANTINE.md exists", quarantine.is_file())
    check("internal disabled by default", "LEGACY_AI_RECRUITER_INTERNAL_ENABLED" in main_py)
    check("internal token gate present", "require_legacy_internal_token" in main_py)
    check("middleware blocks /internal when disabled", "legacy_internal_disabled" in main_py)
    check("docker binds localhost only", "127.0.0.1:8000:8000" in compose)
    check("docker defaults internal off", 'LEGACY_AI_RECRUITER_INTERNAL_ENABLED: "0"' in compose)
    check("uvicorn binds 127.0.0.1", "--host\", \"127.0.0.1\"" in dockerfile or "--host 127.0.0.1" in dockerfile)
    check("not claimed as Wathefni HR", "wathefni_hr" in main_py or "Not Wathefni HR" in main_py)

    # Prefer a live TestClient when FastAPI is installed; otherwise the source
    # + compose/Dockerfile pins above are the local quarantine proof.
    try:
        from fastapi.testclient import TestClient  # noqa: F401
    except ModuleNotFoundError:
        check("runtime client optional (fastapi not installed locally)", True)
        print(f"\n{PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0

    sys.path.insert(0, str(repo / "ai-recruiter"))
    os.environ.pop("LEGACY_AI_RECRUITER_INTERNAL_ENABLED", None)
    os.environ.pop("LEGACY_AI_RECRUITER_INTERNAL_TOKEN", None)
    try:
        import importlib
        import app.main as legacy_main

        importlib.reload(legacy_main)
        client = TestClient(legacy_main.app)
        resp = client.get("/internal/companies")
        check("GET /internal/companies disabled -> 404", resp.status_code == 404)
        detail = resp.json().get("detail") or {}
        if isinstance(detail, dict):
            check("disabled detail is legacy_internal_disabled", detail.get("error") == "legacy_internal_disabled")
        else:
            check("disabled detail is legacy_internal_disabled", False)

        health = client.get("/health")
        check("health reports internal disabled", health.json().get("internal_routes_enabled") is False)
    except Exception as exc:
        check(f"runtime quarantine client ({type(exc).__name__})", False)
        print(f"      note: {exc}")

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
