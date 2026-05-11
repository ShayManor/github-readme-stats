import { useEffect, useMemo, useState } from 'react'
import { fetchUsers, type UserRow } from '../lib/dev'

function timeAgo(ts: number | null): string {
  if (!ts) return '—'
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export function UsersTable() {
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<'requests' | 'latency' | 'last_seen'>('requests')
  const [rows, setRows] = useState<UserRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    const h = window.setTimeout(() => {
      setLoading(true)
      fetchUsers(q, sort).then(r => { if (alive) { setRows(r); setLoading(false) } })
                       .catch(() => { if (alive) setLoading(false) })
    }, 200)
    return () => { alive = false; window.clearTimeout(h) }
  }, [q, sort])

  const sorted = useMemo(() => rows, [rows])

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02]">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2">
        <div className="text-sm text-white/70">Users</div>
        <div className="flex gap-2">
          <select value={sort} onChange={e => setSort(e.target.value as 'requests' | 'latency' | 'last_seen')}
                  className="rounded bg-white/[0.04] px-2 py-1 text-xs text-white/80">
            <option value="requests">requests</option>
            <option value="latency">latency</option>
            <option value="last_seen">last seen</option>
          </select>
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="search…"
                 className="rounded bg-white/[0.04] px-2 py-1 text-xs text-white/80 placeholder:text-white/30" />
        </div>
      </div>
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase text-white/40">
          <tr>
            <th className="px-4 py-2 font-normal">User</th>
            <th className="px-4 py-2 font-normal">Req 7d</th>
            <th className="px-4 py-2 font-normal">Last seen</th>
            <th className="px-4 py-2 font-normal">Top endpoint</th>
            <th className="px-4 py-2 text-right font-normal">Avg ms</th>
          </tr>
        </thead>
        <tbody>
          {loading && <tr><td colSpan={5} className="px-4 py-6 text-center text-white/40">loading…</td></tr>}
          {!loading && sorted.length === 0 && (
            <tr><td colSpan={5} className="px-4 py-6 text-center text-white/40">no users yet</td></tr>
          )}
          {sorted.map(u => (
            <tr key={u.username} className="border-t border-white/5">
              <td className="px-4 py-2 text-white/90">
                <div className="flex items-center gap-2">
                  {u.github_avatar_url
                    ? <img src={u.github_avatar_url} alt="" className="h-5 w-5 rounded-full" />
                    : <span className="inline-block h-5 w-5 rounded-full bg-white/10" />}
                  <span className="font-mono">{u.username}</span>
                </div>
              </td>
              <td className="px-4 py-2 font-mono text-white/80">{u.requests_7d.toLocaleString()}</td>
              <td className="px-4 py-2 text-white/60">{timeAgo(u.last_seen)}</td>
              <td className="px-4 py-2 font-mono text-white/60">{u.top_endpoint || '—'}</td>
              <td className="px-4 py-2 text-right font-mono text-white/80">{u.avg_latency_ms}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
