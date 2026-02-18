"""Data fetching and processing for GitHub profiles."""

from .fetcher import fetch_github_data
from .processor import (
    compute_grade,
    compute_impact_timeline,
    compute_collaborators,
    compute_focus,
    compute_languages,
    generate_widgets_from_github,
)

__all__ = [
    "fetch_github_data",
    "compute_grade",
    "compute_impact_timeline",
    "compute_collaborators",
    "compute_focus",
    "compute_languages",
    "generate_widgets_from_github",
]
