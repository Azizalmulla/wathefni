-- Isolated, auditable App Store / Google Play reviewer authentication.
-- Credentials never live in this table; only non-reversible identity digests do.
CREATE TABLE IF NOT EXISTS store_review_access_audit (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username_digest text NOT NULL,
  requested_principal text NOT NULL,
  store text,
  result text NOT NULL,
  error_code text,
  source_digest text,
  company_code text NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT store_review_access_principal_ck CHECK (requested_principal IN ('employee', 'hr')),
  CONSTRAINT store_review_access_result_ck CHECK (result IN ('attempt', 'success', 'denied', 'error')),
  CONSTRAINT store_review_access_company_ck CHECK (company_code = 'OCTOHR-STORE-REVIEW')
);

CREATE INDEX IF NOT EXISTS store_review_access_audit_recent_idx
  ON store_review_access_audit (created_at DESC);

CREATE INDEX IF NOT EXISTS store_review_access_audit_identity_idx
  ON store_review_access_audit (username_digest, created_at DESC);
