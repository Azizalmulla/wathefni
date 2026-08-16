import { createContext, useContext, type ReactNode } from 'react'

export const PLATFORM_BRAND = 'OctoHR'

export type CompanyBrandIdentity = {
  company_code: string
  display_name?: string | null
  display_name_en?: string | null
  display_name_ar?: string | null
  logo_url?: string | null
}

type ResolvedCompanyBrand = {
  name: string
  logoUrl: string | null
  isTenantBrand: boolean
}

const CompanyBrandContext = createContext<CompanyBrandIdentity | null>(null)
const OLD_PLATFORM_BRAND = /\bwathefni\b|وظفني|وظّفني|وثفني|وثّفني/i

function clean(value: unknown): string {
  return String(value ?? '').trim()
}

function safeLogoUrl(value: unknown): string | null {
  const raw = clean(value)
  if (!raw) return null
  try {
    const parsed = new URL(raw)
    if (parsed.protocol !== 'https:' || !parsed.hostname || parsed.username || parsed.password) return null
    return parsed.toString()
  } catch {
    return null
  }
}

export function resolveCompanyBrand(
  identity: CompanyBrandIdentity | null | undefined,
  locale: string,
): ResolvedCompanyBrand {
  if (!identity) return { name: PLATFORM_BRAND, logoUrl: null, isTenantBrand: false }

  const localized = locale === 'ar'
    ? [identity.display_name_ar, identity.display_name_en, identity.display_name]
    : [identity.display_name_en, identity.display_name, identity.display_name_ar]
  const name = localized.map(clean).find((candidate) => candidate && !OLD_PLATFORM_BRAND.test(candidate))

  if (!name) return { name: PLATFORM_BRAND, logoUrl: null, isTenantBrand: false }
  return {
    name,
    logoUrl: safeLogoUrl(identity.logo_url),
    isTenantBrand: name !== PLATFORM_BRAND,
  }
}

export function CompanyBrandProvider({
  identity,
  children,
}: {
  identity: CompanyBrandIdentity | null | undefined
  children: ReactNode
}) {
  return (
    <CompanyBrandContext.Provider value={identity || null}>
      {children}
    </CompanyBrandContext.Provider>
  )
}

export function useCompanyBrandIdentity(): CompanyBrandIdentity | null {
  return useContext(CompanyBrandContext)
}
