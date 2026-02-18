"""Focus areas widget rendering."""

from ..models import FocusCategory
from ..themes import THEMES, FOCUS_COLORS
from ..utils import escape, card_wrapper


def render_focus_widget(categories: list[FocusCategory], theme_name: str = "dark", period: str = "1y") -> str:
    """Renders the focus areas widget with horizontal bars."""
    t = THEMES[theme_name]
    cats = sorted(categories, key=lambda c: -c.percentage)[:6]
    if not cats:
        return ""

    # Format period for display
    period_map = {
        "1w": "last week",
        "1m": "last month",
        "3m": "last 3 months",
        "6m": "last 6 months",
        "1y": "last year",
        "all": "all time"
    }
    period_display = period_map.get(period, period)

    max_pct = cats[0].percentage if cats else 100
    max_pct = max(max_pct, 1)  # Avoid division by zero
    bar_max_w = 210
    items = ""

    for i, cat in enumerate(cats):
        color = FOCUS_COLORS[i % len(FOCUS_COLORS)]
        y = i * 36
        bar_w = (cat.percentage / max_pct) * bar_max_w

        items += f'''
    <g transform="translate(16, {y})">
      <text x="0" y="14" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="12" font-weight="600" fill="{t["text"]}">{escape(cat.category)}</text>
      <rect x="90" y="4" width="{bar_max_w}" height="14" rx="7" fill="{t["grid"]}"/>
      <rect x="90" y="4" width="{bar_w}" height="14" rx="7" fill="{color}" opacity="0.8">
        <animate attributeName="width" from="0" to="{bar_w}" dur="0.7s" fill="freeze"/>
      </rect>
      <text x="90" y="32" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="9" fill="{t["text_secondary"]}">{cat.commit_count} commits</text>
      <text x="{90 + bar_max_w + 8}" y="15" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="12" font-weight="700" fill="{color}">{cat.percentage:.0f}%</text>
    </g>'''

    # Add period subtitle
    subtitle_y = len(cats) * 36 + 8
    items += f'''
    <text x="16" y="{subtitle_y}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="9" fill="{t["text_secondary"]}" opacity="0.7">Recent activity · {period_display}</text>'''

    card_h = len(cats) * 36 + 54
    return card_wrapper(items, 380, card_h, t, "Recent Focus")
