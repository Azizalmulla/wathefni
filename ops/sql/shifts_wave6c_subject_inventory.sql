-- Shifts Wave 6C — read-only production subject inventory.
-- STRICTLY SELECT-ONLY. No DDL, no DML. Used to propose controlled-rollout allowlists
-- for owner approval before any real mutation or real notification delivery is enabled.
\pset pager off
\set QUIET on
\timing off

\echo '=== SECTION company ==='
select company_code, name, status
from companies
where company_code = 'WATHEFNI';

\echo '=== SECTION company_modules ==='
select module_key, enabled, source
from company_modules
where company_code = 'WATHEFNI'
  and module_key in ('shifts','employee_app','attendance','leave','payroll','employees','onboarding')
order by module_key;

\echo '=== SECTION dashboard_users ==='
select u.user_id,
       coalesce(u.email,'-')                          as email,
       coalesce(u.name,'-')                           as name,
       coalesce(u.phone,'-')                          as phone,
       u.role,
       u.status,
       coalesce(to_char(u.last_active_at,'YYYY-MM-DD'),'never') as last_active,
       coalesce(to_char(u.accepted_at,'YYYY-MM-DD'),'-')        as accepted,
       coalesce(to_char(u.disabled_at,'YYYY-MM-DD'),'-')        as disabled
from dashboard_users u
where u.company_code = 'WATHEFNI'
order by u.role, u.email;

\echo '=== SECTION dashboard_permission_grants ==='
select g.user_id, g.permission, g.status,
       coalesce(to_char(g.granted_at,'YYYY-MM-DD'),'-') as granted_at,
       coalesce(to_char(g.revoked_at,'YYYY-MM-DD'),'-') as revoked_at
from dashboard_user_permission_grants g
where g.company_code = 'WATHEFNI'
order by g.user_id, g.permission;

\echo '=== SECTION manager_scopes ==='
select s.scope_id, coalesce(s.dashboard_user_id,'-') as dashboard_user_id,
       coalesce(s.manager_phone,'-') as manager_phone,
       s.scope_type, coalesce(s.branch_key,'-') as branch_key,
       coalesce(s.team_key,'-') as team_key, coalesce(s.role,'-') as role,
       s.is_active,
       coalesce(s.permissions::text,'{}') as permissions
from manager_scopes s
where s.company_code = 'WATHEFNI'
order by s.scope_type, s.manager_phone;

\echo '=== SECTION manager_scope_members ==='
select m.scope_id, m.employee_key
from manager_scope_members m
where m.company_code = 'WATHEFNI'
order by m.scope_id, m.employee_key;

\echo '=== SECTION branches ==='
select branch_key, branch_name, is_active
from company_branches where company_code = 'WATHEFNI' order by branch_key;

\echo '=== SECTION teams ==='
select team_key, team_name, coalesce(branch_key,'-') as branch_key, is_active
from company_teams where company_code = 'WATHEFNI' order by team_key;

\echo '=== SECTION real_employees ==='
select e.employee_key,
       coalesce(e.name,'-')             as name,
       coalesce(e.phone,'-')            as phone,
       coalesce(e.email,'-')            as email,
       coalesce(e.position_title,'-')   as position_title,
       coalesce(e.employment_status,'-') as employment_status,
       coalesce(to_char(e.hire_date,'YYYY-MM-DD'),'-') as hire_date,
       coalesce(em.lifecycle_state,'-')  as lifecycle_state,
       coalesce(em.employment_status,'-') as employment_lifecycle_status,
       coalesce(to_char(em.last_working_day,'YYYY-MM-DD'),'-') as last_working_day,
       coalesce(to_char(em.termination_effective_on,'YYYY-MM-DD'),'-') as termination_effective_on,
       coalesce(oa.branch_key,'-')      as branch_key,
       coalesce(oa.team_key,'-')        as team_key,
       coalesce(oa.role,'-')            as org_role,
       coalesce(e.app_key,'-')          as app_key
from employees e
left join employee_employments em on em.employment_id = e.employment_id
left join employee_org_assignments oa
       on oa.company_code = e.company_code
      and oa.employee_key = e.employee_key
      and coalesce(oa.is_primary, true)
where e.company_code = 'WATHEFNI'
  and e.employee_key not like '%SHW%'
  and coalesce(e.name,'') not like '%SHW%'
  and coalesce(e.phone,'') !~ '^9655(2[89]|3[0-7])'
order by e.employee_key;

\echo '=== SECTION synthetic_employee_count ==='
select count(*) as synthetic_like_rows
from employees
where company_code = 'WATHEFNI'
  and (employee_key like '%SHW%' or coalesce(phone,'') ~ '^9655(2[89]|3[0-7])');

\echo '=== SECTION push_tokens ==='
select employee_key, platform, active,
       coalesce(to_char(last_seen_at,'YYYY-MM-DD'),'-') as last_seen,
       right(coalesce(push_token,''), 6) as token_tail
from employee_push_tokens
where company_code = 'WATHEFNI'
order by employee_key, platform;

\echo '=== SECTION employee_sessions_recent ==='
select employee_key, count(*) as sessions,
       coalesce(to_char(max(created_at),'YYYY-MM-DD'),'-') as last_session
from employee_sessions
where company_code = 'WATHEFNI'
group by employee_key
order by employee_key;

\echo '=== SECTION channel_preferences ==='
select scope_type, scope_key, channel_order::text, enabled_channels::text, fallback_enabled
from shift_channel_preferences
where company_code = 'WATHEFNI'
order by scope_type, scope_key;

\echo '=== SECTION whatsapp_identities ==='
select user_id, phone, status, coalesce(to_char(linked_at,'YYYY-MM-DD'),'-') as linked_at
from dashboard_whatsapp_identities
where company_code = 'WATHEFNI'
order by phone;

\echo '=== SECTION consent_records ==='
select purpose, status, count(*) as n
from person_consent_records
where company_code = 'WATHEFNI'
group by purpose, status
order by purpose, status;

\echo '=== SECTION real_shift_footprint ==='
select 'shift_assignments' as t, count(*) as n from shift_assignments where company_code='WATHEFNI' and employee_key not like '%SHW%'
union all select 'shift_templates', count(*) from shift_templates where company_code='WATHEFNI'
union all select 'shift_schedule_periods', count(*) from shift_schedule_periods where company_code='WATHEFNI'
union all select 'shift_notification_events', count(*) from shift_notification_events where company_code='WATHEFNI'
union all select 'shift_open_shifts', count(*) from shift_open_shifts where company_code='WATHEFNI'
union all select 'shift_rotation_patterns', count(*) from shift_rotation_patterns where company_code='WATHEFNI'
order by t;
