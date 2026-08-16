"""Wave 2 additive schema extensions for universal enforcement and lifecycle safety.

Extends Wave 1 tables without replacing companies / company_modules /
company_settings or making the new model globally authoritative.
"""

from __future__ import annotations

from typing import Any

import tenant_control_schema as wave1


SCHEMA_VERSION = "tenant-control-schema-v2"

ENSURE_WAVE2_SCHEMA_SQL = """
-- Expand tenant lifecycle vocabulary (drop/recreate check).
ALTER TABLE tc_tenants DROP CONSTRAINT IF EXISTS tc_tenants_lifecycle_status_check;
ALTER TABLE tc_tenants
  ADD CONSTRAINT tc_tenants_lifecycle_status_check
  CHECK (lifecycle_status IN (
    'draft', 'setup', 'provisioning', 'testing', 'ready', 'active',
    'paused', 'suspended', 'offboarding', 'archived'
  ));

ALTER TABLE tc_tenants
  ADD COLUMN IF NOT EXISTS activation_epoch bigint NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS lifecycle_reason text,
  ADD COLUMN IF NOT EXISTS suspended_at timestamptz,
  ADD COLUMN IF NOT EXISTS restored_at timestamptz,
  ADD COLUMN IF NOT EXISTS synthetic boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS externally_usable boolean NOT NULL DEFAULT false;

ALTER TABLE tc_tenant_module_instances
  ADD COLUMN IF NOT EXISTS purchased boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS desired boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS configured boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS tested boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS ready boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS live boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS paused boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS degraded boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS blocked boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS activation_epoch bigint NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS block_reason text,
  ADD COLUMN IF NOT EXISTS pause_reason text;

ALTER TABLE tc_tenant_module_instances DROP CONSTRAINT IF EXISTS tc_tenant_module_instances_instance_state_check;
ALTER TABLE tc_tenant_module_instances
  ADD CONSTRAINT tc_tenant_module_instances_instance_state_check
  CHECK (instance_state IN (
    'imported', 'draft', 'configured', 'tested', 'ready', 'live',
    'paused', 'degraded', 'blocked', 'disabled', 'archived'
  ));

CREATE TABLE IF NOT EXISTS tc_activation_epochs (
  epoch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tc_tenants(tenant_id) ON DELETE CASCADE,
  module_key text,
  scope text NOT NULL DEFAULT 'tenant',
  epoch_number bigint NOT NULL,
  reason text NOT NULL DEFAULT '',
  actor text,
  correlation_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, module_key, epoch_number),
  CHECK (scope IN ('tenant', 'module'))
);

CREATE TABLE IF NOT EXISTS tc_blocked_work (
  blocked_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tc_tenants(tenant_id) ON DELETE SET NULL,
  company_code text NOT NULL,
  work_kind text NOT NULL,
  work_ref text,
  module_key text,
  capability_key text,
  surface text,
  reason_code text NOT NULL,
  disposition text NOT NULL DEFAULT 'hold',
  queued_epoch bigint,
  live_epoch bigint,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  correlation_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  CHECK (disposition IN ('hold', 'cancel', 'drain', 'reject', 'recorded'))
);

CREATE INDEX IF NOT EXISTS idx_tc_blocked_work_company
  ON tc_blocked_work (company_code, created_at DESC);

CREATE TABLE IF NOT EXISTS tc_role_templates (
  template_key text PRIMARY KEY,
  label text NOT NULL,
  description text NOT NULL DEFAULT '',
  permissions jsonb NOT NULL DEFAULT '[]'::jsonb,
  module_scopes jsonb NOT NULL DEFAULT '[]'::jsonb,
  capability_scopes jsonb NOT NULL DEFAULT '[]'::jsonb,
  system boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tc_tenant_roles (
  role_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tc_tenants(tenant_id) ON DELETE CASCADE,
  role_key text NOT NULL,
  label text NOT NULL,
  template_key text REFERENCES tc_role_templates(template_key),
  permissions jsonb NOT NULL DEFAULT '[]'::jsonb,
  module_scopes jsonb NOT NULL DEFAULT '[]'::jsonb,
  capability_scopes jsonb NOT NULL DEFAULT '[]'::jsonb,
  org_scopes jsonb NOT NULL DEFAULT '[]'::jsonb,
  deny_permissions jsonb NOT NULL DEFAULT '[]'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, role_key)
);

CREATE TABLE IF NOT EXISTS tc_role_grants (
  grant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tc_tenants(tenant_id) ON DELETE CASCADE,
  role_id uuid NOT NULL REFERENCES tc_tenant_roles(role_id) ON DELETE CASCADE,
  subject_type text NOT NULL DEFAULT 'user',
  subject_key text NOT NULL,
  expires_at timestamptz,
  granted_by text,
  sod_warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, role_id, subject_type, subject_key),
  CHECK (subject_type IN ('user', 'service', 'group'))
);

CREATE TABLE IF NOT EXISTS tc_canary_authority (
  canary_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  module_key text,
  capability_key text,
  surface text,
  enabled boolean NOT NULL DEFAULT true,
  reason text NOT NULL DEFAULT '',
  actor text,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz,
  UNIQUE (company_code, module_key, capability_key, surface)
);

CREATE TABLE IF NOT EXISTS tc_decision_audit (
  decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  correlation_id text NOT NULL,
  company_code text NOT NULL,
  surface text NOT NULL,
  module_key text,
  capability_key text,
  allowed boolean NOT NULL,
  reason_code text NOT NULL,
  mode text NOT NULL DEFAULT 'shadow',
  legacy_allowed boolean,
  parity boolean,
  config_version integer,
  activation_epoch bigint,
  remediation text,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tc_decision_audit_company
  ON tc_decision_audit (company_code, created_at DESC);

CREATE TABLE IF NOT EXISTS tc_orphan_monitoring (
  monitor_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  checked_at timestamptz NOT NULL DEFAULT now(),
  orphan_settings_count integer NOT NULL DEFAULT 0,
  new_orphan_settings_count integer NOT NULL DEFAULT 0,
  other_orphan_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tc_permission_parity_runs (
  run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  checked integer NOT NULL DEFAULT 0,
  mismatches integer NOT NULL DEFAULT 0,
  parity boolean NOT NULL DEFAULT false,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
"""


SYSTEM_ROLE_TEMPLATES = (
    ("owner", "Owner", ["*"], [], []),
    ("hr_admin", "HR Admin", ["prehire.*", "posthire.*", "team.*", "settings.read"], [], []),
    ("recruiter", "Recruiter", ["prehire.read", "prehire.write", "candidates.read", "candidates.write", "interview.manage"], ["pre_hiring", "interviews", "assessments", "video_interviews", "employment_offers"], []),
    ("hiring_manager", "Hiring Manager", ["prehire.read", "candidates.read", "interview.manage"], ["pre_hiring", "interviews"], []),
    ("viewer", "Viewer", ["prehire.read", "candidates.read"], ["pre_hiring"], []),
)


def ensure_tenant_control_schema(cur: Any) -> dict[str, Any]:
    wave1_result = wave1.ensure_tenant_control_schema(cur)
    cur.execute(ENSURE_WAVE2_SCHEMA_SQL)
    for key, label, perms, modules, caps in SYSTEM_ROLE_TEMPLATES:
        cur.execute(
            """
            INSERT INTO tc_role_templates (
              template_key, label, description, permissions, module_scopes, capability_scopes, system
            ) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,true)
            ON CONFLICT (template_key) DO UPDATE SET
              label = EXCLUDED.label,
              permissions = EXCLUDED.permissions,
              module_scopes = EXCLUDED.module_scopes,
              capability_scopes = EXCLUDED.capability_scopes
            """,
            (
                key,
                label,
                f"System template for {label}",
                __import__("json").dumps(perms),
                __import__("json").dumps(modules),
                __import__("json").dumps(caps),
            ),
        )
    cur.execute(
        """
        INSERT INTO tc_control_plane_meta (meta_key, meta_value, updated_at)
        VALUES ('schema_version', %s::jsonb, now())
        ON CONFLICT (meta_key) DO UPDATE
          SET meta_value = EXCLUDED.meta_value, updated_at = now()
        """,
        (f'{{"version": "{SCHEMA_VERSION}"}}',),
    )
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "wave1": wave1_result,
    }
