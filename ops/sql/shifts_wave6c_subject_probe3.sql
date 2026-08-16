\pset pager off
\echo '=== SECTION reminder_queue_owners ==='
select employee_key, status, count(*) as n,
       coalesce(to_char(min(scheduled_for),'YYYY-MM-DD'),'-') as first_due,
       coalesce(to_char(max(scheduled_for),'YYYY-MM-DD'),'-') as last_due
from shift_reminder_queue
where company_code='WATHEFNI'
group by 1,2 order by 1,2;

\echo '=== SECTION lifecycle_flag_owners ==='
select employee_key, count(*) as n
from shift_lifecycle_flags where company_code='WATHEFNI'
group by 1 order by 1;

\echo '=== SECTION orphan_quarantine ==='
select count(*) as n from shift_orphan_quarantine where company_code='WATHEFNI';
