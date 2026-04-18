import { THEMES, TAG_COLORS, GRADE_COLORS, FOCUS_COLORS, LANG_COLORS, type Theme } from './themes'

// --- Types matching the API `format=data` response ---

export type GradeData = {
  grade: string; score: number
  stats: Record<string, number>
  tags: { tag: string; source: string; confidence: number; label?: string | null }[]
  breakdown: Record<string, number>
}
export type ImpactWeek = { week_start: string; commits: number }
export type CollaboratorData = { username: string; shared_repos: number; shared_commits: number }
export type FocusCategory = { category: string; percentage: number; commit_count: number }
export type LanguageData = { language: string; percentage: number; loc: number }
export type AchievementInput = { title: string; subtitle: string; event_date: string; icon: string }

export type WidgetData = {
  grade?: GradeData
  impact?: ImpactWeek[]
  collaborators?: CollaboratorData[]
  focus?: FocusCategory[]
  languages?: LanguageData[]
}

export type PerWidgetSettings = {
  grade?: { max_tags?: number }
  impact?: { line_color?: string }
  collaborators?: { max_count?: number; bar_color?: string }
  focus?: { max_categories?: number }
  languages?: { max_languages?: number }
  achievements?: { max_items?: number }
}

// --- Helpers ---

const esc = (s: string) => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')
const font = '-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif'

const TAG_ACRONYMS = new Set(['ml','ai','ui','ux','api','cli','sql','css','html','js','ios'])
function formatTagLabel(tag: string): string {
  return tag.split('-')
    .map(w => TAG_ACRONYMS.has(w.toLowerCase())
      ? w.toUpperCase()
      : w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function cardWrapper(inner: string, w: number, h: number, t: Theme, title: string, prefix = '') {
  const sid = `${prefix}shadow`
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" fill="none">
  <defs><filter id="${sid}" x="-2%" y="-2%" width="104%" height="104%"><feDropShadow dx="0" dy="1" stdDeviation="2" flood-color="#000" flood-opacity="0.15"/></filter></defs>
  <rect x="1" y="1" width="${w-2}" height="${h-2}" rx="10" ry="10" fill="${t.card_bg}" stroke="${t.card_border}" stroke-width="1" filter="url(#${sid})"/>
  ${title ? `<text x="20" y="30" font-family="${font}" font-size="11" font-weight="600" fill="${t.text_secondary}" letter-spacing="0.8" opacity="0.7">${esc(title.toUpperCase())}</text>` : ''}
  <g transform="translate(0, ${title ? 36 : 0})">${inner}</g>
</svg>`
}

function iconSvg(kind: string, color: string): string {
  const icons: Record<string, string> = {
    commits: `<circle cx="7" cy="7" r="3" fill="none" stroke="${color}" stroke-width="1.4"/><circle cx="7" cy="7" r="1" fill="${color}"/><line x1="7" y1="10" x2="7" y2="14" stroke="${color}" stroke-width="1.4"/><line x1="7" y1="0" x2="7" y2="4" stroke="${color}" stroke-width="1.4"/>`,
    prs: `<circle cx="4" cy="4" r="2" fill="none" stroke="${color}" stroke-width="1.2"/><circle cx="10" cy="10" r="2" fill="none" stroke="${color}" stroke-width="1.2"/><path d="M4 6v4c0 1.1.9 2 2 2h2" fill="none" stroke="${color}" stroke-width="1.2"/>`,
    stars: `<path d="M7 1l1.8 3.6 4 .6-2.9 2.8.7 4L7 10.2 3.4 12l.7-4L1.2 5.2l4-.6z" fill="none" stroke="${color}" stroke-width="1.2" stroke-linejoin="round"/>`,
    repos: `<rect x="2" y="1" width="10" height="12" rx="1.5" fill="none" stroke="${color}" stroke-width="1.2"/><line x1="5" y1="4" x2="9" y2="4" stroke="${color}" stroke-width="1"/><line x1="5" y1="6.5" x2="9" y2="6.5" stroke="${color}" stroke-width="1"/><line x1="5" y1="9" x2="7" y2="9" stroke="${color}" stroke-width="1"/>`,
    followers: `<circle cx="5" cy="4" r="2.5" fill="none" stroke="${color}" stroke-width="1.2"/><path d="M0.5 12c0-2.5 2-4 4.5-4s4.5 1.5 4.5 4" fill="none" stroke="${color}" stroke-width="1.2"/><circle cx="11" cy="3.5" r="1.8" fill="none" stroke="${color}" stroke-width="1"/><path d="M10 7.5c1.5 0 3.5 1 3.5 3" fill="none" stroke="${color}" stroke-width="1"/>`,
  }
  return `<g>${icons[kind] ?? ''}</g>`
}

// --- Widget renderers ---

function renderGrade(data: GradeData, t: Theme, s?: { max_tags?: number }): string {
  const tags = s?.max_tags ? data.tags.slice(0, s.max_tags) : data.tags
  const base = data.grade[0]
  const color = GRADE_COLORS[base] ?? t.accent
  const radius = 36
  const circ = 2 * Math.PI * radius
  const offset = circ * (1 - data.score / 100)
  const gf = data.grade.length <= 2 ? 30 : 22

  const statLabels: Record<string, string> = { commits:'Commits', prs:'PRs', stars:'Stars', repos:'Repos', followers:'Followers' }
  const statKeys = ['commits','prs','stars','repos','followers'].filter(k => k in data.stats)
  const sw = 340 / Math.max(statKeys.length, 1)
  let statsSvg = ''
  for (let i = 0; i < statKeys.length; i++) {
    const k = statKeys[i], v = data.stats[k]
    const sx = i * sw + sw / 2
    const vs = v < 100000 ? v.toLocaleString() : `${Math.round(v/1000)}k`
    statsSvg += `<g transform="translate(${sx}, 0)"><g transform="translate(-7, 0)">${iconSvg(k, t.text_secondary)}</g><text x="0" y="28" text-anchor="middle" font-family="${font}" font-size="14" font-weight="700" fill="${t.text}">${vs}</text><text x="0" y="41" text-anchor="middle" font-family="${font}" font-size="9" fill="${t.text_secondary}">${statLabels[k]??k}</text></g>`
  }

  let tagsSvg = '', tx = 0, ty = 0
  for (const tag of tags) {
    const tc = TAG_COLORS[tag.tag] ?? t.accent
    const label = tag.label || formatTagLabel(tag.tag)
    const tw = Math.round(label.length * 6.6 + 18)
    const po = tag.source === 'earned' ? 0.9 : 0.55
    if (tx + tw > 340) { tx = 0; ty += 30 }
    tagsSvg += `<g transform="translate(${tx}, ${ty})" opacity="${po}"><rect width="${tw}" height="24" rx="12" fill="${tc}" opacity="0.12"/><rect width="${tw}" height="24" rx="12" fill="none" stroke="${tc}" stroke-width="1" opacity="0.3"/><text x="${Math.round(tw/2)}" y="16" text-anchor="middle" font-family="${font}" font-size="10" font-weight="500" fill="${tc}">${esc(label)}</text></g>`
    tx += tw + 6
  }

  const tagsH = tags.length ? ty + 24 : 0
  const statsY = 100, tagsY = statsY + 54
  const tagPad = tagsH > 24 ? 18 : 14
  const cardH = tags.length ? tagsY + tagsH + tagPad : statsY + 54

  let inner = `<g transform="translate(52, 48)"><circle cx="0" cy="0" r="${radius}" fill="none" stroke="${t.grid}" stroke-width="5"/><circle cx="0" cy="0" r="${radius}" fill="none" stroke="${color}" stroke-width="5" stroke-dasharray="${circ.toFixed(1)}" stroke-dashoffset="${offset.toFixed(1)}" stroke-linecap="round" transform="rotate(-90)"/><text x="0" y="-4" text-anchor="middle" dominant-baseline="middle" font-family="${font}" font-size="${gf}" font-weight="800" fill="${color}">${esc(data.grade)}</text><text x="0" y="18" text-anchor="middle" font-family="${font}" font-size="11" fill="${t.text_secondary}">${data.score.toFixed(0)} / 100</text></g>
    <line x1="100" y1="16" x2="100" y2="80" stroke="${t.grid}" stroke-width="1"/>
    <g transform="translate(114, 26)"><text x="0" y="10" font-family="${font}" font-size="16" font-weight="700" fill="${t.text}">Developer Profile</text><text x="0" y="28" font-family="${font}" font-size="11" fill="${t.text_secondary}">Grade <tspan fill="${color}" font-weight="700">${esc(data.grade)}</tspan> · ${data.score.toFixed(0)}/100</text></g>
    <line x1="20" y1="${statsY-4}" x2="360" y2="${statsY-4}" stroke="${t.grid}" stroke-width="0.5"/>
    <g transform="translate(20, ${statsY})">${statsSvg}</g>`

  if (tags.length) {
    inner += `<line x1="20" y1="${tagsY-6}" x2="360" y2="${tagsY-6}" stroke="${t.grid}" stroke-width="0.5"/><g transform="translate(20, ${tagsY})">${tagsSvg}</g>`
  }

  return cardWrapper(inner, 380, cardH, t, '')
}

function renderImpact(weeks: ImpactWeek[], t: Theme, s?: { line_color?: string }): string {
  const w = 380, h = 200, cx = 40, cy = 8, cw = 316, ch = 82
  const lineColor = s?.line_color ?? t.accent

  if (!weeks.length) {
    const inner = `<line x1="${cx}" y1="${cy+ch}" x2="${cx+cw}" y2="${cy+ch}" stroke="${t.grid}" stroke-width="0.5"/>
      <text x="${cx+cw/2}" y="${cy+ch/2+4}" text-anchor="middle" font-family="${font}" font-size="11" fill="${t.text_secondary}">No contribution data yet</text>
      <g transform="translate(20, ${cy+ch+46})"><text x="0" y="0" font-family="${font}" font-size="13" font-weight="700" fill="${t.text}">0</text><text x="0" y="14" font-family="${font}" font-size="9" fill="${t.text_secondary}">commits over 6mo</text></g>`
    return cardWrapper(inner, w, h, t, 'Impact Timeline')
  }

  const maxC = Math.max(...weeks.map(w => w.commits), 1)
  const n = weeks.length
  const pts = weeks.map((wk, i) => ({
    x: cx + (i / Math.max(n-1, 1)) * cw,
    y: cy + ch - (wk.commits / maxC) * ch,
  }))

  let pathD = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`
  for (let i = 1; i < pts.length; i++) {
    const mx = (pts[i-1].x + pts[i].x) / 2
    pathD += ` C ${mx.toFixed(1)} ${pts[i-1].y.toFixed(1)}, ${mx.toFixed(1)} ${pts[i].y.toFixed(1)}, ${pts[i].x.toFixed(1)} ${pts[i].y.toFixed(1)}`
  }
  const areaD = pathD + ` L ${pts[n-1].x.toFixed(1)} ${cy+ch} L ${pts[0].x.toFixed(1)} ${cy+ch} Z`

  let yLabels = ''
  for (let i = 0; i < 3; i++) {
    const v = Math.round(maxC * (1 - i/2))
    const yy = cy + (i/2) * ch
    yLabels += `<text x="${cx-6}" y="${yy+4}" text-anchor="end" font-family="${font}" font-size="9" fill="${t.text_secondary}">${v}</text><line x1="${cx}" y1="${yy}" x2="${cx+cw}" y2="${yy}" stroke="${t.grid}" stroke-width="0.5" stroke-dasharray="3,3"/>`
  }

  let xLabels = ''
  const li = n > 2 ? [0, Math.floor(n/2), n-1] : Array.from({length: n}, (_, i) => i)
  for (const idx of li) {
    if (idx < weeks.length) {
      const px = cx + (idx / Math.max(n-1,1)) * cw
      xLabels += `<text x="${px.toFixed(1)}" y="${cy+ch+14}" text-anchor="middle" font-family="${font}" font-size="9" fill="${t.text_secondary}">${weeks[idx].week_start.slice(0,7)}</text>`
    }
  }

  const total = weeks.reduce((a, w) => a + w.commits, 0)
  const sy = cy + ch + 46
  const inner = `<defs><linearGradient id="areaGrad" x1="0" y1="${cy}" x2="0" y2="${cy+ch}" gradientUnits="userSpaceOnUse"><stop offset="0%" stop-color="${lineColor}" stop-opacity="0.35"/><stop offset="100%" stop-color="${lineColor}" stop-opacity="0.02"/></linearGradient></defs>
    ${yLabels}${xLabels}
    <path d="${areaD}" fill="url(#areaGrad)"/>
    <path d="${pathD}" fill="none" stroke="${lineColor}" stroke-width="2" stroke-linecap="round"/>
    <g transform="translate(20, ${sy})"><text x="0" y="0" font-family="${font}" font-size="13" font-weight="700" fill="${t.text}">${total.toLocaleString()}</text><text x="0" y="14" font-family="${font}" font-size="9" fill="${t.text_secondary}">commits over 6mo</text></g>`

  return cardWrapper(inner, w, h, t, 'Impact Timeline')
}

function renderCollaborators(collabs: CollaboratorData[], t: Theme, s?: { max_count?: number; bar_color?: string }): string {
  const maxCount = Math.min(Math.max(s?.max_count ?? 5, 1), 10)
  const barColor = s?.bar_color ?? t.purple
  const shown = collabs.slice(0, maxCount)
  const barMax = Math.max(...shown.map(c => c.shared_commits), 1)
  let items = ''

  for (let i = 0; i < shown.length; i++) {
    const c = shown[i], y = i * 50
    const hue = [...c.username].reduce((h, ch) => h + ch.charCodeAt(0), 0) % 360
    const avatar = `<circle cx="0" cy="0" r="18" fill="hsl(${hue}, 50%, 40%)"/><text x="0" y="1" text-anchor="middle" dominant-baseline="middle" font-family="${font}" font-size="14" font-weight="600" fill="white">${esc(c.username[0].toUpperCase())}</text>`
    const bw = (c.shared_commits / barMax * 120).toFixed(1)
    items += `<g transform="translate(36, ${y+20})">${avatar}<text x="28" y="-2" font-family="${font}" font-size="13" font-weight="600" fill="${t.text}">${esc(c.username)}</text><text x="28" y="14" font-family="${font}" font-size="10" fill="${t.text_secondary}">${c.shared_repos} repos · ${c.shared_commits} commits</text><rect x="200" y="-6" width="130" height="8" rx="4" fill="${t.grid}"/><rect x="200" y="-6" width="${bw}" height="8" rx="4" fill="${barColor}" opacity="0.8"/></g>`
  }

  return cardWrapper(items, 380, shown.length * 50 + 48, t, 'Top Collaborators')
}

function renderFocus(cats: FocusCategory[], t: Theme, s?: { max_categories?: number }): string {
  const maxCats = Math.min(Math.max(s?.max_categories ?? 6, 1), 10)
  const sorted = [...cats].sort((a, b) => b.percentage - a.percentage).slice(0, maxCats)
  if (!sorted.length) return ''

  const maxPct = Math.max(sorted[0].percentage, 1)
  const barMaxW = 210
  let items = ''

  for (let i = 0; i < sorted.length; i++) {
    const cat = sorted[i], y = i * 36
    const color = FOCUS_COLORS[i % FOCUS_COLORS.length]
    const bw = (cat.percentage / maxPct * barMaxW).toFixed(1)
    items += `<g transform="translate(16, ${y})"><text x="0" y="14" font-family="${font}" font-size="12" font-weight="600" fill="${t.text}">${esc(cat.category)}</text><rect x="90" y="4" width="${barMaxW}" height="14" rx="7" fill="${t.grid}"/><rect x="90" y="4" width="${bw}" height="14" rx="7" fill="${color}" opacity="0.8"/><text x="90" y="32" font-family="${font}" font-size="9" fill="${t.text_secondary}">${cat.commit_count} commits</text><text x="${90+barMaxW+8}" y="15" font-family="${font}" font-size="12" font-weight="700" fill="${color}">${Math.round(cat.percentage)}%</text></g>`
  }

  const subY = sorted.length * 36 + 8
  items += `<text x="16" y="${subY}" font-family="${font}" font-size="9" fill="${t.text_secondary}" opacity="0.7">Recent activity · last year</text>`

  return cardWrapper(items, 380, sorted.length * 36 + 54, t, 'Recent Focus')
}

function renderLanguages(languages: LanguageData[], t: Theme, s?: { max_languages?: number }): string {
  const maxLangs = Math.min(Math.max(s?.max_languages ?? 5, 1), 10)
  const topLangs = [...languages].sort((a, b) => b.percentage - a.percentage).slice(0, maxLangs)
  if (!topLangs.length) return ''

  const totalPct = topLangs.reduce((a, l) => a + l.percentage, 0)
  const langs = [...topLangs]

  if (totalPct < 99.9 && languages.length > maxLangs) {
    langs.push({ language: 'Other', percentage: Math.round((100 - totalPct) * 10) / 10, loc: 0 })
  } else if (totalPct < 99.9 && totalPct > 0) {
    const f = 100 / totalPct
    for (const l of langs) l.percentage = Math.round(l.percentage * f * 10) / 10
  }

  const legendStart = 20, legendH = langs.length * 22
  const ccy = legendStart + legendH / 2, ccx = 60, r = 44, innerR = 28
  const circ = 2 * Math.PI * r

  let arcs = '', legend = '', offset = 0
  for (let i = 0; i < langs.length; i++) {
    const lang = langs[i]
    const color = lang.language === 'Other' ? t.text_secondary : (LANG_COLORS[lang.language] ?? FOCUS_COLORS[i % FOCUS_COLORS.length])
    const dash = circ * lang.percentage / 100
    const gap = circ - dash
    arcs += `<circle cx="${ccx}" cy="${ccy}" r="${r}" fill="none" stroke="${color}" stroke-width="16" stroke-dasharray="${dash.toFixed(1)} ${gap.toFixed(1)}" stroke-dashoffset="${(-offset).toFixed(1)}" transform="rotate(-90 ${ccx} ${ccy})" opacity="0.85"/>`
    offset += dash

    const ly = i * 22
    legend += `<g transform="translate(140, ${ly + legendStart})"><rect width="10" height="10" rx="2" fill="${color}"/><text x="16" y="9" font-family="${font}" font-size="12" fill="${t.text}">${esc(lang.language)}</text><text x="210" y="9" text-anchor="end" font-family="${font}" font-size="11" font-weight="600" fill="${t.text_secondary}">${Math.round(lang.percentage)}%</text></g>`
  }

  const center = `<circle cx="${ccx}" cy="${ccy}" r="${innerR}" fill="${t.card_bg}"/><text x="${ccx}" y="${ccy+1}" text-anchor="middle" dominant-baseline="middle" font-family="${font}" font-size="11" font-weight="700" fill="${t.text}">${esc(langs[0].language)}</text>`
  const inner = `<g transform="translate(16, 0)">${arcs}${center}${legend}</g>`
  const rowsH = Math.max(langs.length * 22 + 40, 120)
  return cardWrapper(inner, 380, rowsH + 36, t, 'Languages')
}

function achievementIconSvg(iconType: string, color: string): string {
  // Mirrors generator/src/widgets/achievements.py::_achievement_icon_svg so
  // the Workshop client preview matches the backend-rendered composite.
  const icons: Record<string, string> = {
    trophy: `<svg viewBox="0 0 24 24" width="24" height="24"><path d="M7 2h10v2h2.5c.8 0 1.5.7 1.5 1.5V8c0 1.7-1.3 3-3 3h-.5c-.5 1.5-1.8 2.7-3.5 3v2.5h3c.6 0 1 .4 1 1s-.4 1-1 1H7c-.6 0-1-.4-1-1s.4-1 1-1h3V14c-1.7-.3-3-1.5-3.5-3H6c-1.7 0-3-1.3-3-3V5.5C3 4.7 3.7 4 4.5 4H7V2zm0 4H4.5v2c0 .8.7 1.5 1.5 1.5h1V6zm12.5 0H17v3.5h1c.8 0 1.5-.7 1.5-1.5V6z" fill="${color}" opacity="0.85"/></svg>`,
    medal: `<svg viewBox="0 0 24 24" width="24" height="24"><circle cx="12" cy="14" r="5" fill="${color}" opacity="0.2"/><circle cx="12" cy="14" r="4" fill="none" stroke="${color}" stroke-width="1.5"/><path d="M12 11.5l1 2 2.2.3-1.6 1.5.4 2.2-2-1-2 1 .4-2.2-1.6-1.5 2.2-.3z" fill="${color}"/><path d="M9 3l3 8m0-8l3 8m-6-8h6" stroke="${color}" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>`,
    star: `<svg viewBox="0 0 24 24" width="24" height="24"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round"/></svg>`,
    hackathon: `<svg viewBox="0 0 24 24" width="24" height="24"><rect x="4" y="5" width="16" height="11" rx="1" fill="none" stroke="${color}" stroke-width="1.5"/><rect x="3" y="16" width="18" height="1.5" rx="0.5" fill="${color}" opacity="0.85"/><path d="M9 9l-2 3 2 3m6-6l2 3-2 3" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>`,
  }
  return icons[iconType] ?? icons.trophy
}

function renderAchievements(achievements: AchievementInput[], t: Theme, s?: { max_items?: number }): string {
  const maxItems = Math.min(Math.max(s?.max_items ?? 5, 1), 10)
  const shown = achievements.filter(a => a.title.trim()).slice(0, maxItems)
  if (!shown.length) return ''

  const accentColors = [t.orange, t.green, t.accent, t.purple, t.pink]
  let items = ''

  for (let i = 0; i < shown.length; i++) {
    const ach = shown[i], y = i * 56
    const color = accentColors[i % accentColors.length]
    const icon = achievementIconSvg(ach.icon, color)
    items += `<g transform="translate(16, ${y+8})"><rect width="348" height="48" rx="8" fill="${color}" opacity="0.06"/><rect width="348" height="48" rx="8" fill="none" stroke="${color}" stroke-width="0.5" opacity="0.3"/><g transform="translate(12, 12)">${icon}</g><text x="48" y="20" font-family="${font}" font-size="13" font-weight="600" fill="${t.text}">${esc(ach.title)}</text><text x="48" y="36" font-family="${font}" font-size="10" fill="${t.text_secondary}">${esc(ach.subtitle)}${ach.event_date ? ' · ' + ach.event_date : ''}</text></g>`
  }

  return cardWrapper(items, 380, shown.length * 56 + 50, t, 'Achievements')
}

// --- Composite ---

function extractInner(svg: string, key: string): { inner: string; h: number } {
  const hm = svg.match(/height="(\d+)"/)
  const h = hm ? parseInt(hm[1]) : 160

  // Prefix IDs
  const ids = [...svg.matchAll(/id="([^"]+)"/g)].map(m => m[1])
  let inner = svg
  for (const id of ids) {
    const nid = `${key}_${id}`
    inner = inner.replaceAll(`id="${id}"`, `id="${nid}"`)
    inner = inner.replaceAll(`url(#${id})`, `url(#${nid})`)
    inner = inner.replaceAll(`href="#${id}"`, `href="#${nid}"`)
  }
  inner = inner.replace(/<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '')
  return { inner, h }
}

// --- Main export ---

export function renderAllWidgets(opts: {
  data: WidgetData
  theme: string
  widgets: string[]
  widgetOrder: string[]
  achievements: AchievementInput[]
  widgetSettings: PerWidgetSettings
  hiddenLanguages?: string[]
  username: string
}): string {
  const t = THEMES[opts.theme] ?? THEMES.dark
  const enabled = new Set(opts.widgets)
  const widgetSvgs: Record<string, string> = {}

  if (enabled.has('grade') && opts.data.grade)
    widgetSvgs.grade = renderGrade(opts.data.grade, t, opts.widgetSettings.grade)
  if (enabled.has('impact') && opts.data.impact)
    widgetSvgs.impact = renderImpact(opts.data.impact, t, opts.widgetSettings.impact)
  if (enabled.has('collaborators') && opts.data.collaborators)
    widgetSvgs.collaborators = renderCollaborators(opts.data.collaborators, t, opts.widgetSettings.collaborators)
  if (enabled.has('focus') && opts.data.focus)
    widgetSvgs.focus = renderFocus(opts.data.focus, t, opts.widgetSettings.focus)
  if (enabled.has('languages') && opts.data.languages) {
    // Apply hidden_languages client-side too so the Workshop preview reflects
    // the user's choice instantly — backend filtering only kicks in on the
    // next prefetch or on POST /generate.
    const hiddenSet = new Set(opts.hiddenLanguages ?? [])
    const filtered = opts.data.languages.filter(l => !hiddenSet.has(l.language))
    const total = filtered.reduce((a, l) => a + l.percentage, 0) || 1
    const rescaled = filtered.map(l => ({ ...l, percentage: Math.round(l.percentage / total * 1000) / 10 }))
    widgetSvgs.languages = renderLanguages(rescaled, t, opts.widgetSettings.languages)
  }
  if (enabled.has('achievements'))
    widgetSvgs.achievements = renderAchievements(opts.achievements, t, opts.widgetSettings.achievements)

  // Compose
  const totalW = 420, headerH = 60, padding = 20, gap = 16
  const ordered = opts.widgetOrder.filter(k => enabled.has(k) && widgetSvgs[k])

  const parts = ordered.map(key => {
    const { inner, h } = extractInner(widgetSvgs[key], key)
    return { key, inner, h }
  })

  const contentH = parts.reduce((a, p) => a + p.h, 0) + gap * Math.max(parts.length - 1, 0)
  const totalH = headerH + contentH + padding * 2 + 10

  const avatar = `<circle cx="30" cy="30" r="16" fill="${t.accent}" opacity="0.3"/>`
  const header = `${avatar}<text x="54" y="38" font-family="${font}" font-size="16" font-weight="700" fill="${t.text}">${esc(opts.username || 'Developer')}</text><line x1="${padding}" y1="${headerH}" x2="${totalW-padding}" y2="${headerH}" stroke="${t.card_border}" stroke-width="0.5"/>`

  let yOffset = headerH + padding
  let embedded = ''
  for (const { inner, h } of parts) {
    embedded += `<svg x="${padding}" y="${yOffset}" width="380" height="${h}" viewBox="0 0 380 ${h}">${inner}</svg>`
    yOffset += h + gap
  }

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${totalW}" height="${totalH}" viewBox="0 0 ${totalW} ${totalH}">
  <rect width="${totalW}" height="${totalH}" rx="16" fill="${t.bg}"/>
  <rect x="0.5" y="0.5" width="${totalW-1}" height="${totalH-1}" rx="16" fill="none" stroke="${t.card_border}" stroke-width="1"/>
  ${header}${embedded}
  <text x="${totalW/2}" y="${totalH-8}" text-anchor="middle" font-family="${font}" font-size="9" fill="${t.text_secondary}" opacity="0.5">Generated with gh-stats</text>
</svg>`
}
