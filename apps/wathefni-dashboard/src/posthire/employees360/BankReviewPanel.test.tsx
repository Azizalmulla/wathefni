import { beforeEach, describe, expect, test, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import type { BankReviewResponse } from '@/types'
import { renderWithProviders } from '@/test/render'

import {
  BANK_STATE_LABELS,
  bankFieldLabel,
  bankReadableFields,
  bankStateLabel,
  bankStateTone,
  bankWorkflowStageLabel,
} from './bankReview'

const getEmployeeBankReview = vi.fn()
const decideEmployeeEssRequest = vi.fn()
const applyEmployeeEssRequest = vi.fn()
const openBankEvidence = vi.fn()

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    getEmployeeBankReview: (...args: unknown[]) => getEmployeeBankReview(...args),
    decideEmployeeEssRequest: (...args: unknown[]) => decideEmployeeEssRequest(...args),
    applyEmployeeEssRequest: (...args: unknown[]) => applyEmployeeEssRequest(...args),
    openBankEvidence: (...args: unknown[]) => openBankEvidence(...args),
  }
})

const access = { token: 't', companyCode: 'WATHEFNI', permissions: [], role: 'owner' } as never

beforeEach(() => {
  vi.clearAllMocks()
})

async function renderPanel(data: BankReviewResponse, canDecide = true, onDecided?: () => void) {
  getEmployeeBankReview.mockResolvedValue(data)
  const { BankReviewPanel } = await import('./BankReviewPanel')
  renderWithProviders(
    <BankReviewPanel
      access={access}
      employeeKey="WATHEFNI-1"
      canDecide={canDecide}
      onAccessIssue={() => {}}
      onDecided={onDecided}
    />,
  )
  await waitFor(() => expect(screen.getByTestId('bank-review')).toBeTruthy())
}

describe('bank review helpers', () => {
  test('every submission state has a bilingual label', () => {
    for (const state of [
      'none',
      'draft',
      'pending_hr',
      'pending_review',
      'pending_payroll',
      'approved',
      'applied',
      'rejected',
      'needs_correction',
      'withdrawn',
    ]) {
      expect(BANK_STATE_LABELS[state]?.en).toBeTruthy()
      expect(BANK_STATE_LABELS[state]?.ar).toBeTruthy()
    }
  })

  test('tones separate applied, awaiting review and returned', () => {
    expect(bankStateTone('applied')).toBe('success')
    expect(bankStateTone('approved')).toBe('warning')
    expect(bankStateTone('pending_payroll')).toBe('warning')
    expect(bankStateTone('pending_hr')).toBe('review')
    expect(bankStateTone('pending_review')).toBe('review')
    expect(bankStateTone('rejected')).toBe('danger')
    expect(bankStateTone('needs_correction')).toBe('danger')
  })

  test('does not collapse HR and payroll approval stages', () => {
    expect(bankWorkflowStageLabel('pending_hr', 'pending_hr', false)).toBe('Awaiting HR approval')
    expect(bankWorkflowStageLabel('pending_payroll', 'pending_payroll', false)).toBe('Pending payroll approval')
    expect(bankWorkflowStageLabel('approved', 'approved', false)).toBe('Ready to apply')
  })

  test('mask markers are not rendered as fields', () => {
    const rows = bankReadableFields({
      iban: 'KW**********1234',
      iban__masked: true,
      iban_last4: '1234',
      bank_name: 'NBK',
    })
    expect(rows.map((r) => r.field)).toEqual(['iban', 'bank_name'])
  })

  test('field labels are localized and fall back safely', () => {
    expect(bankFieldLabel('iban', false)).toBe('IBAN')
    expect(bankFieldLabel('account_number', true)).toBe('رقم الحساب')
    expect(bankFieldLabel('unknown_field', false)).toBe('unknown field')
  })

  test('an unrecognized state degrades to readable text instead of a wrong label', () => {
    expect(bankStateLabel('pending_review', false)).toBe('Awaiting HR review')
    expect(bankStateLabel('pending_review', true)).toBe('بانتظار مراجعة الموارد البشرية')
    expect(bankStateLabel('some_future_state', false)).toBe('some future state')
    expect(bankStateTone('some_future_state')).toBe('neutral')
  })
})

describe('BankReviewPanel', () => {
  test('shows verified and proposed separately and marks changed fields', async () => {
    await renderPanel({
      has_verified_bank: true,
      submission_state: 'pending_review',
      verified: { display: { iban: 'KW**********1111', bank_name: 'NBK' } },
      payroll_effective: { display: { iban: 'KW**********1111' }, effective_from: '2026-07-01' },
      submission: {
        request_id: 'req-1',
        submission_state: 'pending_review',
        proposed: { display: { iban: 'KW**********2222', bank_name: 'NBK' } },
      },
      comparison: {
        current_verified: { iban: 'KW**********1111', bank_name: 'NBK' },
        proposed: { iban: 'KW**********2222', bank_name: 'NBK' },
        changed_fields: ['iban'],
        is_first_submission: false,
      },
    })
    expect(screen.getByText('Currently verified')).toBeTruthy()
    expect(screen.getByText('Proposed by employee')).toBeTruthy()
    expect(screen.getByText('KW**********1111')).toBeTruthy()
    expect(screen.getByText('KW**********2222')).toBeTruthy()
    // Exactly one field differs, so exactly one "changed" marker.
    expect(screen.getAllByText('changed')).toHaveLength(1)
    expect(screen.getByText(/Payroll-effective from/)).toBeTruthy()
  })

  test('rejecting requires a reason before the action is enabled', async () => {
    await renderPanel({
      submission_state: 'pending_review',
      submission: { request_id: 'req-2', submission_state: 'pending_review', proposed: { display: { iban: 'KW1' } } },
    })
    const toggle = screen.getByRole('button', { name: /Reject \/ request correction/ })
    toggle.click()
    await waitFor(() => expect(screen.getByLabelText(/Reason/)).toBeTruthy())
    const reject = screen.getByRole('button', { name: /Return to employee/ }) as HTMLButtonElement
    expect(reject.disabled).toBe(true)
    expect(decideEmployeeEssRequest).not.toHaveBeenCalled()
  })

  test('decide and apply controls are hidden without permission', async () => {
    await renderPanel(
      {
        submission_state: 'pending_review',
        submission: { request_id: 'req-3', submission_state: 'pending_review' },
      },
      false,
    )
    expect(screen.queryByRole('button', { name: /Approve/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Reject/ })).toBeNull()
  })

  test('a first submission is labelled as such rather than as a change', async () => {
    await renderPanel({
      has_verified_bank: false,
      submission_state: 'pending_review',
      submission: { request_id: 'req-4', submission_state: 'pending_review', proposed: { display: { iban: 'KW9' } } },
      comparison: { proposed: { iban: 'KW9' }, changed_fields: ['iban'], is_first_submission: true },
    })
    expect(screen.getByText('First submission')).toBeTruthy()
    expect(screen.getByText('Nothing verified yet.')).toBeTruthy()
  })

  test('approving tells the host to refetch so onboarding cannot show stale', async () => {
    const onDecided = vi.fn()
    decideEmployeeEssRequest.mockResolvedValueOnce({ ok: true })
    await renderPanel(
      {
        submission_state: 'pending_review',
        submission: { request_id: 'req-6', submission_state: 'pending_review' },
      },
      true,
      onDecided,
    )
    screen.getByRole('button', { name: /Approve/ }).click()
    await waitFor(() => expect(onDecided).toHaveBeenCalledTimes(1))
    // Approval alone must not be presented as payroll truth.
    expect(screen.getByText(/pending payroll approval/)).toBeTruthy()
    expect(applyEmployeeEssRequest).not.toHaveBeenCalled()
  })

  test('pending payroll uses a distinct action and concurrency guard', async () => {
    decideEmployeeEssRequest.mockResolvedValueOnce({ ok: true })
    await renderPanel({
      submission_state: 'pending_review',
      submission: {
        request_id: 'req-payroll',
        state: 'pending_payroll',
        concurrency_version: 2,
        submission_state: 'pending_review',
      },
    })
    expect(screen.queryByRole('button', { name: /^Approve$/ })).toBeNull()
    screen.getByRole('button', { name: /Approve for payroll/ }).click()
    await waitFor(() => expect(decideEmployeeEssRequest).toHaveBeenCalledTimes(1))
    expect(decideEmployeeEssRequest.mock.calls[0][2]).toEqual({
      action: 'approve',
      comment: undefined,
      expected_concurrency_version: 2,
    })
  })

  test('an immediate double-click submits one decision', async () => {
    decideEmployeeEssRequest.mockResolvedValueOnce({ ok: true })
    await renderPanel({
      submission_state: 'pending_review',
      submission: {
        request_id: 'req-double',
        state: 'pending_hr',
        concurrency_version: 1,
        submission_state: 'pending_review',
      },
    })
    const approve = screen.getByRole('button', { name: /^Approve$/ })
    approve.click()
    approve.click()
    await waitFor(() => expect(decideEmployeeEssRequest).toHaveBeenCalledTimes(1))
  })

  test('applying uses a stable idempotency key so a retry cannot double-apply', async () => {
    applyEmployeeEssRequest.mockResolvedValueOnce({ ok: true })
    await renderPanel({
      submission_state: 'approved',
      submission: { request_id: 'req-7', state: 'approved', submission_state: 'approved' },
    })
    screen.getByRole('button', { name: /Apply to payroll/ }).click()
    await waitFor(() => expect(applyEmployeeEssRequest).toHaveBeenCalled())
    expect(applyEmployeeEssRequest.mock.calls[0][2]).toEqual({ idempotency_key: 'apply-req-7' })
  })

  test('payroll lock explains that the change lands next period', async () => {
    await renderPanel({
      submission_state: 'pending_review',
      submission: { request_id: 'req-5', submission_state: 'pending_review' },
      payroll_lock: { locked: true, period_status: 'processing' },
    })
    expect(screen.getByText(/next period/)).toBeTruthy()
  })
})
