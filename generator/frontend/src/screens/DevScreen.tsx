import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { fetchSummary, type Summary } from '../lib/dev'
import { StatCards } from '../components/StatCards'
import { UsersTable } from '../components/UsersTable'
import { LatencyChart } from '../components/LatencyChart'
import { HealthStrip } from '../components/HealthStrip'
import { GrowthChart } from '../components/GrowthChart'

const REFRESH_MS = 15_000

export function DevScreen() {
  const [s, setS] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  useEffect(() => {
    let alive = true
    const load = () =>
      fetchSummary()
        .then(v => { if (!alive) return; setS(v); setError(null); setLastRefresh(new Date()) })
        .catch(e => { if (alive) setError(e.message || 'error') })
    load()
    const h = window.setInterval(load, REFRESH_MS)
    return () => { alive = false; window.clearInterval(h) }
  }, [])

  if (error === 'dashboard_disabled') {
    return (
      <Shell>
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/[0.06] p-6 text-amber-200">
          The /dev dashboard is not configured on this deploy
          (set DEV_DASHBOARD_USER and DEV_DASHBOARD_PASSWORD).
        </div>
      </Shell>
    )
  }
  if (error === 'unauthorized') {
    return (
      <Shell>
        <div className="text-white/60">Sign in to view the dashboard. Reload to retry.</div>
      </Shell>
    )
  }

  return (
    <Shell lastRefresh={lastRefresh}>
      {s ? <StatCards s={s} /> : <div className="text-white/40">loading…</div>}
      <div className="mt-6">
        <GrowthChart />
      </div>
      <div className="mt-6">
        <UsersTable />
      </div>
      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
        <LatencyChart />
        <HealthStrip />
      </div>
    </Shell>
  )
}

function Shell({ children, lastRefresh }: { children: ReactNode; lastRefresh?: Date }) {
  return (
    <div className="min-h-screen bg-[#0b0d10] px-6 py-6 text-white">
      <div className="mx-auto max-w-6xl">
        <header className="mb-6 flex items-baseline justify-between">
          <h1 className="font-mono text-lg text-white/90">/dev · gh-stats analytics</h1>
          {lastRefresh && (
            <div className="text-xs text-white/40">
              last refresh {lastRefresh.toLocaleTimeString()}
            </div>
          )}
        </header>
        {children}
      </div>
    </div>
  )
}
