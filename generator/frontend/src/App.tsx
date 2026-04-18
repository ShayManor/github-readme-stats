import { useState, useRef, useCallback, useEffect } from 'react'
import './index.css'
import { SearchScreen } from './screens/SearchScreen'
import { WorkshopScreen } from './screens/WorkshopScreen'
import { ResultScreen } from './screens/ResultScreen'
import type { WidgetData } from './lib/renderWidgets'
import { DEMO_WIDGET_DATA } from './lib/demoData'

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
  const [step, setStep] = useState<Step>('search')
  const [username, setUsername] = useState('')
  const [settings, setSettings] = useState<WidgetSettings>({ ...DEFAULT_SETTINGS })
  const [widgetData, setWidgetData] = useState<WidgetData | null>(null)
  const [isDemo, setIsDemo] = useState(false)
  const [fetchDone, setFetchDone] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)
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

  const startFetch = useCallback((user: string) => {
    stopPolling()
    aborted.current = false
    pollStart.current = Date.now()
    setFetchDone(false)
    setFetchError(null)
    // Show demo data immediately so Workshop is interactive while the worker builds.
    setWidgetData(DEMO_WIDGET_DATA)
    setIsDemo(true)

    const poll = async () => {
      if (aborted.current) return
      try {
        const r = await fetch(`/api/${encodeURIComponent(user)}/data`)
        if (aborted.current) return
        const body = await r.json().catch(() => ({} as { status?: string; data?: WidgetData }))
        const status = body.status

        if (r.status === 200 && status === 'ready' && body.data) {
          setWidgetData(body.data)
          setIsDemo(false)
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

  const handleGenerate = () => {
    setStep('result')
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
          isDemo={isDemo}
          widgetData={widgetData}
        />
      )}
      {step === 'result' && (
        <ResultScreen
          username={username}
          settings={settings}
          fetchDone={fetchDone}
          fetchError={fetchError}
          widgetData={widgetData}
          onBack={handleBack}
        />
      )}
    </div>
  )
}
