/**
 * Turning a stored phone number into something the phone app can dial.
 *
 * The roster stores digits, sometimes as an 8-digit Kuwait local number and
 * sometimes already carrying the 965 country code. Both have to dial from a
 * device that may be roaming, so a recognised Kuwait number is normalised to
 * full international form. A shape we do not recognise returns null rather than
 * a guess: a `tel:` link built from the wrong digits dials someone else.
 *
 * This adds no data. It only makes a number the employee is already shown
 * actionable.
 */
const KUWAIT_CODE = '965'
const KUWAIT_LOCAL_LENGTH = 8

export function telHref(phone: string | null | undefined): string | null {
  const digits = String(phone || '').replace(/\D/g, '')
  if (!digits) return null
  if (digits.length === KUWAIT_LOCAL_LENGTH) return `tel:+${KUWAIT_CODE}${digits}`
  if (digits.startsWith(KUWAIT_CODE) && digits.length === KUWAIT_CODE.length + KUWAIT_LOCAL_LENGTH) {
    return `tel:+${digits}`
  }
  // Long enough to be a real international number, short enough not to be an
  // identifier that happened to be numeric.
  if (digits.length >= 9 && digits.length <= 15) return `tel:+${digits}`
  return null
}

/** Display form: grouped Kuwait local digits, otherwise the digits as stored. */
export function displayPhone(phone: string | null | undefined): string {
  const digits = String(phone || '').replace(/\D/g, '')
  if (!digits) return ''
  const local =
    digits.startsWith(KUWAIT_CODE) && digits.length === KUWAIT_CODE.length + KUWAIT_LOCAL_LENGTH
      ? digits.slice(KUWAIT_CODE.length)
      : digits
  if (local.length === KUWAIT_LOCAL_LENGTH) return `${local.slice(0, 4)} ${local.slice(4)}`
  return digits
}
