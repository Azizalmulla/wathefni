import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const leaveSrc = readFileSync(resolve(__dirname, './LeaveWorkspace.tsx'), 'utf8')
const postHire = readFileSync(resolve(__dirname, './PostHire.tsx'), 'utf8')
const leaveProfile = postHire.slice(
  postHire.indexOf('id="emp360-section-leave"'),
  postHire.indexOf('id="emp360-section-shifts"'),
)

describe('Leave Wave 1 refinement contract', () => {
  it('is queue-first with attention strip and demoted history chrome', () => {
    expect(leaveSrc).toContain('data-leave-queue')
    expect(leaveSrc).toContain('data-leave-attention')
    expect(leaveSrc).toContain('data-leave-pending')
    expect(leaveSrc).toContain('data-leave-history')
    expect(leaveSrc).toContain('data-leave-filters')
    expect(leaveSrc).not.toContain('<NextAction')
  })

  it('uses one primary action with secondary More menu', () => {
    expect(leaveSrc).toContain('leavePrimaryAction')
    expect(leaveSrc).toContain('data-primary-action')
    expect(leaveSrc).toContain('MoreHorizontal')
    expect(leaveSrc).toContain("primaryKind === 'approve'")
    expect(leaveSrc).toContain('confirm_leave_stale_dual_control')
    expect(leaveSrc).toContain('initiate_leave_stale_dual_control')
    expect(leaveSrc).toContain('expected_row_version')
  })

  it('keeps approve and dual-control as separate authorities', () => {
    expect(leaveSrc).toContain('approve_leave_request')
    expect(leaveSrc).toContain('initiate_leave_stale_dual_control')
    expect(leaveSrc).toContain('confirm_leave_stale_dual_control')
    expect(leaveSrc).toContain('dualConfirmBody')
    expect(leaveSrc).toContain('approveSeparate')
  })

  it('preserves unpaid honesty and non-binding balances messaging', () => {
    expect(leaveSrc).toContain('balancesBanner')
    expect(leaveSrc).toContain('unpaidNote')
    expect(leaveSrc).toContain('enforced=false')
  })

  it('demotes profile leave mutates to Open in Leave', () => {
    expect(leaveProfile).toContain('Open in Leave')
    expect(leaveProfile).not.toContain('approve_leave_request')
    expect(leaveProfile).not.toContain('reject_leave_request')
  })
})
