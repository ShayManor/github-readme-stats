"""
GitHub Profile Widget Generator
Generates polished SVG mini-widgets from GitHub profile data.
Each widget is composable into a single unified profile card.
"""

import requests
import math
import base64
from datetime import datetime, timedelta
from collections import defaultdict
from io import BytesIO
from typing import Optional
from dataclasses import dataclass, field

# ─── Theme ────────────────────────────────────────────────────────────────────

THEMES = {
    "dark": {
        "bg": "#121820",
        "card_bg": "#1a2230",
        "card_border": "#2a3444",
        "text": "#d1d9e0",
        "text_secondary": "#7d8895",
        "accent": "#58a6ff",
        "green": "#3fb950",
        "orange": "#d29922",
        "red": "#f85149",
        "purple": "#bc8cff",
        "pink": "#f778ba",
        "grid": "#1e2836",
    },
    "light": {
        "bg": "#ffffff",
        "card_bg": "#f6f8fa",
        "card_border": "#d8dee4",
        "text": "#24292f",
        "text_secondary": "#656d76",
        "accent": "#0969da",
        "green": "#1a7f37",
        "orange": "#9a6700",
        "red": "#cf222e",
        "purple": "#8250df",
        "pink": "#bf3989",
        "grid": "#eaeef2",
    },
}

# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class GradeData:
    grade: str          # e.g. "A++", "S+", "B-"
    score: float        # 0-100
    stats: dict         # {"commits": 1423, "prs": 87, "stars": 342, "repos": 28, "followers": 156}
    tags: list          # list of TagData
    breakdown: dict = field(default_factory=dict)  # optional bar breakdown

@dataclass
class TagData:
    tag: str
    source: str = "earned"    # "earned" | "chosen"
    confidence: float = 1.0

@dataclass
class ImpactWeek:
    week_start: str     # ISO date
    commits: int = 0
    additions: int = 0
    deletions: int = 0

@dataclass
class CollaboratorData:
    username: str
    avatar_b64: str = ""      # base64 encoded avatar
    shared_repos: int = 0
    shared_commits: int = 0

@dataclass
class FocusCategory:
    category: str
    percentage: float
    commit_count: int = 0

@dataclass
class LanguageData:
    language: str
    percentage: float
    loc: int = 0              # lines of code or repo count

@dataclass
class AchievementData:
    title: str
    subtitle: str = ""
    event_date: str = ""
    icon: str = "trophy"      # trophy, medal, star, hackathon


# ─── SVG Helpers ──────────────────────────────────────────────────────────────

def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _card_wrapper(inner_svg: str, width: int, height: int, theme: dict, title: str = "") -> str:
    """Wraps content in a styled card with rounded corners and border."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none">
  <defs>
    <filter id="shadow" x="-2%" y="-2%" width="104%" height="104%">
      <feDropShadow dx="0" dy="1" stdDeviation="2" flood-color="#000" flood-opacity="0.15"/>
    </filter>
    <clipPath id="avatarClip"><circle cx="0" cy="0" r="18"/></clipPath>
  </defs>
  <rect x="1" y="1" width="{width-2}" height="{height-2}" rx="10" ry="10"
        fill="{theme["card_bg"]}" stroke="{theme["card_border"]}" stroke-width="1" filter="url(#shadow)"/>
  {f'<text x="20" y="30" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Noto Sans,Helvetica,Arial,sans-serif" font-size="11" font-weight="600" fill="{theme["text_secondary"]}" letter-spacing="0.8" opacity="0.7">{_escape(title.upper())}</text>' if title else ''}
  <g transform="translate(0, {36 if title else 0})">
    {inner_svg}
  </g>
</svg>'''



# ─── SVG stat icons (14x14) ──────────────────────────────────────────────────

def _icon_svg(kind: str, color: str) -> str:
    icons = {
        "commits": f'<circle cx="7" cy="7" r="3" fill="none" stroke="{color}" stroke-width="1.4"/><circle cx="7" cy="7" r="1" fill="{color}"/><line x1="7" y1="10" x2="7" y2="14" stroke="{color}" stroke-width="1.4"/><line x1="7" y1="0" x2="7" y2="4" stroke="{color}" stroke-width="1.4"/>',
        "prs": f'<circle cx="4" cy="4" r="2" fill="none" stroke="{color}" stroke-width="1.2"/><circle cx="10" cy="10" r="2" fill="none" stroke="{color}" stroke-width="1.2"/><path d="M4 6v4c0 1.1.9 2 2 2h2" fill="none" stroke="{color}" stroke-width="1.2"/>',
        "stars": f'<path d="M7 1l1.8 3.6 4 .6-2.9 2.8.7 4L7 10.2 3.4 12l.7-4L1.2 5.2l4-.6z" fill="{color}" opacity="0.85"/>',
        "repos": f'<rect x="2" y="1" width="10" height="12" rx="1.5" fill="none" stroke="{color}" stroke-width="1.2"/><line x1="5" y1="4" x2="9" y2="4" stroke="{color}" stroke-width="1"/><line x1="5" y1="6.5" x2="9" y2="6.5" stroke="{color}" stroke-width="1"/><line x1="5" y1="9" x2="7" y2="9" stroke="{color}" stroke-width="1"/>',
        "followers": f'<circle cx="5" cy="4" r="2.5" fill="none" stroke="{color}" stroke-width="1.2"/><path d="M0.5 12c0-2.5 2-4 4.5-4s4.5 1.5 4.5 4" fill="none" stroke="{color}" stroke-width="1.2"/><circle cx="11" cy="3.5" r="1.8" fill="none" stroke="{color}" stroke-width="1"/><path d="M10 7.5c1.5 0 3.5 1 3.5 3" fill="none" stroke="{color}" stroke-width="1"/>',
    }
    return f'<g>{icons.get(kind, "")}</g>'


TAG_COLORS = {
    "ml-engineer": "#bc8cff", "frontend": "#58a6ff", "backend": "#3fb950",
    "fullstack": "#d29922", "devops": "#f0883e", "database": "#f778ba",
    "mobile": "#ff6b9d", "security": "#f85149", "data-science": "#79c0ff",
    "systems": "#7ee787", "cloud": "#58a6ff", "open-source": "#3fb950",
}

GRADE_COLORS = {
    "S": "#ff6b9d", "A": "#3fb950", "B": "#58a6ff", "C": "#d29922",
    "D": "#f0883e", "F": "#f85149",
}

def render_grade_widget(data: GradeData, theme_name: str = "dark") -> str:
    t = THEMES[theme_name]
    base = data.grade[0]
    color = GRADE_COLORS.get(base, t["accent"])
    score = data.score

    radius = 36
    circumference = 2 * math.pi * radius
    offset = circumference * (1 - score / 100)

    grade_font = 30 if len(data.grade) <= 2 else 22

    # ── Stats row with icons ──
    stat_labels = {"commits": "Commits", "prs": "PRs", "stars": "Stars", "repos": "Repos", "followers": "Followers"}
    stat_keys = [k for k in ["commits", "prs", "stars", "repos", "followers"] if k in data.stats]
    stats_svg = ""
    stat_w = 340 / max(len(stat_keys), 1)
    for i, key in enumerate(stat_keys):
        val = data.stats[key]
        sx = i * stat_w + stat_w / 2
        val_str = f"{val:,}" if val < 100000 else f"{val/1000:.0f}k"
        stats_svg += f'''
      <g transform="translate({sx}, 0)">
        <g transform="translate(-7, 0)">{_icon_svg(key, t["text_secondary"])}</g>
        <text x="0" y="28" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
              font-size="14" font-weight="700" fill="{t["text"]}">{val_str}</text>
        <text x="0" y="41" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
              font-size="9" fill="{t["text_secondary"]}">{stat_labels.get(key, key)}</text>
      </g>'''

    # ── Tag pills (no dots) ──
    tags_svg = ""
    tx, ty = 0, 0
    max_tw = 340
    for tag in (data.tags or []):
        tag_color = TAG_COLORS.get(tag.tag, t["accent"])
        label = tag.tag.replace("-", " ").title()
        tw = int(len(label) * 6.6 + 18)
        pill_opacity = 0.9 if tag.source == "earned" else 0.55

        if tx + tw > max_tw:
            tx = 0
            ty += 30

        tags_svg += f'''
      <g transform="translate({tx}, {ty})" opacity="{pill_opacity}">
        <rect width="{tw}" height="24" rx="12" fill="{tag_color}" opacity="0.12"/>
        <rect width="{tw}" height="24" rx="12" fill="none" stroke="{tag_color}" stroke-width="1" opacity="0.3"/>
        <text x="{tw // 2}" y="16" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
              font-size="10" font-weight="500" fill="{tag_color}">{_escape(label)}</text>
      </g>'''
        tx += tw + 6

    tags_h = ty + 24 if data.tags else 0

    # ── Layout ──
    stats_y = 100
    tags_y = stats_y + 54
    # Add extra padding if there are multiple rows of tags
    tag_padding = 18 if tags_h > 24 else 14
    card_h = (tags_y + tags_h + tag_padding) if data.tags else (stats_y + 54)

    inner = f'''
    <g transform="translate(52, 48)">
      <circle cx="0" cy="0" r="{radius}" fill="none" stroke="{t["grid"]}" stroke-width="5"/>
      <circle cx="0" cy="0" r="{radius}" fill="none" stroke="{color}" stroke-width="5"
              stroke-dasharray="{circumference}" stroke-dashoffset="{offset}"
              stroke-linecap="round" transform="rotate(-90)">
        <animate attributeName="stroke-dashoffset" from="{circumference}" to="{offset}" dur="1s" fill="freeze"/>
      </circle>
      <text x="0" y="-4" text-anchor="middle" dominant-baseline="middle"
            font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="{grade_font}" font-weight="800" fill="{color}">{_escape(data.grade)}</text>
      <text x="0" y="18" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="11" fill="{t["text_secondary"]}">{score:.0f} / 100</text>
    </g>
    <line x1="100" y1="16" x2="100" y2="80" stroke="{t["grid"]}" stroke-width="1"/>
    <g transform="translate(114, 26)">
      <text x="0" y="10" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="16" font-weight="700" fill="{t["text"]}">Developer Profile</text>
      <text x="0" y="28" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="11" fill="{t["text_secondary"]}">Grade <tspan fill="{color}" font-weight="700">{_escape(data.grade)}</tspan> · {score:.0f}/100</text>
    </g>
    <line x1="20" y1="{stats_y - 4}" x2="360" y2="{stats_y - 4}" stroke="{t["grid"]}" stroke-width="0.5"/>
    <g transform="translate(20, {stats_y})">
      {stats_svg}
    </g>'''

    if data.tags:
        inner += f'''
    <line x1="20" y1="{tags_y - 6}" x2="360" y2="{tags_y - 6}" stroke="{t["grid"]}" stroke-width="0.5"/>
    <g transform="translate(20, {tags_y})">
      {tags_svg}
    </g>'''

    return _card_wrapper(inner, 380, card_h, t, "")


# ─── Impact Timeline Widget ──────────────────────────────────────────────────

def render_impact_widget(weeks: list[ImpactWeek], theme_name: str = "dark", period: str = "6mo") -> str:
    t = THEMES[theme_name]
    if not weeks:
        return ""

    w, h = 380, 200
    chart_x, chart_y = 40, 8
    chart_w, chart_h = 316, 82

    max_commits = max((wk.commits for wk in weeks), default=1) or 1
    n = len(weeks)

    # Build area path
    points = []
    for i, wk in enumerate(weeks):
        px = chart_x + (i / max(n - 1, 1)) * chart_w
        py = chart_y + chart_h - (wk.commits / max_commits) * chart_h
        points.append((px, py))

    if not points:
        return ""

    # Smooth curve using cardinal spline
    path_d = f"M {points[0][0]:.1f} {points[0][1]:.1f}"
    for i in range(1, len(points)):
        cx = (points[i-1][0] + points[i][0]) / 2
        path_d += f" C {cx:.1f} {points[i-1][1]:.1f}, {cx:.1f} {points[i][1]:.1f}, {points[i][0]:.1f} {points[i][1]:.1f}"

    area_d = path_d + f" L {points[-1][0]:.1f} {chart_y + chart_h} L {points[0][0]:.1f} {chart_y + chart_h} Z"

    # Y-axis labels
    y_labels = ""
    for i in range(3):
        val = int(max_commits * (1 - i / 2))
        yy = chart_y + (i / 2) * chart_h
        y_labels += f'<text x="{chart_x - 6}" y="{yy + 4}" text-anchor="end" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="9" fill="{t["text_secondary"]}">{val}</text>'
        y_labels += f'<line x1="{chart_x}" y1="{yy}" x2="{chart_x + chart_w}" y2="{yy}" stroke="{t["grid"]}" stroke-width="0.5" stroke-dasharray="3,3"/>'

    # X-axis labels (first, mid, last)
    x_labels = ""
    label_indices = [0, n // 2, n - 1] if n > 2 else list(range(n))
    for idx in label_indices:
        if idx < len(weeks):
            px = chart_x + (idx / max(n - 1, 1)) * chart_w
            x_labels += f'<text x="{px:.1f}" y="{chart_y + chart_h + 14}" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="9" fill="{t["text_secondary"]}">{weeks[idx].week_start[:7]}</text>'

    # Total commits - aligned with left edge, stacked layout
    total = sum(wk.commits for wk in weeks)
    summary_y = chart_y + chart_h + 46

    inner = f'''
    <defs>
      <linearGradient id="areaGrad" x1="0" y1="{chart_y}" x2="0" y2="{chart_y + chart_h}" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stop-color="{t["accent"]}" stop-opacity="0.35"/>
        <stop offset="100%" stop-color="{t["accent"]}" stop-opacity="0.02"/>
      </linearGradient>
    </defs>
    {y_labels}
    {x_labels}
    <path d="{area_d}" fill="url(#areaGrad)"/>
    <path d="{path_d}" fill="none" stroke="{t["accent"]}" stroke-width="2" stroke-linecap="round"/>
    <g transform="translate(20, {summary_y})">
      <text x="0" y="0" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="13" font-weight="700" fill="{t["text"]}">{total:,}</text>
      <text x="0" y="14" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="9" fill="{t["text_secondary"]}">commits over {period}</text>
    </g>'''

    return _card_wrapper(inner, w, h, t, "Impact Timeline")

# ─── Collaborators Widget ─────────────────────────────────────────────────────

def render_collaborators_widget(collabs: list[CollaboratorData], theme_name: str = "dark") -> str:
    t = THEMES[theme_name]
    items = ""
    for i, c in enumerate(collabs[:5]):
        y = i * 50
        avatar_el = ""
        if c.avatar_b64:
            avatar_el = f'''<image x="-18" y="-18" width="36" height="36" href="data:image/png;base64,{c.avatar_b64}" clip-path="url(#avatarClip)"/>'''
        else:
            hue = hash(c.username) % 360
            avatar_el = f'''
            <circle cx="0" cy="0" r="18" fill="hsl({hue}, 50%, 40%)"/>
            <text x="0" y="1" text-anchor="middle" dominant-baseline="middle"
                  font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
                  font-size="14" font-weight="600" fill="white">{_escape(c.username[0].upper())}</text>'''

        bar_max = max((x.shared_commits for x in collabs[:5]), default=1) or 1
        bar_w = c.shared_commits / bar_max * 120

        items += f'''
    <g transform="translate(36, {y + 20})">
      {avatar_el}
      <text x="28" y="-2" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="13" font-weight="600" fill="{t["text"]}">{_escape(c.username)}</text>
      <text x="28" y="14" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="10" fill="{t["text_secondary"]}">{c.shared_repos} repos · {c.shared_commits} commits</text>
      <rect x="200" y="-6" width="130" height="8" rx="4" fill="{t["grid"]}"/>
      <rect x="200" y="-6" width="{bar_w}" height="8" rx="4" fill="{t["purple"]}" opacity="0.8">
        <animate attributeName="width" from="0" to="{bar_w}" dur="0.6s" fill="freeze"/>
      </rect>
    </g>'''

    total_h = len(collabs[:5]) * 50 + 48
    return _card_wrapper(items, 380, total_h, t, "Top Collaborators")



# ─── Focus Score Widget ───────────────────────────────────────────────────────


# ─── Focus Areas Widget (horizontal bars) ────────────────────────────────────

FOCUS_COLORS = ["#58a6ff", "#3fb950", "#bc8cff", "#d29922", "#f0883e", "#f778ba", "#f85149", "#79c0ff"]

def render_focus_widget(categories: list[FocusCategory], theme_name: str = "dark", period: str = "1y") -> str:
    t = THEMES[theme_name]
    cats = sorted(categories, key=lambda c: -c.percentage)[:6]
    if not cats:
        return ""

    # Format period for display
    period_map = {
        "1w": "last week", "1m": "last month", "3m": "last 3 months",
        "6m": "last 6 months", "1y": "last year", "all": "all time"
    }
    period_display = period_map.get(period, period)

    max_pct = cats[0].percentage if cats else 100
    bar_max_w = 210
    items = ""

    for i, cat in enumerate(cats):
        color = FOCUS_COLORS[i % len(FOCUS_COLORS)]
        y = i * 36
        bar_w = (cat.percentage / max_pct) * bar_max_w

        items += f'''
    <g transform="translate(16, {y})">
      <text x="0" y="14" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="12" font-weight="600" fill="{t["text"]}">{_escape(cat.category)}</text>
      <rect x="90" y="4" width="{bar_max_w}" height="14" rx="7" fill="{t["grid"]}"/>
      <rect x="90" y="4" width="{bar_w}" height="14" rx="7" fill="{color}" opacity="0.8">
        <animate attributeName="width" from="0" to="{bar_w}" dur="0.7s" fill="freeze"/>
      </rect>
      <text x="90" y="32" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="9" fill="{t["text_secondary"]}">{cat.commit_count} commits</text>
      <text x="{90 + bar_max_w + 8}" y="15" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="12" font-weight="700" fill="{color}">{cat.percentage:.0f}%</text>
    </g>'''

    # Add period subtitle at the bottom
    subtitle_y = len(cats) * 36 + 8
    items += f'''
    <text x="16" y="{subtitle_y}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="9" fill="{t["text_secondary"]}" opacity="0.7">Recent activity · {period_display}</text>'''

    card_h = len(cats) * 36 + 54
    return _card_wrapper(items, 380, card_h, t, "Recent Focus")


# ─── Languages Widget (donut chart) ──────────────────────────────────────────

LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Go": "#00ADD8", "Rust": "#dea584", "Java": "#b07219", "C++": "#f34b7d",
    "C": "#555555", "Ruby": "#701516", "Shell": "#89e051", "HTML": "#e34c26",
    "CSS": "#563d7c", "Kotlin": "#A97BFF", "Swift": "#F05138",
    "Jupyter Notebook": "#DA5B0B", "Dockerfile": "#384d54",
}

def render_languages_widget(languages: list[LanguageData], theme_name: str = "dark") -> str:
    t = THEMES[theme_name]
    langs = sorted(languages, key=lambda l: -l.percentage)[:6]
    if not langs:
        return ""

    # Calculate center position to align with legend
    legend_start = 20
    legend_height = len(langs) * 22
    cy = legend_start + legend_height / 2
    cx, r = 60, 44
    inner_r = 28
    circumference = 2 * math.pi * r

    arcs = ""
    legend = ""
    offset = 0

    for i, lang in enumerate(langs):
        color = LANG_COLORS.get(lang.language, FOCUS_COLORS[i % len(FOCUS_COLORS)])
        dash = circumference * lang.percentage / 100
        gap = circumference - dash

        arcs += f'''
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="16"
            stroke-dasharray="{dash:.1f} {gap:.1f}" stroke-dashoffset="{-offset:.1f}"
            transform="rotate(-90 {cx} {cy})" opacity="0.85">
      <animate attributeName="stroke-dashoffset" from="{circumference - offset:.1f}" to="{-offset:.1f}" dur="0.8s" fill="freeze"/>
    </circle>'''
        offset += dash

        ly = i * 22
        legend += f'''
    <g transform="translate(140, {ly + legend_start})">
      <rect width="10" height="10" rx="2" fill="{color}"/>
      <text x="16" y="9" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="12" fill="{t["text"]}">{_escape(lang.language)}</text>
      <text x="210" y="9" text-anchor="end" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="11" font-weight="600" fill="{t["text_secondary"]}">{lang.percentage:.0f}%</text>
    </g>'''

    # Center: just the top language name, centered vertically
    top_lang = langs[0].language if langs else ""
    center = f'''
    <circle cx="{cx}" cy="{cy}" r="{inner_r}" fill="{t["card_bg"]}"/>
    <text x="{cx}" y="{cy + 1}" text-anchor="middle" dominant-baseline="middle"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="11" font-weight="700" fill="{t["text"]}">{_escape(top_lang)}</text>'''

    inner = f'''
    <g transform="translate(16, 0)">
      {arcs}
      {center}
      {legend}
    </g>'''

    rows_h = max(len(langs) * 22 + 40, 120)
    return _card_wrapper(inner, 380, rows_h + 36, t, "Languages")


# ─── Achievements Widget ─────────────────────────────────────────────────────

def _achievement_icon_svg(icon_type: str, color: str) -> str:
    """Returns SVG path for achievement icons (24x24 centered)."""
    icons = {
        "trophy": f'''<svg viewBox="0 0 24 24" width="24" height="24">
          <path d="M7 2h10v2h2.5c.8 0 1.5.7 1.5 1.5V8c0 1.7-1.3 3-3 3h-.5c-.5 1.5-1.8 2.7-3.5 3v2.5h3c.6 0 1 .4 1 1s-.4 1-1 1H7c-.6 0-1-.4-1-1s.4-1 1-1h3V14c-1.7-.3-3-1.5-3.5-3H6c-1.7 0-3-1.3-3-3V5.5C3 4.7 3.7 4 4.5 4H7V2zm0 4H4.5v2c0 .8.7 1.5 1.5 1.5h1V6zm12.5 0H17v3.5h1c.8 0 1.5-.7 1.5-1.5V6z" fill="{color}" opacity="0.85"/>
        </svg>''',
        "medal": f'''<svg viewBox="0 0 24 24" width="24" height="24">
          <circle cx="12" cy="14" r="5" fill="{color}" opacity="0.2"/>
          <circle cx="12" cy="14" r="4" fill="none" stroke="{color}" stroke-width="1.5"/>
          <path d="M12 11.5l1 2 2.2.3-1.6 1.5.4 2.2-2-1-2 1 .4-2.2-1.6-1.5 2.2-.3z" fill="{color}"/>
          <path d="M9 3l3 8m0-8l3 8m-6-8h6" stroke="{color}" stroke-width="1.5" fill="none" stroke-linecap="round"/>
        </svg>''',
        "star": f'''<svg viewBox="0 0 24 24" width="24" height="24">
          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" fill="{color}" opacity="0.85"/>
        </svg>''',
        "hackathon": f'''<svg viewBox="0 0 24 24" width="24" height="24">
          <rect x="4" y="5" width="16" height="11" rx="1" fill="none" stroke="{color}" stroke-width="1.5"/>
          <rect x="3" y="16" width="18" height="1.5" rx="0.5" fill="{color}" opacity="0.85"/>
          <path d="M9 9l-2 3 2 3m6-6l2 3-2 3" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
        </svg>''',
    }
    return icons.get(icon_type, icons["trophy"])

def render_achievements_widget(achievements: list[AchievementData], theme_name: str = "dark", max_items: int = 5) -> str:
    t = THEMES[theme_name]
    items = ""
    accent_colors = [t["orange"], t["green"], t["accent"], t["purple"], t["pink"]]

    # Limit achievements to max_items
    shown = achievements[:max_items]
    if not shown:
        return ""

    for i, ach in enumerate(shown):
        y = i * 56
        color = accent_colors[i % len(accent_colors)]
        icon_svg = _achievement_icon_svg(ach.icon, color)

        items += f'''
    <g transform="translate(16, {y + 8})">
      <rect width="348" height="48" rx="8" fill="{color}" opacity="0.06"/>
      <rect width="348" height="48" rx="8" fill="none" stroke="{color}" stroke-width="0.5" opacity="0.3"/>
      <g transform="translate(12, 12)">
        {icon_svg}
      </g>
      <text x="48" y="20" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="13" font-weight="600" fill="{t["text"]}">{_escape(ach.title)}</text>
      <text x="48" y="36" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="10" fill="{t["text_secondary"]}">{_escape(ach.subtitle)}{(" · " + ach.event_date) if ach.event_date else ""}</text>
    </g>'''

    # Adjust height based on actual number of items shown
    total_h = len(shown) * 56 + 50
    return _card_wrapper(items, 380, total_h, t, "Achievements")

# ─── Composite Widget Builder ─────────────────────────────────────────────────

def compose_widget(
    widgets: dict[str, str],
    enabled: list[str],
    theme_name: str = "dark",
    username: str = "",
    avatar_b64: str = "",
) -> str:
    """
    Takes rendered SVG strings for each widget type and composes them
    into a single unified profile widget.
    """
    import re as _re
    t = THEMES[theme_name]
    total_w = 420
    header_h = 60
    padding = 20
    gap = 16

    # Parse each widget's height from its SVG
    parts = []
    for key in enabled:
        if key in widgets and widgets[key]:
            svg = widgets[key]
            hm = _re.search(r'height="(\d+)"', svg)
            h = int(hm.group(1)) if hm else 160
            parts.append((key, svg, h))

    content_h = sum(h for _, _, h in parts) + gap * max(len(parts) - 1, 0)
    total_h = header_h + content_h + padding * 2 + 10

    # Header
    avatar_svg = ""
    if avatar_b64:
        avatar_svg = f'''
    <defs><clipPath id="mainAvatarClip"><circle cx="30" cy="30" r="16"/></clipPath></defs>
    <image x="14" y="14" width="32" height="32" href="data:image/png;base64,{avatar_b64}" clip-path="url(#mainAvatarClip)"/>'''
    else:
        avatar_svg = f'<circle cx="30" cy="30" r="16" fill="{t["accent"]}" opacity="0.3"/>'

    header = f'''
    {avatar_svg}
    <text x="54" y="28" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="16" font-weight="700" fill="{t["text"]}">{_escape(username or "Developer")}</text>
    <text x="54" y="44" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="11" fill="{t["text_secondary"]}">GitHub Profile Widget</text>
    <line x1="{padding}" y1="{header_h}" x2="{total_w - padding}" y2="{header_h}"
          stroke="{t["card_border"]}" stroke-width="0.5"/>'''

    # Stack widgets via base64 data URI embedding
    y_offset = header_h + padding
    embedded = ""
    for key, svg, h in parts:
        svg_b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        embedded += f'''
    <image x="{padding}" y="{y_offset}" width="380" height="{h}"
           href="data:image/svg+xml;base64,{svg_b64}"/>'''
        y_offset += h + gap

    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{total_w}" height="{total_h}" viewBox="0 0 {total_w} {total_h}">
  <rect width="{total_w}" height="{total_h}" rx="16" fill="{t["bg"]}"/>
  <rect x="0.5" y="0.5" width="{total_w-1}" height="{total_h-1}" rx="16"
        fill="none" stroke="{t["card_border"]}" stroke-width="1"/>
  {header}
  {embedded}
  <text x="{total_w // 2}" y="{total_h - 8}" text-anchor="middle"
        font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
        font-size="9" fill="{t["text_secondary"]}" opacity="0.5">Generated with ♥</text>
</svg>'''


# ─── GitHub API Fetcher ───────────────────────────────────────────────────

# ─── GitHub API Fetcher ───────────────────────────────────────────────────────

def fetch_github_data(username: str, token: Optional[str] = None) -> dict:
    """
    Fetches all relevant GitHub data for a user.
    Returns a dict matching the structure expected by the DB / widget renderers.
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    base = "https://api.github.com"

    # User profile
    user = requests.get(f"{base}/users/{username}", headers=headers).json()

    # Repos (up to 100)
    repos = requests.get(
        f"{base}/users/{username}/repos",
        headers=headers,
        params={"per_page": 100, "sort": "pushed", "type": "owner"},
    ).json()

    # Events (recent activity)
    events = requests.get(
        f"{base}/users/{username}/events",
        headers=headers,
        params={"per_page": 100},
    ).json()

    # Avatar as base64
    avatar_b64 = ""
    if user.get("avatar_url"):
        try:
            resp = requests.get(user["avatar_url"] + "&s=64", timeout=5)
            if resp.ok:
                avatar_b64 = base64.b64encode(resp.content).decode("ascii")
        except Exception:
            pass

    return {
        "user": user,
        "repos": repos if isinstance(repos, list) else [],
        "events": events if isinstance(events, list) else [],
        "avatar_b64": avatar_b64,
    }


# ─── Data Processing (GitHub API → Widget Data) ──────────────────────────────

def compute_grade(github_data: dict) -> GradeData:
    """Compute a developer grade from GitHub profile data."""
    user = github_data["user"]
    repos = github_data["repos"]
    events = github_data["events"]

    repo_count = min(len(repos), 50)
    stars = sum(r.get("stargazers_count", 0) for r in repos)
    forks = sum(r.get("forks_count", 0) for r in repos)
    followers = user.get("followers", 0)
    commits = sum(len(ev.get("payload", {}).get("commits", [])) for ev in events if ev.get("type") == "PushEvent")
    prs = sum(1 for ev in events if ev.get("type") == "PullRequestEvent")

    scores = {
        "repos": min(repo_count / 30 * 100, 100),
        "stars": min(stars / 200 * 100, 100),
        "forks": min(forks / 50 * 100, 100),
        "followers": min(followers / 100 * 100, 100),
        "activity": min(len(events) / 80 * 100, 100),
    }

    total = sum(scores.values()) / len(scores)

    # Grade scale: S++/S+/S, A++/A+/A/A-, B++/B+/B/B-, C+/C/C-, D+/D/D-, F
    if total >= 97:    grade = "S++"
    elif total >= 93:  grade = "S+"
    elif total >= 89:  grade = "S"
    elif total >= 86:  grade = "A++"
    elif total >= 82:  grade = "A+"
    elif total >= 78:  grade = "A"
    elif total >= 72:  grade = "A-"
    elif total >= 68:  grade = "B++"
    elif total >= 64:  grade = "B+"
    elif total >= 58:  grade = "B"
    elif total >= 50:  grade = "B-"
    elif total >= 42:  grade = "C+"
    elif total >= 35:  grade = "C"
    elif total >= 28:  grade = "C-"
    elif total >= 20:  grade = "D+"
    elif total >= 12:  grade = "D"
    elif total >= 5:   grade = "D-"
    else:              grade = "F"

    stats = {
        "commits": commits,
        "prs": prs,
        "stars": stars,
        "repos": repo_count,
        "followers": followers,
    }

    tags = compute_tags(github_data)

    return GradeData(
        grade=grade,
        score=round(total, 1),
        stats=stats,
        tags=tags,
        breakdown={k: round(v, 1) for k, v in scores.items()},
    )

def compute_tags(github_data: dict) -> list[TagData]:
    """Infer developer tags from repo languages and topics."""
    repos = github_data["repos"]
    lang_counts = defaultdict(int)
    topic_set = set()

    for r in repos:
        lang = r.get("language")
        if lang:
            lang_counts[lang] += 1
        for topic in r.get("topics", []):
            topic_set.add(topic.lower())

    tags = []
    total = sum(lang_counts.values()) or 1

    # Language-based tags
    lang_map = {
        "Python": ["ml-engineer", "backend"], "JavaScript": ["frontend"],
        "TypeScript": ["frontend"], "Go": ["backend", "systems"],
        "Rust": ["systems"], "Java": ["backend"], "C++": ["systems"],
        "Swift": ["mobile"], "Kotlin": ["mobile"],
        "Dockerfile": ["devops"], "HCL": ["devops", "cloud"],
    }
    inferred = defaultdict(float)
    for lang, count in lang_counts.items():
        pct = count / total
        for tag in lang_map.get(lang, []):
            inferred[tag] = max(inferred[tag], pct)

    # Topic-based
    topic_map = {
        "machine-learning": "ml-engineer", "deep-learning": "ml-engineer",
        "frontend": "frontend", "react": "frontend", "vue": "frontend",
        "backend": "backend", "api": "backend", "database": "database",
        "devops": "devops", "docker": "devops", "kubernetes": "devops",
        "security": "security", "fullstack": "fullstack",
    }
    for topic in topic_set:
        if topic in topic_map:
            inferred[topic_map[topic]] = max(inferred.get(topic_map[topic], 0), 0.7)

    # Fullstack heuristic
    has_fe = any(lang_counts.get(l, 0) > 0 for l in ["JavaScript", "TypeScript"])
    has_be = any(lang_counts.get(l, 0) > 0 for l in ["Python", "Go", "Java", "Rust", "C++"])
    if has_fe and has_be:
        inferred["fullstack"] = max(inferred.get("fullstack", 0), 0.6)

    for tag, conf in sorted(inferred.items(), key=lambda x: -x[1])[:6]:
        tags.append(TagData(tag=tag, source="earned", confidence=round(conf, 2)))

    return tags


def compute_impact_timeline(github_data: dict) -> list[ImpactWeek]:
    """Aggregate events into weekly impact data."""
    events = github_data["events"]
    weekly = defaultdict(lambda: {"commits": 0, "additions": 0, "deletions": 0})

    for ev in events:
        if ev.get("type") == "PushEvent":
            created = ev.get("created_at", "")[:10]
            if created:
                dt = datetime.fromisoformat(created)
                week_start = (dt - timedelta(days=dt.weekday())).isoformat()[:10]
                commits = len(ev.get("payload", {}).get("commits", []))
                weekly[week_start]["commits"] += commits

    weeks = []
    for ws in sorted(weekly.keys()):
        d = weekly[ws]
        weeks.append(ImpactWeek(week_start=ws, commits=d["commits"]))

    return weeks


def compute_collaborators(github_data: dict) -> list[CollaboratorData]:
    """Find top collaborators from events."""
    events = github_data["events"]
    me = github_data["user"].get("login", "").lower()
    collab_stats = defaultdict(lambda: {"repos": set(), "commits": 0, "avatar": ""})

    for ev in events:
        actor = ev.get("actor", {}).get("login", "")
        if actor.lower() == me:
            # Look at mentions in PR/issue events
            if ev.get("type") in ("PullRequestEvent", "IssuesEvent"):
                payload = ev.get("payload", {})
                pr = payload.get("pull_request", {}) or payload.get("issue", {})
                assignees = pr.get("assignees", [])
                for a in assignees:
                    login = a.get("login", "")
                    if login.lower() != me:
                        collab_stats[login]["repos"].add(ev.get("repo", {}).get("name", ""))
                        collab_stats[login]["avatar"] = a.get("avatar_url", "")
                        collab_stats[login]["commits"] += 1
        else:
            repo = ev.get("repo", {}).get("name", "")
            collab_stats[actor]["repos"].add(repo)
            collab_stats[actor]["avatar"] = ev.get("actor", {}).get("avatar_url", "")
            collab_stats[actor]["commits"] += 1

    collabs = []
    for username, stats in sorted(collab_stats.items(), key=lambda x: -x[1]["commits"])[:5]:
        collabs.append(CollaboratorData(
            username=username,
            shared_repos=len(stats["repos"]),
            shared_commits=stats["commits"],
        ))

    return collabs

def compute_focus(github_data: dict) -> list[FocusCategory]:
    """Classify commits into focus categories."""
    repos = github_data["repos"]
    events = github_data["events"]

    lang_to_focus = {
        "Python": "Python", "JavaScript": "Frontend", "TypeScript": "Frontend",
        "HTML": "Frontend", "CSS": "Frontend", "Go": "Backend",
        "Rust": "Systems", "Java": "Backend", "C++": "Systems", "C": "Systems",
        "Ruby": "Backend", "PHP": "Backend", "Shell": "DevOps",
        "Dockerfile": "DevOps", "Jupyter Notebook": "ML",
    }

    focus_counts = defaultdict(int)
    repo_langs = {}
    for r in repos:
        lang = r.get("language")
        if lang:
            repo_langs[r["full_name"]] = lang

    for ev in events:
        if ev.get("type") == "PushEvent":
            repo_name = ev.get("repo", {}).get("name", "")
            lang = repo_langs.get(repo_name)
            focus = lang_to_focus.get(lang, "Other")
            commits = len(ev.get("payload", {}).get("commits", []))
            focus_counts[focus] += commits

    total = sum(focus_counts.values()) or 1
    return [
        FocusCategory(category=cat, percentage=round(count / total * 100, 1), commit_count=count)
        for cat, count in sorted(focus_counts.items(), key=lambda x: -x[1])
    ]


def compute_languages(github_data: dict) -> list[LanguageData]:
    """Compute language distribution from repos."""
    repos = github_data["repos"]
    lang_counts = defaultdict(int)
    for r in repos:
        lang = r.get("language")
        if lang:
            lang_counts[lang] += 1
    total = sum(lang_counts.values()) or 1
    return [
        LanguageData(language=lang, percentage=round(count / total * 100, 1), loc=count)
        for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1])
    ]


# ─── Main Entry Points ───────────────────────────────────────────────────────

def generate_widgets_from_github(github_data: dict, theme: str = "dark") -> dict[str, str]:
    """
    Takes raw GitHub API data (as stored in DB) and returns rendered SVG strings
    for each widget type.
    """
    grade = compute_grade(github_data)
    impact = compute_impact_timeline(github_data)
    collabs = compute_collaborators(github_data)
    focus = compute_focus(github_data)
    languages = compute_languages(github_data)

    return {
        "grade": render_grade_widget(grade, theme),
        "impact": render_impact_widget(impact, theme),
        "collaborators": render_collaborators_widget(collabs, theme),
        "focus": render_focus_widget(focus, theme, period="1y"),
        "languages": render_languages_widget(languages, theme),
    }


def generate_full_widget(
    username: str,
    token: Optional[str] = None,
    theme: str = "dark",
    enabled: Optional[list[str]] = None,
    achievements: Optional[list[AchievementData]] = None,
) -> str:
    if enabled is None:
        enabled = ["grade", "impact", "collaborators", "focus", "languages", "achievements"]

    print(f"Fetching GitHub data for {username}...")
    github_data = fetch_github_data(username, token)

    print("Generating widgets...")
    widgets = generate_widgets_from_github(github_data, theme)

    if achievements:
        widgets["achievements"] = render_achievements_widget(achievements, theme)

    for name, svg in widgets.items():
        if svg:
            with open(f"widget_{name}.svg", "w") as f:
                f.write(svg)
            print(f"  Saved widget_{name}.svg")

    print("Composing final widget...")
    composite = compose_widget(
        widgets=widgets,
        enabled=[e for e in enabled if e in widgets and widgets[e]],
        theme_name=theme,
        username=username,
        avatar_b64=github_data.get("avatar_b64", ""),
    )

    with open(f"widget_{username}.svg", "w") as f:
        f.write(composite)
    print(f"  Saved widget_{username}.svg")

    return composite


# ─── CLI Usage ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import os

    username = sys.argv[1] if len(sys.argv) > 1 else None
    token = os.environ.get("GITHUB_TOKEN")
    theme = sys.argv[2] if len(sys.argv) > 2 else "dark"

    if username:
        achievements = [
            AchievementData("MIT IQuHACK Winner", "1st Place · Quantum Track", "2025-01", "trophy"),
            AchievementData("MLH Top 50", "Global Hackathon League", "2025", "medal"),
        ]
        generate_full_widget(username, token, theme, achievements=achievements)
    else:
        print("Demo mode (no username). Generating with mock data...")

        grade = GradeData(
            grade="A+",
            score=86.2,
            stats={"commits": 1423, "prs": 87, "stars": 342, "repos": 28, "followers": 156},
            tags=[
                TagData("ml-engineer", "earned", 0.92),
                TagData("backend", "earned", 0.85),
                TagData("fullstack", "earned", 0.7),
                TagData("devops", "earned", 0.65),
                TagData("systems", "earned", 0.55),
                TagData("open-source", "chosen", 0.8),
            ],
        )

        weeks = [
            ImpactWeek(f"2025-{m:02d}-{d:02d}", commits=c)
            for m, d, c in [
                (7,7,12),(7,14,18),(7,21,25),(7,28,15),(8,4,30),(8,11,22),
                (8,18,35),(8,25,28),(9,1,40),(9,8,33),(9,15,45),(9,22,38),
                (9,29,50),(10,6,42),(10,13,55),(10,20,48),(10,27,60),(11,3,52),
                (11,10,65),(11,17,58),(11,24,70),(12,1,62),(12,8,75),(12,15,68),
            ]
        ]

        collabs = [
            CollaboratorData("torvalds", "", 3, 142),
            CollaboratorData("gaearon", "", 5, 98),
            CollaboratorData("karpathy", "", 2, 76),
            CollaboratorData("nat", "", 4, 51),
        ]

        focus = [
            FocusCategory("ML", 32.1, 192),
            FocusCategory("Frontend", 22.5, 135),
            FocusCategory("Backend", 18.8, 113),
            FocusCategory("DevOps", 14.2, 85),
            FocusCategory("Systems", 8.4, 50),
            FocusCategory("Data", 4.0, 24),
        ]

        languages = [
            LanguageData("Python", 38.5, 42),
            LanguageData("TypeScript", 22.0, 24),
            LanguageData("Go", 14.2, 15),
            LanguageData("Rust", 10.8, 12),
            LanguageData("Shell", 8.0, 9),
            LanguageData("Dockerfile", 6.5, 7),
        ]

        achievements = [
            AchievementData("MIT IQuHACK Winner", "1st Place · Quantum Track", "2025-01", "trophy"),
            AchievementData("MLH Top 50", "Global Hackathon League 2025", "2025", "medal"),
            AchievementData("BostonHacks Champion", "Best AI/ML Project", "2024-11", "hackathon"),
            AchievementData("CoreWeave Intern Hackathon", "Infrastructure Innovation Award", "2024-08", "star"),
        ]

        for t_name in ["dark", "light"]:
            widgets = {
                "grade": render_grade_widget(grade, t_name),
                "impact": render_impact_widget(weeks, t_name, "6mo"),
                "collaborators": render_collaborators_widget(collabs, t_name),
                "focus": render_focus_widget(focus, t_name, period="1y"),
                "languages": render_languages_widget(languages, t_name),
                "achievements": render_achievements_widget(achievements, t_name, max_items=4),
            }

            for name, svg in widgets.items():
                suffix = "" if t_name == "dark" else f"_{t_name}"
                path = f"widget_{name}{suffix}.svg"
                with open(path, "w") as f:
                    f.write(svg)
                print(f"  Saved {path}")

            composite = compose_widget(
                widgets=widgets,
                enabled=["grade", "impact", "collaborators", "focus", "languages", "achievements"],
                theme_name=t_name,
                username="demo_user",
            )
            suffix = "" if t_name == "dark" else f"_{t_name}"
            with open(f"widget_full{suffix}.svg", "w") as f:
                f.write(composite)
            print(f"  Saved widget_full{suffix}.svg")