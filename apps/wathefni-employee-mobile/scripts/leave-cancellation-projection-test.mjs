import assert from 'node:assert/strict'

import {
  canCancelLeaveRequest,
  leavePresentationStatus,
  partitionLeaveRequests,
} from '../src/features/leave/leaveRequests.ts'

function row(overrides = {}) {
  return {
    leave_id: 'leave-1',
    start_date: '2026-08-19',
    end_date: '2026-08-19',
    leave_type: 'annual',
    status: 'approved',
    reason: null,
    requested_at: null,
    decided_at: null,
    temporal_state: 'future',
    presentation_status: 'approved',
    can_cancel: false,
    allowed_actions: [],
    ...overrides,
  }
}

// Status alone never grants authority.
assert.equal(canCancelLeaveRequest(row({ status: 'approved' })), false)
assert.equal(canCancelLeaveRequest(row({ status: 'requested' })), false)

// Both canonical projection fields must agree; either missing/false fails closed.
assert.equal(canCancelLeaveRequest(row({ can_cancel: true, allowed_actions: ['cancel'] })), true)
assert.equal(canCancelLeaveRequest(row({ can_cancel: true, allowed_actions: [] })), false)
assert.equal(canCancelLeaveRequest(row({ can_cancel: false, allowed_actions: ['cancel'] })), false)

const pastApproved = row({
  leave_id: 'past-approved',
  start_date: '2026-08-01',
  end_date: '2026-08-02',
  temporal_state: 'completed',
  presentation_status: 'completed',
  can_cancel: false,
  allowed_actions: [],
})
assert.equal(pastApproved.status, 'approved')
assert.equal(leavePresentationStatus(pastApproved), 'completed')
const partitioned = partitionLeaveRequests([pastApproved, row({ leave_id: 'future' })])
assert.deepEqual(partitioned.history.map((item) => item.leave_id), ['past-approved'])
assert.deepEqual(partitioned.current.map((item) => item.leave_id), ['future'])

console.log('PASS mobile Leave cancellation projection contract')
