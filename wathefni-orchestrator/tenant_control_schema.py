"""Additive tenant control-plane schema (Wave 1).

Does not remove or replace companies, company_modules, company_settings, or
current entitlement reads. Tables are created IF NOT EXISTS only.
"""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "tenant-control-schema-v1"

ENSURE_TENANT_CONTROL_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tc_tenants (
  tenant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL UNIQUE,
  display_name text NOT NULL DEFAULT '',
  lifecycle_status text NOT NULL DEFAULT 'active',
  legacy_company_status text,
  imported_from text NOT NULL DEFAULT 'companies',
  catalog_version text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (lifecycle_status IN (
    'draft', 'provisioning', 'ready', 'active', 'paused', 'suspended', 'offboarding', 'archived'
  ))
);

CREATE TABLE IF NOT EXISTS tc_contract_entitlements (
  entitlement_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tc_tenants(tenant_id) ON DELETE CASCADE,
  capability_key text NOT NULL,
  commercial boolean NOT NULL DEFAULT true,
  status text NOT NULL DEFAULT 'entitled',
  source text NOT NULL DEFAULT 'import',
  effective_from timestamptz NOT NULL DEFAULT now(),
  effective_to timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, capability_key),
  CHECK (status IN ('entitled', 'suspended', 'expired', 'revoked'))
);

CREATE TABLE IF NOT EXISTS tc_tenant_module_instances (
  instance_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tc_tenants(tenant_id) ON DELETE CASCADE,
  module_key text NOT NULL,
  capability_key text NOT NULL,
  enabled boolean NOT NULL DEFAULT false,
  instance_state text NOT NULL DEFAULT 'imported',
  legacy_source text,
  settings jsonb NOT NULL DEFAULT '{}'::jsonb,
  catalog_version text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, module_key),
  CHECK (instance_state IN (
    'imported', 'draft', 'configured', 'ready', 'live', 'paused', 'disabled', 'archived'
  ))
);

CREATE TABLE IF NOT EXISTS tc_tenant_capability_grants (
  grant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tc_tenants(tenant_id) ON DELETE CASCADE,
  capability_key text NOT NULL,
  granted boolean NOT NULL DEFAULT true,
  grant_mode text NOT NULL DEFAULT 'purchased',
  grant_reason text NOT NULL DEFAULT 'import',
  commercial boolean NOT NULL DEFAULT false,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, capability_key),
  CHECK (grant_mode IN ('purchased', 'implied_technical', 'compatibility', 'flag_gated', 'manual'))
);

CREATE TABLE IF NOT EXISTS tc_dependency_definitions (
  dependency_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  capability_key text NOT NULL,
  requires_capability_key text NOT NULL,
  dependency_class text NOT NULL DEFAULT 'technical',
  catalog_version text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (capability_key, requires_capability_key, catalog_version),
  CHECK (dependency_class IN ('technical', 'commercial'))
);

CREATE TABLE IF NOT EXISTS tc_tenant_config_versions (
  config_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tc_tenants(tenant_id) ON DELETE CASCADE,
  version_number integer NOT NULL,
  status text NOT NULL DEFAULT 'published',
  catalog_version text NOT NULL,
  config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  diff_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text,
  rollback_of_version integer,
  published_by text,
  published_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, version_number),
  UNIQUE (tenant_id, idempotency_key),
  CHECK (status IN ('draft', 'validated', 'published', 'rolled_back', 'superseded'))
);

CREATE TABLE IF NOT EXISTS tc_configuration_drafts (
  draft_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tc_tenants(tenant_id) ON DELETE CASCADE,
  draft_kind text NOT NULL DEFAULT 'modules',
  status text NOT NULL DEFAULT 'open',
  base_version_number integer,
  proposed_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, idempotency_key),
  CHECK (status IN ('open', 'validated', 'published', 'discarded', 'failed'))
);

CREATE TABLE IF NOT EXISTS tc_readiness_checks (
  check_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tc_tenants(tenant_id) ON DELETE CASCADE,
  check_key text NOT NULL,
  capability_key text,
  status text NOT NULL DEFAULT 'unknown',
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  checked_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, check_key),
  CHECK (status IN ('unknown', 'pass', 'warn', 'fail', 'skipped'))
);

CREATE TABLE IF NOT EXISTS tc_activation_events (
  activation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tc_tenants(tenant_id) ON DELETE CASCADE,
  event_type text NOT NULL,
  capability_key text,
  from_state text,
  to_state text,
  actor text,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tc_audit_events (
  audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tc_tenants(tenant_id) ON DELETE SET NULL,
  company_code text,
  event_type text NOT NULL,
  actor text,
  idempotency_key text,
  before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  diff_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tc_audit_events_idempotency
  ON tc_audit_events (company_code, event_type, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS tc_outbox_events (
  outbox_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tc_tenants(tenant_id) ON DELETE SET NULL,
  company_code text,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'pending',
  idempotency_key text,
  available_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('pending', 'processed', 'failed', 'cancelled'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tc_outbox_events_idempotency
  ON tc_outbox_events (company_code, event_type, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS tc_shadow_decision_runs (
  run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tc_tenants(tenant_id) ON DELETE SET NULL,
  company_code text NOT NULL,
  surface text NOT NULL,
  subject_key text NOT NULL,
  legacy_decision jsonb NOT NULL DEFAULT '{}'::jsonb,
  canonical_decision jsonb NOT NULL DEFAULT '{}'::jsonb,
  parity boolean NOT NULL DEFAULT false,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tc_shadow_decision_runs_company
  ON tc_shadow_decision_runs (company_code, created_at DESC);

CREATE TABLE IF NOT EXISTS tc_orphan_classifications (
  classification_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  record_table text NOT NULL,
  record_key text NOT NULL,
  company_code text NOT NULL,
  classification text NOT NULL,
  ownership text,
  origin_hypothesis text,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  action_plan text NOT NULL DEFAULT 'retain_do_not_delete',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (record_table, record_key),
  CHECK (classification IN (
    'test_seed', 'staging_leak', 'deleted_company_residue', 'unknown', 'cross_tenant_suspect'
  ))
);

CREATE TABLE IF NOT EXISTS tc_control_plane_meta (
  meta_key text PRIMARY KEY,
  meta_value jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);
"""


def ensure_tenant_control_schema(cur: Any) -> dict[str, Any]:
    cur.execute(ENSURE_TENANT_CONTROL_SCHEMA_SQL)
    cur.execute(
        """
        INSERT INTO tc_control_plane_meta (meta_key, meta_value, updated_at)
        VALUES ('schema_version', %s::jsonb, now())
        ON CONFLICT (meta_key) DO UPDATE
          SET meta_value = EXCLUDED.meta_value, updated_at = now()
        """,
        (f'{{"version": "{SCHEMA_VERSION}"}}',),
    )
    return {"ok": True, "schema_version": SCHEMA_VERSION}
