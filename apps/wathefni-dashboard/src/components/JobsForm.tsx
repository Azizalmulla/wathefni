import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronUp, Pencil } from 'lucide-react'
import { useConfirm } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { PeoplePicker } from '@/components/PeoplePicker'
import type { DashboardAccess, PositionSummary } from '@/types'
import { recruitingCopy, type RecruitingLocale } from '@/lib/recruitingLifecycle'

export type JobFormValues = {
  title: string
  title_ar: string
  visibility: 'public' | 'share_only' | 'internal'
  position_code: string
  short_summary_en: string
  short_summary_ar: string
  approve_content_en: boolean
  approve_content_ar: boolean
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
    visibility: 'public',
    position_code: '',
    short_summary_en: '',
    short_summary_ar: '',
    approve_content_en: false,
    approve_content_ar: false,
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
    title: job.title_en === undefined ? String(job.title || job.position_title || '') : String(job.title_en || ''),
    title_ar: String(job.title_ar || ''),
    visibility: job.visibility || 'public',
    position_code: String(job.position_code || ''),
    short_summary_en: String(job.short_summary_en || ''),
    short_summary_ar: String(job.short_summary_ar || ''),
    approve_content_en: Boolean(job.content_approved_en),
    approve_content_ar: Boolean(job.content_approved_ar),
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

export function validateJobForm(values: JobFormValues, locale: RecruitingLocale, forPublish = false): JobFormErrors {
  const t = (key: Parameters<typeof recruitingCopy>[1]) => recruitingCopy(locale, key)
  const errors: JobFormErrors = {}
  if (!values.title.trim() && !values.title_ar.trim()) errors.title = t('jobsValidationTitleRequired')
  if (values.salary_min && Number.isNaN(Number(values.salary_min))) errors.salary_min = t('jobsValidationNumber')
  if (values.salary_max && Number.isNaN(Number(values.salary_max))) errors.salary_max = t('jobsValidationNumber')
  if (values.vacancies && (!Number.isInteger(Number(values.vacancies)) || Number(values.vacancies) < (forPublish ? 1 : 0))) {
    errors.vacancies = t('jobsValidationVacancies')
  }
  if (values.salary_min && values.salary_max && Number(values.salary_min) > Number(values.salary_max)) {
    errors.salary_max = t('jobsValidationSalaryRange')
  }
  if (forPublish) {
    const fullyRemote = ['remote', 'fully_remote', 'fully remote'].includes(values.work_arrangement.trim().toLowerCase().replace(/-/g, '_'))
    if (!values.location.trim() && !fullyRemote) {
      errors.location = t('jobsValidationLocationRemote')
      errors.work_arrangement = t('jobsValidationLocationRemote')
    }
    if (!values.employment_type.trim()) errors.employment_type = t('jobsValidationEmploymentType')
    const enReady = Boolean(values.title.trim() && values.short_summary_en.trim() && linesToList(values.requirements_en).length && values.approve_content_en)
    const arReady = Boolean(values.title_ar.trim() && values.short_summary_ar.trim() && linesToList(values.requirements_ar).length && values.approve_content_ar)
    if (!enReady && !arReady) {
      errors.short_summary_en = t('jobsValidationApprovedContent')
      errors.short_summary_ar = t('jobsValidationApprovedContent')
    }
    if (values.salary_visibility === 'public' && (!values.salary_min || !values.salary_max || !values.currency.trim())) {
      errors.salary_min = t('jobsValidationPublicSalary')
    }
  }
  return errors
}

export function jobFormToPayload(values: JobFormValues, extras?: Record<string, unknown>) {
  return {
    title: values.title.trim(),
    title_en: values.title.trim(),
    title_ar: values.title_ar.trim() || null,
    visibility: values.visibility,
    position_code: values.position_code.trim().toUpperCase() || undefined,
    short_summary_en: values.short_summary_en.trim() || null,
    short_summary_ar: values.short_summary_ar.trim() || null,
    approve_content_en: values.approve_content_en,
    approve_content_ar: values.approve_content_ar,
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

function FormSection({
  title,
  description,
  open,
  onToggle,
  children,
}: {
  title: string
  description?: string
  open: boolean
  onToggle: () => void
  children: React.ReactNode
}) {
  return (
    <section className="rounded-[1.4rem] border border-line/60 bg-panel/80 ring-1 ring-white/45">
      <button
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 border-b border-line/45 px-5 py-4 text-left"
        onClick={onToggle}
        type="button"
      >
        <span>
          <span className="block text-[15px] font-semibold tracking-[-0.015em] text-text">{title}</span>
          {description ? <span className="mt-0.5 block text-[12px] text-subtle/90">{description}</span> : null}
        </span>
        {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
      </button>
      {open ? <div className="p-5">{children}</div> : null}
    </section>
  )
}

export function JobsForm({
  access,
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
  access: DashboardAccess
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
  const confirm = useConfirm()
  const [values, setValues] = useState<JobFormValues>(() =>
    initial ? jobToFormValues(initial) : emptyJobFormValues(),
  )
  const [errors, setErrors] = useState<JobFormErrors>({})
  const [preview, setPreview] = useState(false)
  const [baseline, setBaseline] = useState(() => JSON.stringify(initial ? jobToFormValues(initial) : emptyJobFormValues()))
  const [openSections, setOpenSections] = useState({
    basics: true,
    hiring: true,
    content: true,
    advanced: false,
  })

  useEffect(() => {
    const next = initial ? jobToFormValues(initial) : emptyJobFormValues()
    setValues(next)
    setBaseline(JSON.stringify(next))
    setErrors({})
  }, [initial, mode])

  const dirty = useMemo(() => JSON.stringify(values) !== baseline, [values, baseline])
  const isDraft = !initial || String(initial.status || '').toLowerCase() === 'draft'

  function setField<K extends keyof JobFormValues>(key: K, value: JobFormValues[K]) {
    setValues((current) => {
      const next = { ...current, [key]: value }
      if (['title', 'short_summary_en', 'requirements_en'].includes(String(key))) next.approve_content_en = false
      if (['title_ar', 'short_summary_ar', 'requirements_ar'].includes(String(key))) next.approve_content_ar = false
      return next
    })
  }

  function toggleSection(key: keyof typeof openSections) {
    setOpenSections((current) => ({ ...current, [key]: !current[key] }))
  }

  async function run(action: 'draft' | 'save' | 'publish') {
    const nextErrors = validateJobForm(values, locale, action === 'publish')
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    if (action === 'draft') await onSaveDraft(values)
    else if (action === 'save') await onSaveChanges(values)
    else await onPublish(values)
  }

  return (
    <div className="fixed inset-0 z-40 bg-ink/35" dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <div className="ml-auto flex h-full w-full max-w-4xl flex-col overflow-y-auto border-l border-line bg-[#fbf8f2] p-4 shadow-soft sm:p-6">
        <div className="flex items-start justify-between gap-4 rounded-[1.6rem] border border-line/60 bg-panel/90 p-5 ring-1 ring-white/55">
          <div>
            <h2 className="text-2xl font-semibold tracking-[-0.03em] text-text">
              {mode === 'create' ? t('jobsFormCreateTitle') : t('jobsFormEditTitle')}
            </h2>
            <p className="mt-1 text-sm text-subtle">{t('jobsFormSubtitle')}</p>
          </div>
          <Button
            onClick={() => {
              void (async () => {
                if (dirty) {
                  const ok = await confirm({
                    title: t('jobsCancel'),
                    body: t('jobsUnsavedConfirm'),
                    confirmLabel: t('jobsCancel'),
                    destructive: true,
                    dir: locale === 'ar' ? 'rtl' : 'ltr',
                  })
                  if (!ok) return
                }
                onCancel()
              })()
            }}
            type="button"
            variant="secondary"
          >
            {t('jobsCancel')}
          </Button>
        </div>

        <div className="mt-4 space-y-4 pb-4">
          <FormSection
            description={t('jobsFormSectionBasicsHint')}
            onToggle={() => toggleSection('basics')}
            open={openSections.basics}
            title={t('jobsFormSectionBasics')}
          >
            <div className="grid gap-4 md:grid-cols-2">
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
              <Field label={t('jobsFieldVisibility')}>
                <select
                  className={inputClass}
                  onChange={(e) => setField('visibility', e.target.value as JobFormValues['visibility'])}
                  value={values.visibility}
                >
                  <option value="public">{t('jobsVisibilityPublic')}</option>
                  <option value="share_only">{t('jobsVisibilityShareOnly')}</option>
                  <option value="internal">{t('jobsVisibilityInternal')}</option>
                </select>
              </Field>
            </div>
          </FormSection>

          <FormSection
            description={t('jobsFormSectionHiringHint')}
            onToggle={() => toggleSection('hiring')}
            open={openSections.hiring}
            title={t('jobsFormSectionHiring')}
          >
            <div className="grid gap-4 md:grid-cols-2">
              <Field label={t('jobsFieldDepartment')}>
                <input className={inputClass} onChange={(e) => setField('department', e.target.value)} value={values.department} />
              </Field>
              <Field error={errors.location} label={t('jobsFieldLocation')}>
                <input className={inputClass} onChange={(e) => setField('location', e.target.value)} value={values.location} />
              </Field>
              <Field error={errors.employment_type} label={t('jobsFieldEmploymentType')}>
                <input className={inputClass} onChange={(e) => setField('employment_type', e.target.value)} value={values.employment_type} />
              </Field>
              <Field error={errors.work_arrangement} label={t('jobsFieldWorkArrangement')}>
                <input className={inputClass} onChange={(e) => setField('work_arrangement', e.target.value)} value={values.work_arrangement} />
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
          </FormSection>

          <FormSection
            description={t('jobsFormSectionContentHint')}
            onToggle={() => toggleSection('content')}
            open={openSections.content}
            title={t('jobsFormSectionContent')}
          >
            <div className="grid gap-4">
              <Field error={errors.short_summary_en} label={t('jobsFieldSummaryEn')}>
                <textarea
                  className={inputClass}
                  onChange={(e) => setField('short_summary_en', e.target.value)}
                  rows={3}
                  value={values.short_summary_en}
                />
              </Field>
              <label className="flex items-start gap-2 text-sm text-text">
                <input
                  checked={values.approve_content_en}
                  className="mt-1"
                  onChange={(e) => setField('approve_content_en', e.target.checked)}
                  type="checkbox"
                />
                <span>{t('jobsApproveContentEn')}</span>
              </label>
              <Field error={errors.short_summary_ar} label={t('jobsFieldSummaryAr')}>
                <textarea
                  className={inputClass}
                  dir="rtl"
                  onChange={(e) => setField('short_summary_ar', e.target.value)}
                  rows={3}
                  value={values.short_summary_ar}
                />
              </Field>
              <label className="flex items-start gap-2 text-sm text-text">
                <input
                  checked={values.approve_content_ar}
                  className="mt-1"
                  onChange={(e) => setField('approve_content_ar', e.target.checked)}
                  type="checkbox"
                />
                <span>{t('jobsApproveContentAr')}</span>
              </label>
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
          </FormSection>

          <FormSection
            description={t('jobsFormSectionAdvancedHint')}
            onToggle={() => toggleSection('advanced')}
            open={openSections.advanced}
            title={t('jobsFormSectionAdvanced')}
          >
            <div className="grid gap-4 md:grid-cols-2">
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
              <Field label={t('jobsFieldRecruiter')}>
                <PeoplePicker
                  access={access}
                  allowUnassigned
                  disabled={busy}
                  locale={locale}
                  onChange={(userId) => setField('recruiter_user_id', userId)}
                  placeholder={t('jobsOwnershipHint')}
                  purpose="recruiter"
                  value={values.recruiter_user_id}
                />
              </Field>
              <Field label={t('jobsFieldHiringManager')}>
                <PeoplePicker
                  access={access}
                  allowUnassigned
                  disabled={busy}
                  locale={locale}
                  onChange={(userId) => setField('hiring_manager_user_id', userId)}
                  placeholder={t('jobsOwnershipHint')}
                  purpose="hiring_manager"
                  value={values.hiring_manager_user_id}
                />
              </Field>
            </div>
          </FormSection>

          {preview ? (
            <div className="rounded-[1.4rem] border border-line/60 bg-panel/85 p-5 text-sm ring-1 ring-white/45">
              <div className="font-semibold">{values.title || values.title_ar || t('jobsPreviewUntitled')}</div>
              {values.title_ar ? <div className="mt-1" dir="rtl">{values.title_ar}</div> : null}
              <p className="mt-3 whitespace-pre-wrap text-subtle">
                {values.short_summary_en || values.short_summary_ar || values.description || values.description_ar || t('jobsPreviewNoDescription')}
              </p>
              <ul className="mt-3 list-disc ps-5 text-subtle">
                {linesToList(values.requirements_en || values.requirements_ar).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>

        <div className="sticky bottom-0 -mx-4 mt-auto border-t border-line/60 bg-[#fbf8f2]/95 px-4 py-4 backdrop-blur sm:-mx-6 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-[1.4rem] border border-line/60 bg-panel/90 p-3 ring-1 ring-white/55">
            <div className="flex items-center gap-2 text-sm text-subtle">
              <Pencil size={15} />
              <span>{dirty ? t('jobsFormDirty') : t('jobsFormClean')}</span>
            </div>
            <div className="flex flex-wrap gap-2">
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
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
