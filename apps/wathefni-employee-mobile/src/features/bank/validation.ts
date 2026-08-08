import type { BankField, BankFormValues } from './BankView'

export type BankFormProblem =
  | 'iban_characters'
  | 'kw_iban_format'
  | 'account_number_format'
  | 'swift_format'

export type BankFieldErrors = Partial<Record<BankField, string>>

function schemeKey(scheme: unknown): string {
  if (typeof scheme === 'string') return scheme.toLowerCase()
  if (scheme && typeof scheme === 'object') {
    const record = scheme as Record<string, unknown>
    return String(record.key || record.scheme || '').toLowerCase()
  }
  return ''
}

/**
 * Fast client correction only. The backend registry remains authoritative and
 * performs country length/checksum validation before storing or applying.
 */
export function validateBankForm(
  form: BankFormValues,
  scheme: unknown,
): BankFormProblem | null {
  const iban = String(form.iban || '').trim().toUpperCase()
  const compactIban = iban.replace(/\s+/g, '')
  const account = String(form.account_number || '').trim().replace(/[\s-]+/g, '')
  const swift = String(form.swift || '').trim().replace(/\s+/g, '').toUpperCase()

  if (iban && !/^[A-Z0-9\s]+$/.test(iban)) return 'iban_characters'
  if (schemeKey(scheme) === 'kw_iban' && iban) {
    if (!/^KW[0-9]{2}[A-Z0-9]{26}$/.test(compactIban)) return 'kw_iban_format'
  }
  if (account && !/^[A-Z0-9]{4,34}$/i.test(account)) return 'account_number_format'
  if (swift && !/^[A-Z0-9]{8}([A-Z0-9]{3})?$/.test(swift)) return 'swift_format'
  return null
}

export function bankProblemMessageKey(problem: BankFormProblem): string {
  switch (problem) {
    case 'iban_characters':
      return 'bank.validation.ibanCharacters'
    case 'kw_iban_format':
      return 'bank.validation.kwIbanFormat'
    case 'account_number_format':
      return 'bank.validation.accountNumber'
    case 'swift_format':
      return 'bank.validation.swift'
  }
}

export function bankProblemField(problem: BankFormProblem): BankField {
  switch (problem) {
    case 'iban_characters':
    case 'kw_iban_format':
      return 'iban'
    case 'account_number_format':
      return 'account_number'
    case 'swift_format':
      return 'swift'
  }
}

/** Map backend problem/field codes onto form fields. */
export function fieldErrorsFromApi(
  problems: string[] | undefined,
  fields: string[] | undefined,
  t: (key: string) => string,
): BankFieldErrors {
  const errors: BankFieldErrors = {}
  const targets =
    fields?.length
      ? fields
      : (problems || []).flatMap((problem) => {
          if (problem.startsWith('iban_') || problem === 'account_identifier_required') return ['iban']
          if (problem.startsWith('account_number_')) return ['account_number']
          if (problem.startsWith('swift_')) return ['swift']
          return []
        })
  for (const field of targets) {
    if (field === 'iban') errors.iban = t('bank.validation.kwIbanFormat')
    if (field === 'account_number') errors.account_number = t('bank.validation.accountNumber')
    if (field === 'swift') errors.swift = t('bank.validation.swift')
  }
  if (!Object.keys(errors).length && problems?.length) {
    errors.iban = t('bank.validation.kwIbanFormat')
  }
  return errors
}
