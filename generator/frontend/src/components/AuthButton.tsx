import type { Me } from '../lib/auth'
import { signInUrl, signOut } from '../lib/auth'

export function AuthButton({ me, onChange }: { me: Me; onChange: (m: Me) => void }) {
  if (!me.login) {
    return (
      <a className="auth-btn" href={signInUrl()}>
        Sign in with GitHub
      </a>
    )
  }
  return (
    <div className="auth-chip">
      {me.avatar_url && <img src={me.avatar_url} alt="" className="auth-avatar" />}
      <span>{me.login}</span>
      <button onClick={async () => { await signOut(); onChange({ login: null }) }}>
        Sign out
      </button>
    </div>
  )
}
