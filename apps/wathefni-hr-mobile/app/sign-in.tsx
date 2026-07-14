import { useAuth } from '@/auth/AuthProvider'
import { SignInView } from '@/features/auth/SignInView'

export default function SignInRoute() {
  const { signIn } = useAuth()
  return <SignInView onSignIn={signIn} />
}
