import { describe, expect, it } from 'vitest'
import { onboardingPrimaryAction, itemLooksUploaded } from './onboardingPrimaryAction'

describe('onboardingPrimaryAction', () => {
  it('reminds only for employee-owned missing items', () => {
    expect(
      onboardingPrimaryAction({
        pending_count: 2,
        next_owner_group: 'employee',
        next_item_label: 'Civil ID',
        next_item_status: 'pending',
      }),
    ).toBe('remind')
  })

  it('opens checklist for HR-owned next items', () => {
    expect(
      onboardingPrimaryAction({
        pending_count: 1,
        next_owner_group: 'hr',
        next_item_label: 'Contract signed',
        next_item_status: 'pending',
      }),
    ).toBe('open_checklist')
  })

  it('reviews when storage shows an uploaded open item', () => {
    expect(
      onboardingPrimaryAction({
        pending_count: 1,
        next_owner_group: 'employee',
        next_item_label: 'Passport',
        next_item_status: 'pending',
        next_item_storage_status: 'stored',
      }),
    ).toBe('review')
  })

  it('reviews when detail document_index has a file for the next open item', () => {
    expect(
      onboardingPrimaryAction({
        employee_key: 'E1',
        pending_count: 1,
        next_owner_group: 'employee',
        next_item_label: 'Civil ID',
        detail: {
          employee_key: 'E1',
          next_owner_group: 'employee',
          document_index: { civil_id: 'file-1' },
          pending: [{ item_id: 'civil_id', label: 'Civil ID', status: 'pending', owner: 'employee', required: true }],
        },
      }),
    ).toBe('review')
  })

  it('views details when nothing is pending', () => {
    expect(onboardingPrimaryAction({ pending_count: 0, next_item_label: null })).toBe('view_details')
  })

  it('falls back from remind when viewer cannot remind', () => {
    expect(
      onboardingPrimaryAction({
        pending_count: 1,
        next_owner_group: 'employee',
        next_item_label: 'Civil ID',
        canRemind: false,
      }),
    ).toBe('view_details')
  })

  it('does not treat empty storage as uploaded', () => {
    expect(itemLooksUploaded({ status: 'pending', storage_status: null })).toBe(false)
    expect(itemLooksUploaded({ status: 'pending', storage_status: 'not_required' })).toBe(false)
  })
})
