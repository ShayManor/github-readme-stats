import type { ReactNode } from 'react'
import { Sparkline } from './Sparkline'
import type { Summary } from '../lib/dev'

function Card({ label, value, sub }: { label: string; value: string; sub?: ReactNode }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-white/50">{label}</div>
      <div className="mt-1 text-2xl font-mono text-white">{value}</div>
      {sub && <div className="mt-1 text-xs text-white/40">{sub}</div>}
    </div>
  )
}

export function StatCards({ s }: { s: Summary }) {
  const fmt = (n: number) => n.toLocaleString()
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
      <Card label="Requests 7d" value={fmt(s.requests_7d)}
            sub={<Sparkline values={s.daily_requests.map(d => d.count)} />} />
      <Card label="Active users 7d" value={fmt(s.active_users_7d)} />
      <Card label="p50 / p95 latency" value={`${s.p50_ms}/${s.p95_ms}ms`} />
      <Card label="Renders 7d" value={fmt(s.renders_7d)} sub={`avg ${s.avg_render_ms}ms`} />
    </div>
  )
}
