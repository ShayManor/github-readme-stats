import DOMPurify from 'dompurify'
import { useMemo, useState } from 'react'

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
  const [copied, setCopied] = useState(false)
  const embedUrl = `${window.location.origin}/api/${encodeURIComponent(username)}`
  const embedSnippet = `![${username}](${embedUrl})`

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(embedSnippet)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center animate-fade-in-up">
      <div className="w-full max-w-3xl px-6 pt-6">
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

      <div className="flex-1 flex flex-col items-center justify-center px-6 pb-12 w-full max-w-3xl">
        <h2 className="font-serif text-3xl text-gray-800 tracking-tight mb-2">
          Your Widget
        </h2>

        {generating && (
          <div className="mt-10 flex flex-col items-center gap-3">
            <div className="w-6 h-6 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin-slow" />
            <p className="text-xs text-gray-400">Generating with real data…</p>
          </div>
        )}

        {!generating && generateError && (
          <div className="mt-10 flex flex-col items-center gap-3">
            <p className="text-sm text-red-500">{generateError}</p>
          </div>
        )}

        {!generating && !generateError && safeSvg && (
          <>
            <p className="text-xs text-gray-400 mb-6">Rendered from live GitHub data</p>
            <div className="w-full rounded-2xl bg-white shadow-lg ring-1 ring-gray-200 p-6 flex justify-center">
              {/*
                Force the inline SVG to scale up to the card width. The
                composite is authored at 380px wide — without this the
                preview looked tiny on wide screens.
              */}
              <div
                className="w-full max-w-xl [&_svg]:w-full [&_svg]:h-auto"
                dangerouslySetInnerHTML={{ __html: safeSvg }}
              />
            </div>

            <div className="w-full mt-8">
              <div className="flex items-baseline justify-between mb-2">
                <p className="text-xs uppercase tracking-wider text-gray-500">Embed in your README</p>
                <button
                  onClick={copy}
                  className="text-xs text-gray-500 hover:text-gray-800 transition-colors"
                >
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>
              <pre className="bg-gray-900 text-gray-100 text-xs p-4 rounded-lg overflow-x-auto">
                {embedSnippet}
              </pre>
              <p className="text-[11px] text-gray-400 mt-2">
                GitHub requires HTTPS for README images — serve this behind a TLS
                reverse proxy or Cloudflare Tunnel if the page is on http://.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
