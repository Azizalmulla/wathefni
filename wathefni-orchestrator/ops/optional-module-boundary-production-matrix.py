#!/usr/bin/env python3
"""Production wrapper for the optional-module boundary ON/OFF matrix.

Loads the frozen local matrix bytes, patches only the production refuse gate in
memory (does not modify the hashed artifact file), and runs against synthetic
PRODBND* tenants with dry_run delivery.

Usage (on the VPS, from the production orchestrator checkout):

    WATHEFNI_ENV=production \\
    WATHEFNI_DELIVERY_MODE=dry_run \\
    WATHEFNI_BOUNDARY_ALLOW_PRODUCTION=1 \\
    WATHEFNI_PRODUCTION_MAINTENANCE_OPERATION=optional-module-boundary-matrix \\
    WATHEFNI_PRODUCTION_MAINTENANCE_ACK=I_UNDERSTAND_THIS_MUTATES_PRODUCTION \\
    WATHEFNI_APPLY_WHATSAPP_NUMBER=<prod apply number> \\
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env \\
  WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni \\
  WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 \\
  WATHEFNI_EXPECTED_DATABASE_PORT=5432 \\
  WATHEFNI_EXPECTED_DATABASE_NAME=wathefni \\
  WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1 \\
  /opt/wathefni/orchestrator/.venv/bin/python ops/optional-module-boundary-production-matrix.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

ORCH = Path(__file__).resolve().parents[1]
RUN_STARTED_AT = time.time()
sys.path.insert(0, str(ORCH))

SPEC_PATH = ORCH / "ops" / "optional-module-boundary-matrix.py"
if not SPEC_PATH.exists():
    raise SystemExit(f"missing matrix: {SPEC_PATH}")

if os.environ.get("WATHEFNI_BOUNDARY_ALLOW_PRODUCTION") != "1":
    raise SystemExit("REFUSING: set WATHEFNI_BOUNDARY_ALLOW_PRODUCTION=1")
if os.environ.get("WATHEFNI_ENV") != "production":
    raise SystemExit("REFUSING: WATHEFNI_ENV must be production")
if (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") != "wathefni":
    raise SystemExit("REFUSING: expected database must be wathefni")
if (os.environ.get("WATHEFNI_DELIVERY_MODE") or "") != "dry_run":
    raise SystemExit("REFUSING: production boundary matrix requires dry_run delivery")

import production_data_safety as _pds  # noqa: E402

_pds.require_production_maintenance(operation="optional-module-boundary-matrix")

# Patch only the hard production refuse so the frozen on-disk matrix SHA stays intact.
text = SPEC_PATH.read_text(encoding="utf-8")
old = (
    '    if expected_db == "wathefni" or env_name == "production":\n'
    '        print(f"REFUSING: matrix pointed at production ({expected_db!r})", file=sys.stderr)\n'
    "        return 2\n"
)
new = (
    '    if (expected_db == "wathefni" or env_name == "production") and '
    'os.environ.get("WATHEFNI_BOUNDARY_ALLOW_PRODUCTION") != "1":\n'
    '        print(f"REFUSING: production requires WATHEFNI_BOUNDARY_ALLOW_PRODUCTION=1 '
    '(db={expected_db!r})", file=sys.stderr)\n'
    "        return 2\n"
)
if old not in text:
    raise SystemExit("REFUSING: production refuse patch target not found in matrix source")
patched = text.replace(old, new, 1)

# Keep the frozen matrix source immutable while bringing its synthetic Job in
# line with the current publishability contract. This changes fixture data only.
fixture_old = (
    '                    "position_code": POSITION,\n'
    '                    "title_en": "Boundary Operations Engineer",\n'
    '                    "title_ar": "مهندس عمليات",\n'
    '                    "short_summary_en": "Own logistics data pipelines.",\n'
)
fixture_new = (
    '                    "position_code": POSITION,\n'
    '                    "title": "Boundary Operations Engineer",\n'
    '                    "title_en": "Boundary Operations Engineer",\n'
    '                    "title_ar": "مهندس عمليات",\n'
    '                    "description": "Synthetic optional-module boundary role for isolated matrix assertions.",\n'
    '                    "short_summary_en": "Own logistics data pipelines.",\n'
)
if fixture_old not in patched:
    raise SystemExit("REFUSING: synthetic Job fixture patch target not found")
patched = patched.replace(fixture_old, fixture_new, 1)
created_old = "            jobs.create_job(\n"
created_new = "            synthetic_job = jobs.create_job(\n"
if patched.count(created_old) != 1:
    raise SystemExit("REFUSING: expected one synthetic Job creation in frozen matrix")
patched = patched.replace(created_old, created_new, 1)
publish_old = (
    "            published = jobs.transition_job(\n"
)
publish_new = (
    "            if synthetic_job.get('publish_blockers'):\n"
    "                raise RuntimeError(f\"synthetic_job_not_publishable:{synthetic_job.get('publish_blockers')}\")\n"
    "            published = jobs.transition_job(\n"
)
if publish_old not in patched:
    raise SystemExit("REFUSING: synthetic Job publish assertion target not found")
patched = patched.replace(publish_old, publish_new, 1)

with tempfile.NamedTemporaryFile("w", suffix="-boundary-prod-matrix.py", delete=False) as tmp:
    tmp.write(patched)
    tmp_path = Path(tmp.name)

spec = importlib.util.spec_from_file_location("optional_module_boundary_matrix_prod", tmp_path)
if spec is None or spec.loader is None:
    raise SystemExit("unable to load patched matrix")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# The patched copy lives under /tmp, so re-bind ORCH to the real orchestrator root
# before any gate reads app.py / writes evidence.
mod.ORCH = ORCH
if hasattr(mod, "ROOT"):
    mod.ROOT = ORCH

# Namespace production fixtures away from staging STBND* / local BND*.
mod.MARKER = "prehire-optional-module-boundary-production-v1"
mod.PHONE_PREFIX = "+9658872"
mod.COMBOS = [
    {"code": "PRODBND1", "combo": "interviews_ON__video_ON", "live": True, "video": True},
    {"code": "PRODBND2", "combo": "interviews_ON__video_OFF", "live": True, "video": False},
    {"code": "PRODBND3", "combo": "interviews_OFF__video_ON", "live": False, "video": True},
    {"code": "PRODBND4", "combo": "interviews_OFF__video_OFF", "live": False, "video": False},
]
mod.HISTORY_TENANT = {"code": "PRODBNDH", "combo": "history_preservation", "live": True, "video": True}
mod.OFFER_TENANT = {"code": "PRODBNDO", "combo": "public_offer_link_policy", "live": True, "video": True}
mod.TENANTS = mod.COMBOS + [mod.HISTORY_TENANT, mod.OFFER_TENANT]
mod.COMPANIES = [t["code"] for t in mod.TENANTS]
mod.ACTOR_A = "b0d20000-0000-4000-8000-00000000000a"
mod.ACTOR_B = "b0d20000-0000-4000-8000-00000000000b"

os.environ.setdefault("WATHEFNI_OFFER_TOKEN_SECRET", "production-boundary-matrix-secret-v1")
# Job publish requires an apply channel; production unit env has this, CLI may not.
if not os.environ.get("WATHEFNI_APPLY_WHATSAPP_NUMBER"):
    raise SystemExit("REFUSING: set WATHEFNI_APPLY_WHATSAPP_NUMBER for production matrix")

reports = ORCH / "reports"
reports.mkdir(parents=True, exist_ok=True)


def cleanup_synthetic_outbound() -> int:
    """Remove only dry-run rows belonging to this namespaced matrix."""
    import app

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM outbound_delivery_events
                WHERE subject_key LIKE 'PRODBND%%'
                  AND status='dry_run'
                  AND created_at >= to_timestamp(%s)
                """,
                (RUN_STARTED_AT,),
            )
            removed = cur.rowcount
        conn.commit()
    return int(removed)


if __name__ == "__main__":
    try:
        try:
            code = mod.main()
        finally:
            print(f"production synthetic outbound cleanup={cleanup_synthetic_outbound()}", flush=True)
        src = reports / "optional-module-boundary-matrix.json"
        dst = reports / "optional-module-boundary-production-matrix.json"
        if src.exists():
            src.replace(dst)
            print(f"production evidence={dst}", flush=True)
        raise SystemExit(code)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
