"""Single remaining Jobs permission expander.

Canonical grants are explicit jobs.* keys. Until older administrators are
migrated, settings.manage still implies Jobs mutations and prehire.read still
implies jobs.read. Frontend surfaces must not reimplement this mapping.
"""

from __future__ import annotations

from typing import Iterable

SETTINGS_MANAGE_COMPAT_JOBS = frozenset(
    {"jobs.create", "jobs.edit", "jobs.publish", "jobs.close"}
)


def expand_effective_jobs_permissions(permissions: Iterable[str] | None) -> set[str]:
    perms = {str(item).strip() for item in (permissions or []) if str(item).strip()}
    if "settings.manage" in perms or "*:*" in perms:
        perms.update(SETTINGS_MANAGE_COMPAT_JOBS)
    if "prehire.read" in perms or "*:*" in perms:
        perms.add("jobs.read")
    return perms
