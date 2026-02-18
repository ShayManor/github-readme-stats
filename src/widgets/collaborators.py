"""Collaborators widget rendering."""

from ..models import CollaboratorData
from ..themes import THEMES
from ..utils import escape, card_wrapper


def render_collaborators_widget(collabs: list[CollaboratorData], theme_name: str = "dark") -> str:
    """Renders the top collaborators widget with avatars and contribution bars."""
    t = THEMES[theme_name]
    items = ""

    for i, c in enumerate(collabs[:4]):
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
                  font-size="14" font-weight="600" fill="white">{escape(c.username[0].upper())}</text>'''

        bar_max = max((x.shared_commits for x in collabs[:4]), default=1) or 1
        bar_w = c.shared_commits / bar_max * 120

        items += f'''
    <g transform="translate(36, {y + 20})">
      {avatar_el}
      <text x="28" y="-2" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="13" font-weight="600" fill="{t["text"]}">{escape(c.username)}</text>
      <text x="28" y="14" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="10" fill="{t["text_secondary"]}">{c.shared_repos} repos · {c.shared_commits} commits</text>
      <rect x="200" y="-6" width="130" height="8" rx="4" fill="{t["grid"]}"/>
      <rect x="200" y="-6" width="{bar_w}" height="8" rx="4" fill="{t["purple"]}" opacity="0.8">
        <animate attributeName="width" from="0" to="{bar_w}" dur="0.6s" fill="freeze"/>
      </rect>
    </g>'''

    total_h = len(collabs[:4]) * 50 + 48
    return card_wrapper(items, 380, total_h, t, "Top Collaborators")
