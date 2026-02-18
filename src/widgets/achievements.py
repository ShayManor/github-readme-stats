"""Achievements widget rendering."""

from ..models import AchievementData
from ..themes import THEMES
from ..utils import escape, card_wrapper


def _achievement_icon_svg(icon_type: str, color: str) -> str:
    """Returns SVG for achievement icons (24x24)."""
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


def render_achievements_widget(
    achievements: list[AchievementData],
    theme_name: str = "dark",
    max_items: int = 5
) -> str:
    """Renders the achievements widget with icons and descriptions."""
    t = THEMES[theme_name]
    items = ""
    accent_colors = [t["orange"], t["green"], t["accent"], t["purple"], t["pink"]]

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
            font-size="13" font-weight="600" fill="{t["text"]}">{escape(ach.title)}</text>
      <text x="48" y="36" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="10" fill="{t["text_secondary"]}">{escape(ach.subtitle)}{(" · " + ach.event_date) if ach.event_date else ""}</text>
    </g>'''

    total_h = len(shown) * 56 + 50
    return card_wrapper(items, 380, total_h, t, "Achievements")
