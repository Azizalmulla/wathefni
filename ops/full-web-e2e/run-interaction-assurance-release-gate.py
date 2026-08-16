#!/usr/bin/env python3
"""Fail releases only on confirmed P0/P1 interaction regressions.

Unproven P1 and P2 residual rows are tracked by the Interaction Assurance
Program and do not fail this gate.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

DEFAULT_MATRIX = (
    Path(__file__).resolve().parents[1]
    / "evidence/full-interaction-dead-control-audit-20260805T195406Z/findings/interaction-control-matrix.json"
)

BLOCKING_STATUSES = {"broken", "dead", "permission mismatch"}
BLOCKING_SEVERITIES = {"P0", "P1"}


def main() -> int:
    matrix_path = Path(os.environ.get("INTERACTION_AUDIT_MATRIX") or DEFAULT_MATRIX)
    if not matrix_path.is_file():
        print(f"NO_MATRIX {matrix_path}")
        return 2

    rows = json.loads(matrix_path.read_text())
    if not isinstance(rows, list):
        print("INVALID_MATRIX: expected list")
        return 2

    blockers = [
        r
        for r in rows
        if str(r.get("severity") or "") in BLOCKING_SEVERITIES
        and str(r.get("status") or "").lower() in BLOCKING_STATUSES
    ]
    by_status = Counter(str(r.get("status")) for r in blockers)
    by_sev = Counter(str(r.get("severity")) for r in blockers)

    unproven_p1 = sum(
        1
        for r in rows
        if str(r.get("severity")) == "P1" and str(r.get("status") or "").lower() == "unproven"
    )
    p2_broken = sum(
        1
        for r in rows
        if str(r.get("severity")) == "P2" and str(r.get("status") or "").lower() == "broken"
    )

    report = {
        "matrix": str(matrix_path),
        "blocking_confirmed_p0_p1": len(blockers),
        "blocking_by_status": dict(by_status),
        "blocking_by_severity": dict(by_sev),
        "tracked_unproven_p1": unproven_p1,
        "tracked_p2_broken": p2_broken,
        "release_fail": len(blockers) > 0,
        "policy": "fail only on confirmed P0/P1 broken|dead|permission mismatch",
    }
    print(json.dumps(report, indent=2))

    if blockers:
        print("\nBLOCKERS (first 20):")
        for r in blockers[:20]:
            print(
                f"- [{r.get('severity')}] {r.get('status')} :: {r.get('screen')} :: {r.get('control')}"
            )
        return 1

    print("\nGO: no confirmed P0/P1 interaction regressions (residual register retained).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
