"""Grade widget rendering."""

import math
from ..models import GradeData
from ..themes import THEMES, TAG_COLORS, GRADE_COLORS
from ..utils import escape, card_wrapper, icon_svg

# Tokens that should render uppercase instead of title-cased (e.g. "ml-engineer"
# → "ML Engineer", not "Ml Engineer").
_TAG_ACRONYMS = {"ml", "ai", "ui", "ux", "api", "cli", "sql", "css", "html", "js", "ios"}

# Human-readable names for the breakdown factors `compute_grade` emits. Used in
# the subtitle's "Strong in ..." callout to surface the two highest-scoring
# pillars of the grade — real info instead of repeating the letter + score.
_BREAKDOWN_LABELS = {
    "commits": "Commits",
    "consistency": "Consistency",
    "repos": "Repos",
    "stars": "Stars",
    "forks": "Forks",
    "activity": "Activity",
    "followers": "Followers",
}


def _top_strengths(breakdown: dict | None, n: int = 2) -> list[str]:
    if not breakdown:
        return []
    ranked = sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)
    return [_BREAKDOWN_LABELS.get(k, k.capitalize()) for k, _ in ranked[:n]]


def _format_tag_label(tag: str) -> str:
    # Custom tags may define an explicit label in src/tag_rules.py::TAG_DEFS.
    try:
        from .. import tag_rules
        meta = tag_rules.TAG_DEFS.get(tag)
        if meta and meta.get("label"):
            return meta["label"]
    except Exception:
        pass
    return " ".join(
        w.upper() if w.lower() in _TAG_ACRONYMS else w.capitalize()
        for w in tag.split("-")
    )


def render_grade_widget(data: GradeData, theme_name: str = "dark", settings: dict | None = None) -> str:
    """Renders the developer grade widget with stats and tags.

    Settings:
        max_tags (int): Max tags to display (default all)
    """
    t = THEMES[theme_name]
    s = settings or {}
    max_tags = s.get("max_tags")
    if max_tags is not None:
        max_tags = min(max(int(max_tags), 1), 20)
        data = GradeData(
            grade=data.grade, score=data.score, stats=data.stats,
            tags=data.tags[:max_tags] if data.tags else [],
            breakdown=data.breakdown,
        )
    base = data.grade[0]
    color = GRADE_COLORS.get(base, t["accent"])
    score = data.score

    radius = 36
    circumference = 2 * math.pi * radius
    # S-tier grades get a fully closed ring regardless of exact score — the
    # letter "S" itself carries the "top of the scale" meaning, so the visual
    # should match. S+, S++ share the full circle.
    offset = 0 if base == "S" else circumference * (1 - score / 100)
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
        label = getattr(tag, "label", None) or _format_tag_label(tag.tag)
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
    # Reserve space at the bottom for the "Generated with gh-stats"
    # attribution. Matches the composite widget's footer convention so
    # the standalone grade widget feels visually consistent when it's
    # embedded on its own (the /api/<u>/grade.svg path).
    footer_h = 16
    card_h = (tags_y + tags_h + tag_padding) if data.tags else (stats_y + 54)
    card_h += footer_h

    strengths = _top_strengths(data.breakdown)
    strengths_line = f"Strong in {' · '.join(strengths)}" if strengths else ""

    inner = f'''
    <g transform="translate(52, 48)">
      <circle cx="0" cy="0" r="{radius}" fill="none" stroke="{t["grid"]}" stroke-width="5"/>
      <circle cx="0" cy="0" r="{radius}" fill="none" stroke="{color}" stroke-width="5"
              stroke-dasharray="{circumference}" stroke-dashoffset="{offset}"
              stroke-linecap="round" transform="rotate(-90)">
        <animate attributeName="stroke-dashoffset" from="{circumference}" to="{offset}" dur="1s" fill="freeze"/>
      </circle>
      <text x="0" y="{grade_font * 0.35:.2f}" text-anchor="middle"
            font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="{grade_font}" font-weight="800" fill="{color}">{escape(data.grade)}</text>
    </g>
    <line x1="100" y1="16" x2="100" y2="80" stroke="{t["grid"]}" stroke-width="1"/>
    <g transform="translate(114, 26)">
      <text x="0" y="10" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="16" font-weight="700" fill="{t["text"]}">Developer Profile</text>
      <text x="0" y="32" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="11" fill="{t["text_secondary"]}">{strengths_line}</text>
      <text x="0" y="50" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="10" fill="{t["text_secondary"]}" letter-spacing="0.4">Score <tspan fill="{t["text"]}" font-weight="600">{score:.0f}</tspan> / 100</text>
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

    # Footer attribution. Positioned in the inner-svg coordinate space
    # (card_wrapper passes title="" here, so inner is not vertically
    # offset). 8px above the bottom edge mirrors the composite widget.
    inner += f'''
    <text x="190" y="{card_h - 8}" text-anchor="middle"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="9" fill="{t["text_secondary"]}" opacity="0.5">Generated with gh-stats</text>'''

    return card_wrapper(inner, 380, card_h, t, "")
