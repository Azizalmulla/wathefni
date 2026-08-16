import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import {
  buildShiftDayMap,
  cellHasOverlap,
  ShiftsRosterBoard,
  shiftDuration,
  type ShiftBoardItem,
} from './ShiftsRosterBoard'
import type { PosthireShiftRow } from '@/types'

const workspaceSrc = readFileSync(resolve(__dirname, './ShiftsWorkspace.tsx'), 'utf8')
const rosterSrc = readFileSync(resolve(__dirname, './ShiftsRosterBoard.tsx'), 'utf8')

function shift(partial: Partial<PosthireShiftRow>): PosthireShiftRow {
  return {
    shift_id: 'shift-1',
    employee_key: 'employee-1',
    employee_name: 'Fatima Al-Sabah',
    shift_date: '2026-08-03',
    start_time: '09:00',
    end_time: '17:00',
    status: 'scheduled',
    role: 'Front desk',
    site_key: 'Marina',
    ...partial,
  }
}

const days = Array.from({ length: 7 }, (_, index) => new Date(2026, 7, 2 + index))

describe('Shifts Visual & Interaction Redesign Wave 3B', () => {
  it('uses roster lanes and renders employee identity once per row', () => {
    const html = renderToStaticMarkup(
      <ShiftsRosterBoard
        shifts={[
          shift({ shift_id: 'shift-1' }),
          shift({ shift_id: 'shift-2', shift_date: '2026-08-04', start_time: '12:00', end_time: '18:00' }),
        ]}
        days={days}
        anchor={days[2]}
        locale="en"
        isMobile={false}
        coldLoading={false}
        canManage
        selectedId={null}
        onSelect={() => undefined}
        onCreate={() => undefined}
        onSelectDay={() => undefined}
      />,
    )

    expect(rosterSrc).not.toContain('<table')
    expect(html.match(/Fatima Al-Sabah/g)).toHaveLength(1)
    expect(html).toContain('data-shifts-roster-row')
    expect(html.indexOf('09:00–17:00')).toBeLessThan(html.indexOf('Front desk'))
  })

  it('lays out overlap and overnight continuation as visual fragments', () => {
    const first = shift({ shift_id: 'first', start_time: '08:00', end_time: '14:00' })
    const second = shift({ shift_id: 'second', start_time: '10:00', end_time: '16:00' })
    expect(cellHasOverlap([first, second] as ShiftBoardItem[])).toBe(true)

    const overnight = shift({
      shift_id: 'overnight',
      start_time: '22:00',
      end_time: '06:00',
      ends_next_day: true,
    })
    expect(shiftDuration(overnight)).toBe(8 * 60)
    const map = buildShiftDayMap([overnight])
    expect(map.get('employee-1|2026-08-04')?.[0]).toMatchObject({
      shift_id: 'overnight',
      spanMarker: true,
    })
  })

  it('keeps the drawer overlay-stable and prior history rendered while refreshing', () => {
    expect(workspaceSrc).toContain('data-shifts-aside-sheet')
    expect(workspaceSrc).toContain('sm:max-w-[420px]')
    expect(workspaceSrc).toContain('fixed inset-y-0 end-0')
    expect(workspaceSrc).toContain('data-shifts-history-soft-keep')
    expect(workspaceSrc).toContain("historyLoading && 'opacity-70'")
    expect(workspaceSrc).toContain('selectedSnapshot')
  })

  it('keeps status filtering client-only and preserves Wave 1 / IQ-12 contracts', () => {
    const filterStart = workspaceSrc.indexOf('const filterKey = useMemo')
    const filterEnd = workspaceSrc.indexOf('const { data, refreshing', filterStart)
    expect(workspaceSrc.slice(filterStart, filterEnd)).not.toContain('status:')
    expect(workspaceSrc).toContain('data-shifts-iq-wave2')
    expect(workspaceSrc).toContain('data-shifts-visual-wave3b')
    expect(workspaceSrc).toContain('data-shifts-composer-org')
    expect(workspaceSrc).toContain('data-shifts-edit-org')
    expect(workspaceSrc).toContain('resultNeedsConfirmation')
  })
})

