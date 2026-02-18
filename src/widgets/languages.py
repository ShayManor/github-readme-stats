"""Languages widget rendering."""

import math
from ..models import LanguageData
from ..themes import THEMES, LANG_COLORS, FOCUS_COLORS
from ..utils import escape, card_wrapper


def render_languages_widget(languages: list[LanguageData], theme_name: str = "dark") -> str:
    """Renders the languages donut chart widget."""
    t = THEMES[theme_name]
    top_langs = sorted(languages, key=lambda l: -l.percentage)[:5]
    if not top_langs:
        return ""

    # Ensure percentages always sum to exactly 100% for a complete circle
    total_percentage = sum(lang.percentage for lang in top_langs)
    langs = list(top_langs)

    # Add "Other" category if there are remaining languages
    if total_percentage < 99.9 and len(languages) > 5:
        other_percentage = 100 - total_percentage
        from ..models import LanguageData
        langs.append(LanguageData(
            language="Other",
            percentage=round(other_percentage, 1),
            loc=0
        ))
    elif total_percentage < 99.9:
        # If we have <= 5 languages total but they don't sum to 100%,
        # adjust the percentages proportionally to sum to 100%
        if total_percentage > 0:
            factor = 100 / total_percentage
            for lang in langs:
                lang.percentage = round(lang.percentage * factor, 1)

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
        # Use gray for "Other" category
        if lang.language == "Other":
            color = t["text_secondary"]
        else:
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
            font-size="12" fill="{t["text"]}">{escape(lang.language)}</text>
      <text x="210" y="9" text-anchor="end" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="11" font-weight="600" fill="{t["text_secondary"]}">{lang.percentage:.0f}%</text>
    </g>'''

    # Center circle with top language
    top_lang = langs[0].language if langs else ""
    center = f'''
    <circle cx="{cx}" cy="{cy}" r="{inner_r}" fill="{t["card_bg"]}"/>
    <text x="{cx}" y="{cy + 1}" text-anchor="middle" dominant-baseline="middle"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="11" font-weight="700" fill="{t["text"]}">{escape(top_lang)}</text>'''

    inner = f'''
    <g transform="translate(16, 0)">
      {arcs}
      {center}
      {legend}
    </g>'''

    rows_h = max(len(langs) * 22 + 40, 120)
    return card_wrapper(inner, 380, rows_h + 36, t, "Languages")
