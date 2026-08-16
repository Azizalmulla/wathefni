"""Wave 3 additive schema: configuration, integrations, readiness, secret refs."""

from __future__ import annotations

import json
from typing import Any

import tenant_control_wave2_schema as wave2


SCHEMA_VERSION = "tenant-control-schema-v3"

ENSURE_WAVE3_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tc_config_schemas (
  schema_key text NOT NULL,
  schema_version text NOT NULL,
  domain text NOT NULL,
  json_schema jsonb NOT NULL DEFAULT '{}'::jsonb,
  description text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (schema_key, schema_version)
);

CREATE TABLE IF NOT EXISTS tc_config_documents (
  document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tc_tenants(tenant_id) ON DELETE CASCADE,
  domain text NOT NULL,
  schema_key text NOT NULL,
  schema_version text NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  version_number integer,
  effective_from timestamptz,
  owned_by text,
  approved_by text,
  config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  migration_impact jsonb NOT NULL DEFAULT '{}'::jsonb,
  before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  diff_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text,
  rollback_of_version integer,
  correlation_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz,
  UNIQUE (tenant_id, domain, idempotency_key),
  CHECK (status IN (
    'draft', 'validated', 'in_review', 'approved', 'published',
    'scheduled', 'rolled_back', 'superseded', 'rejected'
  ))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tc_config_documents_published_version
  ON tc_config_documents (tenant_id, domain, version_number)
  WHERE version_number IS NOT NULL;

CREATE TABLE IF NOT EXISTS tc_secret_refs (
  secret_ref_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tc_tenants(tenant_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  provider_key text NOT NULL,
  purpose text NOT NULL,
  secret_backend text NOT NULL DEFAULT 'env_file',
  secret_locator text NOT NULL,
  fingerprint text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  rotated_at timestamptz,
  revoked_at timestamptz,
  UNIQUE (company_code, provider_key, purpose),
  CHECK (secret_backend IN ('env_file', 'systemd_credential', 'vault', 'external'))
);

CREATE TABLE IF NOT EXISTS tc_integrations (
  integration_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tc_tenants(tenant_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  provider_key text NOT NULL,
  channel_key text NOT NULL,
  display_name text NOT NULL DEFAULT '',
  state text NOT NULL DEFAULT 'not_selected',
  supported boolean NOT NULL DEFAULT false,
  support_tier text NOT NULL DEFAULT 'unsupported',
  provider_account_ref text,
  secret_ref_id uuid REFERENCES tc_secret_refs(secret_ref_id) ON DELETE SET NULL,
  required_scopes jsonb NOT NULL DEFAULT '[]'::jsonb,
  granted_scopes jsonb NOT NULL DEFAULT '[]'::jsonb,
  health_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_tested_at timestamptz,
  last_verified_at timestamptz,
  kill_switch boolean NOT NULL DEFAULT false,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, provider_key, channel_key),
  CHECK (state IN (
    'not_selected', 'selected', 'setup_required', 'connected', 'verified',
    'testing', 'live', 'degraded', 'disconnected', 'blocked', 'uninstalling'
  )),
  CHECK (support_tier IN ('supported', 'partial', 'platform_global', 'unsupported', 'future'))
);

CREATE TABLE IF NOT EXISTS tc_integration_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  integration_id uuid NOT NULL REFERENCES tc_integrations(integration_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  event_type text NOT NULL,
  from_state text,
  to_state text,
  actor text,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tc_readiness_catalog (
  check_key text PRIMARY KEY,
  module_key text,
  integration_provider text,
  label text NOT NULL,
  severity text NOT NULL DEFAULT 'blocker',
  description text NOT NULL DEFAULT '',
  owner text NOT NULL DEFAULT 'platform',
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (severity IN ('blocker', 'warning', 'info'))
);

CREATE TABLE IF NOT EXISTS tc_readiness_results (
  result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tc_tenants(tenant_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  check_key text NOT NULL REFERENCES tc_readiness_catalog(check_key),
  module_key text,
  integration_provider text,
  status text NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  remediation text,
  owner text,
  checked_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz,
  correlation_id text,
  CHECK (status IN ('pass', 'fail', 'warning', 'blocked', 'skipped'))
);

CREATE INDEX IF NOT EXISTS idx_tc_readiness_results_company
  ON tc_readiness_results (company_code, checked_at DESC);

CREATE TABLE IF NOT EXISTS tc_worker_epoch_stamps (
  stamp_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  work_kind text NOT NULL,
  work_ref text NOT NULL,
  module_key text,
  activation_epoch bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, work_kind, work_ref)
);

CREATE TABLE IF NOT EXISTS tc_reconstruction_snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  completeness_score numeric,
  gaps jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
"""


def ensure_tenant_control_schema(cur: Any) -> dict[str, Any]:
    wave2_result = wave2.ensure_tenant_control_schema(cur)
    cur.execute(ENSURE_WAVE3_SCHEMA_SQL)
    cur.execute(
        """
        INSERT INTO tc_control_plane_meta (meta_key, meta_value, updated_at)
        VALUES ('schema_version', %s::jsonb, now())
        ON CONFLICT (meta_key) DO UPDATE
          SET meta_value = EXCLUDED.meta_value, updated_at = now()
        """,
        (json.dumps({"version": SCHEMA_VERSION}),),
    )
    return {"ok": True, "schema_version": SCHEMA_VERSION, "wave2": wave2_result}
