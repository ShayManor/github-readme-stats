import { useState, useRef, useCallback, useEffect } from 'react'
import './index.css'
import { SearchScreen } from './screens/SearchScreen'
import { WorkshopScreen } from './screens/WorkshopScreen'
import { ResultScreen } from './screens/ResultScreen'
import { AuthButton } from './components/AuthButton'
import type { WidgetData } from './lib/renderWidgets'
import { DEMO_WIDGET_DATA } from './lib/demoData'
import { fetchMe, type Me } from './lib/auth'

export type Achievement = {
  title: string
  subtitle: string
  event_date: string
  icon: string
}

export type PerWidgetSettings = {
  grade?: { max_tags?: number }
  impact?: { line_color?: string }
  collaborators?: { max_count?: number; bar_color?: string }
  focus?: { max_categories?: number }
  languages?: { max_languages?: number }
  achievements?: { max_items?: number }
}

export type WidgetSettings = {
  theme: string
  widgets: string[]
  impactPeriod: string
  customTags: string[]
  hiddenLanguages: string[]
  achievements: Achievement[]
  widgetSettings: PerWidgetSettings
}

const DEFAULT_SETTINGS: WidgetSettings = {
  theme: 'midnight',
  widgets: ['grade', 'impact', 'collaborators', 'focus', 'languages'],
  impactPeriod: '6mo',
  customTags: [],
  hiddenLanguages: [],
  achievements: [],
  widgetSettings: {},
}

type Step = 'search' | 'workshop' | 'result'

const POLL_INTERVAL_MS = 2000
const POLL_TIMEOUT_MS = 120_000

export default function App() {
  const [me, setMe] = useState<Me>({ login: null })
  const [step, setStep] = useState<Step>('search')
  const [username, setUsername] = useState('')
  const [settings, setSettings] = useState<WidgetSettings>({ ...DEFAULT_SETTINGS })
  const [widgetData, setWidgetData] = useState<WidgetData | null>(null)
  const [fetchDone, setFetchDone] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)
  // Final SVG produced by POST /api/<u>/generate. Rendered on the Result
  // screen so the user sees the actual backend output, not demo data.
  const [generatedSvg, setGeneratedSvg] = useState<string | null>(null)
  const [generateError, setGenerateError] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const pollTimer = useRef<number | null>(null)
  const pollStart = useRef<number>(0)
  const aborted = useRef(false)

  const stopPolling = useCallback(() => {
    if (pollTimer.current != null) {
      window.clearTimeout(pollTimer.current)
      pollTimer.current = null
    }
  }, [])

  useEffect(() => stopPolling, [stopPolling])
  useEffect(() => { fetchMe().then(setMe) }, [])

  const startFetch = useCallback((user: string) => {
    stopPolling()
    aborted.current = false
    pollStart.current = Date.now()
    setFetchDone(false)
    setFetchError(null)
    // Show demo data immediately so Workshop is interactive while the worker builds.
    setWidgetData(DEMO_WIDGET_DATA)

    const poll = async () => {
      if (aborted.current) return
      try {
        const r = await fetch(`/api/${encodeURIComponent(user)}/data`)
        if (aborted.current) return
        const body = await r.json().catch(
          () => ({} as { status?: string; data?: WidgetData })
        )
        const status = body.status

        if (r.status === 200 && status === 'ready' && body.data) {
          setWidgetData(body.data)
          setFetchDone(true)
          return
        }
        if (r.status === 404 || status === 'not_found') {
          setFetchError('User not found')
          setFetchDone(true)
          return
        }
        if (r.status === 429 || status === 'rate_limited') {
          setFetchError('Enrollment limit reached — try again tomorrow')
          setFetchDone(true)
          return
        }
        // 202 building (or any non-terminal) — poll again until timeout.
        if (Date.now() - pollStart.current > POLL_TIMEOUT_MS) {
          setFetchError('Still building — refresh to keep waiting')
          setFetchDone(true)
          return
        }
        pollTimer.current = window.setTimeout(poll, POLL_INTERVAL_MS)
      } catch (e) {
        if (aborted.current) return
        console.warn('Data poll failed:', e)
        setFetchError('Network error')
        setFetchDone(true)
      }
    }

    poll()
  }, [stopPolling])

  const handleSearch = (user: string) => {
    setUsername(user)
    startFetch(user)
    setStep('workshop')
  }

  const handleGenerate = async () => {
    setStep('result')
    setGenerating(true)
    setGeneratedSvg(null)
    setGenerateError(null)
    try {
      // Push the user's Workshop choices to the backend BEFORE rendering.
      // The backend's /generate endpoint re-reads settings from SQLite and
      // renders with them, so without this PATCH the SVG would reflect
      // whatever was last persisted (usually the enroll-time defaults)
      // rather than the user's current selections.
      const backendSettings = {
        theme: settings.theme,
        enabled: settings.widgets,
        custom_tags: settings.customTags,
        hidden_languages: settings.hiddenLanguages,
        widget_settings: settings.widgetSettings,
        achievements: settings.achievements.filter(a => a.title.trim()),
      }
      const patchRes = await fetch(`/api/${encodeURIComponent(username)}/settings`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(backendSettings),
      })
      if (!patchRes.ok && patchRes.status !== 404) {
        setGenerateError(`Settings sync failed (HTTP ${patchRes.status})`)
        return
      }

      const r = await fetch(`/api/${encodeURIComponent(username)}/generate`, { method: 'POST' })
      if (r.status === 404) {
        const body = await r.json().catch(() => ({} as { status?: string }))
        setGenerateError(body.status === 'not_found' ? 'User not found' : 'Not enrolled')
        return
      }
      if (!r.ok) {
        setGenerateError(`Generate failed (HTTP ${r.status})`)
        return
      }
      // Fetch the backend-rendered composite SVG. Cache-bust so regenerate
      // after settings change shows the new version, not a stale browser copy.
      const svgRes = await fetch(`/api/${encodeURIComponent(username)}?t=${Date.now()}`)
      if (!svgRes.ok) {
        setGenerateError(`SVG fetch failed (HTTP ${svgRes.status})`)
        return
      }
      setGeneratedSvg(await svgRes.text())
    } catch (e) {
      console.warn('generate call failed:', e)
      setGenerateError('Network error')
    } finally {
      setGenerating(false)
    }
  }

  const handleBack = () => {
    if (step === 'result') setStep('workshop')
    else if (step === 'workshop') {
      aborted.current = true
      stopPolling()
      setStep('search')
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="header-bar">
        <AuthButton me={me} onChange={setMe} />
      </div>
      {step === 'search' && (
        <SearchScreen onSearch={handleSearch} />
      )}
      {step === 'workshop' && (
        <WorkshopScreen
          username={username}
          settings={settings}
          onSettingsChange={setSettings}
          onGenerate={handleGenerate}
          onBack={handleBack}
          fetchDone={fetchDone}
          fetchError={fetchError}
          widgetData={widgetData}
          me={me}
          onAuthChange={setMe}
        />
      )}
      {step === 'result' && (
        <ResultScreen
          username={username}
          generating={generating}
          generatedSvg={generatedSvg}
          generateError={generateError}
          onBack={handleBack}
        />
      )}
    </div>
  )
}
