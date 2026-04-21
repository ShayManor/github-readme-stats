import { useState, useMemo, type ReactNode } from 'react'
import DOMPurify from 'dompurify'
import type { WidgetSettings, Achievement, PerWidgetSettings } from '../App'
import { renderAllWidgets, type WidgetData } from '../lib/renderWidgets'
import { signInUrl } from '../lib/auth'
import type { Me } from '../lib/auth'

// Defense-in-depth: the client-rendered preview assembles SVG from
// GitHub-sourced strings (collaborator logins, repo names) and user-typed
// achievement text. renderWidgets escapes known fields, but one missed
// interpolation anywhere upstream would turn into HTML in the preview.
// DOMPurify neutralises that without affecting normal SVG shapes/styles.
const SVG_SANITIZE_CONFIG = {
  USE_PROFILES: { svg: true, svgFilters: true },
  ADD_TAGS: [
    'image', 'use', 'clipPath', 'defs', 'style', 'animate', 'animateTransform',
    'feDropShadow', 'filter', 'linearGradient', 'stop',
  ],
  ADD_ATTR: [
    'xlink:href', 'href', 'clip-path', 'viewBox', 'preserveAspectRatio',
    'xmlns', 'xmlns:xlink', 'rx', 'ry', 'attributeName', 'from', 'to', 'dur',
    'fill', 'stroke-dasharray', 'stroke-dashoffset', 'stroke-linecap',
    'stroke-linejoin', 'dominant-baseline', 'letter-spacing', 'opacity',
    'filter', 'flood-color', 'flood-opacity', 'stdDeviation',
  ],
}

// Mini-preview swatches (bg + card + accent). Flat-color swatches all read
// the same dark/light — showing the accent color is what actually separates
// Midnight (blue) from Onyx (purple) from Nord (cyan), etc.
const THEMES = [
  { id: 'midnight', label: 'Midnight', bg: '#121820', card: '#1a2230', border: '#2a3444', accent: '#58a6ff', light: false },
  { id: 'onyx',     label: 'Onyx',     bg: '#09090b', card: '#18181b', border: '#27272a', accent: '#a78bfa', light: false },
  { id: 'nord',     label: 'Nord',     bg: '#1e2433', card: '#2a3142', border: '#3d4659', accent: '#88c0d0', light: false },
  { id: 'clean',    label: 'Clean',    bg: '#ffffff', card: '#f6f8fa', border: '#d8dee4', accent: '#0969da', light: true  },
  { id: 'paper',    label: 'Paper',    bg: '#faf8f5', card: '#f5f0eb', border: '#e0d8cf', accent: '#b45309', light: true  },
]

const ALL_WIDGETS = [
  // "name" is the avatar + username header. Pinned at the top — can be
  // toggled off but never reordered. Keep this entry first.
  { id: 'name', label: 'Name' },
  { id: 'grade', label: 'Grade' },
  { id: 'impact', label: 'Impact Timeline' },
  { id: 'streaks', label: 'Streaks' },
  { id: 'collaborators', label: 'Top Collaborators' },
  { id: 'focus', label: 'Recent Focus' },
  { id: 'languages', label: 'Languages' },
  { id: 'achievements', label: 'Achievements' },
]

// Lucide-style hollow glyphs: consistent stroke-weight + viewBox so the 4
// buttons line up and read as one icon family. Kept as JSX so they inherit
// currentColor from the surrounding button's text color.
const ICON_SVG_PROPS = {
  width: 16,
  height: 16,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.75,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

const ICONS: { id: string; svg: ReactNode }[] = [
  {
    id: 'trophy',
    svg: (
      <svg {...ICON_SVG_PROPS}>
        <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" />
        <path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" />
        <path d="M4 22h16" />
        <path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22" />
        <path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22" />
        <path d="M18 2H6v7a6 6 0 0 0 12 0V2z" />
      </svg>
    ),
  },
  {
    id: 'medal',
    svg: (
      <svg {...ICON_SVG_PROPS}>
        <path d="M7.21 15 2.66 7.14a2 2 0 0 1 .13-2.2L4.4 2.8A2 2 0 0 1 6 2h12a2 2 0 0 1 1.6.8l1.6 2.14a2 2 0 0 1 .14 2.2L16.79 15" />
        <path d="M11 12 5.12 2.2" />
        <path d="m13 12 5.88-9.8" />
        <path d="M8 7h8" />
        <circle cx="12" cy="17" r="5" />
        <path d="M12 18v-2h-.5" />
      </svg>
    ),
  },
  {
    id: 'star',
    svg: (
      <svg {...ICON_SVG_PROPS}>
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26" />
      </svg>
    ),
  },
  {
    id: 'hackathon',
    svg: (
      <svg {...ICON_SVG_PROPS}>
        <polyline points="16 18 22 12 16 6" />
        <polyline points="8 6 2 12 8 18" />
      </svg>
    ),
  },
]

const COLOR_PRESETS = [
  '#58a6ff', '#a78bfa', '#4ade80', '#fb923c', '#f472b6',
  '#ff6b6b', '#38bdf8', '#facc15', '#34d399', '#c084fc',
]

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="12" height="12" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className={`transition-transform ${open ? 'rotate-90' : ''}`}
    >
      <path d="M9 18l6-6-6-6" />
    </svg>
  )
}

function NumberStepper({ value, min, max, onChange }: {
  value: number; min: number; max: number; onChange: (v: number) => void
}) {
  return (
    <div className="flex items-center gap-1.5">
      <button
        onClick={() => onChange(Math.max(min, value - 1))}
        className="w-6 h-6 rounded bg-gray-100 text-gray-500 hover:bg-gray-200 text-xs font-medium flex items-center justify-center"
      >-</button>
      <span className="text-xs text-gray-700 w-5 text-center tabular-nums">{value}</span>
      <button
        onClick={() => onChange(Math.min(max, value + 1))}
        className="w-6 h-6 rounded bg-gray-100 text-gray-500 hover:bg-gray-200 text-xs font-medium flex items-center justify-center"
      >+</button>
    </div>
  )
}

// Common "noise" languages users typically want to hide — shown even when
// the account-level detection hasn't surfaced them yet (e.g., first load).
const COMMON_HIDE_LANGS = ['HTML', 'CSS', 'SCSS', 'Jupyter Notebook', 'TeX', 'Shell', 'Dockerfile', 'Makefile', 'Batchfile']

function HiddenLanguagesPicker({
  detected, hidden, onChange,
}: {
  detected: { language: string }[]
  hidden: string[]
  onChange: (next: string[]) => void
}) {
  const seen = new Set<string>()
  const options: string[] = []
  for (const d of detected) if (d.language && !seen.has(d.language)) { seen.add(d.language); options.push(d.language) }
  for (const c of COMMON_HIDE_LANGS) if (!seen.has(c)) { seen.add(c); options.push(c) }
  // Preserve any user-set hidden that we haven't otherwise seen.
  for (const h of hidden) if (!seen.has(h)) { seen.add(h); options.push(h) }

  const toggle = (lang: string) => {
    onChange(hidden.includes(lang) ? hidden.filter(h => h !== lang) : [...hidden, lang])
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] text-gray-500">Hide languages</span>
        {hidden.length > 0 && (
          <button
            onClick={() => onChange([])}
            className="text-[10px] text-gray-400 hover:text-gray-600 transition-colors"
          >
            Clear
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-1">
        {options.map(lang => {
          const active = hidden.includes(lang)
          return (
            <button
              key={lang}
              onClick={() => toggle(lang)}
              className={`px-2 py-0.5 rounded-md text-[10px] transition-colors ${
                active
                  ? 'bg-gray-800 text-white border border-gray-800'
                  : 'bg-white text-gray-500 border border-gray-200 hover:text-gray-800 hover:border-gray-300'
              }`}
            >
              {lang}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function ColorPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex gap-1.5 flex-wrap">
      {COLOR_PRESETS.map(c => (
        <button
          key={c}
          onClick={() => onChange(c)}
          className={`w-5 h-5 rounded-full transition-all ${
            value === c ? 'ring-2 ring-offset-1 ring-gray-900' : 'hover:ring-1 hover:ring-gray-300'
          }`}
          style={{ backgroundColor: c }}
        />
      ))}
    </div>
  )
}

type Props = {
  username: string
  settings: WidgetSettings
  onSettingsChange: (s: WidgetSettings) => void
  onGenerate: () => void
  onBack: () => void
  fetchDone: boolean
  fetchError: string | null
  widgetData: WidgetData | null
  me: Me
  onAuthChange?: (m: Me) => void
}

export function WorkshopScreen({
  username,
  settings,
  onSettingsChange,
  onGenerate,
  onBack,
  fetchDone,
  fetchError,
  widgetData,
  me,
}: Props) {
  const canEdit = !!me.login && me.login.toLowerCase() === username.toLowerCase()
  const [expandedWidget, setExpandedWidget] = useState<string | null>(null)
  // Index being dragged + index currently hovered (for drop-line indicator).
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [dropIndex, setDropIndex] = useState<number | null>(null)

  // Build the render-order list from settings.widgetOrder, tolerating
  // stale persisted data: drop unknown ids, append any known widgets
  // the stored order forgot. Keeps the UI functional if ALL_WIDGETS
  // gains or loses an entry between releases.
  const knownIds = useMemo(() => new Set(ALL_WIDGETS.map(w => w.id)), [])
  // "name" is pinned at index 0 regardless of persisted order. We still keep
  // it in orderedIds so the composite-render path can find it, but the drag
  // UI below treats it as non-reorderable.
  const orderedIds = useMemo(() => {
    const seen = new Set<string>()
    const out: string[] = ['name']
    seen.add('name')
    for (const id of settings.widgetOrder) {
      if (knownIds.has(id) && !seen.has(id)) { seen.add(id); out.push(id) }
    }
    for (const w of ALL_WIDGETS) {
      if (!seen.has(w.id)) { seen.add(w.id); out.push(w.id) }
    }
    return out
  }, [settings.widgetOrder, knownIds])

  const moveWidget = (from: number, to: number) => {
    if (from === to || from < 0 || to < 0 || from >= orderedIds.length || to >= orderedIds.length) return
    // Never move "name" and never drop another widget above it (index 0).
    if (orderedIds[from] === 'name' || to === 0) return
    const next = orderedIds.slice()
    const [item] = next.splice(from, 1)
    next.splice(to, 0, item)
    onSettingsChange({ ...settings, widgetOrder: next })
  }

  const updateSetting = <K extends keyof WidgetSettings>(key: K, val: WidgetSettings[K]) => {
    onSettingsChange({ ...settings, [key]: val })
  }

  const updateWidgetSetting = (widget: keyof PerWidgetSettings, key: string, val: unknown) => {
    const current = settings.widgetSettings[widget] || {}
    const next = { ...settings.widgetSettings, [widget]: { ...current, [key]: val } }
    updateSetting('widgetSettings', next)
  }

  const getWidgetSetting = <T,>(widget: keyof PerWidgetSettings, key: string, fallback: T): T => {
    const ws = settings.widgetSettings[widget] as Record<string, unknown> | undefined
    return (ws?.[key] as T) ?? fallback
  }

  const toggleWidget = (id: string) => {
    const next = settings.widgets.includes(id)
      ? settings.widgets.filter(w => w !== id)
      : [...settings.widgets, id]
    updateSetting('widgets', next)
  }

  const toggleAdvanced = (id: string) => {
    setExpandedWidget(expandedWidget === id ? null : id)
  }

  const addAchievement = () => {
    updateSetting('achievements', [
      ...settings.achievements,
      { title: '', subtitle: '', event_date: '', icon: 'trophy' },
    ])
  }

  const updateAchievement = (idx: number, field: keyof Achievement, val: string) => {
    const next = settings.achievements.map((a, i) =>
      i === idx ? { ...a, [field]: val } : a
    )
    updateSetting('achievements', next)
  }

  const removeAchievement = (idx: number) => {
    updateSetting('achievements', settings.achievements.filter((_, i) => i !== idx))
  }

  // Render SVG client-side whenever settings change (instant, no API call)
  const svgContent = useMemo(() => {
    if (!widgetData) return ''
    const raw = renderAllWidgets({
      data: widgetData,
      theme: settings.theme,
      widgets: settings.widgets,
      widgetOrder: orderedIds,
      achievements: settings.achievements,
      widgetSettings: settings.widgetSettings,
      hiddenLanguages: settings.hiddenLanguages,
      username,
    })
    return DOMPurify.sanitize(raw, SVG_SANITIZE_CONFIG)
  }, [widgetData, settings, username, orderedIds])

  return (
    <div className="min-h-screen animate-fade-in-up">
      <div className="flex min-h-screen">
        {/* Left settings panel */}
        <div className="w-80 flex-shrink-0 border-r border-gray-200 bg-white p-6 flex flex-col overflow-y-auto">
          {/* Back */}
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 mb-6 transition-colors self-start"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
            Back
          </button>

          <div className="text-sm font-semibold text-gray-800 mb-4">{username}</div>

          {canEdit && (
            <button
              onClick={onGenerate}
              className="w-full py-3 rounded-xl bg-gray-800 text-white text-sm font-medium hover:bg-gray-700 transition-colors mb-6"
            >
              Generate →
            </button>
          )}

          {fetchError && (
            <div className="flex items-center gap-1.5 text-[10px] text-red-500 mb-6">
              <div className="w-1.5 h-1.5 rounded-full bg-red-400" />
              {fetchError}
            </div>
          )}

          {!canEdit && (
            <div className="banner">
              {me.login
                ? `Signed in as ${me.login}. You can only edit your own widget.`
                : <a href={signInUrl()}>Sign in with GitHub to edit your widget</a>}
            </div>
          )}

          {/* Theme, Widgets, Achievements editor, Generate — owner-only */}
          {canEdit && (
            <>
              {/* Theme */}
              <div className="mb-5">
                <div className="text-[10px] uppercase tracking-wider text-gray-400 font-medium mb-3">Theme</div>
                <div className="flex gap-2 flex-wrap">
                  {THEMES.map(t => (
                    <button
                      key={t.id}
                      onClick={() => updateSetting('theme', t.id)}
                      title={t.label}
                      aria-label={t.label}
                      className={`w-9 h-9 rounded-lg overflow-hidden transition-all ${
                        settings.theme === t.id
                          ? 'ring-2 ring-gray-900 ring-offset-2'
                          : t.light
                            ? 'ring-1 ring-gray-200 hover:ring-gray-300'
                            : 'hover:ring-1 hover:ring-gray-400 hover:ring-offset-1'
                      }`}
                    >
                      <svg viewBox="0 0 36 36" width="36" height="36">
                        <rect width="36" height="36" rx="8" fill={t.bg} />
                        <rect x="6" y="8" width="24" height="20" rx="4" fill={t.card} stroke={t.border} strokeWidth="1" />
                        <circle cx="11" cy="18" r="3" fill={t.accent} />
                        <rect x="16" y="16.25" width="10" height="1.75" rx="0.875" fill={t.accent} opacity="0.75" />
                        <rect x="16" y="19.75" width="7" height="1.5" rx="0.75" fill={t.accent} opacity="0.35" />
                      </svg>
                    </button>
                  ))}
                </div>
                <div className="text-[10px] text-gray-400 mt-1.5">
                  {THEMES.find(t => t.id === settings.theme)?.label}
                </div>
              </div>

              {/* Widgets with inline advanced settings */}
              <div className="mb-5">
                <div className="text-[10px] uppercase tracking-wider text-gray-400 font-medium mb-3">Widgets</div>
                <div className="flex flex-col gap-0.5">
                  {orderedIds.map((id, idx) => {
                    const w = ALL_WIDGETS.find(x => x.id === id)
                    if (!w) return null
                    const enabled = settings.widgets.includes(w.id)
                    const hasAdvanced = ['grade', 'impact', 'streaks', 'collaborators', 'focus', 'languages', 'achievements'].includes(w.id)
                    const isExpanded = expandedWidget === w.id && enabled
                    // "name" is pinned — no drag affordance, no drop lines.
                    // The dropIndex comparisons below still use the real idx
                    // so downstream rows behave normally when name is skipped.
                    const isPinned = w.id === 'name'
                    const isDragging = !isPinned && dragIndex === idx
                    const showDropLineAbove = !isPinned && idx > 0 && dropIndex === idx && dragIndex !== null && dragIndex !== idx
                    // Drop-line below the last row when dragging past the end.
                    const showDropLineBelow = !isPinned && idx === orderedIds.length - 1 && dropIndex === orderedIds.length && dragIndex !== null

                    return (
                      <div key={w.id}>
                        {showDropLineAbove && <div className="h-0.5 bg-gray-900 rounded-full mx-2 mb-0.5" />}
                        <div
                          className={`flex items-center transition-opacity ${isDragging ? 'opacity-40' : ''}`}
                          draggable={!isPinned}
                          onDragStart={isPinned ? undefined : e => {
                            setDragIndex(idx)
                            e.dataTransfer.effectAllowed = 'move'
                            // Firefox needs some payload to start a drag.
                            e.dataTransfer.setData('text/plain', String(idx))
                          }}
                          onDragOver={isPinned ? undefined : e => {
                            if (dragIndex === null) return
                            e.preventDefault()
                            e.dataTransfer.dropEffect = 'move'
                            // Midpoint decides whether the drop slot is this row
                            // or the next — gives a predictable feel between rows.
                            const rect = e.currentTarget.getBoundingClientRect()
                            const after = e.clientY - rect.top > rect.height / 2
                            const target = after ? idx + 1 : idx
                            // Landing on the drag source's own slot is a no-op;
                            // hide the indicator so it doesn't look interactive.
                            if (target === dragIndex || target === dragIndex + 1) {
                              setDropIndex(null)
                            } else {
                              setDropIndex(target)
                            }
                          }}
                          onDrop={isPinned ? undefined : e => {
                            e.preventDefault()
                            if (dragIndex === null || dropIndex === null) {
                              setDragIndex(null); setDropIndex(null); return
                            }
                            // Removing the source before inserting shifts later
                            // indices down by one — adjust the target accordingly.
                            const to = dropIndex > dragIndex ? dropIndex - 1 : dropIndex
                            moveWidget(dragIndex, to)
                            setDragIndex(null); setDropIndex(null)
                          }}
                          onDragEnd={isPinned ? undefined : () => { setDragIndex(null); setDropIndex(null) }}
                        >
                          {isPinned ? (
                            <span
                              className="px-1 text-gray-300 select-none"
                              title="Pinned — can't be reordered"
                              aria-hidden
                            >
                              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <rect x="3" y="11" width="18" height="10" rx="2"/>
                                <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                              </svg>
                            </span>
                          ) : (
                            <span
                              className="px-1 text-gray-300 hover:text-gray-500 cursor-grab active:cursor-grabbing select-none"
                              title="Drag to reorder"
                              aria-hidden
                            >
                              ⋮⋮
                            </span>
                          )}
                          <button
                            onClick={() => toggleWidget(w.id)}
                            className={`flex-1 flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-xs transition-colors text-left ${
                              enabled
                                ? 'text-gray-800 bg-gray-50'
                                : 'text-gray-400 hover:text-gray-500 hover:bg-gray-50/50'
                            }`}
                          >
                            <div className={`w-3.5 h-3.5 rounded flex-shrink-0 transition-colors ${enabled ? 'bg-gray-900' : 'bg-gray-200'}`} />
                            {w.label}
                          </button>
                          {hasAdvanced && enabled && (
                            <button
                              onClick={() => toggleAdvanced(w.id)}
                              className="p-1.5 text-gray-400 hover:text-gray-600 transition-colors"
                              title="Advanced settings"
                            >
                              <ChevronIcon open={isExpanded} />
                            </button>
                          )}
                        </div>
                        {showDropLineBelow && <div className="h-0.5 bg-gray-900 rounded-full mx-2 mt-0.5" />}

                        {isExpanded && (
                          <div className="ml-6 mt-1 mb-2 p-2.5 rounded-lg bg-gray-50/80 border border-gray-100 flex flex-col gap-2.5">
                            {w.id === 'grade' && (
                              <div className="flex items-center justify-between">
                                <span className="text-[10px] text-gray-500">Max tags</span>
                                <NumberStepper
                                  value={getWidgetSetting('grade', 'max_tags', 6)}
                                  min={1} max={20}
                                  onChange={v => updateWidgetSetting('grade', 'max_tags', v)}
                                />
                              </div>
                            )}

                            {w.id === 'impact' && (
                              <div>
                                <span className="text-[10px] text-gray-500 block mb-1.5">Line color</span>
                                <ColorPicker
                                  value={getWidgetSetting('impact', 'line_color', '#58a6ff')}
                                  onChange={v => updateWidgetSetting('impact', 'line_color', v)}
                                />
                              </div>
                            )}

                            {w.id === 'streaks' && (
                              <div>
                                <span className="text-[10px] text-gray-500 block mb-1.5">Streak color</span>
                                <ColorPicker
                                  value={getWidgetSetting('streaks', 'color', '#58a6ff')}
                                  onChange={v => updateWidgetSetting('streaks', 'color', v)}
                                />
                              </div>
                            )}

                            {w.id === 'collaborators' && (
                              <div className="flex flex-col gap-2.5">
                                <div className="flex items-center justify-between">
                                  <span className="text-[10px] text-gray-500">Max shown</span>
                                  <NumberStepper
                                    value={getWidgetSetting('collaborators', 'max_count', 5)}
                                    min={1} max={10}
                                    onChange={v => updateWidgetSetting('collaborators', 'max_count', v)}
                                  />
                                </div>
                                <div>
                                  <span className="text-[10px] text-gray-500 block mb-1.5">Bar color</span>
                                  <ColorPicker
                                    value={getWidgetSetting('collaborators', 'bar_color', '#a78bfa')}
                                    onChange={v => updateWidgetSetting('collaborators', 'bar_color', v)}
                                  />
                                </div>
                              </div>
                            )}

                            {w.id === 'focus' && (
                              <div className="flex items-center justify-between">
                                <span className="text-[10px] text-gray-500">Max categories</span>
                                <NumberStepper
                                  value={getWidgetSetting('focus', 'max_categories', 6)}
                                  min={1} max={10}
                                  onChange={v => updateWidgetSetting('focus', 'max_categories', v)}
                                />
                              </div>
                            )}

                            {w.id === 'languages' && (
                              <div className="flex flex-col gap-2.5">
                                <div className="flex items-center justify-between">
                                  <span className="text-[10px] text-gray-500">Max languages</span>
                                  <NumberStepper
                                    value={getWidgetSetting('languages', 'max_languages', 5)}
                                    min={1} max={10}
                                    onChange={v => updateWidgetSetting('languages', 'max_languages', v)}
                                  />
                                </div>
                                <HiddenLanguagesPicker
                                  detected={widgetData?.languages ?? []}
                                  hidden={settings.hiddenLanguages}
                                  onChange={next => updateSetting('hiddenLanguages', next)}
                                />
                              </div>
                            )}

                            {w.id === 'achievements' && (
                              <div className="flex flex-col gap-2.5">
                                <div className="flex items-center justify-between">
                                  <span className="text-[10px] text-gray-500">Max shown</span>
                                  <NumberStepper
                                    value={getWidgetSetting('achievements', 'max_items', 5)}
                                    min={1} max={10}
                                    onChange={v => updateWidgetSetting('achievements', 'max_items', v)}
                                  />
                                </div>
                                <div className="flex flex-col gap-2">
                                  {settings.achievements.map((ach, aidx) => (
                                    <div key={aidx} className="p-2.5 rounded-lg border border-gray-100 bg-white">
                                      <div className="flex items-center gap-1.5 mb-2">
                                        {ICONS.map(ic => {
                                          const selected = ach.icon === ic.id
                                          return (
                                            <button
                                              key={ic.id}
                                              onClick={() => updateAchievement(aidx, 'icon', ic.id)}
                                              className={`w-8 h-8 rounded-md flex items-center justify-center transition-colors ${
                                                selected
                                                  ? 'bg-gray-800 text-white border border-gray-800'
                                                  : 'bg-white text-gray-500 border border-gray-200 hover:text-gray-800 hover:border-gray-300'
                                              }`}
                                              title={ic.id}
                                              aria-pressed={selected}
                                            >
                                              {ic.svg}
                                            </button>
                                          )
                                        })}
                                        <div className="flex-1" />
                                        <button
                                          onClick={() => removeAchievement(aidx)}
                                          className="text-gray-300 hover:text-red-400 transition-colors text-xs px-1"
                                          title="Remove"
                                        >
                                          ✕
                                        </button>
                                      </div>
                                      <input
                                        type="text"
                                        value={ach.title}
                                        onChange={e => updateAchievement(aidx, 'title', e.target.value)}
                                        placeholder="Title (e.g. Hackathon Winner)"
                                        className="w-full px-2 py-1.5 rounded-md border border-gray-200 bg-white text-xs text-gray-800 placeholder:text-gray-300 focus:outline-none focus:ring-1 focus:ring-gray-300 mb-1.5"
                                      />
                                      <input
                                        type="text"
                                        value={ach.subtitle}
                                        onChange={e => updateAchievement(aidx, 'subtitle', e.target.value)}
                                        placeholder="Subtitle (e.g. 1st Place · AI Track)"
                                        className="w-full px-2 py-1.5 rounded-md border border-gray-200 bg-white text-xs text-gray-800 placeholder:text-gray-300 focus:outline-none focus:ring-1 focus:ring-gray-300 mb-1.5"
                                      />
                                      <input
                                        type="text"
                                        value={ach.event_date}
                                        onChange={e => updateAchievement(aidx, 'event_date', e.target.value)}
                                        placeholder="Date (e.g. 2025-01)"
                                        className="w-full px-2 py-1.5 rounded-md border border-gray-200 bg-white text-xs text-gray-800 placeholder:text-gray-300 focus:outline-none focus:ring-1 focus:ring-gray-300"
                                      />
                                    </div>
                                  ))}
                                  <button
                                    onClick={addAchievement}
                                    className="w-full py-2 rounded-lg border border-dashed border-gray-200 text-xs text-gray-400 hover:text-gray-600 hover:border-gray-300 transition-colors"
                                  >
                                    + Add achievement
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>

            </>
          )}
        </div>

        {/* Right preview area */}
        <div className="flex-1 flex items-start justify-center p-8 overflow-auto">
          <div className="relative">
            {svgContent ? (
              <div dangerouslySetInnerHTML={{ __html: svgContent }} />
            ) : (
              <div className="w-[420px] h-[600px] rounded-2xl border border-gray-200 bg-white flex items-center justify-center">
                {!fetchDone ? (
                  <div className="w-5 h-5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin-slow" />
                ) : (
                  <p className="text-xs text-gray-400">No data available</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
