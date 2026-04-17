import { useState, useEffect } from 'react'
import DOMPurify from 'dompurify'
import type { WidgetSettings } from '../App'

function sanitizeSvg(raw: string): string {
  return DOMPurify.sanitize(raw, {
    USE_PROFILES: { svg: true, svgFilters: true },
    ADD_TAGS: ['image', 'use', 'clipPath', 'defs', 'style', 'animate', 'animateTransform', 'feDropShadow', 'filter', 'linearGradient', 'stop'],
    ADD_ATTR: ['xlink:href', 'href', 'clip-path', 'viewBox', 'preserveAspectRatio', 'xmlns', 'xmlns:xlink', 'rx', 'ry', 'attributeName', 'from', 'to', 'dur', 'fill', 'stroke-dasharray', 'stroke-dashoffset', 'stroke-linecap', 'stroke-linejoin', 'dominant-baseline', 'letter-spacing', 'opacity', 'filter', 'flood-color', 'flood-opacity', 'stdDeviation'],
  })
}

type Props = {
  username: string
  settings: WidgetSettings
  fetchDone: boolean
  fetchError: string | null
  onBack: () => void
}

export function ResultScreen({ username, settings, fetchDone, fetchError, onBack }: Props) {
  const [svgContent, setSvgContent] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [generated, setGenerated] = useState(false)

  // Generate the final SVG once fetch completes
  useEffect(() => {
    if (!fetchDone) return
    if (generated) return

    setLoading(true)
    fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username,
        theme: settings.theme,
        widgets: settings.widgets,
        widget_order: ['grade', 'impact', 'collaborators', 'focus', 'languages', 'achievements'],
        custom_tags: settings.customTags.length ? settings.customTags : undefined,
        hidden_languages: settings.hiddenLanguages.length ? settings.hiddenLanguages : undefined,
        achievements: settings.achievements.filter(a => a.title.trim()),
        widget_settings: settings.widgetSettings,
        format: 'svg',
      }),
    })
      .then(r => r.text())
      .then(svg => {
        // SVG is sanitized via DOMPurify before rendering
        setSvgContent(sanitizeSvg(svg))
        setLoading(false)
        setGenerated(true)
      })
      .catch(() => setLoading(false))
  }, [fetchDone])

  const waiting = !fetchDone

  return (
    <div className="min-h-screen flex flex-col items-center animate-fade-in-up">
      {/* Back button */}
      <div className="w-full max-w-2xl px-6 pt-6">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          Back
        </button>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center px-6 pb-12">
        <h2 className="font-serif text-2xl text-gray-800 tracking-tight mb-1">
          Your Widget
        </h2>

        {waiting ? (
          <div className="mt-8 flex flex-col items-center gap-3">
            <div className="w-5 h-5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin-slow" />
            <p className="text-xs text-gray-400">Generating with real data...</p>
          </div>
        ) : loading ? (
          <div className="mt-8 flex flex-col items-center gap-3">
            <div className="w-5 h-5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin-slow" />
            <p className="text-xs text-gray-400">Rendering...</p>
          </div>
        ) : (
          <>
            {fetchError && (
              <p className="text-[10px] text-amber-500 mb-4">
                Could not fetch live data — showing demo widget
              </p>
            )}
            {!fetchError && (
              <p className="text-xs text-gray-400 mb-6">
                Generated with real data
              </p>
            )}
            {/* SVG content is sanitized with DOMPurify.sanitize() before rendering */}
            <div dangerouslySetInnerHTML={{ __html: svgContent }} />
          </>
        )}
      </div>
    </div>
  )
}
