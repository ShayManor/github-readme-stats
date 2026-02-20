#!/usr/bin/env python3
"""
GitHub Profile Widget Generator
Generates polished SVG mini-widgets from GitHub profile data.
"""

import sys
import os
from typing import Optional

from .models import AchievementData
from .data import fetch_github_data, generate_widgets_from_github
from .widgets import render_achievements_widget, compose_widget


def generate_full_widget(
    username: str,
    token: Optional[str] = None,
    theme: str = "dark",
    enabled: Optional[list[str]] = None,
    achievements: Optional[list[AchievementData]] = None,
) -> str:
    """Generate a complete profile widget for a GitHub user."""
    if enabled is None:
        enabled = [
            "grade",
            "impact",
            "collaborators",
            "focus",
            "languages",
            "achievements",
        ]

    print(f"Fetching GitHub data for {username}...")
    github_data = fetch_github_data(username, token)

    # Log contribution counts
    total_commits = github_data.get("total_commits", 0)
    recent_commits = github_data.get("recent_commits", 0)
    total_prs = github_data.get("total_prs", 0)
    daily_commits = len(github_data.get("commits", []))

    if total_commits > 0:
        print(f"  Total contributions (all-time): {total_commits:,}")
        print(f"  Recent contributions (6 months): {recent_commits:,}")
        print(f"  Total PRs (all-time): {total_prs:,}")
        print(f"  Daily contribution data points: {daily_commits}")
    else:
        print(f"  Warning: Could not fetch contribution count")
        if daily_commits == 0:
            print(f"    Try running with GITHUB_PAT environment variable")

    print("Generating widgets...")
    widgets = generate_widgets_from_github(github_data, theme)

    if achievements:
        widgets["achievements"] = render_achievements_widget(
            achievements, theme
        )

    # Save individual widgets
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


def main():
    """CLI entry point."""
    username = sys.argv[1] if len(sys.argv) > 1 else "shaymanor"
    token = os.environ.get("GITHUB_PAT")
    theme = sys.argv[2] if len(sys.argv) > 2 else "dark"

    if username:
        achievements = [
            AchievementData(
                "MIT IQuHACK Winner",
                "1st Place · Quantum Track",
                "2025-01",
                "trophy",
            ),
            AchievementData(
                "MLH Top 50", "Global Hackathon League", "2025", "medal"
            ),
        ]
        generate_full_widget(username, token, theme, achievements=achievements)
    else:
        print("Usage: python generate.py <username> [theme]")
        sys.exit(1)


if __name__ == "__main__":
    main()
