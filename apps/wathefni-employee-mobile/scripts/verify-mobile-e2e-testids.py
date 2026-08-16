#!/usr/bin/env python3
"""Static proof that Maestro e2e testIDs remain wired in the unified app."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "src/principals/UnifiedSignInView.tsx": [
        "e2e.auth.methodSwitch",
        "e2e.auth.method.phone",
        "e2e.auth.method.workEmail",
        "e2e.auth.hr.company",
        "e2e.auth.hr.email",
        "e2e.auth.hr.password",
        "e2e.auth.hr.signIn",
    ],
    "src/features/activation/ActivationView.tsx": [
        "e2e.auth.employee.phone",
        "e2e.auth.employee.code",
        "e2e.auth.employee.signIn",
        "e2e.auth.employee.requestCode",
    ],
    "app/(tabs)/_layout.tsx": [
        "e2e.tab.employee.home",
        "e2e.tab.employee.schedule",
        "e2e.tab.employee.leave",
        "e2e.tab.employee.payslips",
        "e2e.tab.employee.profile",
    ],
    "app/hr/(tabs)/_layout.tsx": [
        "e2e.tab.hr.home",
        "e2e.tab.hr.people",
        "e2e.tab.hr.inbox",
        "e2e.tab.hr.hiring",
        "e2e.tab.hr.more",
    ],
    "src/hr/features/leave/LeaveApprovalView.tsx": [
        "e2e.hr.leave.approve",
        "e2e.hr.leave.reject",
        "e2e.hr.leave.rejectReason",
    ],
    "src/hr/components/primitives.tsx": [
        "e2e.confirm.sheet",
        "e2e.confirm.submit",
    ],
    "src/features/pin/PinView.tsx": [
        "e2e.pin.root",
        "e2e.pin.input",
        "e2e.pin.continue",
    ],
    "src/features/pin/BiometricOptInView.tsx": [
        "e2e.biometric.optIn",
        "e2e.biometric.notNow",
    ],
    "src/components/premium.tsx": [
        "testID?: string",
        "testID={testID}",
    ],
}

FLOWS = [
    ".maestro/smoke/00-unsigned-entry.yaml",
    ".maestro/smoke/01-hr-login.yaml",
    ".maestro/smoke/02-hr-tabs.yaml",
    ".maestro/smoke/03-employee-activation.yaml",
    ".maestro/smoke/04-employee-tabs.yaml",
    ".maestro/smoke/05-method-switch-en.yaml",
]


def main() -> int:
    failed = 0
    for rel, needles in REQUIRED.items():
        path = ROOT / rel
        text = path.read_text() if path.exists() else ""
        for needle in needles:
            ok = needle in text
            print(f"{'PASS' if ok else 'FAIL'}\t{rel}\t{needle}")
            if not ok:
                failed += 1
    for rel in FLOWS:
        path = ROOT / rel
        ok = path.is_file()
        print(f"{'PASS' if ok else 'FAIL'}\t{rel}\texists")
        if not ok:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
