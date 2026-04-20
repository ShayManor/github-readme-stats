// Settings ⇄ query-string encoder for the public widget embed URL.
//
// The backend's `GET /api/<u>?...` accepts the same fields that
// `PATCH /settings` takes, but encoded flat in the query. The encoding is
// designed to stay human-readable for the common cases (theme, widgets,
// order) and fall back to compact base64 only for achievements, which are
// shape-y enough that spelling them out inflates the URL.
//
// Keep this in sync with `sanitize_settings_query` in `generator/src/api.py`.

import type { WidgetSettings, Achievement } from '../App'

// The theme id the backend treats as the default. Omit from the URL so
// the common case stays terse.
const DEFAULT_THEME = 'midnight'

// Standard widget set / order. If the user hasn't deviated, skip emitting
// the param so the embed URL doesn't balloon with boilerplate.
const DEFAULT_WIDGETS = ['name', 'grade', 'impact', 'streaks', 'collaborators', 'focus', 'languages']
const DEFAULT_ORDER = ['name', 'grade', 'impact', 'streaks', 'collaborators', 'focus', 'languages', 'achievements']

function arrayEquals(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false
  return true
}

// RFC-4648 url-safe base64 without padding. Matches what Python's
// `base64.urlsafe_b64decode` re-pads in the backend parser.
function urlsafeB64Encode(s: string): string {
  const bytes = new TextEncoder().encode(s)
  let bin = ''
  for (const b of bytes) bin += String.fromCharCode(b)
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

function achievementsParam(achievements: Achievement[]): string | null {
  const keepers = achievements.filter(a => (a.title || '').trim())
  if (!keepers.length) return null
  const payload = keepers.map(a => ({
    title: a.title,
    subtitle: a.subtitle,
    event_date: a.event_date,
    icon: a.icon,
  }))
  return urlsafeB64Encode(JSON.stringify(payload))
}

export function settingsToQuery(settings: WidgetSettings): string {
  const params = new URLSearchParams()

  if (settings.theme && settings.theme !== DEFAULT_THEME) {
    params.set('theme', settings.theme)
  }
  if (!arrayEquals(settings.widgets, DEFAULT_WIDGETS)) {
    params.set('widgets', settings.widgets.join(','))
  }
  if (!arrayEquals(settings.widgetOrder, DEFAULT_ORDER)) {
    params.set('order', settings.widgetOrder.join(','))
  }
  if (settings.hiddenLanguages.length) {
    params.set('hide', settings.hiddenLanguages.join(','))
  }
  if (settings.customTags.length) {
    params.set('tags', settings.customTags.join(','))
  }

  // Per-widget settings flatten to `<widget>.<key>=<value>`. Any undefined
  // or null leaf is skipped so the URL stays minimal.
  for (const [widget, ws] of Object.entries(settings.widgetSettings)) {
    if (!ws) continue
    for (const [key, val] of Object.entries(ws as Record<string, unknown>)) {
      if (val === undefined || val === null || val === '') continue
      params.set(`${widget}.${key}`, String(val))
    }
  }

  const ach = achievementsParam(settings.achievements)
  if (ach) params.set('ach', ach)

  // URLSearchParams.toString() percent-encodes values (including the `#` in
  // hex colors), so callers can splice the result straight into a URL.
  return params.toString()
}

export function buildEmbedUrl(origin: string, username: string, settings: WidgetSettings): string {
  const qs = settingsToQuery(settings)
  const base = `${origin}/api/${encodeURIComponent(username)}`
  return qs ? `${base}?${qs}` : base
}
