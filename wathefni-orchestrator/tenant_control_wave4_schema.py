"""Wave 4 additive schema: wizard drafts, runtime cutover, imports, impact previews."""

from __future__ import annotations

import json
from typing import Any

import tenant_control_wave3_schema as wave3


SCHEMA_VERSION = "tenant-control-schema-v4"

ENSURE_WAVE4_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tc_onboarding_wizard_drafts (
  draft_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text,
  synthetic boolean NOT NULL DEFAULT false,
  externally_usable boolean NOT NULL DEFAULT false,
  current_step integer NOT NULL DEFAULT 1,
  status text NOT NULL DEFAULT 'in_progress',
  locale text NOT NULL DEFAULT 'en',
  draft_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  progress_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  owned_by text,
  idempotency_key text,
  correlation_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (idempotency_key),
  CHECK (status IN ('in_progress','ready_to_activate','activated','abandoned','archived')),
  CHECK (current_step BETWEEN 1 AND 10)
);

CREATE TABLE IF NOT EXISTS tc_runtime_cutover (
  cutover_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  boundary_key text NOT NULL,
  mode text NOT NULL DEFAULT 'legacy',
  parity_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  canary_token text,
  activated_at timestamptz,
  rolled_back_at timestamptz,
  actor text,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, boundary_key),
  CHECK (mode IN ('legacy','shadow','canary_canonical','rolled_back'))
);

CREATE TABLE IF NOT EXISTS tc_impact_previews (
  preview_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  action text NOT NULL,
  module_key text,
  preview_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  actor text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tc_import_batches (
  batch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  import_kind text NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  mapping_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  preview_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  dry_run boolean NOT NULL DEFAULT true,
  actor text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('draft','validated','previewed','imported','reconciled','rolled_back','failed')),
  CHECK (import_kind IN (
    'users_admins','org_structure','candidates','employees','policies','templates','integration_refs'
  ))
);

CREATE TABLE IF NOT EXISTS tc_activation_approvals (
  approval_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  module_key text,
  status text NOT NULL DEFAULT 'pending',
  readiness_correlation_id text,
  approved_by text,
  approved_at timestamptz,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('pending','approved','rejected','expired','rolled_back'))
);

CREATE TABLE IF NOT EXISTS tc_offboarding_runs (
  run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  in_flight_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  choices_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  export_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  actor text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('draft','exporting','holding','cancelling','archived','completed','aborted'))
);
"""


def ensure_tenant_control_schema(cur: Any) -> dict[str, Any]:
    wave3_result = wave3.ensure_tenant_control_schema(cur)
    cur.execute(ENSURE_WAVE4_SCHEMA_SQL)
    cur.execute(
        """
        INSERT INTO tc_control_plane_meta (meta_key, meta_value, updated_at)
        VALUES ('schema_version', %s::jsonb, now())
        ON CONFLICT (meta_key) DO UPDATE
          SET meta_value = EXCLUDED.meta_value, updated_at = now()
        """,
        (json.dumps({"version": SCHEMA_VERSION}),),
    )
    return {"ok": True, "schema_version": SCHEMA_VERSION, "wave3": wave3_result}
