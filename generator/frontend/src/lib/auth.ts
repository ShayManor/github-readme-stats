export type Me = { login: string | null; avatar_url?: string }

export async function fetchMe(): Promise<Me> {
  const r = await fetch('/api/auth/me', { credentials: 'include' })
  if (!r.ok) return { login: null }
  return r.json() as Promise<Me>
}

export function signInUrl(next?: string): string {
  const n = next ?? (window.location.pathname + window.location.search)
  return `/api/auth/github/login?next=${encodeURIComponent(n)}`
}

export async function signOut(): Promise<void> {
  await fetch('/api/auth/logout', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
  })
}
