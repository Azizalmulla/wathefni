import { act, fireEvent, screen, within } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { useState } from 'react'

import { useDebouncedValue } from '@/components/ui/search-input'
import { InterviewDetailDrawer, InterviewsPage } from '@/pages/InterviewsPage'
import { renderWithProviders } from '@/test/render'
import type { CandidateInterview, DashboardAccess } from '@/types'

const access = {
  token: 'test-token',
  companyCode: 'WATHEFNI',
  baseUrl: 'http://localhost',
  hrPhone: '+96500000000',
} as DashboardAccess

function waitingVideoInterview(partial: Partial<CandidateInterview> = {}): CandidateInterview {
  return {
    interview_id: '06e4a65d-wait',
    company_code: 'WATHEFNI',
    app_key: 'app-wait',
    candidate_name: 'Waiting Candidate',
    candidate_email: 'wait@example.com',
    position_title: 'Operations Lead',
    application_stage: 'interview',
    status: 'scheduled',
    interview_type: 'async_video',
    allowed_actions: ['resend_video_link', 'cancel_interview', 'open_candidate'],
    video_answers: [],
    video_questions: [{ question_id: 'q1', question_order: 1, prompt_text: 'Tell us about yourself' }],
    feedback: { state: 'not_started', label: 'Not started', complete: false, needs_feedback: true },
    presentation: {
      interview_type: 'async_video',
      interview_type_label: 'Recorded video interview',
      progress_state: 'consented',
      progress_label: 'Opened',
      schedule_state: 'not_applicable',
      invitation_state: 'send_accepted',
      candidate_confirmation: 'confirmed',
      evidence_readiness: 'waiting',
      next_human_action: 'wait_for_video_response',
      allowed_actions: ['resend_video_link', 'cancel_interview', 'open_candidate'],
      display: { is_async: true, show_datetime: false, status_label: 'Opened' },
      interviewer_assignment: { assigned: false, label: 'Unassigned' },
    },
    ...partial,
  }
}

const basePageProps = {
  access,
  busy: false,
  canManageInterviews: true,
  feedbackCounts: [{ feedback_status: 'notes_pending', count: 1 }],
  filters: { tab: 'upcoming', q: '', role: '', date: '', interviewer: '' },
  limit: 25,
  locale: 'en' as const,
  notesDrafts: {},
  offset: 0,
  onOpenCandidate: vi.fn(),
  onLocale: vi.fn(),
  onPreviewVideoAnswer: vi.fn(),
  onRetryVideoTranscripts: vi.fn(),
  onSaveNotes: vi.fn(),
  onRefresh: vi.fn(),
  onSetNotes: vi.fn(),
  onSetOffset: vi.fn(),
  onStatusChange: vi.fn(),
  onUpdateFilters: vi.fn(),
  statusCounts: [
    { status: 'scheduled', count: 2 },
    { status: 'completed', count: 1 },
    { status: 'no_show', count: 3 },
    { status: 'cancelled', count: 4 },
  ],
  total: 1,
  videoCount: 5,
}

describe('Interviews UI refinement', () => {
  test('removes MetricGrid and keeps primary tabs with counts only', () => {
    renderWithProviders(<InterviewsPage {...basePageProps} interviews={[waitingVideoInterview()]} />)
    expect(screen.queryByText('Upcoming interviews')).not.toBeInTheDocument()
    expect(screen.queryByText('Feedback complete')).not.toBeInTheDocument()
    // Status tiles + primary tabs both expose these labels; assert counts on every match.
    for (const btn of screen.getAllByRole('button', { name: /Upcoming/i })) {
      expect(btn).toHaveTextContent('2')
    }
    for (const btn of screen.getAllByRole('button', { name: /Needs feedback/i })) {
      expect(btn).toHaveTextContent('1')
    }
    expect(screen.getByRole('tab', { name: /^Video/i })).toHaveTextContent('5')
    for (const btn of screen.getAllByRole('button', { name: /Completed/i })) {
      expect(btn).toHaveTextContent('1')
    }
    expect(screen.getByRole('tab', { name: /^All/i })).toBeInTheDocument()
    // Secondary queues live under More (still in DOM), not as primary pills.
    expect(screen.getByText('More')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Upcoming/i }).length).toBeGreaterThan(0)
  })

  test('More control exposes No-shows and Cancelled with counts and selected state', () => {
    const onUpdateFilters = vi.fn()
    const { rerender } = renderWithProviders(
      <InterviewsPage {...basePageProps} interviews={[waitingVideoInterview()]} onUpdateFilters={onUpdateFilters} />,
    )
    const more = screen.getByText('More').closest('summary')
    expect(more).toBeTruthy()
    fireEvent.click(more!)
    fireEvent.click(screen.getByRole('button', { name: /No-shows/i }))
    expect(onUpdateFilters).toHaveBeenCalledWith({ tab: 'no_show' })

    rerender(
      <InterviewsPage
        {...basePageProps}
        filters={{ ...basePageProps.filters, tab: 'no_show' }}
        interviews={[waitingVideoInterview()]}
        onUpdateFilters={onUpdateFilters}
      />,
    )
    expect(screen.getByText(/No-shows 3/)).toBeInTheDocument()
  })

  test('keeps search visible and nests role/date/interviewer behind Filters', () => {
    const onUpdateFilters = vi.fn()
    renderWithProviders(
      <InterviewsPage {...basePageProps} interviews={[waitingVideoInterview()]} onUpdateFilters={onUpdateFilters} />,
    )
    expect(screen.getByPlaceholderText('Search candidate or email')).toBeInTheDocument()
    const filtersSummary = screen.getByText('Filters').closest('summary')
    expect(filtersSummary).toBeTruthy()
    const filtersPanel = filtersSummary!.closest('details')!
    expect(within(filtersPanel).getByPlaceholderText('Filter by role')).toBeInTheDocument()
    fireEvent.click(filtersSummary!)
    fireEvent.change(within(filtersPanel).getByPlaceholderText('Filter by role'), { target: { value: 'Ops' } })
    expect(onUpdateFilters).toHaveBeenCalledWith({ role: 'Ops' })
  })

  test('drawer hierarchy: interview status primary, application stage secondary, no duplicate state, no fake tabs', () => {
    const interview = waitingVideoInterview()
    renderWithProviders(
      <InterviewDetailDrawer
        access={access}
        busy={false}
        canManageInterviews
        interview={interview}
        locale="en"
        notesDraft=""
        onClose={vi.fn()}
        onOpenCandidate={vi.fn()}
        onPreviewVideoAnswer={vi.fn()}
        onRefresh={vi.fn()}
        onRetryVideoTranscripts={vi.fn()}
        onSaveNotes={vi.fn()}
        onSetNotes={vi.fn()}
        onStatusChange={vi.fn()}
      />,
    )
    expect(screen.getByText('Waiting for the candidate to submit a video answer.')).toBeInTheDocument()
    expect(screen.getAllByText('Opened').length).toBeGreaterThan(0)
    expect(screen.getAllByText((_content, node) => node?.tagName === 'DIV' && (node.textContent || '').startsWith('Application stage')).length).toBeGreaterThan(0)
    expect(screen.queryByRole('navigation', { name: 'Interview sections' })).not.toBeInTheDocument()
    expect(screen.queryByText('No advisory analysis')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Status details'))
    const statusBlock = screen.getByText('Status details').closest('details')!
    expect(within(statusBlock).getAllByText('Interview state')).toHaveLength(1)
  })

  test('Arabic drawer chrome is translated and avoids uppercase tracking labels in QuietInfo', () => {
    renderWithProviders(
      <InterviewDetailDrawer
        access={access}
        busy={false}
        canManageInterviews
        interview={waitingVideoInterview()}
        locale="ar"
        notesDraft=""
        onClose={vi.fn()}
        onOpenCandidate={vi.fn()}
        onPreviewVideoAnswer={vi.fn()}
        onRefresh={vi.fn()}
        onRetryVideoTranscripts={vi.fn()}
        onSaveNotes={vi.fn()}
        onSetNotes={vi.fn()}
        onStatusChange={vi.fn()}
      />,
    )
    expect(screen.getByText('بانتظار تقديم المرشح لإجابة فيديو.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'إغلاق' })).toBeInTheDocument()
    expect(screen.getByText('تفاصيل الدعوة')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('أضف ملاحظات المقابلة أو الخطوات التالية…')).toBeInTheDocument()
  })

  test('source contract preserves live drawer, debounce, and no MetricGrid', () => {
    const page = readFileSync(resolve(__dirname, './InterviewsPage.tsx'), 'utf8')
    const app = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
    expect(page).toContain('selectedInterviewId')
    expect(page).toContain('overscrollBehavior')
    expect(page).not.toContain('MetricGrid')
    expect(page).not.toContain('Interview sections')
    expect(app).toContain('useDebouncedValue(interviewQuery.trim(), 350)')
  })
})

describe('Interviews live drawer + scroll + debounce regressions', () => {
  test('drawer reflects refreshed query data for the same interview id', () => {
    const initial = waitingVideoInterview()
    const refreshed = waitingVideoInterview({
      presentation: {
        ...waitingVideoInterview().presentation!,
        progress_state: 'ready_for_review',
        progress_label: 'Ready for review',
        evidence_readiness: 'ready',
        next_human_action: 'review_video_interview',
        allowed_actions: ['review_video', 'write_notes', 'mark_reviewed', 'cancel_interview'],
      },
      video_answers: [
        {
          response_id: 'r1',
          question_id: 'q1',
          question_order: 1,
          has_video: true,
          transcript_status: 'completed',
          transcript_text: 'Candidate answer',
          question_text: 'Tell us about yourself',
        },
      ],
    })
    function Host() {
      const [rows, setRows] = useState([initial])
      return (
        <div>
          <button type="button" onClick={() => setRows([refreshed])}>refresh-rows</button>
          <InterviewsPage {...basePageProps} interviews={rows} total={rows.length} />
        </div>
      )
    }
    renderWithProviders(<Host />)
    fireEvent.click(screen.getByRole('button', { name: /Wait for video response|Open/i }))
    expect(screen.getByText('Waiting for the candidate to submit a video answer.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'refresh-rows' }))
    expect(screen.getByText('The video answer is ready for HR review.')).toBeInTheDocument()
  })

  test('locks body scroll while drawer open and restores on close', () => {
    Object.defineProperty(window, 'scrollY', { configurable: true, get: () => 220 })
    const scrollSpy = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined)
    const { unmount } = renderWithProviders(
      <InterviewDetailDrawer
        access={access}
        busy={false}
        canManageInterviews
        interview={waitingVideoInterview()}
        locale="en"
        notesDraft=""
        onClose={vi.fn()}
        onOpenCandidate={vi.fn()}
        onPreviewVideoAnswer={vi.fn()}
        onRefresh={vi.fn()}
        onRetryVideoTranscripts={vi.fn()}
        onSaveNotes={vi.fn()}
        onSetNotes={vi.fn()}
        onStatusChange={vi.fn()}
      />,
    )
    expect(document.body.style.position).toBe('fixed')
    expect(document.body.style.top).toBe('-220px')
    unmount()
    expect(scrollSpy).toHaveBeenCalledWith(0, 220)
    scrollSpy.mockRestore()
  })

  test('debounce settles after ~350ms', async () => {
    vi.useFakeTimers()
    function Probe({ value }: { value: string }) {
      const debounced = useDebouncedValue(value, 350)
      return <div data-testid="debounced">{debounced}</div>
    }
    function Host() {
      const [value, setValue] = useState('a')
      return (
        <div>
          <button type="button" onClick={() => setValue('abc')}>type</button>
          <Probe value={value} />
        </div>
      )
    }
    renderWithProviders(<Host />)
    fireEvent.click(screen.getByRole('button', { name: 'type' }))
    await act(async () => { vi.advanceTimersByTime(349) })
    expect(screen.getByTestId('debounced').textContent).toBe('a')
    await act(async () => { vi.advanceTimersByTime(1) })
    expect(screen.getByTestId('debounced').textContent).toBe('abc')
    vi.useRealTimers()
  })

  test('successful empty list shows genuine empty, not an error', () => {
    renderWithProviders(<InterviewsPage {...basePageProps} interviews={[]} total={0} />)
    expect(screen.getByTestId('interviews-list-empty')).toHaveTextContent(/No interviews match this queue/i)
    expect(screen.queryByTestId('interviews-list-error')).not.toBeInTheDocument()
  })

  test('API failure shows error/retry and never a fake empty queue', () => {
    renderWithProviders(
      <InterviewsPage {...basePageProps} interviews={[]} total={0} listError listLoading={false} />,
    )
    expect(screen.getByTestId('interviews-list-error')).toHaveTextContent(/not an empty queue/i)
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument()
    expect(screen.queryByTestId('interviews-list-empty')).not.toBeInTheDocument()
    expect(screen.queryByText(/No interviews match this queue/i)).not.toBeInTheDocument()
  })
})
