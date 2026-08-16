import { describe, expect, it } from 'vitest'
import { leavePrimaryAction } from './leavePrimaryAction'

describe('leavePrimaryAction', () => {
  it('approves decidable requested leave', () => {
    expect(leavePrimaryAction({ status: 'requested', next_action: 'decide', canDecide: true })).toBe('approve')
  })

  it('starts dual for stale needs_review even when next is decide', () => {
    expect(leavePrimaryAction({ status: 'needs_review', next_action: 'decide', canDecide: true })).toBe('start_dual')
  })

  it('confirms dual when second leg is pending', () => {
    expect(
      leavePrimaryAction({ status: 'needs_review', dual_control_status: 'pending_second', canDecide: true }),
    ).toBe('confirm_dual')
  })

  it('cancels approved leave that may cancel', () => {
    expect(leavePrimaryAction({ status: 'approved', next_action: 'may_cancel', canDecide: true })).toBe('cancel')
  })

  it('views details for needs_info and read-only viewers', () => {
    expect(leavePrimaryAction({ status: 'needs_info', canDecide: true })).toBe('view_details')
    expect(leavePrimaryAction({ status: 'requested', canDecide: false })).toBe('view_details')
  })
})
