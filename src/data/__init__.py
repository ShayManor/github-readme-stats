"""Data fetching and processing for GitHub profiles.

Note: ``fetch_github_data`` is intentionally NOT re-exported from this package
so that importing :mod:`src.data.processor` (used by the generator service)
does not transitively pull in the fetcher module and its ``requests`` dependency.
Import it directly from ``src.data.fetcher`` when you need it.
"""

from .processor import (
    compute_grade,
    compute_impact_timeline,
    compute_collaborators,
    compute_focus,
    compute_languages,
    generate_widgets_from_github,
)

__all__ = [
    "compute_grade",
    "compute_impact_timeline",
    "compute_collaborators",
    "compute_focus",
    "compute_languages",
    "generate_widgets_from_github",
]
