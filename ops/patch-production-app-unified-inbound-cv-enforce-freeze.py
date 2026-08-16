#!/usr/bin/env python3
"""Surgical production patches for final ENFORCE freeze.

1) Ranking gate uses a real DB cursor (binding lookup).
2) Ranking gate checks tenant-scoped ENFORCE.
Does not enable Role Profiles or external tenants.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER = "UNIFIED_VERIFIED_JOB_BINDING_GATE_WAVE4"
CURSOR_MARKER = "UNIFIED_VERIFIED_JOB_BINDING_GATE_CURSOR_V2"

OLD = '''    # UNIFIED_VERIFIED_JOB_BINDING_GATE_WAVE4
    try:
        import inbound_cv_wave4 as _inbound_cv_wave4
        import verified_job_binding_gate as _vjbg

        if _vjbg.gate_enabled():
            _gate = _inbound_cv_wave4.check_downstream_action(
                None,
                company_code=company,
                app_key=app_key,
                action="ranking",
                application=application,
            )
            if _vjbg.enforce_enabled() and not _gate.get("allowed", True):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "verified_job_binding_required",
                        "message": "Ranking requires a verified Job binding.",
                        "gate": _gate,
                    },
                )
    except HTTPException:
        raise
    except Exception:
        pass
'''

NEW = '''    # UNIFIED_VERIFIED_JOB_BINDING_GATE_WAVE4
    # UNIFIED_VERIFIED_JOB_BINDING_GATE_CURSOR_V2
    try:
        import inbound_cv_wave4 as _inbound_cv_wave4
        import verified_job_binding_gate as _vjbg

        if _vjbg.gate_enabled():
            with db_connect() as _gate_conn:
                with _gate_conn.cursor() as _gate_cur:
                    _gate = _inbound_cv_wave4.check_downstream_action(
                        _gate_cur,
                        company_code=company,
                        app_key=app_key,
                        action="ranking",
                        application=application,
                    )
            if _vjbg.enforce_enabled(company_code=company) and not _gate.get("allowed", True):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "verified_job_binding_required",
                        "message": "Ranking requires a verified Job binding.",
                        "gate": _gate,
                    },
                )
    except HTTPException:
        raise
    except Exception:
        pass
'''


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "app.py")
    text = path.read_text(encoding="utf-8")
    if CURSOR_MARKER in text:
        print(json.dumps({"ok": True, "skipped": True, "reason": "already_cursor_v2"}))
        return 0
    if OLD not in text:
        print(json.dumps({"ok": False, "error": "old_gate_block_missing"}))
        return 1
    path.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print(json.dumps({"ok": True, "path": str(path), "marker": CURSOR_MARKER}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
