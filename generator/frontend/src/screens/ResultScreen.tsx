import DOMPurify from 'dompurify'
import { useMemo } from 'react'

function sanitizeSvg(raw: string): string {
  return DOMPurify.sanitize(raw, {
    USE_PROFILES: { svg: true, svgFilters: true },
    ADD_TAGS: ['image', 'use', 'clipPath', 'defs', 'style', 'animate', 'animateTransform', 'feDropShadow', 'filter', 'linearGradient', 'stop'],
    ADD_ATTR: ['xlink:href', 'href', 'clip-path', 'viewBox', 'preserveAspectRatio', 'xmlns', 'xmlns:xlink', 'rx', 'ry', 'attributeName', 'from', 'to', 'dur', 'fill', 'stroke-dasharray', 'stroke-dashoffset', 'stroke-linecap', 'stroke-linejoin', 'dominant-baseline', 'letter-spacing', 'opacity', 'filter', 'flood-color', 'flood-opacity', 'stdDeviation'],
  })
}

type Props = {
  username: string
  generating: boolean
  generatedSvg: string | null
  generateError: string | null
  onBack: () => void
}

export function ResultScreen({ username, generating, generatedSvg, generateError, onBack }: Props) {
  const safeSvg = useMemo(() => (generatedSvg ? sanitizeSvg(generatedSvg) : ''), [generatedSvg])
  const embedUrl = `${window.location.origin}/api/${encodeURIComponent(username)}`
  const embedSnippet = `![${username}](${embedUrl})`

  return (
    <div className="min-h-screen flex flex-col items-center animate-fade-in-up">
      <div className="w-full max-w-2xl px-6 pt-6">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          Back
        </button>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center px-6 pb-12 w-full max-w-2xl">
        <h2 className="font-serif text-2xl text-gray-800 tracking-tight mb-1">
          Your Widget
        </h2>

        {generating && (
          <div className="mt-8 flex flex-col items-center gap-3">
            <div className="w-5 h-5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin-slow" />
            <p className="text-xs text-gray-400">Generating with real data…</p>
          </div>
        )}

        {!generating && generateError && (
          <div className="mt-8 flex flex-col items-center gap-3">
            <p className="text-xs text-red-500">{generateError}</p>
          </div>
        )}

        {!generating && !generateError && safeSvg && (
          <>
            <p className="text-xs text-gray-400 mb-6">Rendered from live data</p>
            <div className="w-full flex justify-center" dangerouslySetInnerHTML={{ __html: safeSvg }} />
            <div className="w-full mt-8">
              <p className="text-xs text-gray-500 mb-2">Embed in your README:</p>
              <pre className="bg-gray-100 text-xs p-3 rounded overflow-x-auto">{embedSnippet}</pre>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
