#!/usr/bin/env python3
"""Surgical production app.py patch for Unified Inbound CV production-dark.

Applies Wave 3 adapter hooks + Wave 4 verified-binding gate (shadow-capable).
Does NOT replace app.py wholesale.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Reuse Wave 3 patcher logic inline so production does not depend on staging filename.
from importlib.util import module_from_spec, spec_from_file_location


WAVE4_MARKER = "UNIFIED_VERIFIED_JOB_BINDING_GATE_WAVE4"

WAVE4_PATCH = '''
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

WAVE4_ANCHOR = '''    if str(application.get("status") or "") in HELD_IMPORT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "held_record_evaluation_forbidden",
                "message": "Talent Pool held records cannot be ranked or evaluated until linked to a Job.",
            },
        )
'''


def _load_wave3_patcher(repo_ops: Path):
    path = repo_ops / "patch-staging-app-unified-inbound-cv-wave3.py"
    spec = spec_from_file_location("wave3_patcher", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_wave3_patcher:{path}")
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    app_py = Path(sys.argv[1] if len(sys.argv) > 1 else "app.py")
    ops_dir = Path(__file__).resolve().parent
    wave3 = _load_wave3_patcher(ops_dir)
    actions = wave3.patch(app_py)

    text = app_py.read_text(encoding="utf-8")
    if WAVE4_MARKER not in text:
        if WAVE4_ANCHOR not in text:
            print(json.dumps({"ok": False, "error": "wave4_anchor_not_found", "actions": actions}))
            return 1
        insert_at = text.find(WAVE4_ANCHOR) + len(WAVE4_ANCHOR)
        text = text[:insert_at] + WAVE4_PATCH + text[insert_at:]
        app_py.write_text(text, encoding="utf-8")
        actions.append("wave4_gate")
    else:
        actions.append("wave4_gate_already_present")

    print(json.dumps({"ok": True, "path": str(app_py), "actions": actions}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
