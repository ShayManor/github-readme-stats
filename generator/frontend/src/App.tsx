import { useState, useRef, useCallback } from 'react'
import './index.css'
import { SearchScreen } from './screens/SearchScreen'
import { WorkshopScreen } from './screens/WorkshopScreen'
import { ResultScreen } from './screens/ResultScreen'
import type { WidgetData } from './lib/renderWidgets'

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

export default function App() {
  const [step, setStep] = useState<Step>('search')
  const [username, setUsername] = useState('')
  const [settings, setSettings] = useState<WidgetSettings>({ ...DEFAULT_SETTINGS })
  const [widgetData, setWidgetData] = useState<WidgetData | null>(null)
  const [fetchDone, setFetchDone] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const fetchRef = useRef<AbortController | null>(null)

  const startFetch = useCallback((user: string) => {
    if (fetchRef.current) fetchRef.current.abort()
    const ctrl = new AbortController()
    fetchRef.current = ctrl
    setFetchDone(false)
    setFetchError(null)
    setWidgetData(null)

    fetch(`/api/${encodeURIComponent(user)}/data`, { signal: ctrl.signal })
      .then(async r => {
        if (r.status === 404) throw new Error('User not found')
        if (!r.ok) throw new Error(`Fetch failed (${r.status})`)
        return r.json()
      })
      .then(json => {
        setWidgetData(json.data)
        setFetchDone(true)
      })
      .catch(e => {
        if (e.name !== 'AbortError') {
          console.warn('Fetch error:', e)
          setFetchError(e.message)
          setFetchDone(true)
        }
      })
  }, [])

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
      if (fetchRef.current) fetchRef.current.abort()
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
