import { useEffect, useState } from 'react'
import { fetchGrowth, type Growth } from '../lib/dev'

type Mode = 'daily' | 'weekly'

export function GrowthChart() {
  const [data, setData] = useState<Growth | null>(null)
  const [mode, setMode] = useState<Mode>('daily')
  useEffect(() => { fetchGrowth().then(setData).catch(() => {}) }, [])

  const points = data ? (mode === 'daily' ? data.daily : data.weekly) : []
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
      {points.length === 0 ? (
        <div className="text-xs text-white/40">loading…</div>
      ) : (
        <div className="space-y-4">
          <Line label="Requests" values={requests} labels={labels} stroke="#60a5fa" />
          <Line label="Unique users" values={users} labels={labels} stroke="#a78bfa" />
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

function Line({ label, values, labels, stroke }: {
  label: string; values: number[]; labels: string[]; stroke: string
}) {
  const width = 600
  const height = 70
  const max = Math.max(1, ...values)
  const stepX = width / Math.max(1, values.length - 1)
  const total = values.reduce((a, b) => a + b, 0)
  const latest = values[values.length - 1] ?? 0
  const pts = values.map((v, i) => {
    const x = i * stepX
    const y = height - (v / max) * (height - 4) - 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  const area = `0,${height} ${pts} ${width},${height}`
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="text-white/60">{label}</span>
        <span className="font-mono tabular-nums text-white/40">
          latest <span className="text-white/80">{latest.toLocaleString()}</span>
          <span className="ml-3">total <span className="text-white/80">{total.toLocaleString()}</span></span>
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" preserveAspectRatio="none">
        <polyline points={area} fill={stroke} fillOpacity="0.08" stroke="none" />
        <polyline points={pts} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <div className="flex justify-between font-mono text-[10px] text-white/30">
        <span>{labels[0]}</span>
        <span>{labels[labels.length - 1]}</span>
      </div>
    </div>
  )
}
