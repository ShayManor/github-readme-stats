import { useMemo } from 'react'
import DOMPurify from 'dompurify'
import type { WidgetSettings } from '../App'
import { renderAllWidgets, type WidgetData } from '../lib/renderWidgets'

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
  widgetData: WidgetData | null
  onBack: () => void
}

export function ResultScreen({ username, settings, fetchDone, fetchError, widgetData, onBack }: Props) {
  const svgContent = useMemo(() => {
    if (!widgetData) return ''
    const raw = renderAllWidgets({
      data: widgetData,
      theme: settings.theme,
      widgets: settings.widgets,
      widgetOrder: ['grade', 'impact', 'collaborators', 'focus', 'languages', 'achievements'],
      achievements: settings.achievements.filter(a => a.title.trim()),
      widgetSettings: settings.widgetSettings,
      username,
    })
    return sanitizeSvg(raw)
  }, [widgetData, settings, username])

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
        ) : !svgContent ? (
          <div className="mt-8 flex flex-col items-center gap-3">
            <p className="text-[10px] text-amber-500">
              {fetchError ?? 'Could not fetch live data'}
            </p>
          </div>
        ) : (
          <>
            <p className="text-xs text-gray-400 mb-6">
              Generated with real data
            </p>
            {/* SVG sanitized via DOMPurify.sanitize() before rendering */}
            <div dangerouslySetInnerHTML={{ __html: svgContent }} />
          </>
        )}
      </div>
    </div>
  )
}
