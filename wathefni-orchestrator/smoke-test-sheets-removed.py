#!/usr/bin/env python3
"""Regression guard: the Google Sheets sync/mirror layer must stay removed.

This is a static source-level check (no DB required). It fails loudly if any of
the deleted Sheets plumbing is reintroduced, so a future refactor cannot quietly
bring back the "Postgres writes then syncs Sheets" behavior we removed.
"""

import re
from pathlib import Path

import app

APP_SOURCE = Path(app.__file__).with_name("app.py").read_text(encoding="utf-8")
REGISTRY_SOURCE = Path(app.__file__).with_name("action_registry.py").read_text(encoding="utf-8")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    # 1) No Sheets sync helpers may exist as module attributes anymore.
    forbidden_attrs = [
        "replace_dashboard_tab_values",
        "_replace_dashboard_tab_values_blocking",
        "sheets_sync_mode",
        "ensure_dashboard_tab",
        "dashboard_sheet_id",
        "payroll_export_sheet_url",
        "workspace_tool_sheet_sync",
        "workspace_tool_sheet_sync_ok",
        "sync_employee_posthire",
    ]
    for name in forbidden_attrs:
        assert_true(
            not hasattr(app, name),
            f"deleted Sheets helper '{name}' must not be reachable on the app module",
        )

    # 2) No sync_*_sheet* helpers may be defined.
    sheet_syncers = re.findall(r"\bdef\s+(sync_\w*sheet\w*)\s*\(", APP_SOURCE)
    assert_true(
        not sheet_syncers,
        f"no sync_*_sheet* helpers may remain, found: {sorted(set(sheet_syncers))}",
    )

    # 3) run_gog_wathefni must never be invoked with the "sheets" subcommand.
    sheets_transport = re.findall(
        r"run_gog_wathefni\(\s*\[\s*[\"']sheets[\"']", APP_SOURCE
    )
    assert_true(
        not sheets_transport,
        "run_gog_wathefni must never be called with 'sheets' as the first arg",
    )

    # 4) No posthire mutation may reintroduce the sync-result keys.
    for source_name, source in (("app.py", APP_SOURCE), ("action_registry.py", REGISTRY_SOURCE)):
        for key in ("sheet_sync", "shift_sync", "attendance_sync"):
            assert_true(
                f'"{key}"' not in source and f"'{key}'" not in source,
                f"'{key}' must not appear in {source_name}",
            )

    # 5) No reply line may promise a Sheets update.
    assert_true(
        "sheet updated" not in APP_SOURCE.lower(),
        "no reply may claim a sheet was updated",
    )

    print("sheets-removed regression smoke tests passed")


if __name__ == "__main__":
    main()
