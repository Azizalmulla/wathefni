-- Phase A slice 2b — task/SLA invariants (additive, idempotent)
-- One open hr_task per logical subject/action; UTC clocks unchanged (timestamptz).

CREATE UNIQUE INDEX IF NOT EXISTS idx_hr_tasks_open_subject_action_uniq
  ON hr_tasks (company_code, task_type, subject_type, subject_id)
  WHERE status = 'open'
    AND subject_type IS NOT NULL
    AND subject_id IS NOT NULL
    AND subject_type <> ''
    AND subject_id <> '';
