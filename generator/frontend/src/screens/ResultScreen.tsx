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
  // Owner renders embed as /api/<u>; visitors get /api/<u>?<their settings>.
  // We display whichever URL was used to produce the SVG above, so the
  // snippet they copy matches what they're previewing.
  embedUrl: string
  // 'building' means the SVG above is still the "Building @user's
  // widget…" placeholder; the parent is auto-polling for the real one.
  widgetStatus: 'ready' | 'building' | 'not_found' | 'rate_limited'
  onBack: () => void
  onRegenerate: () => void
  // Manual refetch — same fetch the auto-poll runs, exposed as a button
  // so the user has a way to nudge it if they want.
  onRefresh: () => void
}

export function ResultScreen({ username, generating, generatedSvg, generateError, embedUrl, widgetStatus, onBack, onRegenerate, onRefresh }: Props) {
  const safeSvg = useMemo(() => (generatedSvg ? sanitizeSvg(generatedSvg) : ''), [generatedSvg])
  const [copied, setCopied] = useState(false)
  const fallbackUrl = `${window.location.origin}/api/${encodeURIComponent(username)}`
  const finalUrl = embedUrl || fallbackUrl
  const embedSnippet = `[![${username}](${finalUrl})](${window.location.origin})`

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
      <div className="w-full max-w-3xl px-6 pt-6 flex items-center justify-between">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          Back
        </button>
        <button
          onClick={onRegenerate}
          disabled={generating}
          title="Re-render the widget from the most recent cached data. Does not re-fetch from GitHub."
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={generating ? 'animate-spin-slow' : ''}
          >
            <path d="M21 12a9 9 0 1 1-3-6.7L21 8" />
            <path d="M21 3v5h-5" />
          </svg>
          {generating ? 'Regenerating…' : 'Regenerate'}
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
            {widgetStatus === 'building' && (
              <div className="mt-6 flex items-center gap-2 text-xs text-gray-500">
                <div className="w-3 h-3 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin-slow" />
                <span>Still building on the server — this page will update automatically when ready.</span>
                <button
                  onClick={onRefresh}
                  className="ml-2 px-2 py-1 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100 transition-colors"
                >
                  Check now
                </button>
              </div>
            )}
            <div className="w-full mt-6 rounded-2xl bg-white shadow-lg ring-1 ring-gray-200 p-6 flex justify-center">
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
              <p className="text-xs uppercase tracking-wider text-gray-500 mb-2">Embed in your README</p>
              <div className="relative">
                <pre className="bg-gray-900 text-gray-100 text-xs p-4 pr-12 rounded-lg overflow-x-auto">
                  {embedSnippet}
                </pre>
                <button
                  onClick={copy}
                  title={copied ? 'Copied!' : 'Copy'}
                  className="absolute top-2 right-2 p-1.5 rounded-md text-gray-400 hover:text-gray-100 hover:bg-gray-800 transition-colors"
                >
                  {copied ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
