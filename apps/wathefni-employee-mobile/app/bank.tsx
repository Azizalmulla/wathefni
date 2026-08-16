import { useCallback, useRef, useState } from 'react'
import { Alert } from 'react-native'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'
import { ApiError } from '@/api/client'
import { approvedErrorMessage } from '@/api/errors'
import { openPrivateFile } from '@/lib/documents'
import { pickDocument, pickImageFromLibrary, UploadPickError } from '@/lib/uploadDocument'
import { errorFeedback, successFeedback, warningFeedback } from '@/native/haptics'
import { useEmployeeSafeBack } from '@/navigation/useEmployeeSafeBack'
import {
  BankErrorView,
  BankLoadingView,
  BankUnavailableView,
  BankView,
  type BankField,
  type BankFormValues,
} from '@/features/bank/BankView'
import {
  bankProblemField,
  bankProblemMessageKey,
  fieldErrorsFromApi,
  validateBankForm,
  type BankFieldErrors,
} from '@/features/bank/validation'
import type { BankEvidenceRow, BankMutationResponse, BankStatusResponse } from '@/api/types'

export default function BankScreen() {
  const { t, locale } = useI18n()
  const { request, uploadFile, downloadFile, hasFeature } = useAuth()
  const onBack = useEmployeeSafeBack()
  const queryClient = useQueryClient()
  const bankEnabled = hasFeature('bank')

  const query = useAppQuery<BankStatusResponse>(
    ['bank', locale],
    `/app/bank?locale=${encodeURIComponent(locale)}`,
    { staleTime: HIGH_CHURN_STALE_MS, enabled: bankEnabled },
  )

  const [form, setForm] = useState<BankFormValues>({})
  const [formOpen, setFormOpen] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<BankFieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [savingDraft, setSavingDraft] = useState(false)
  const [withdrawing, setWithdrawing] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [openingEvidenceId, setOpeningEvidenceId] = useState<string | null>(null)
  const [pendingEvidenceIds, setPendingEvidenceIds] = useState<string[]>([])
  const [extractionNote, setExtractionNote] = useState<string | null>(null)
  // Retrying a failed submit must reuse the same key, or one change request
  // becomes two. Cleared only after the server accepts the submission.
  const idempotencyKey = useRef<string | null>(null)
  const busy = useRef(false)
  /** Latest evidence open wins — a newer tap supersedes an in-flight open. */
  const openGeneration = useRef(0)

  const softRefreshBank = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['bank'] })
    void queryClient.invalidateQueries({ queryKey: ['onboarding'] })
  }, [queryClient])

  const applyResult = useCallback(
    (result: BankMutationResponse | { bank?: BankStatusResponse }) => {
      const next = (result as BankMutationResponse).bank
      if (next) queryClient.setQueryData(['bank', locale], next)
      void queryClient.invalidateQueries({ queryKey: ['onboarding'] })
    },
    [locale, queryClient],
  )

  const onChangeField = useCallback((field: BankField, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }))
    setFieldErrors((prev) => {
      if (!prev[field]) return prev
      const next = { ...prev }
      delete next[field]
      return next
    })
    setFormError(null)
  }, [])

  const send = useCallback(
    async (draft: boolean) => {
      if (busy.current) return
      const iban = String(form.iban || '').trim()
      const accountNumber = String(form.account_number || '').trim()
      if (!iban && !accountNumber) {
        setFieldErrors({ iban: t('bank.identifierRequired') })
        setFormError(t('bank.identifierRequired'))
        return
      }
      const formProblem = validateBankForm(form, query.data?.validation_scheme)
      if (formProblem) {
        const message = t(bankProblemMessageKey(formProblem))
        setFieldErrors({ [bankProblemField(formProblem)]: message })
        setFormError(message)
        return
      }
      busy.current = true
      setFormError(null)
      setFieldErrors({})
      if (draft) setSavingDraft(true)
      else setSubmitting(true)
      if (!idempotencyKey.current) {
        idempotencyKey.current = `bank-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
      }
      try {
        const result = await request<BankMutationResponse>('/app/bank/requests', {
          method: 'POST',
          json: {
            iban: iban || undefined,
            account_number: accountNumber || undefined,
            bank_name: String(form.bank_name || '').trim() || undefined,
            account_holder: String(form.account_holder || '').trim() || undefined,
            branch: String(form.branch || '').trim() || undefined,
            swift: String(form.swift || '').trim() || undefined,
            idempotency_key: idempotencyKey.current,
            draft,
            evidence_ids: pendingEvidenceIds.length ? pendingEvidenceIds : undefined,
          },
        })
        idempotencyKey.current = null
        successFeedback()
        applyResult(result)
        // Sensitive values never linger in component state after they are sealed.
        setForm({})
        setFieldErrors({})
        setFormError(null)
        setFormOpen(false)
        setPendingEvidenceIds([])
        setExtractionNote(null)
        Alert.alert(
          draft ? t('bank.draftSavedTitle') : t('bank.submittedTitle'),
          draft ? t('bank.draftSavedMessage') : t('bank.submittedMessage'),
        )
      } catch (error) {
        // Keep entered values so the employee can correct the failing field.
        if (error instanceof ApiError && error.code === 'bank_account_invalid') {
          const nextErrors = fieldErrorsFromApi(error.problems, error.fields, t)
          setFieldErrors(nextErrors)
          setFormError(approvedErrorMessage(error, t))
        } else if (error instanceof ApiError && error.code === 'bank_request_already_active') {
          setFormError(approvedErrorMessage(error, t))
        } else {
          setFormError(approvedErrorMessage(error, t))
        }
      } finally {
        busy.current = false
        setSavingDraft(false)
        setSubmitting(false)
      }
    },
    [applyResult, form, pendingEvidenceIds, query.data?.validation_scheme, request, t],
  )

  const onSubmitDraft = useCallback(async () => {
    const requestId = query.data?.submission?.request_id
    if (!requestId || busy.current) return
    busy.current = true
    setSubmitting(true)
    try {
      const result = await request<BankMutationResponse>(
        `/app/bank/requests/${encodeURIComponent(requestId)}/submit`,
        { method: 'POST' },
      )
      successFeedback()
      applyResult(result)
    } catch (error) {
      errorFeedback()
      Alert.alert(t('common.error'), approvedErrorMessage(error, t))
    } finally {
      busy.current = false
      setSubmitting(false)
    }
  }, [applyResult, query.data, request, t])

  const onWithdraw = useCallback(() => {
    const requestId = query.data?.submission?.request_id
    if (!requestId || busy.current) return
    warningFeedback()
    Alert.alert(t('bank.withdrawConfirmTitle'), t('bank.withdrawConfirmMessage'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('bank.withdraw'),
        style: 'destructive',
        onPress: () => {
          void (async () => {
            busy.current = true
            setWithdrawing(true)
            try {
              const result = await request<BankMutationResponse>(
                `/app/bank/requests/${encodeURIComponent(requestId)}/withdraw`,
                { method: 'POST' },
              )
              applyResult(result)
            } catch (error) {
              errorFeedback()
              Alert.alert(t('common.error'), approvedErrorMessage(error, t))
            } finally {
              busy.current = false
              setWithdrawing(false)
            }
          })()
        },
      },
    ])
  }, [applyResult, query.data, request, t])

  const onUploadEvidence = useCallback(async () => {
    const requestId = query.data?.submission?.request_id
    if (uploading) return
    try {
      const picked = await chooseEvidenceFile(t)
      if (!picked) return
      setUploading(true)
      const parameters: Record<string, string> = {}
      if (requestId) parameters.request_id = requestId
      const transfer = uploadFile('/app/bank/evidence', picked, parameters)
      const uploaded = (await transfer.promise) as import('@/api/types').BankEvidenceUploadResponse
      successFeedback()
      const evidenceId = String(uploaded?.evidence_id || '')
      if (evidenceId) {
        setPendingEvidenceIds((prev) => (prev.includes(evidenceId) ? prev : [...prev, evidenceId]))
      }
      const proposed = uploaded?.proposed_fields || uploaded?.extraction?.proposed || {}
      const nextForm: BankFormValues = { ...form }
      for (const key of ['iban', 'account_number', 'bank_name', 'account_holder', 'branch', 'swift'] as const) {
        const value = String(proposed[key] || '').trim()
        // Never prefill masked placeholders into the editable form.
        if (value && !value.includes('*')) nextForm[key] = value
      }
      setForm(nextForm)
      setFormOpen(true)
      setFieldErrors({})
      setFormError(null)
      setExtractionNote(extractionNoteFromUpload(uploaded, t))
      // Soft refresh — never block the form open on a full bank refetch.
      softRefreshBank()
    } catch (error) {
      if (error instanceof UploadPickError) {
        Alert.alert(t('onboarding.permissionTitle'), t('onboarding.permissionMessage'))
        return
      }
      errorFeedback()
      Alert.alert(t('common.error'), approvedErrorMessage(error, t))
      // Fail open: still let the employee enter details manually.
      setFormOpen(true)
      setExtractionNote(t('bank.extraction.manualFallback'))
    } finally {
      setUploading(false)
    }
  }, [form, query.data?.submission?.request_id, softRefreshBank, t, uploadFile, uploading])

  const onOpenEvidence = useCallback(
    async (evidence: BankEvidenceRow) => {
      const generation = ++openGeneration.current
      setOpeningEvidenceId(evidence.evidence_id)
      try {
        const handle = await openPrivateFile(
          `/app/bank/evidence/${encodeURIComponent(evidence.evidence_id)}`,
          evidence.filename || `bank-evidence-${evidence.evidence_id}`,
          evidence.evidence_id,
          downloadFile,
        )
        if (generation !== openGeneration.current) return
        await handle.completed
      } catch (error) {
        if (generation !== openGeneration.current) return
        errorFeedback()
        Alert.alert(t('common.error'), approvedErrorMessage(error, t))
      } finally {
        if (generation === openGeneration.current) {
          setOpeningEvidenceId(null)
        }
      }
    },
    [downloadFile, t],
  )

  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await query.refetch()
    } finally {
      setRefreshing(false)
    }
  }, [query])

  if (!bankEnabled) {
    return <BankUnavailableView onBack={onBack} />
  }

  if (query.isLoading && !query.data) return <BankLoadingView onBack={onBack} />
  if (!query.data) {
    // Controlled rollout and company opt-out are explicit states, not errors:
    // show why the screen is unavailable instead of a retry loop.
    const code = String((query.error as { code?: string } | null)?.code || '')
    if (code === 'bank_ess_disabled' || code === 'bank_ess_not_allowlisted' || code === 'ess_v5_disabled') {
      return <BankUnavailableView onBack={onBack} />
    }
    return <BankErrorView onRetry={() => void query.refetch()} onBack={onBack} />
  }

  return (
    <BankView
      data={query.data}
      form={form}
      onChangeField={onChangeField}
      formOpen={formOpen}
      onCloseForm={() => {
        setForm({})
        setFieldErrors({})
        setFormError(null)
        setFormOpen(false)
        setExtractionNote(null)
      }}
      onOpenForm={() => {
        const display = query.data?.submission?.proposed?.display || {}
        const next: BankFormValues = {}
        for (const key of ['iban', 'account_number', 'bank_name', 'account_holder', 'branch', 'swift'] as const) {
          const value = String(display[key] || '').trim()
          // Display masking uses '*'; never put masked values into inputs.
          if (value && !value.includes('*')) next[key] = value
        }
        setForm(next)
        setFieldErrors({})
        setFormError(null)
        setExtractionNote(t('bank.extraction.correctHint'))
        setFormOpen(true)
      }}
      submitting={submitting}
      savingDraft={savingDraft}
      withdrawing={withdrawing}
      uploading={uploading}
      onSubmit={() => void send(false)}
      onSaveDraft={() => void send(true)}
      onSubmitDraft={() => void onSubmitDraft()}
      onWithdraw={onWithdraw}
      onUploadEvidence={() => void onUploadEvidence()}
      onOpenEvidence={(evidence) => void onOpenEvidence(evidence)}
      openingEvidenceId={openingEvidenceId}
      refreshing={refreshing}
      onRefresh={() => void onRefresh()}
      onBack={onBack}
      fieldErrors={fieldErrors}
      formError={formError}
      extractionNote={extractionNote}
    />
  )
}

async function chooseEvidenceFile(t: (key: string) => string) {
  const source = await new Promise<'library' | 'files' | null>((resolve) => {
    Alert.alert(
      t('bank.uploadCertificate'),
      t('bank.evidenceHint'),
      [
        { text: t('onboarding.photoLibrary'), onPress: () => resolve('library') },
        { text: t('onboarding.browseFiles'), onPress: () => resolve('files') },
        { text: t('common.cancel'), style: 'cancel', onPress: () => resolve(null) },
      ],
      { cancelable: true, onDismiss: () => resolve(null) },
    )
  })
  if (source === 'library') return pickImageFromLibrary()
  if (source === 'files') return pickDocument()
  return null
}

function extractionNoteFromUpload(
  uploaded: import('@/api/types').BankEvidenceUploadResponse | null | undefined,
  t: (key: string) => string,
): string {
  const extraction = uploaded?.extraction
  const proposed = uploaded?.proposed_fields || extraction?.proposed || {}
  const status = String(extraction?.status || '')
  const docType = String(extraction?.document_type || '').toLowerCase()
  const hasIban = Boolean(String(proposed.iban || '').trim())
  const warnings = extraction?.warnings || []
  const wrongType =
    Boolean(extraction?.wrong_document_type) ||
    warnings.includes('wrong_document_type') ||
    (Boolean(docType) && !['bank_certificate', 'iban_letter', 'unknown', ''].includes(docType))

  if (wrongType) return t('bank.extraction.wrongDocument')
  if (extraction?.unreadable_reason || status === 'failed') return t('bank.extraction.manualFallback')
  if (!hasIban && (status === 'extracted' || status === 'partial' || status === 'low_confidence' || Object.keys(proposed).length > 0 || extraction?.missing_iban)) {
    return t('bank.extraction.missingIban')
  }
  if (status === 'partial' || (extraction?.uncertain && hasIban)) return t('bank.extraction.partial')
  if (uploaded?.needs_manual_fallback || extraction?.needs_manual_fallback) {
    return t('bank.extraction.manualFallback')
  }
  if (extraction?.uncertain) return t('bank.extraction.uncertain')
  if (Object.keys(proposed).length) return t('bank.extraction.confirmHint')
  return t('bank.extraction.manualFallback')
}
