import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const postHire = readFileSync(resolve(__dirname, './PostHire.tsx'), 'utf8')
const pageStart = postHire.indexOf('function AttendancePage(')
const pageEnd = postHire.indexOf('// --- Leave', pageStart)
const pageSrc = postHire.slice(pageStart, pageEnd)
const boardSrc = readFileSync(resolve(__dirname, './AttendanceDailyBoard.tsx'), 'utf8')
const opsSrc = readFileSync(resolve(__dirname, './AttendanceOpsPanel.tsx'), 'utf8')

describe('Attendance Wave 1 refinement contract', () => {
  it('is board-first with compact header, date chrome, and attention strip', () => {
    expect(pageSrc).toContain('attendance-board')
    expect(pageSrc).toContain('attendance-date-chrome')
    expect(pageSrc).toContain('AttendanceAttentionStrip')
    expect(pageSrc).toContain('Understand today’s attendance')
    expect(pageSrc).not.toContain('<NextAction')
    expect(pageSrc).not.toContain('AttendanceOverviewStats')
  })

  it('removes competing board Correct / Mark absent mutation paths', () => {
    expect(pageSrc).not.toContain('AttendanceCorrectionRow')
    expect(pageSrc).not.toContain('correct_attendance_record')
    expect(pageSrc).not.toContain('mark_attendance_absent')
    expect(boardSrc).not.toContain('onMarkAbsent')
    expect(boardSrc).not.toContain('onToggleCorrect')
    expect(boardSrc).not.toContain('Save correction')
    expect(boardSrc).toContain('onResolve')
  })

  it('keeps Ops request → dual review → apply as the sole correction authority', () => {
    expect(pageSrc).toContain('AttendanceOpsPanel')
    expect(opsSrc).toContain('requestAttendanceOpsCorrection')
    expect(opsSrc).toContain('reviewAttendanceOpsCase')
    expect(opsSrc).toContain('applyAttendanceOpsCase')
    expect(opsSrc).toContain('expected_row_version')
    expect(opsSrc).toContain('dual_pending')
    expect(opsSrc).toContain('Approve confirms the decision. Apply writes the new attendance version.')
    expect(opsSrc).toContain('attendance-exception-row')
    expect(opsSrc).toContain('compact')
  })

  it('moves Capture / Import / Export behind collapsed Operations', () => {
    expect(pageSrc).toContain('attendance-operations')
    expect(pageSrc).toContain('Show Operations')
    expect(pageSrc).toMatch(/operationsOpen[\s\S]*AttendanceCaptureOpsPanel/)
    expect(pageSrc).toMatch(/operationsOpen[\s\S]*Import from device|operationsOpen[\s\S]*copy\.import/)
    // Capture must not mount ahead of the board on first paint
    const boardIdx = pageSrc.indexOf('attendance-board')
    const opsIdx = pageSrc.indexOf('AttendanceOpsPanel')
    const operationsIdx = pageSrc.indexOf('attendance-operations')
    const captureIdx = pageSrc.indexOf('AttendanceCaptureOpsPanel')
    expect(boardIdx).toBeGreaterThan(-1)
    expect(opsIdx).toBeGreaterThan(boardIdx)
    expect(operationsIdx).toBeGreaterThan(opsIdx)
    expect(captureIdx).toBeGreaterThan(operationsIdx)
  })
})
