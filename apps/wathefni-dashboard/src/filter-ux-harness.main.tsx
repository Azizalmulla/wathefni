import { StrictMode, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'

import { DEFAULT_CLASSIFICATION_FILTERS } from '@/components/candidates/ClassificationFilters'
import { EMPTY_CANDIDATE_FILTERS } from '@/lib/candidateFilterAuthority'
import { CandidatesPage } from '@/pages/CandidatesPage'
import type { CandidateFilters } from '@/types'
import type { RecruitingLocale } from '@/lib/recruitingLifecycle'
import '@/index.css'

function Harness() {
  const params = useMemo(() => new URLSearchParams(window.location.search), [])
  const initialLocale = (params.get('locale') === 'ar' ? 'ar' : 'en') as RecruitingLocale
  const openFilters = params.get('open') === '1'
  const [locale, setLocale] = useState<RecruitingLocale>(initialLocale)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [filters, setFilters] = useState<CandidateFilters>({
    ...EMPTY_CANDIDATE_FILTERS,
    followUp: 'needed',
    overviewCohort: 'follow_up_needed',
    cohortKey: 'follow_up_needed',
    action: 'follow_up_failed_delivery',
    position: 'ACCOUNTING_EXCEL',
    assessmentStatus: 'completed',
    sourceChannel: 'email',
  })
  const [classificationFilters, setClassificationFilters] = useState(DEFAULT_CLASSIFICATION_FILTERS)

  useEffect(() => {
    if (!openFilters) return
    const timer = window.setTimeout(() => {
      document.querySelector<HTMLButtonElement>('[data-testid="candidates-open-filters"]')?.click()
    }, 80)
    return () => window.clearTimeout(timer)
  }, [openFilters])

  return (
    <div className="mx-auto max-w-6xl p-4 md:p-8">
      <CandidatesPage
        applications={[]}
        assessmentEnabled
        busy={false}
        classificationEnabled={false}
        classificationFilters={classificationFilters}
        filters={filters}
        locale={locale}
        onClassificationFiltersChange={setClassificationFilters}
        onLocale={() => setLocale((current) => (current === 'ar' ? 'en' : 'ar'))}
        onSaveView={async () => undefined}
        onSelect={() => undefined}
        onSelectSavedView={() => undefined}
        positions={[
          { position_code: 'ACCOUNTING_EXCEL', position_title: 'Accounting Excel', application_count: 4, active_count: 2 },
          { position_code: 'SALES', position_title: 'Sales', application_count: 1, active_count: 1 },
        ]}
        query={query}
        savedViews={[]}
        setFilters={setFilters}
        setQuery={setQuery}
        setStatus={setStatus}
        status={status}
        unifiedEnabled
      />
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Harness />
  </StrictMode>,
)
