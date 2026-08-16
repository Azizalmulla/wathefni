-- Shifts Wave 6C — read-only follow-up probe (SELECT-ONLY).
\pset pager off

\echo '=== SECTION real_assignment_owners ==='
select a.employee_key,
       count(*) as n,
       min(a.shift_date)::text as first_date,
       max(a.shift_date)::text as last_date,
       count(*) filter (where a.shift_date >= current_date) as future_rows,
       coalesce(string_agg(distinct a.status, ','), '-') as statuses
from shift_assignments a
where a.company_code = 'WATHEFNI'
  and a.employee_key not like '%SHW%'
group by a.employee_key
order by a.employee_key;

\echo '=== SECTION real_assignment_source ==='
select coalesce(source, '-') as source, coalesce(created_by,'-') as created_by, count(*) as n
from shift_assignments
where company_code = 'WATHEFNI' and employee_key not like '%SHW%'
group by 1,2 order by 3 desc;

\echo '=== SECTION employees_all_keys ==='
select employee_key, coalesce(name,'-') as name, coalesce(phone,'-') as phone,
       coalesce(employment_status,'-') as st
from employees
where company_code = 'WATHEFNI'
  and employee_key in (
    select distinct employee_key from shift_assignments
    where company_code='WATHEFNI' and employee_key not like '%SHW%'
  )
order by employee_key;

\echo '=== SECTION dashboard_users_all_companies_roles ==='
select company_code, role, status, count(*) as n
from dashboard_users
group by 1,2,3 order by 1,2,3;

\echo '=== SECTION talal_detail ==='
select e.employee_key, e.name, e.phone, e.email, e.app_key,
       coalesce(e.profile::text,'{}') as profile,
       coalesce(e.raw_json->>'consent','-') as raw_consent
from employees e
where e.company_code='WATHEFNI' and e.employee_key='WATHEFNI-96550252254';

\echo '=== SECTION employee_notification_reads_schema ==='
select column_name, data_type from information_schema.columns
where table_schema='public' and table_name='employee_notification_reads' order by ordinal_position;

\echo '=== SECTION employee_messages_recent ==='
select coalesce(direction,'-') as direction, coalesce(channel,'-') as channel, count(*) as n,
       coalesce(to_char(max(created_at),'YYYY-MM-DD'),'-') as last_at
from employee_messages
where company_code='WATHEFNI'
group by 1,2 order by 3 desc;

\echo '=== SECTION realblock_employee ==='
select employee_key, name, phone, coalesce(raw_json::text,'{}') as raw_json,
       to_char(created_at,'YYYY-MM-DD') as created
from employees
where company_code='WATHEFNI' and employee_key like '%REALBLOCK%';

\echo '=== SECTION shift_authority_settings ==='
select * from shift_authority_settings where company_code='WATHEFNI';

\echo '=== SECTION shift_lifecycle_flags ==='
select count(*) as n from shift_lifecycle_flags where company_code='WATHEFNI';

\echo '=== SECTION shift_reminder_queue ==='
select coalesce(status,'-') as status, count(*) as n
from shift_reminder_queue where company_code='WATHEFNI' group by 1 order by 1;
