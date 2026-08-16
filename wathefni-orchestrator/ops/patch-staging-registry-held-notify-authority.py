#!/usr/bin/env python3
"""Surgical held-communication authority patch for staging action_registry.py.

Preserves staging-specific APIs (e.g. clarify_first) while adding fail-closed
communication gates for Assistant/tool and bulk surfaces.
"""
from __future__ import annotations

import pathlib
import sys

MARKER = "HELD_COMMUNICATION_AUTHORITY_STAGING_PATCH"

HELPERS = f'''
COMMUNICATION_ACTION_KINDS = {{
    "notify_candidate": "notify",
    "send_email": "email",
    "send_assessment": "assessment",
    "send_screening_questions": "screening",
    "send_interview_invite": "interview_invite",
    "send_video_interview": "video_interview",
    "schedule_interview": "calendar_invite",
}}


def _communication_denied_result(action_type: str, decision_or_exc: Any, *, app: dict[str, Any] | None = None, legacy: Any = None) -> dict[str, Any]:
    if isinstance(decision_or_exc, _candidate_communication_authority.CandidateCommunicationAuthorityError):
        payload = decision_or_exc.as_result()
    elif isinstance(decision_or_exc, dict):
        payload = {{
            "ok": False,
            "success": False,
            "status": "failed",
            "error": decision_or_exc.get("code"),
            "error_code": decision_or_exc.get("code"),
            "reason": decision_or_exc.get("reason"),
            "message": decision_or_exc.get("message"),
            "safe_user_message": decision_or_exc.get("message"),
        }}
    else:
        payload = {{
            "ok": False,
            "success": False,
            "status": "failed",
            "error": "candidate_communication_forbidden",
            "message": "Candidate communication is not allowed for this application.",
        }}
    out = {{
        "action_type": action_type,
        **payload,
        "success": False,
        "status": "failed",
    }}
    if app is not None and legacy is not None and hasattr(legacy, "json_safe"):
        out["application"] = legacy.json_safe(app)
        out["result"] = legacy.json_safe(payload)
    return out


def _assert_app_communication(ctx: ExecutionContext, app: dict[str, Any], *, action_type: str) -> dict[str, Any] | None:
    """Return a failed ActionResult when communication is forbidden; else None."""
    kind = COMMUNICATION_ACTION_KINDS.get(action_type, "assistant")
    try:
        if hasattr(ctx.legacy, "assert_application_communication_allowed"):
            ctx.legacy.assert_application_communication_allowed(app, kind=kind)
        else:
            _candidate_communication_authority.assert_candidate_communication_allowed(app, kind=kind)
    except _candidate_communication_authority.CandidateCommunicationAuthorityError as exc:
        return _communication_denied_result(action_type, exc, app=app, legacy=ctx.legacy)
    return None  # {MARKER}


def _is_live_for_batch_communication(legacy: Any, app: dict[str, Any], *, action_type: str) -> dict[str, Any]:
    kind = COMMUNICATION_ACTION_KINDS.get(action_type, "bulk")
    if hasattr(legacy, "evaluate_application_communication_authority"):
        return legacy.evaluate_application_communication_authority(app, kind=kind)
    return _candidate_communication_authority.evaluate_candidate_communication_authority(app, kind=kind)

'''


def _replace_once(src: str, old: str, new: str, label: str) -> str:
    if new in src and MARKER in new:
        return src
    if old not in src:
        raise RuntimeError(f"anchor missing for {label}")
    return src.replace(old, new, 1)


def patch(src: str) -> str:
    if "import candidate_communication_authority as _candidate_communication_authority" not in src:
        src = _replace_once(
            src,
            "from typing import Any, Callable, Optional, Union\n\nlogger = logging.getLogger",
            "from typing import Any, Callable, Optional, Union\n\n"
            "import candidate_communication_authority as _candidate_communication_authority  # "
            + MARKER
            + "\n\nlogger = logging.getLogger",
            "import",
        )

    if "def _assert_app_communication(" not in src:
        anchor = "def _resolve_app(ctx: ExecutionContext) -> dict[str, Any] | None:\n    return ctx.legacy.resolve_application_for_action(ctx.action, allow_latest=False)\n"
        if anchor not in src:
            raise RuntimeError("resolve_app anchor missing")
        src = src.replace(anchor, anchor + "\n" + HELPERS, 1)

    if "BATCH_COMMUNICATION_ACTIONS" not in src:
        src = _replace_once(
            src,
            'BATCH_ALLOWED_ACTIONS = {\n    "send_video_interview",\n    "send_assessment",\n    "send_screening_questions",\n    "send_interview_invite",\n    "notify_candidate",\n    "send_email",\n    "shortlist_candidate",\n}\nBATCH_MAX_ITEMS = 20\n',
            'BATCH_ALLOWED_ACTIONS = {\n    "send_video_interview",\n    "send_assessment",\n    "send_screening_questions",\n    "send_interview_invite",\n    "notify_candidate",\n    "send_email",\n    "shortlist_candidate",\n}\n'
            "BATCH_COMMUNICATION_ACTIONS = {\n"
            '    "send_video_interview",\n'
            '    "send_assessment",\n'
            '    "send_screening_questions",\n'
            '    "send_interview_invite",\n'
            '    "notify_candidate",\n'
            '    "send_email",\n'
            "}\n"
            "BATCH_MAX_ITEMS = 20\n",
            "BATCH_COMMUNICATION_ACTIONS",
        )

    executor_gates = [
        ("send_email", 'return _candidate_not_found_result("send_email", "email")\n'),
        ("notify_candidate", 'return _candidate_not_found_result("notify_candidate", "notify")\n'),
        ("send_assessment", 'return _candidate_not_found_result("send_assessment", "send an assessment to")\n'),
        ("send_screening_questions", 'return _candidate_not_found_result("send_screening_questions", "send screening questions to")\n'),
        ("send_video_interview", 'return _candidate_not_found_result("send_video_interview", "send an AI video interview to")\n'),
        ("schedule_interview", 'return _candidate_not_found_result("schedule_interview", "schedule")\n'),
        ("send_interview_invite", 'return _candidate_not_found_result("send_interview_invite", "send an interview invite to")\n'),
    ]
    for action_type, not_found in executor_gates:
        gate = (
            f"{not_found}"
            f"    denied = _assert_app_communication(ctx, app, action_type=\"{action_type}\")  # {MARKER}\n"
            f"    if denied:\n"
            f"        return denied\n"
        )
        if f'action_type="{action_type}")  # {MARKER}' not in src:
            src = _replace_once(src, not_found, gate, f"gate:{action_type}")

    # Batch preflight: exclude held rows from communication batches
    old_preflight = """    resolved = _resolve_batch_candidates(ctx)
    candidates = resolved["candidates"]
    if not candidates:
        return {
            "action_type": "execute_candidate_batch",
            "success": False,
            "status": "needs_clarification",
            "needs_clarification": True,
            "missing_fields": ["candidate_selection"],
            "message": "I could not resolve candidates for this batch. Ask for exact names, app keys, or run a candidate ranking first.",
            "resolution_errors": resolved["errors"],
        }
"""
    new_preflight = f"""    resolved = _resolve_batch_candidates(ctx)
    candidates = resolved["candidates"]
    excluded_held: list[dict[str, Any]] = []
    if batch_action in BATCH_COMMUNICATION_ACTIONS:
        live_candidates: list[dict[str, Any]] = []
        for app in candidates:
            decision = _is_live_for_batch_communication(ctx.legacy, app, action_type=batch_action)
            if decision.get("allowed"):
                live_candidates.append(app)
            else:
                excluded_held.append(
                    {{
                        "app_key": app.get("app_key"),
                        "candidate_name": app.get("candidate_name"),
                        "error": decision.get("code"),
                        "reason": decision.get("reason"),
                        "message": decision.get("message"),
                    }}
                )
        candidates = live_candidates
    if not candidates:
        if excluded_held:
            return {{
                "action_type": "execute_candidate_batch",
                "success": False,
                "status": "failed",
                "error": "held_record_communication_forbidden",
                "message": (
                    "None of the selected candidates are live Job applications. "
                    "Talent Pool held or restricted records cannot receive outreach."
                ),
                "excluded_held": excluded_held,
            }}
        return {{
            "action_type": "execute_candidate_batch",
            "success": False,
            "status": "needs_clarification",
            "needs_clarification": True,
            "missing_fields": ["candidate_selection"],
            "message": "I could not resolve candidates for this batch. Ask for exact names, app keys, or run a candidate ranking first.",
            "resolution_errors": resolved["errors"],
        }}
"""
    if "excluded_held: list[dict[str, Any]] = []" not in src:
        src = _replace_once(src, old_preflight, new_preflight, "batch_preflight")

    ready_old = (
        '        "status": "ready",\n'
        '        "batch_action_type": batch_action,\n'
        '        "company_code": resolved["company_code"],\n'
        '        "candidate_count": len(labels),\n'
        '        "candidates": labels,\n'
        '        "resolution_errors": resolved["errors"],\n'
    )
    ready_new = (
        '        "status": "ready",\n'
        '        "batch_action_type": batch_action,\n'
        '        "company_code": resolved["company_code"],\n'
        '        "candidate_count": len(labels),\n'
        '        "candidates": labels,\n'
        '        "excluded_held": excluded_held,  # '
        + MARKER
        + "\n"
        '        "resolution_errors": resolved["errors"],\n'
    )
    if '        "excluded_held": excluded_held,  # ' + MARKER not in src:
        src = _replace_once(src, ready_old, ready_new, "preflight_excluded_held_field")

    # Batch executor: re-filter held before execution
    old_exec = """    batch_action = str(preflight.get("batch_action_type") or "")
    resolved = _resolve_batch_candidates(ctx)
    apps = resolved["candidates"]
    batch_id = _insert_batch_action(ctx, {**preflight, "candidate_count": len(apps)})
"""
    new_exec = f"""    batch_action = str(preflight.get("batch_action_type") or "")
    resolved = _resolve_batch_candidates(ctx)
    apps = resolved["candidates"]
    excluded_held = list(preflight.get("excluded_held") or [])
    if batch_action in BATCH_COMMUNICATION_ACTIONS:
        live_apps: list[dict[str, Any]] = []
        for app in apps:
            decision = _is_live_for_batch_communication(legacy, app, action_type=batch_action)
            if decision.get("allowed"):
                live_apps.append(app)
            else:
                excluded_held.append(
                    {{
                        "app_key": app.get("app_key"),
                        "candidate_name": app.get("candidate_name"),
                        "error": decision.get("code"),
                        "reason": decision.get("reason"),
                        "message": decision.get("message"),
                    }}
                )
        apps = live_apps
    if not apps:
        return {{
            "action_type": "execute_candidate_batch",
            "success": False,
            "status": "failed",
            "error": "held_record_communication_forbidden",
            "message": "No live Job applications remained after excluding held/restricted records.",
            "excluded_held": excluded_held,
        }}
    batch_id = _insert_batch_action(ctx, {{**preflight, "candidate_count": len(apps)}})  # {MARKER}
"""
    if "No live Job applications remained after excluding held/restricted records." not in src:
        src = _replace_once(src, old_exec, new_exec, "batch_executor")

    # Mixed batch: skip held communication items
    old_mixed = """        if resolution.get("status") == "resolved" and matches:
            app = matches[0]
            items.append(
                {
                    "index": index,
                    "action_type": action_type,
                    "app": app,
                    "candidate": _candidate_summary_for_batch(legacy, app),
                    "item_args": {key: value for key, value in item.items() if value not in (None, "", [], {})},
                }
            )
"""
    new_mixed = f"""        if resolution.get("status") == "resolved" and matches:
            app = matches[0]
            if action_type in BATCH_COMMUNICATION_ACTIONS:
                decision = _is_live_for_batch_communication(legacy, app, action_type=action_type)
                if not decision.get("allowed"):
                    errors.append(
                        {{
                            "index": index,
                            "error": decision.get("code") or "held_record_communication_forbidden",
                            "reason": decision.get("reason"),
                            "action_type": action_type,
                            "app_key": app.get("app_key"),
                            "message": decision.get("message"),
                        }}
                    )
                    continue  # {MARKER}
            items.append(
                {{
                    "index": index,
                    "action_type": action_type,
                    "app": app,
                    "candidate": _candidate_summary_for_batch(legacy, app),
                    "item_args": {{key: value for key, value in item.items() if value not in (None, "", [], {{}})}},
                }}
            )
"""
    if "held_record_communication_forbidden" not in src or "action_type in BATCH_COMMUNICATION_ACTIONS" not in src.split("_resolve_mixed_batch_items")[1][:2500]:
        # safer: only replace if marker not already in mixed section
        if f"continue  # {MARKER}" not in src:
            src = _replace_once(src, old_mixed, new_mixed, "mixed_batch")

    if MARKER not in src:
        raise RuntimeError("registry held authority patch failed")
    return src


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: patch-staging-registry-held-notify-authority.py <in> <out>", file=sys.stderr)
        return 2
    inp, outp = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    patched = patch(inp.read_text(encoding="utf-8"))
    import ast

    ast.parse(patched)
    outp.write_text(patched, encoding="utf-8")
    print(f"patched {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
