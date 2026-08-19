/**
 * Customer-visible OctoHR branding for HR Web.
 *
 * Rewrites legacy product names in prose. Does not rename technical identifiers:
 * storage keys, API fields, sender ids (`wathefni`), env vars, battery keys,
 * tenant company codes (`WATHEFNI`), or operational hosts (`*.wathefni.ai`).
 */

const PROTECTED_HOST = /[A-Za-z0-9._%+-]*wathefni\.ai[A-Za-z0-9.-]*/gi
const LEGACY_LATIN_BRAND = /(?<![A-Za-z0-9_])Wathefni(?![A-Za-z0-9_])/g
const LEGACY_LATIN_BRAND_LOWER = /(?<![A-Za-z0-9_])wathefni(?![A-Za-z0-9_])/g
const LEGACY_ARABIC_BRAND = /واثقني|وظفني|وظّفني|وثفني|وثّفني|وطّفني/g

export const PUBLIC_PRODUCT_NAME = 'OctoHR'

export function customerVisibleBrandCopy(value: string | null | undefined): string {
  const text = String(value || '')
  if (!text) return ''
  const held: string[] = []
  const protectedText = text.replace(PROTECTED_HOST, (match) => {
    held.push(match)
    return `\u0000BRAND${held.length - 1}\u0000`
  })
  const rewritten = protectedText
    .replace(LEGACY_LATIN_BRAND, PUBLIC_PRODUCT_NAME)
    .replace(LEGACY_LATIN_BRAND_LOWER, PUBLIC_PRODUCT_NAME)
    .replace(LEGACY_ARABIC_BRAND, PUBLIC_PRODUCT_NAME)
  return rewritten.replace(/\u0000BRAND(\d+)\u0000/g, (_, index) => held[Number(index)] || '')
}

export function customerVisibleBatteryName(value: string | null | undefined): string {
  const cleaned = customerVisibleBrandCopy(value).trim()
  return cleaned || `${PUBLIC_PRODUCT_NAME} Ability Assessment`
}
