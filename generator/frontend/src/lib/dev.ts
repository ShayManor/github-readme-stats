// Read helpers for the /dev dashboard. All four endpoints require a
// Basic-auth session that the browser establishes via the WWW-Authenticate
// challenge the first time the SPA hits /api/dev/summary.

export type Summary = {
  requests_7d: number
  active_users_7d: number
  p50_ms: number
  p95_ms: number
  renders_7d: number
  avg_render_ms: number
  daily_requests: { day: string; count: number }[]
}

export type UserRow = {
  username: string
  requests_7d: number
  last_seen: number | null
  avg_latency_ms: number
  top_endpoint: string
  github_avatar_url: string | null
}

export type LatencyRow = {
  endpoint: string
  count: number
  p50: number
  p95: number
  p99: number
}

export type Health = {
  edge_cache_hit_rate: number
  fetcher_error_rate: number
  events_dropped_24h: number
  oldest_event_ts: number | null
}

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: 'include' })
  if (r.status === 401) throw new Error('unauthorized')
  if (r.status === 503) throw new Error('dashboard_disabled')
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return (await r.json()) as T
}

export const fetchSummary = () => getJSON<Summary>('/api/dev/summary')
export const fetchUsers = (q = '', sort = 'requests') =>
  getJSON<UserRow[]>(`/api/dev/users?q=${encodeURIComponent(q)}&sort=${sort}`)
export const fetchLatency = () => getJSON<LatencyRow[]>('/api/dev/latency')
export const fetchHealth = () => getJSON<Health>('/api/dev/health')
