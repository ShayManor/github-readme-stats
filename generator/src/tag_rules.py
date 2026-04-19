"""Auto-awarded profile tags.

This is the single place to add new custom tags. Three pieces plug together:

    TAG_DEFS    — display metadata (color, label) for each tag ID.
    USER_TAGS   — hardcoded tags by username. Great for VIP/creator badges.
    TAG_RULES   — predicate-driven awards based on account signals.

To add a new tag:
    1. Add its color + label to TAG_DEFS below.
    2. Award it either by listing the username in USER_TAGS, or by appending
       a (tag_id, predicate) pair to TAG_RULES.

Predicates receive (username, github_data) and return one of:
    False / None   — not awarded
    True           — awarded with the default TAG_DEFS label
    str            — awarded with this string as a custom label (e.g. "Founder #42")

Any exception inside a predicate is swallowed — a broken rule can't break the
whole tag pipeline.
"""
from typing import Callable, Union


# ---- Display metadata -------------------------------------------------------

TAG_DEFS: dict[str, dict] = {
    "creator": {"color": "#f472b6", "label": "Creator"},
    "open-source": {"color": "#3fb950", "label": "Open Source"},
    "founder": {"color": "#facc15", "label": "Founder"},
    "hackathon-winner": {"color": "#fb923c", "label": "Hackathon Winner"},
    "early-adopter": {"color": "#a78bfa", "label": "Early Adopter"},
}


# ---- Username → tags --------------------------------------------------------
# Usernames are compared case-insensitively.

USER_TAGS: dict[str, list[str]] = {
    "shaymanor": ["creator"],
}


# ---- Rule predicates --------------------------------------------------------

PredicateResult = Union[bool, str, None]


def _open_source_maintainer(username: str, data: dict) -> PredicateResult:
    """At least 3 non-fork repos with ≥10 stars, OR ≥50 total stars."""
    repos = data.get("repos") or []
    non_fork = [r for r in repos if not r.get("fork")]
    popular = sum(1 for r in non_fork if (r.get("stargazers_count") or 0) >= 10)
    total_stars = sum((r.get("stargazers_count") or 0) for r in non_fork)
    return popular >= 3 or total_stars >= 50


def _first_n_enrolled(n: int) -> Callable[[str, dict], PredicateResult]:
    """Returns a predicate that fires for users in the first N enrollments.

    When it fires, the label includes the rank (e.g. "Founder #42").
    """
    def predicate(username: str, _data: dict) -> PredicateResult:
        from .db import enrollment_rank
        rank = enrollment_rank(username)
        if rank is None or rank > n:
            return False
        return f"Founder #{rank}"
    return predicate


TAG_RULES: list[tuple[str, Callable[[str, dict], PredicateResult]]] = [
    ("open-source", _open_source_maintainer),
    ("founder", _first_n_enrolled(1000)),
]


# ---- Entry point ------------------------------------------------------------

def evaluate(username: str, github_data: dict) -> list[tuple[str, str | None]]:
    """Return ordered (tag_id, label_override) pairs awarded to this user.

    label_override is None unless the predicate returned a string, in which
    case that string replaces the default TAG_DEFS label for this user.
    """
    awarded: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    key = (username or "").lower()

    for tag in USER_TAGS.get(key, []):
        if tag not in seen:
            awarded.append((tag, None))
            seen.add(tag)

    for tag, predicate in TAG_RULES:
        if tag in seen:
            continue
        try:
            result = predicate(username, github_data)
        except Exception:
            continue
        if not result:
            continue
        label = result if isinstance(result, str) else None
        awarded.append((tag, label))
        seen.add(tag)

    return awarded
