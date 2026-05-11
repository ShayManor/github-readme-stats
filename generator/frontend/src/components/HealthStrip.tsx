import { useEffect, useState } from 'react'
import { fetchHealth, type Health } from '../lib/dev'

export function HealthStrip() {
  const [h, setH] = useState<Health | null>(null)
  useEffect(() => { fetchHealth().then(setH).catch(() => {}) }, [])
  if (!h) return null
  const pct = (n: number) => `${(n * 100).toFixed(1)}%`
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-3 text-sm text-white/70">Health</div>
      <div className="grid grid-cols-3 gap-3 text-center">
        <Pill label="Edge cache hit" value={pct(h.edge_cache_hit_rate)} />
        <Pill label="Fetch error" value={pct(h.fetcher_error_rate)} tone={h.fetcher_error_rate > 0.05 ? 'warn' : 'ok'} />
        <Pill label="Events dropped 24h" value={h.events_dropped_24h.toLocaleString()}
              tone={h.events_dropped_24h > 0 ? 'warn' : 'ok'} />
      </div>
    </div>
  )
}

function Pill({ label, value, tone = 'ok' }: { label: string; value: string; tone?: 'ok' | 'warn' }) {
  const color = tone === 'warn' ? 'text-amber-400' : 'text-emerald-400'
  return (
    <div className="rounded bg-white/[0.03] px-2 py-2">
      <div className="text-xs text-white/40">{label}</div>
      <div className={`mt-1 font-mono text-lg ${color}`}>{value}</div>
    </div>
  )
}
