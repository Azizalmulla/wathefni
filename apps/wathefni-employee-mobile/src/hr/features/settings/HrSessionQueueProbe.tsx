import { useCallback, useEffect, useState } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import * as Updates from 'expo-updates'
import { useQueryClient } from '@tanstack/react-query'

import { mobileApi } from '@hr/api/mobile'
import { useAuth } from '@hr/auth/AuthProvider'
import { kuwaitToday } from '@/lib/format'
import { colors, font, spacing, typeScaling } from '@/theme'
import { useI18n, readingEdgeAlign } from '@/i18n'

type ProbeRow = {
  surface: string
  raw: number
  total: number | null
  rendered: number
  visqa: number
  error?: string
}

function countVisqa(items: unknown[]): number {
  return items.filter((row) => {
    const blob = JSON.stringify(row)
    return (
      blob.includes('VISQA') ||
      blob.includes('W2B-SYNTH') ||
      blob.includes('W2G-SYNTH') ||
      blob.includes('9655280101') ||
      blob.includes('9655238102') ||
      blob.includes('9655248103')
    )
  }).length
}

/**
 * Live session + queue probe for VisQA / empty-queue diagnosis.
 * Read-only — no demo data, no mutations.
 */
export function HrSessionQueueProbe() {
  const { me, request } = useAuth()
  const client = useQueryClient()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const [rows, setRows] = useState<ProbeRow[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const apiBase = String(process.env.EXPO_PUBLIC_API_BASE_URL || '').replace(/\/$/, '') || '—'
  const updateId = Updates.updateId || 'embedded'
  const runtimeVersion = Updates.runtimeVersion || '—'
  const channel = Updates.channel || '—'

  const run = useCallback(async () => {
    if (!me) return
    setBusy(true)
    setError(null)
    const today = kuwaitToday()
    const out: ProbeRow[] = []
    try {
      const docs = await mobileApi.documents(request, { status: 'needs_review' })
      const compliance = (docs.items || []).filter((row) => row.source !== 'onboarding')
      out.push({
        surface: 'documents',
        raw: docs.items.length,
        total: docs.total ?? null,
        rendered: compliance.length,
        visqa: countVisqa(compliance),
      })

      const tasks = await mobileApi.tasks(request, { status: 'open' })
      out.push({
        surface: 'tasks',
        raw: tasks.items.length,
        total: tasks.total ?? null,
        rendered: tasks.items.length,
        visqa: countVisqa(tasks.items),
      })

      const alerts = await mobileApi.alerts(request)
      const alertItems = (alerts.items || []).filter((row) => !row.has_task)
      out.push({
        surface: 'delivery_alerts',
        raw: alerts.items.length,
        total: alerts.total ?? null,
        rendered: alertItems.length,
        visqa: countVisqa(alertItems),
      })

      const onboarding = await mobileApi.onboarding(request)
      out.push({
        surface: 'onboarding',
        raw: onboarding.items.length,
        total: onboarding.total ?? null,
        rendered: onboarding.items.length,
        visqa: countVisqa(onboarding.items),
      })

      const attendance = await mobileApi.attendance(request, {
        start_date: today,
        end_date: today,
        status: 'exceptions',
        limit: 100,
      })
      const exceptions = (attendance.items || []).filter((row) => row.is_exception)
      out.push({
        surface: 'attendance_today',
        raw: attendance.items.length,
        total: attendance.total ?? null,
        rendered: exceptions.length,
        visqa: countVisqa(exceptions),
      })

      setRows(out)
      await client.invalidateQueries()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'probe_failed')
      setRows(null)
    } finally {
      setBusy(false)
    }
  }, [client, me, request])

  useEffect(() => {
    void run()
  }, [run])

  if (!me) return null

  return (
    <View style={styles.wrap}>
      <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.line, align]}>
        {t('hrSettings.probeApi')}: {apiBase}
      </Text>
      <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.line, align]}>
        {t('hrSettings.probeSession')}: {me.principal.email || me.principal.user_id} ·{' '}
        {me.principal.company_code} · {me.principal.role}
      </Text>
      <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.line, align]}>
        {t('hrSettings.probeUpdate')}: {channel} · {runtimeVersion} · {String(updateId).slice(0, 12)}
      </Text>
      {busy ? (
        <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.line, align]}>
          {t('hrSettings.probeRunning')}
        </Text>
      ) : null}
      {error ? (
        <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.error, align]}>
          {error}
        </Text>
      ) : null}
      {rows
        ? rows.map((row) => (
            <Text
              key={row.surface}
              maxFontSizeMultiplier={typeScaling.chip}
              style={[styles.line, align]}
            >
              {row.surface}: raw {row.raw}
              {row.total != null ? ` / total ${row.total}` : ''} → rendered {row.rendered} · VISQA{' '}
              {row.visqa}
            </Text>
          ))
        : null}
    </View>
  )
}

const styles = StyleSheet.create({
  wrap: { gap: 4, paddingVertical: spacing.sm },
  line: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
  error: { color: colors.danger, fontSize: font.tiny },
})
