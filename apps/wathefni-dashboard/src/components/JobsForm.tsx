import { useEffect, useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import type { PositionSummary } from '@/types'
import { recruitingCopy, type RecruitingLocale } from '@/lib/recruitingLifecycle'

export type JobFormValues = {
  title: string
  title_ar: string
  position_code: string
  description: string
  description_ar: string
  requirements_en: string
  requirements_ar: string
  department: string
  location: string
  employment_type: string
  work_arrangement: string
  contract_type: string
  salary_min: string
  salary_max: string
  currency: string
  salary_visibility: string
  vacancies: string
  application_deadline: string
  expected_start_date: string
  hiring_manager_user_id: string
  recruiter_user_id: string
}

export type JobFormErrors = Partial<Record<keyof JobFormValues, string>>

function linesToList(value: string): string[] {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

function listToLines(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => String(item || '').trim()).filter(Boolean).join('\n')
  if (typeof value === 'string') return value
  return ''
}

function dateInputValue(value?: string | null): string {
  if (!value) return ''
  const raw = String(value).slice(0, 10)
  return /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : ''
}

export function emptyJobFormValues(): JobFormValues {
  return {
    title: '',
    title_ar: '',
    position_code: '',
    description: '',
    description_ar: '',
    requirements_en: '',
    requirements_ar: '',
    department: '',
    location: '',
    employment_type: '',
    work_arrangement: '',
    contract_type: '',
    salary_min: '',
    salary_max: '',
    currency: 'KD',
    salary_visibility: 'hr_only',
    vacancies: '1',
    application_deadline: '',
    expected_start_date: '',
    hiring_manager_user_id: '',
    recruiter_user_id: '',
  }
}

export function jobToFormValues(job: PositionSummary): JobFormValues {
  return {
    title: String(job.title_en || job.title || job.position_title || ''),
    title_ar: String(job.title_ar || ''),
    position_code: String(job.position_code || ''),
    description: String(job.description_en || job.description || ''),
    description_ar: String(job.description_ar || ''),
    requirements_en: listToLines(job.requirements_en || job.requirements),
    requirements_ar: listToLines(job.requirements_ar),
    department: String(job.department || ''),
    location: String(job.location || ''),
    employment_type: String(job.employment_type || ''),
    work_arrangement: String(job.work_arrangement || ''),
    contract_type: String(job.contract_type || ''),
    salary_min: job.salary_min != null ? String(job.salary_min) : '',
    salary_max: job.salary_max != null ? String(job.salary_max) : '',
    currency: String(job.currency || 'KD'),
    salary_visibility: String(job.salary_visibility || 'hr_only'),
    vacancies: job.vacancies != null ? String(job.vacancies) : '',
    application_deadline: dateInputValue(job.application_deadline),
    expected_start_date: dateInputValue(job.expected_start_date),
    hiring_manager_user_id: String(job.hiring_manager_user_id || ''),
    recruiter_user_id: String(job.recruiter_user_id || ''),
  }
}

export function validateJobForm(values: JobFormValues, locale: RecruitingLocale): JobFormErrors {
  const t = (key: Parameters<typeof recruitingCopy>[1]) => recruitingCopy(locale, key)
  const errors: JobFormErrors = {}
  if (!values.title.trim()) errors.title = t('jobsValidationTitleRequired')
  if (values.salary_min && Number.isNaN(Number(values.salary_min))) errors.salary_min = t('jobsValidationNumber')
  if (values.salary_max && Number.isNaN(Number(values.salary_max))) errors.salary_max = t('jobsValidationNumber')
  if (values.vacancies && (!Number.isInteger(Number(values.vacancies)) || Number(values.vacancies) < 0)) {
    errors.vacancies = t('jobsValidationVacancies')
  }
  if (values.salary_min && values.salary_max && Number(values.salary_min) > Number(values.salary_max)) {
    errors.salary_max = t('jobsValidationSalaryRange')
  }
  return errors
}

export function jobFormToPayload(values: JobFormValues, extras?: Record<string, unknown>) {
  return {
    title: values.title.trim(),
    title_en: values.title.trim(),
    title_ar: values.title_ar.trim() || null,
    position_code: values.position_code.trim().toUpperCase() || undefined,
    description: values.description.trim(),
    description_en: values.description.trim(),
    description_ar: values.description_ar.trim() || null,
    requirements: linesToList(values.requirements_en),
    requirements_en: linesToList(values.requirements_en),
    requirements_ar: linesToList(values.requirements_ar),
    department: values.department.trim() || null,
    location: values.location.trim() || null,
    employment_type: values.employment_type.trim() || null,
    work_arrangement: values.work_arrangement.trim() || null,
    contract_type: values.contract_type.trim() || null,
    salary_min: values.salary_min === '' ? null : Number(values.salary_min),
    salary_max: values.salary_max === '' ? null : Number(values.salary_max),
    currency: values.currency.trim() || 'KD',
    salary_visibility: values.salary_visibility || 'hr_only',
    vacancies: values.vacancies === '' ? null : Number(values.vacancies),
    application_deadline: values.application_deadline || null,
    expected_start_date: values.expected_start_date || null,
    hiring_manager_user_id: values.hiring_manager_user_id.trim() || null,
    recruiter_user_id: values.recruiter_user_id.trim() || null,
    ...extras,
  }
}

function Field({
  label,
  error,
  children,
}: {
  label: string
  error?: string
  children: React.ReactNode
}) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="font-medium text-text">{label}</span>
      {children}
      {error ? <span className="text-xs text-rose-700">{error}</span> : null}
    </label>
  )
}

const inputClass =
  'w-full rounded-xl border border-line bg-white px-3 py-2 text-sm text-text outline-none focus:border-ink/30'

export function JobsForm({
  locale,
  mode,
  initial,
  busy,
  canPublish,
  onCancel,
  onSaveDraft,
  onSaveChanges,
  onPublish,
}: {
  locale: RecruitingLocale
  mode: 'create' | 'edit'
  initial?: PositionSummary | null
  busy: boolean
  canPublish: boolean
  onCancel: () => void
  onSaveDraft: (values: JobFormValues) => Promise<void> | void
  onSaveChanges: (values: JobFormValues) => Promise<void> | void
  onPublish: (values: JobFormValues) => Promise<void> | void
}) {
  const t = (key: Parameters<typeof recruitingCopy>[1], vars?: Record<string, string | number>) =>
    recruitingCopy(locale, key, vars)
  const [values, setValues] = useState<JobFormValues>(() =>
    initial ? jobToFormValues(initial) : emptyJobFormValues(),
  )
  const [errors, setErrors] = useState<JobFormErrors>({})
  const [preview, setPreview] = useState(false)
  const [baseline, setBaseline] = useState(() => JSON.stringify(initial ? jobToFormValues(initial) : emptyJobFormValues()))

  useEffect(() => {
    const next = initial ? jobToFormValues(initial) : emptyJobFormValues()
    setValues(next)
    setBaseline(JSON.stringify(next))
    setErrors({})
  }, [initial, mode])

  const dirty = useMemo(() => JSON.stringify(values) !== baseline, [values, baseline])
  const isDraft = !initial || String(initial.status || '').toLowerCase() === 'draft'

  function setField<K extends keyof JobFormValues>(key: K, value: JobFormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }))
  }

  async function run(action: 'draft' | 'save' | 'publish') {
    const nextErrors = validateJobForm(values, locale)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    if (action === 'draft') await onSaveDraft(values)
    else if (action === 'save') await onSaveChanges(values)
    else await onPublish(values)
  }

  return (
    <div className="fixed inset-0 z-40 bg-ink/35" dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <div className="ml-auto flex h-full w-full max-w-3xl flex-col overflow-y-auto border-l border-line bg-panel p-6 shadow-soft">
        <div className="flex items-start justify-between gap-4 border-b border-line pb-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">
              {mode === 'create' ? t('jobsFormCreateTitle') : t('jobsFormEditTitle')}
            </h2>
            <p className="mt-1 text-sm text-subtle">{t('jobsFormSubtitle')}</p>
          </div>
          <Button
            onClick={() => {
              if (dirty && !window.confirm(t('jobsUnsavedConfirm'))) return
              onCancel()
            }}
            type="button"
            variant="secondary"
          >
            {t('jobsCancel')}
          </Button>
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <Field error={errors.title} label={t('jobsFieldTitleEn')}>
            <input className={inputClass} onChange={(e) => setField('title', e.target.value)} value={values.title} />
          </Field>
          <Field label={t('jobsFieldTitleAr')}>
            <input className={inputClass} dir="rtl" onChange={(e) => setField('title_ar', e.target.value)} value={values.title_ar} />
          </Field>
          <Field label={t('jobsFieldCode')}>
            <input
              className={inputClass}
              disabled={mode === 'edit'}
              onChange={(e) => setField('position_code', e.target.value.toUpperCase())}
              placeholder={t('jobsFieldCodeHint')}
              value={values.position_code}
            />
          </Field>
          <Field label={t('jobsFieldDepartment')}>
            <input className={inputClass} onChange={(e) => setField('department', e.target.value)} value={values.department} />
          </Field>
          <Field label={t('jobsFieldLocation')}>
            <input className={inputClass} onChange={(e) => setField('location', e.target.value)} value={values.location} />
          </Field>
          <Field label={t('jobsFieldEmploymentType')}>
            <input className={inputClass} onChange={(e) => setField('employment_type', e.target.value)} value={values.employment_type} />
          </Field>
          <Field label={t('jobsFieldWorkArrangement')}>
            <input className={inputClass} onChange={(e) => setField('work_arrangement', e.target.value)} value={values.work_arrangement} />
          </Field>
          <Field label={t('jobsFieldContractType')}>
            <input className={inputClass} onChange={(e) => setField('contract_type', e.target.value)} value={values.contract_type} />
          </Field>
          <Field error={errors.salary_min} label={t('jobsFieldSalaryMin')}>
            <input className={inputClass} onChange={(e) => setField('salary_min', e.target.value)} value={values.salary_min} />
          </Field>
          <Field error={errors.salary_max} label={t('jobsFieldSalaryMax')}>
            <input className={inputClass} onChange={(e) => setField('salary_max', e.target.value)} value={values.salary_max} />
          </Field>
          <Field label={t('jobsFieldCurrency')}>
            <input className={inputClass} onChange={(e) => setField('currency', e.target.value)} value={values.currency} />
          </Field>
          <Field label={t('jobsFieldSalaryVisibility')}>
            <select className={inputClass} onChange={(e) => setField('salary_visibility', e.target.value)} value={values.salary_visibility}>
              <option value="hr_only">{t('jobsSalaryHrOnly')}</option>
              <option value="public">{t('jobsSalaryPublic')}</option>
            </select>
          </Field>
          <Field error={errors.vacancies} label={t('jobsFieldVacancies')}>
            <input className={inputClass} onChange={(e) => setField('vacancies', e.target.value)} value={values.vacancies} />
          </Field>
          <Field label={t('jobsFieldDeadline')}>
            <input className={inputClass} onChange={(e) => setField('application_deadline', e.target.value)} type="date" value={values.application_deadline} />
          </Field>
          <Field label={t('jobsFieldStartDate')}>
            <input className={inputClass} onChange={(e) => setField('expected_start_date', e.target.value)} type="date" value={values.expected_start_date} />
          </Field>
        </div>

        <details className="mt-4 rounded-2xl border border-line bg-panel-muted/40 p-4">
          <summary className="cursor-pointer text-sm font-semibold text-text">{t('jobsOwnershipOptional')}</summary>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Field label={t('jobsFieldRecruiter')}>
              <input className={inputClass} onChange={(e) => setField('recruiter_user_id', e.target.value)} placeholder={t('jobsOwnershipHint')} value={values.recruiter_user_id} />
            </Field>
            <Field label={t('jobsFieldHiringManager')}>
              <input className={inputClass} onChange={(e) => setField('hiring_manager_user_id', e.target.value)} placeholder={t('jobsOwnershipHint')} value={values.hiring_manager_user_id} />
            </Field>
          </div>
        </details>

        <div className="mt-4 grid gap-4">
          <Field label={t('jobsFieldDescriptionEn')}>
            <textarea className={inputClass} onChange={(e) => setField('description', e.target.value)} rows={4} value={values.description} />
          </Field>
          <Field label={t('jobsFieldDescriptionAr')}>
            <textarea className={inputClass} dir="rtl" onChange={(e) => setField('description_ar', e.target.value)} rows={4} value={values.description_ar} />
          </Field>
          <Field label={t('jobsFieldRequirementsEn')}>
            <textarea className={inputClass} onChange={(e) => setField('requirements_en', e.target.value)} rows={4} value={values.requirements_en} />
          </Field>
          <Field label={t('jobsFieldRequirementsAr')}>
            <textarea className={inputClass} dir="rtl" onChange={(e) => setField('requirements_ar', e.target.value)} rows={4} value={values.requirements_ar} />
          </Field>
        </div>

        {preview ? (
          <div className="mt-5 rounded-2xl border border-line bg-panel-muted/60 p-4 text-sm">
            <div className="font-semibold">{values.title || values.title_ar || t('jobsPreviewUntitled')}</div>
            {values.title_ar ? <div className="mt-1" dir="rtl">{values.title_ar}</div> : null}
            <p className="mt-3 whitespace-pre-wrap text-subtle">{values.description || values.description_ar || t('jobsPreviewNoDescription')}</p>
            <ul className="mt-3 list-disc ps-5 text-subtle">
              {linesToList(values.requirements_en || values.requirements_ar).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="sticky bottom-0 mt-6 flex flex-wrap gap-2 border-t border-line bg-panel/95 py-4 backdrop-blur">
          <Button disabled={busy} onClick={() => setPreview((value) => !value)} type="button" variant="secondary">
            {preview ? t('jobsHidePreview') : t('jobsPreview')}
          </Button>
          {mode === 'create' || isDraft ? (
            <Button disabled={busy} onClick={() => void run('draft')} type="button" variant="secondary">
              {t('jobsSaveDraft')}
            </Button>
          ) : (
            <Button disabled={busy || !dirty} onClick={() => void run('save')} type="button" variant="secondary">
              {t('jobsSaveChanges')}
            </Button>
          )}
          {canPublish && (mode === 'create' || isDraft) ? (
            <Button disabled={busy} onClick={() => void run('publish')} type="button">
              {t('jobsPublish')}
            </Button>
          ) : null}
          {mode === 'edit' && !isDraft ? (
            <Button disabled={busy || !dirty} onClick={() => void run('save')} type="button">
              {t('jobsSaveChanges')}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  )
}
