#!/usr/bin/env python3
"""Fail-closed acceptance audit for the qualified classification UI artifact."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess

import psycopg2
from psycopg2.extras import RealDictCursor

EVIDENCE = pathlib.Path(os.environ["FINAL_UI_EVIDENCE"])
BACKUP = pathlib.Path(os.environ["FINAL_UI_BACKUP"])
STAGING = pathlib.Path("/opt/wathefni/staging/dashboard-dist")
PRODUCTION = pathlib.Path("/var/www/wathefni-dashboard")


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha(root: pathlib.Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(sha(path).encode())
        digest.update(b"  ")
        digest.update(str(path).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def database_url() -> str:
    values: dict[str, str] = {}
    for line in pathlib.Path("/root/.openclaw/secrets/postgres.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    return values["WATHEFNI_DATABASE_URL"]


manifest: list[dict[str, str | None]] = []
verified = True
asset_set = hashlib.sha256()
for line in EVIDENCE.joinpath("dashboard-dist.sha256").read_text().splitlines():
    expected, relative = line.split(None, 1)
    relative = relative.removeprefix("./")
    path = STAGING / relative
    actual = sha(path) if path.exists() else None
    verified = verified and actual == expected
    manifest.append({"path": relative, "expected_sha": expected, "actual_sha": actual})
    asset_set.update(relative.encode())
    asset_set.update(b"\0")
    asset_set.update(expected.encode())
    asset_set.update(b"\0")

app_source = EVIDENCE.joinpath("source/App.tsx").read_text()
filter_source = EVIDENCE.joinpath(
    "source/components/candidates/ClassificationFilters.tsx"
).read_text()
section_source = EVIDENCE.joinpath(
    "source/components/candidates/CandidateClassificationSection.tsx"
).read_text()
route_source = pathlib.Path(
    "/opt/wathefni/orchestrator/talent_pool_classification_routes.py"
).read_text()
backend_source = pathlib.Path("/opt/wathefni/orchestrator/app.py").read_text()
staging_javascript = "\n".join(
    path.read_text(errors="ignore") for path in STAGING.glob("assets/*.js")
)

load_start = app_source.find("const loadApplications")
load_window = app_source[load_start : load_start + 6000]
save_start = app_source.find("onSaveView={async")
save_window = app_source[save_start : save_start + 1500]
render_start = filter_source.find("return (")
rendered_filters = filter_source[render_start:]

checks = {
    "markers_present": all(
        marker in staging_javascript
        for marker in (
            "classification/feature",
            "classification-filter-bar",
            "classification-compact-chip",
            "candidate-classification-section",
        )
    ),
    "career_area_control": "careerArea:" in rendered_filters,
    "likely_role_control": "likelyRole:" in rendered_filters,
    "skill_control": "value.skill" in rendered_filters,
    "industry_control": "value.industry" in rendered_filters,
    "seniority_control": "value.seniority" in rendered_filters,
    "experience_band_control": "value.experienceBand" in rendered_filters,
    "confidence_state_control": (
        "value.confidence" in rendered_filters
        and "Needs review" in rendered_filters
        and "Unclassified" in rendered_filters
    ),
    "classification_filters_applied_to_query": "classificationFilters" in load_window,
    "classification_filters_saved": "classificationFilters" in save_window,
    "add_control": "runReview('add'" in section_source,
    "correct_control": "runReview('correct'" in section_source,
    "explicit_review_confirmation_ui": (
        "useConfirm" in section_source or "ConfirmDialog" in section_source
    ),
    "review_history_rendered": "section.history" in section_source,
    "current_stale_rendered": (
        "current" in section_source.lower() and "stale" in section_source.lower()
    ),
    "immutable_run_history_available": "ORDER BY created_at DESC LIMIT 1" not in route_source,
    "candidate_list_chip_projected": "classification_chip" in backend_source,
}

sidecars: dict[str, int] = {}
with psycopg2.connect(database_url(), cursor_factory=RealDictCursor) as conn:
    with conn.cursor() as cursor:
        for table in (
            "candidate_classification_runs",
            "candidate_classification_suggestions",
            "candidate_classification_review_events",
            "talent_pool_classification_jobs",
            "taxonomy_tenant_nodes",
        ):
            cursor.execute(f"SELECT count(*) AS count FROM {table}")
            sidecars[table] = int(cursor.fetchone()["count"])

source_manifest_sha = sha(EVIDENCE / "tpc-final-ui-source-manifest.sha256")
dist_manifest_sha = sha(EVIDENCE / "dashboard-dist.sha256")
candidate_composite = hashlib.sha256(
    (
        "40a4e2621f4818bf7c0f6ce3642032297bfbe7b2\n"
        f"{source_manifest_sha}\n"
        f"{dist_manifest_sha}\n"
        f"{asset_set.hexdigest()}\n"
    ).encode()
).hexdigest()

output = {
    "timestamp": subprocess.run(
        ["date", "-u", "+%FT%TZ"], capture_output=True, text=True, check=True
    ).stdout.strip(),
    "source_commit": "40a4e2621f4818bf7c0f6ce3642032297bfbe7b2",
    "source_manifest_sha": source_manifest_sha,
    "qualified_dist_manifest_sha": dist_manifest_sha,
    "qualified_asset_set_sha": asset_set.hexdigest(),
    "candidate_ui_composite_sha": candidate_composite,
    "staging_manifest_verified": verified,
    "staging_manifest": manifest,
    "staging_current_tree_sha_including_stale_asset": tree_sha(STAGING),
    "production_dashboard_tree_sha": tree_sha(PRODUCTION),
    "production_health": subprocess.run(
        [
            "curl",
            "-sf",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "http://127.0.0.1:8010/health",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout,
    "classification_conf": pathlib.Path(
        "/etc/systemd/system/wathefni-orchestrator.service.d/"
        "talent-pool-classification.conf"
    ).read_text(),
    "worker": subprocess.run(
        [
            "systemctl",
            "is-active",
            "wathefni-talent-pool-classification-worker.service",
        ],
        capture_output=True,
        text=True,
    ).stdout.strip(),
    "sidecars": sidecars,
    "backup": str(BACKUP),
    "backup_db_sha": sha(BACKUP / "db.dump"),
    "restore_entries": len(BACKUP.joinpath("db.restore-list").read_text().splitlines()),
    "rollback_sha": sha(BACKUP / "ROLLBACK.sh"),
    "artifact_acceptance_checks": checks,
    "qualification_blockers": [name for name, value in checks.items() if not value],
    "decision": "NO_GO_PREDEPLOY_ARTIFACT_INCOMPLETE",
    "production_dashboard_deployed": False,
}
EVIDENCE.joinpath("PREFLIGHT.json").write_text(json.dumps(output, indent=2))
print(json.dumps(output, indent=2))
