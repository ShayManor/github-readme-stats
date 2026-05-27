import { useEffect, useState } from 'react'
import { fetchGrowth, type Growth } from '../lib/dev'

type Mode = 'daily' | 'weekly'

export function GrowthChart() {
  const [data, setData] = useState<Growth | null>(null)
  const [mode, setMode] = useState<Mode>('daily')
  useEffect(() => { fetchGrowth().then(setData).catch(() => {}) }, [])

  // Trim leading empty buckets so the chart starts at the first day/week
  // with traffic instead of e.g. four weeks of zeros from before the
  // service went live.
  const rawPoints = data ? (mode === 'daily' ? data.daily : data.weekly) : []
  const firstActive = rawPoints.findIndex(p => p.requests > 0 || p.users > 0)
  const points = firstActive >= 0 ? rawPoints.slice(firstActive) : []
  const labels = points.map(p => 'day' in p ? p.day : p.week)
  const requests = points.map(p => p.requests)
  const users = points.map(p => p.users)

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm text-white/70">Growth</div>
        <div className="flex gap-1 text-xs">
          <Tab active={mode === 'daily'} onClick={() => setMode('daily')}>day · 30</Tab>
          <Tab active={mode === 'weekly'} onClick={() => setMode('weekly')}>week · 12</Tab>
        </div>
      </div>
      {!data ? (
        <div className="text-xs text-white/40">loading…</div>
      ) : points.length === 0 ? (
        <div className="text-xs text-white/40">no traffic yet</div>
      ) : (
        <div className="space-y-4">
          <Line label="Requests" values={requests} labels={labels} mode={mode} stroke="#60a5fa" />
          <Line label="Unique users" values={users} labels={labels} mode={mode} stroke="#a78bfa" />
        </div>
      )}
    </div>
  )
}

function Tab({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`rounded px-2 py-0.5 font-mono transition ${
        active ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'
      }`}
    >
      {children}
    </button>
  )
}

function Line({ label, values, labels, mode, stroke }: {
  label: string; values: number[]; labels: string[]; mode: Mode; stroke: string
}) {
  const width = 600
  const height = 70
  const max = Math.max(1, ...values)
  const n = values.length
  const stepX = n > 1 ? width / (n - 1) : 0
  const total = values.reduce((a, b) => a + b, 0)
  const latest = values[n - 1] ?? 0
  const xy = values.map((v, i) => {
    const x = n > 1 ? i * stepX : width / 2
    const y = height - (v / max) * (height - 4) - 2
    return { x, y }
  })
  const pts = xy.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  // Sealed area polygon: only valid when we have a real line (n >= 2).
  const area = n > 1 ? `0,${height} ${pts} ${width},${height}` : ''
  const ticks = pickTicks(labels, Math.min(6, n))

  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="text-white/60">{label}</span>
        <span className="font-mono tabular-nums text-white/40">
          latest <span className="text-white/80">{latest.toLocaleString()}</span>
          <span className="ml-3">total <span className="text-white/80">{total.toLocaleString()}</span></span>
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height + 10}`} className="w-full" preserveAspectRatio="none">
        {area && <polyline points={area} fill={stroke} fillOpacity="0.08" stroke="none" />}
        {n > 1 && (
          <polyline points={pts} fill="none" stroke={stroke} strokeWidth={1.5}
                    strokeLinecap="round" strokeLinejoin="round"
                    vectorEffect="non-scaling-stroke" />
        )}
        {n === 1 && (
          <circle cx={xy[0].x} cy={xy[0].y} r={3} fill={stroke} />
        )}
        {ticks.map(t => {
          const x = n > 1 ? t.idx * stepX : width / 2
          return (
            <line key={`tick-${t.idx}`} x1={x} x2={x} y1={height} y2={height + 3}
                  stroke="rgb(255 255 255 / 0.15)" strokeWidth={1}
                  vectorEffect="non-scaling-stroke" />
          )
        })}
      </svg>
      <div className="relative mt-1 h-3">
        {ticks.map(t => (
          <span key={`label-${t.idx}`}
                className="absolute -translate-x-1/2 whitespace-nowrap font-mono text-[10px] text-white/40"
                style={{ left: n > 1 ? `${(t.idx / (n - 1)) * 100}%` : '50%' }}>
            {formatTick(t.label, mode)}
          </span>
        ))}
      </div>
    </div>
  )
}

function pickTicks(labels: string[], n: number): { idx: number; label: string }[] {
  if (labels.length === 0 || n <= 0) return []
  if (labels.length <= n) return labels.map((label, idx) => ({ idx, label }))
  const out: { idx: number; label: string }[] = []
  for (let i = 0; i < n; i++) {
    const idx = Math.round((i * (labels.length - 1)) / (n - 1))
    out.push({ idx, label: labels[idx] })
  }
  return out
}

function formatTick(label: string, mode: Mode): string {
  if (mode === 'daily') {
    // "2026-05-27" -> "05-27"
    return label.length >= 10 ? label.slice(5) : label
  }
  // "2026-W21" -> "W21"
  const parts = label.split('-')
  return parts[1] || label
}
