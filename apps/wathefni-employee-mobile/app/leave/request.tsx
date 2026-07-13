import { useEffect, useState } from 'react'
import { Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native'
import { useRouter } from 'expo-router'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { Button } from '@/components/ui'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { approvedErrorMessage } from '@/api/errors'
import { colors, font, radius, spacing } from '@/theme'

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/
export default function LeaveRequestScreen() {
  const { t, isRTL } = useI18n()
  const { request, me, hasFeature, can, refreshMe } = useAuth()
  const router = useRouter()
  const queryClient = useQueryClient()

  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const leaveTypes = me?.leave.types ?? []
  const [leaveType, setLeaveType] = useState(leaveTypes[0] || '')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const enabled = hasFeature('leave') && can('leave', 'request')
  const valid = DATE_RE.test(startDate) && DATE_RE.test(endDate) && Boolean(leaveType)

  useEffect(() => {
    if (!leaveType || !leaveTypes.includes(leaveType)) setLeaveType(leaveTypes[0] || '')
  }, [leaveType, leaveTypes])

  const onSubmit = async () => {
    setError(null)
    setBusy(true)
    try {
      await request('/app/leave/request', {
        method: 'POST',
        json: { start_date: startDate, end_date: endDate, leave_type: leaveType, reason: reason.trim() || null },
      })
      await queryClient.invalidateQueries({ queryKey: ['leave'] })
      router.back()
    } catch (err) {
      setError(approvedErrorMessage(err, t))
    } finally {
      setBusy(false)
    }
  }

  const align = { textAlign: isRTL ? 'right' : 'left' } as const

  if (!enabled) return <FeatureUnavailableState onRefresh={() => void refreshMe()} />

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.flex}>
      <ScrollView style={styles.screen} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.field}>
          <Text style={[styles.label, align]}>{t('leave.type')}</Text>
          <View style={styles.segment}>
            {leaveTypes.map((type) => (
              <Pressable
                key={type}
                style={[styles.segmentItem, leaveType === type && styles.segmentItemActive]}
                onPress={() => setLeaveType(type)}
                accessibilityRole="button"
              >
                <Text style={[styles.segmentText, leaveType === type && styles.segmentTextActive]}>
                  {leaveTypeLabel(type, t)}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>

        <View style={styles.field}>
          <Text style={[styles.label, align]}>{t('leave.startDate')}</Text>
          <TextInput
            value={startDate}
            onChangeText={setStartDate}
            placeholder="YYYY-MM-DD"
            placeholderTextColor={colors.subtle}
            autoCapitalize="none"
            style={[styles.input, align]}
          />
        </View>

        <View style={styles.field}>
          <Text style={[styles.label, align]}>{t('leave.endDate')}</Text>
          <TextInput
            value={endDate}
            onChangeText={setEndDate}
            placeholder="YYYY-MM-DD"
            placeholderTextColor={colors.subtle}
            autoCapitalize="none"
            style={[styles.input, align]}
          />
        </View>

        <View style={styles.field}>
          <Text style={[styles.label, align]}>{t('leave.reason')}</Text>
          <TextInput
            value={reason}
            onChangeText={setReason}
            multiline
            numberOfLines={3}
            style={[styles.input, styles.multiline, align]}
          />
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Button label={t('common.submit')} onPress={onSubmit} busy={busy} disabled={!valid} />
      </ScrollView>
    </KeyboardAvoidingView>
  )
}

function leaveTypeLabel(type: string, t: (key: string) => string): string {
  if (type === 'annual') return t('leave.typeAnnual')
  if (type === 'sick') return t('leave.typeSick')
  return t('leave.typeOther')
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.bg },
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, gap: spacing.md },
  field: { gap: spacing.xs },
  label: { fontSize: font.small, color: colors.subtle, fontWeight: '600' },
  input: {
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    fontSize: font.body,
    color: colors.text,
    minHeight: 50,
  },
  multiline: { minHeight: 90, textAlignVertical: 'top' },
  segment: { flexDirection: 'row', backgroundColor: colors.chip, borderRadius: radius.md, padding: 4, gap: 4 },
  segmentItem: { flex: 1, paddingVertical: spacing.md, borderRadius: radius.sm, alignItems: 'center' },
  segmentItemActive: { backgroundColor: colors.surface },
  segmentText: { fontSize: font.body, color: colors.subtle, fontWeight: '600' },
  segmentTextActive: { color: colors.text },
  error: { color: colors.danger, fontSize: font.small },
})
