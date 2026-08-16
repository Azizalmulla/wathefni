#!/usr/bin/env python3
"""Surgical Wave 4 gate hook for staging app.py (no full replace)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER = "UNIFIED_VERIFIED_JOB_BINDING_GATE_WAVE4"

PATCH = '''
    # UNIFIED_VERIFIED_JOB_BINDING_GATE_WAVE4
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

ANCHOR = '''    if str(application.get("status") or "") in HELD_IMPORT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "held_record_evaluation_forbidden",
                "message": "Talent Pool held records cannot be ranked or evaluated until linked to a Job.",
            },
        )
'''


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "app.py")
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        print(json.dumps({"ok": True, "skipped": True, "reason": "already_patched"}))
        return 0
    if ANCHOR not in text:
        print(json.dumps({"ok": False, "error": "anchor_not_found"}))
        return 1
    # Insert after held-status block (before generate_application_profile_evaluation)
    needle = ANCHOR
    idx = text.find(needle)
    insert_at = idx + len(needle)
    # Prefer placement immediately before generate_application_profile_evaluation if present nearby
    next_chunk = text[insert_at : insert_at + 200]
    if "generate_application_profile_evaluation" not in next_chunk:
        # still insert after held block
        pass
    updated = text[:insert_at] + PATCH + text[insert_at:]
    path.write_text(updated, encoding="utf-8")
    print(json.dumps({"ok": True, "skipped": False, "path": str(path), "marker": MARKER}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
