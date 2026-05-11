import { useEffect, useState } from 'react'
import { fetchLatency, type LatencyRow } from '../lib/dev'

export function LatencyChart() {
  const [rows, setRows] = useState<LatencyRow[]>([])
  useEffect(() => { fetchLatency().then(setRows).catch(() => {}) }, [])

  const max = Math.max(1, ...rows.map(r => r.p95))

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-3 text-sm text-white/70">Latency by endpoint</div>
      {rows.length === 0 && <div className="text-xs text-white/40">no traffic yet</div>}
      <div className="space-y-1.5">
        {rows.map(r => (
          <div key={r.endpoint} className="grid grid-cols-[1fr_auto] items-center gap-3 font-mono text-xs">
            <div>
              <div className="text-white/70">{r.endpoint}</div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded bg-white/[0.04]">
                <div className="h-full bg-sky-400/60" style={{ width: `${(r.p50 / max) * 100}%` }} />
                <div className="-mt-1.5 h-1.5 bg-sky-300/30" style={{ width: `${(r.p95 / max) * 100}%` }} />
              </div>
            </div>
            <div className="text-right text-white/80 tabular-nums">
              <span>{r.p50}</span><span className="text-white/30"> · </span>
              <span>{r.p95}</span><span className="text-white/30"> · </span>
              <span>{r.p99}ms</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
