import { ApiError } from '@/api/client'
import { activeAppLocale } from '@/i18n'

type Translate = (key: string) => string

const MACHINE_CODE = /^[a-z][a-z0-9_]*$/

function isCalmCopy(text: string | undefined | null): text is string {
  const value = String(text || '').trim()
  if (!value) return false
  if (MACHINE_CODE.test(value)) return false
  if (/^document_validation_/i.test(value)) return false
  if (/\b422\b/.test(value)) return false
  return true
}

function localeCorrection(error: ApiError, locale: 'en' | 'ar'): string | null {
  const preferred = locale === 'ar' ? error.messageAr : error.messageEn
  if (isCalmCopy(preferred)) return preferred.trim()
  if (isCalmCopy(error.message)) return error.message.trim()
  const other = locale === 'ar' ? error.messageEn : error.messageAr
  if (isCalmCopy(other)) return other.trim()
  return null
}

/** Document-validation correction copy — never surfaces raw API codes. */
export function approvedErrorMessage(error: unknown, t: Translate): string {
  if (!(error instanceof ApiError)) return t('error.generic')
  if (error.code.startsWith('document_validation_')) {
    const locale = activeAppLocale()
    const correction = localeCorrection(error, locale)
    if (correction) return correction
    if (error.code.includes('unreadable') ||
      error.code.includes('too_blurry') ||
      error.code.includes('document_not_fully_visible') ||
      error.code.includes('glare_or_shadow') ||
      error.code.includes('missing_side') ||
      error.code.includes('missing_page') ||
      error.code.includes('file_too_small')) {
      return t('onboarding.validationUnclear')
    }
    return t('onboarding.validationMismatch')
  }
  switch (error.code) {
    case 'network_error':
      return t('access.offline.message')
    case 'employee_app_disabled':
      return t('access.app_disabled.message')
    case 'company_disabled':
      return t('access.company_disabled.message')
    case 'company_archived':
      return t('access.company_archived.message')
    case 'employee_app_not_enabled_for_company':
      return t('access.company_app_disabled.message')
    case 'employee_app_not_allowlisted':
      return t('access.not_allowlisted.message')
    case 'account_inactive':
      return t('access.employee_inactive.message')
    case 'app_access_revoked':
      return t('access.access_reset.message')
    case 'app_auth_failed':
    case 'stale_session_epoch':
      return t('access.session_expired.message')
    case 'app_activation_failed':
      return t('auth.invalidCode')
    case 'too_many_attempts':
      return t('auth.tooManyAttempts')
    case 'already_activated':
      return t('auth.alreadyActivated')
    case 'employee_feature_disabled':
      return t('feature.unavailable.message')
    case 'leave_type_not_available':
      return t('leave.typeUnavailable')
    case 'leave_already_started':
      return t('leave.cancelAlreadyStarted')
    case 'leave_already_taken':
      return t('leave.cancelAlreadyTaken')
    case 'unsupported_file_type':
      return t('upload.unsupportedType')
    case 'empty_file':
      return t('upload.emptyFile')
    case 'file_too_large':
      return t('upload.fileTooLarge')
    case 'mime_mismatch_or_invalid_content':
      return t('upload.invalidContent')
    case 'item_required':
    case 'item_not_found':
      return t('upload.itemUnavailable')
    case 'bank_account_invalid': {
      const correction = localeCorrection(error, activeAppLocale())
      return correction || t('bank.validation.kwIbanFormat')
    }
    case 'bank_request_already_active': {
      const correction = localeCorrection(error, activeAppLocale())
      return correction || t('bank.validation.requestActive')
    }
    case 'account_identifier_required':
      return t('bank.identifierRequired')
    case 'storage_failed':
    case 'upload_failed':
      return t('upload.failed')
    case 'document_not_found':
    case 'document_file_unavailable':
      return t('documents.unavailable')
    case 'download_failed':
      return t('documents.downloadFailed')
    default:
      return t('error.generic')
  }
}

export function documentValidationSuccessMessage(
  validation: {
    hr_review_recommended?: boolean
    message?: string
    message_en?: string
    message_ar?: string
  } | null | undefined,
  t: Translate,
): string | null {
  if (!validation?.hr_review_recommended) return null
  const locale = activeAppLocale()
  const preferred = locale === 'ar' ? validation.message_ar : validation.message_en
  if (isCalmCopy(preferred)) {
    // Soft-gate uncertain: keep advisory tone (submitted + HR will check).
    return t('onboarding.uploadNeedsReview')
  }
  if (isCalmCopy(validation.message)) return t('onboarding.uploadNeedsReview')
  return t('onboarding.uploadNeedsReview')
}
