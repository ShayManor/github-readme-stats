// Per-username edit token issued by the backend at enrollment. Presented
// as `Authorization: Bearer` on mutating endpoints (PATCH settings,
// POST refresh). Stored in localStorage so a reload keeps the user in
// control of their own profile.
//
// Without this token the backend rejects mutations with HTTP 401. Token is
// only surfaced on the FIRST enroll for a given username — re-hitting the
// enroll path for an existing user returns no token, so we never blow away
// a previously-saved token.

const STORAGE_PREFIX = 'grs:edit_token:'

const keyFor = (username: string) => STORAGE_PREFIX + username.toLowerCase()

export function getEditToken(username: string): string | null {
  if (!username) return null
  try {
    return window.localStorage.getItem(keyFor(username))
  } catch {
    return null
  }
}

export function saveEditToken(username: string, token: string | null | undefined): void {
  if (!username || !token) return
  try {
    window.localStorage.setItem(keyFor(username), token)
  } catch {
    // localStorage can throw in private mode — fall through silently.
  }
}

export function authHeaders(username: string): Record<string, string> {
  const t = getEditToken(username)
  return t ? { Authorization: `Bearer ${t}` } : {}
}
