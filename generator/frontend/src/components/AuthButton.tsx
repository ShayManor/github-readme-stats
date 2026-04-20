import type { Me } from '../lib/auth'
import { signInUrl, signOut } from '../lib/auth'

export function AuthButton({ me, onChange }: { me: Me; onChange: (m: Me) => void }) {
  if (!me.login) {
    return (
      <a
        href={signInUrl()}
        className="inline-flex items-center gap-2 rounded-full bg-gray-900 px-4 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-gray-800"
      >
        <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" className="h-4 w-4">
          <path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.42 7.42 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
        </svg>
        Sign in with GitHub
      </a>
    )
  }
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white py-1 pr-1 pl-3 text-sm shadow-sm">
      {me.avatar_url && (
        <img
          src={me.avatar_url}
          alt=""
          className="h-6 w-6 rounded-full object-cover"
        />
      )}
      <span className="font-medium text-gray-900">{me.login}</span>
      <button
        onClick={async () => { await signOut(); onChange({ login: null }) }}
        className="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-700 transition hover:bg-gray-200"
      >
        Sign out
      </button>
    </div>
  )
}
