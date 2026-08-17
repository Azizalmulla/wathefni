import { useAuth } from '@hr/auth/AuthProvider'
import { SignInView } from '@hr/features/auth/SignInView'
import { usePrincipalGate } from '@/principals/PrincipalGate'

export default function SignInRoute() {
  const { signIn } = useAuth()
  const { refreshAvailability } = usePrincipalGate()
  return (
    <SignInView
      onSignIn={async (email, password, companyCode) => {
        await signIn(email, password, companyCode)
        await refreshAvailability()
      }}
    />
  )
}
