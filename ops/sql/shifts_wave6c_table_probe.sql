\pset pager off
select table_name || '.' || column_name || ' : ' || data_type
from information_schema.columns
where table_schema = 'public'
  and table_name in (
    'employees','dashboard_users','manager_scopes','manager_scope_members',
    'employee_org_assignments','company_branches','company_teams',
    'employee_push_tokens','shift_channel_preferences','person_consent_records',
    'employee_employments','company_modules','dashboard_user_permission_grants',
    'dashboard_whatsapp_identities','employee_identity'
  )
order by table_name, ordinal_position;
