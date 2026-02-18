"""Grade widget rendering."""

import math
from ..models import GradeData
from ..themes import THEMES, TAG_COLORS, GRADE_COLORS
from ..utils import escape, card_wrapper, icon_svg


def render_grade_widget(data: GradeData, theme_name: str = "dark") -> str:
    """Renders the developer grade widget with stats and tags."""
    t = THEMES[theme_name]
    base = data.grade[0]
    color = GRADE_COLORS.get(base, t["accent"])
    score = data.score

    radius = 36
    circumference = 2 * math.pi * radius
    offset = circumference * (1 - score / 100)
    grade_font = 30 if len(data.grade) <= 2 else 22

    # Stats row with icons
    stat_labels = {
        "commits": "Commits",
        "prs": "PRs",
        "stars": "Stars",
        "repos": "Repos",
        "followers": "Followers"
    }
    stat_keys = [k for k in ["commits", "prs", "stars", "repos", "followers"] if k in data.stats]
    stats_svg = ""
    stat_w = 340 / max(len(stat_keys), 1)

    for i, key in enumerate(stat_keys):
        val = data.stats[key]
        sx = i * stat_w + stat_w / 2
        val_str = f"{val:,}" if val < 100000 else f"{val/1000:.0f}k"
        stats_svg += f'''
      <g transform="translate({sx}, 0)">
        <g transform="translate(-7, 0)">{icon_svg(key, t["text_secondary"])}</g>
        <text x="0" y="28" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
              font-size="14" font-weight="700" fill="{t["text"]}">{val_str}</text>
        <text x="0" y="41" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
              font-size="9" fill="{t["text_secondary"]}">{stat_labels.get(key, key)}</text>
      </g>'''

    # Tag pills
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
              font-size="10" font-weight="500" fill="{tag_color}">{escape(label)}</text>
      </g>'''
        tx += tw + 6

    tags_h = ty + 24 if data.tags else 0

    # Layout
    stats_y = 100
    tags_y = stats_y + 54
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
            font-size="{grade_font}" font-weight="800" fill="{color}">{escape(data.grade)}</text>
      <text x="0" y="18" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="11" fill="{t["text_secondary"]}">{score:.0f} / 100</text>
    </g>
    <line x1="100" y1="16" x2="100" y2="80" stroke="{t["grid"]}" stroke-width="1"/>
    <g transform="translate(114, 26)">
      <text x="0" y="10" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="16" font-weight="700" fill="{t["text"]}">Developer Profile</text>
      <text x="0" y="28" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="11" fill="{t["text_secondary"]}">Grade <tspan fill="{color}" font-weight="700">{escape(data.grade)}</tspan> · {score:.0f}/100</text>
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

    return card_wrapper(inner, 380, card_h, t, "")
