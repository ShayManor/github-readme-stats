import { useState, useRef, useCallback, useEffect } from 'react'
import './index.css'
import { SearchScreen } from './screens/SearchScreen'
import { WorkshopScreen } from './screens/WorkshopScreen'
import { ResultScreen } from './screens/ResultScreen'
import { AuthButton } from './components/AuthButton'
import type { WidgetData } from './lib/renderWidgets'
import { DEMO_WIDGET_DATA } from './lib/demoData'
import { fetchMe, type Me } from './lib/auth'
import { buildEmbedUrl } from './lib/settingsQuery'

export type Achievement = {
  title: string
  subtitle: string
  event_date: string
  icon: string
}

export type PerWidgetSettings = {
  grade?: { max_tags?: number }
  impact?: { line_color?: string }
  streaks?: { color?: string }
  collaborators?: { max_count?: number; bar_color?: string }
  focus?: { max_categories?: number }
  languages?: { max_languages?: number }
  achievements?: { max_items?: number }
}

export type WidgetSettings = {
  theme: string
  widgets: string[]
  widgetOrder: string[]
  impactPeriod: string
  customTags: string[]
  hiddenLanguages: string[]
  achievements: Achievement[]
  widgetSettings: PerWidgetSettings
}

const DEFAULT_SETTINGS: WidgetSettings = {
  theme: 'midnight',
  widgets: ['name', 'grade', 'impact', 'streaks', 'collaborators', 'focus', 'languages'],
  widgetOrder: ['name', 'grade', 'impact', 'streaks', 'collaborators', 'focus', 'languages', 'achievements'],
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
  // The URL we actually fetched for the preview — also the one we show as
  // the embed snippet. For owners this is /api/<u> (backed by stored
  // settings). For visitors it's /api/<u>?<query>, which round-trips their
  // Workshop edits without touching the owner's saved widget.
  const [embedUrl, setEmbedUrl] = useState<string>('')
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
    // Reset to defaults first so the form doesn't briefly show the previous
    // user's settings while we fetch this user's saved blob.
    setSettings({ ...DEFAULT_SETTINGS })

    // Hydrate the Workshop form from the user's persisted settings.
    // Backend stores snake_case keys; we map them onto the camelCase
    // state shape here. 404 (not enrolled yet) is expected — keep defaults.
    void (async () => {
      try {
        const r = await fetch(`/api/${encodeURIComponent(user)}/settings`, {
          credentials: 'include',
        })
        if (aborted.current) return
        if (!r.ok) return
        const body = await r.json().catch(() => null) as { settings?: Record<string, unknown> } | null
        const s = body?.settings
        if (!s || typeof s !== 'object') return
        setSettings(prev => {
          const next: WidgetSettings = { ...prev }
          if (typeof s.theme === 'string') next.theme = s.theme
          if (Array.isArray(s.enabled)) next.widgets = s.enabled.filter(x => typeof x === 'string') as string[]
          if (Array.isArray(s.widget_order)) next.widgetOrder = s.widget_order.filter(x => typeof x === 'string') as string[]
          if (Array.isArray(s.custom_tags)) next.customTags = s.custom_tags.filter(x => typeof x === 'string') as string[]
          if (Array.isArray(s.hidden_languages)) next.hiddenLanguages = s.hidden_languages.filter(x => typeof x === 'string') as string[]
          if (s.widget_settings && typeof s.widget_settings === 'object') {
            next.widgetSettings = s.widget_settings as PerWidgetSettings
          }
          if (Array.isArray(s.achievements)) {
            next.achievements = s.achievements
              .filter((a): a is Record<string, unknown> => !!a && typeof a === 'object')
              .map(a => ({
                title: typeof a.title === 'string' ? a.title : '',
                subtitle: typeof a.subtitle === 'string' ? a.subtitle : '',
                event_date: typeof a.event_date === 'string' ? a.event_date : '',
                icon: typeof a.icon === 'string' ? a.icon : 'trophy',
              }))
          }
          return next
        })
      } catch (e) {
        if (!aborted.current) console.warn('Settings load failed:', e)
      }
    })()

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
        if (status === 'not_found') {
          // Fetcher confirmed the user doesn't exist on GitHub.
          setFetchError('User not found')
          setFetchDone(true)
          return
        }
        if (r.status === 404) {
          // 404 without status==='not_found' means the user simply isn't
          // enrolled yet (no settings row). Keep the demo data on screen
          // and stop polling — no error to display.
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
    const isOwner = !!me.login && me.login.toLowerCase() === username.toLowerCase()
    try {
      if (isOwner) {
        // Owner path: persist settings, then force a server-side render
        // against the stored payload. The resulting /api/<u> is the embed.
        const backendSettings = {
          theme: settings.theme,
          enabled: settings.widgets,
          widget_order: settings.widgetOrder,
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

        const r = await fetch(`/api/${encodeURIComponent(username)}/generate`, {
          method: 'POST',
          credentials: 'include',
        })
        if (r.status === 404) {
          const body = await r.json().catch(() => ({} as { status?: string }))
          setGenerateError(body.status === 'not_found' ? 'User not found' : 'Not enrolled')
          return
        }
        if (!r.ok) {
          setGenerateError(`Generate failed (HTTP ${r.status})`)
          return
        }
        const cleanUrl = `${window.location.origin}/api/${encodeURIComponent(username)}`
        // Cache-bust so regenerate after settings change shows the new
        // version, not a stale browser copy. The cache-busting `t` param
        // is not read server-side (not in the allow-list) so the render
        // stays cacheable at the edge.
        const svgRes = await fetch(`${cleanUrl}?t=${Date.now()}`)
        if (!svgRes.ok) {
          setGenerateError(`SVG fetch failed (HTTP ${svgRes.status})`)
          return
        }
        setGeneratedSvg(await svgRes.text())
        setEmbedUrl(cleanUrl)
      } else {
        // Visitor path: encode Workshop edits into a query string and hit
        // the same URL we'll hand the user for their README. No owner
        // settings are written. The backend renders ad-hoc against the
        // fetcher's cached payload for this user.
        const url = buildEmbedUrl(window.location.origin, username, settings)
        // Same cache-bust trick — unknown query params are ignored by the
        // sanitizer, so this doesn't alter the rendered output.
        const svgRes = await fetch(`${url}${url.includes('?') ? '&' : '?'}t=${Date.now()}`)
        if (svgRes.status === 404) {
          setGenerateError('User not enrolled — ask them to sign in and generate first')
          return
        }
        if (!svgRes.ok) {
          setGenerateError(`SVG fetch failed (HTTP ${svgRes.status})`)
          return
        }
        setGeneratedSvg(await svgRes.text())
        setEmbedUrl(url)
      }
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
      <div className="fixed right-4 top-4 z-50">
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
          embedUrl={embedUrl}
          onBack={handleBack}
          onRegenerate={handleGenerate}
        />
      )}
    </div>
  )
}
