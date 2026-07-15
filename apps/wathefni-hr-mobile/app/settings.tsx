import { useAuth } from '@/auth/AuthProvider'
import { SettingsView } from '@/features/settings/SettingsView'
import { useLocale } from '@/i18n'

export default function SettingsRoute() {
  const { me, refreshMe, signOut, signOutAll } = useAuth()
  const { locale, setLocale } = useLocale()
  if (!me) return null
  return (
    <SettingsView
      me={me}
      onLocale={() => void setLocale(locale === 'ar' ? 'en' : 'ar')}
      onRefresh={() => void refreshMe()}
      onSignOut={() => void signOut()}
      onSignOutAll={() => void signOutAll()}
    />
  )
}
