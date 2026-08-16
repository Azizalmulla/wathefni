CREATE TABLE IF NOT EXISTS employee_persons (
  person_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  display_name text,
  primary_phone text,
  primary_email text,
  employee_number text,
  status text NOT NULL DEFAULT 'active',
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('active','merged','archived')),
  UNIQUE (company_code, person_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS employee_persons_number_uq
  ON employee_persons (company_code, employee_number)
  WHERE employee_number IS NOT NULL AND employee_number <> '';

CREATE TABLE IF NOT EXISTS employee_person_contact_aliases (
  alias_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  person_id uuid NOT NULL REFERENCES employee_persons(person_id),
  alias_type text NOT NULL,
  alias_value text NOT NULL,
  alias_value_raw text,
  is_primary boolean NOT NULL DEFAULT false,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (alias_type IN ('phone','email')),
  UNIQUE (company_code, alias_type, alias_value)
);

CREATE INDEX IF NOT EXISTS employee_person_contact_aliases_person_idx
  ON employee_person_contact_aliases (company_code, person_id);

CREATE TABLE IF NOT EXISTS employee_employments (
  employment_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  person_id uuid NOT NULL REFERENCES employee_persons(person_id),
  employment_status text NOT NULL DEFAULT 'active',
  start_date date,
  end_date date,
  hire_source text,
  app_key text,
  legacy_employee_key text,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (employment_status IN ('active','left')),
  CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date),
  UNIQUE (company_code, employment_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS employee_employments_legacy_key_uq
  ON employee_employments (company_code, legacy_employee_key)
  WHERE legacy_employee_key IS NOT NULL AND legacy_employee_key <> '';

CREATE INDEX IF NOT EXISTS employee_employments_person_idx
  ON employee_employments (company_code, person_id, created_at DESC);

CREATE TABLE IF NOT EXISTS employee_assignments (
  assignment_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  employment_id uuid NOT NULL REFERENCES employee_employments(employment_id),
  person_id uuid NOT NULL REFERENCES employee_persons(person_id),
  is_primary boolean NOT NULL DEFAULT true,
  position_title text,
  department text,
  location text,
  manager_employee_key text,
  team_key text,
  branch_key text,
  cost_center text,
  working_pattern jsonb NOT NULL DEFAULT '{}'::jsonb,
  effective_from date,
  effective_to date,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, assignment_id)
);

CREATE INDEX IF NOT EXISTS employee_assignments_employment_idx
  ON employee_assignments (company_code, employment_id, is_primary);

CREATE TABLE IF NOT EXISTS employee_key_authority_map (
  company_code text NOT NULL,
  employee_key text NOT NULL,
  person_id uuid NOT NULL REFERENCES employee_persons(person_id),
  employment_id uuid NOT NULL REFERENCES employee_employments(employment_id),
  assignment_id uuid NOT NULL REFERENCES employee_assignments(assignment_id),
  mapping_status text NOT NULL DEFAULT 'active',
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, employee_key),
  CHECK (mapping_status IN ('active','superseded','rolled_back')),
  UNIQUE (company_code, employment_id)
);

CREATE TABLE IF NOT EXISTS employee_authority_migration_journal (
  journal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  action text NOT NULL,
  idempotency_key text NOT NULL,
  before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'applied',
  created_at timestamptz NOT NULL DEFAULT now(),
  rolled_back_at timestamptz,
  UNIQUE (company_code, idempotency_key)
);

ALTER TABLE IF EXISTS employees ADD COLUMN IF NOT EXISTS person_id uuid;
ALTER TABLE IF EXISTS employees ADD COLUMN IF NOT EXISTS employment_id uuid;
ALTER TABLE IF EXISTS employees ADD COLUMN IF NOT EXISTS assignment_id uuid;
