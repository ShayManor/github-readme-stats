"""Generate static SVG examples for the README.

Renders each widget plus the composite card in every built-in theme using
plausible hand-crafted model instances. Outputs go to
`screenshots/examples/`. Run from the repo root:

    cd generator && python -m scripts.gen_readme_examples

No GitHub calls, no fetcher, no database.
"""
from __future__ import annotations

import os
import pathlib
import sys
from datetime import date, timedelta

# Ensure `src` package is importable when running `python -m scripts.*`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import (
    AchievementData,
    CollaboratorData,
    FocusCategory,
    GradeData,
    ImpactWeek,
    LanguageData,
    StreakData,
    TagData,
)
from src.widgets import (
    render_achievements_widget,
    render_collaborators_widget,
    render_focus_widget,
    render_grade_widget,
    render_impact_widget,
    render_languages_widget,
    render_streaks_widget,
)
from src.widgets.composite import compose_widget


OUT = pathlib.Path(__file__).resolve().parents[2] / "assets" / "examples"
OUT.mkdir(parents=True, exist_ok=True)


def grade_sample() -> GradeData:
    return GradeData(
        grade="A",
        score=88.4,
        stats={"commits": 1423, "prs": 87, "stars": 342, "repos": 28, "followers": 156},
        tags=[
            TagData(tag="Backend", source="earned", confidence=0.95),
            TagData(tag="ML", source="earned", confidence=0.82),
            TagData(tag="Systems", source="earned", confidence=0.70),
            TagData(tag="Cloud", source="earned", confidence=0.60),
            TagData(tag="founder", source="earned", label="Founder #42"),
            TagData(tag="Open Source", source="chosen"),
        ],
    )


def impact_sample() -> list[ImpactWeek]:
    today = date.today()
    start = today - timedelta(days=7 * 26)
    pattern = [3, 5, 8, 6, 11, 14, 9, 12, 18, 22, 17, 19, 25, 21, 28, 32, 26, 24,
               30, 35, 29, 33, 41, 38, 34, 37]
    weeks: list[ImpactWeek] = []
    for i, count in enumerate(pattern):
        weeks.append(ImpactWeek(week_start=(start + timedelta(days=7 * i)).isoformat(),
                                commits=count))
    return weeks


def streaks_sample() -> StreakData:
    today = date.today()
    return StreakData(
        current=23,
        max=61,
        current_start=(today - timedelta(days=22)).isoformat(),
        last_active_date=today.isoformat(),
        max_start=(today - timedelta(days=220)).isoformat(),
        max_end=(today - timedelta(days=160)).isoformat(),
    )


def collaborators_sample() -> list[CollaboratorData]:
    return [
        CollaboratorData(username="torvalds",     shared_repos=4, shared_commits=142),
        CollaboratorData(username="gaearon",      shared_repos=3, shared_commits=98),
        CollaboratorData(username="sindresorhus", shared_repos=2, shared_commits=64),
        CollaboratorData(username="tj",           shared_repos=2, shared_commits=47),
        CollaboratorData(username="yyx990803",    shared_repos=1, shared_commits=31),
    ]


def focus_sample() -> list[FocusCategory]:
    return [
        FocusCategory(category="Backend",  percentage=38.0, commit_count=412),
        FocusCategory(category="ML",       percentage=24.0, commit_count=260),
        FocusCategory(category="Frontend", percentage=18.0, commit_count=195),
        FocusCategory(category="DevOps",   percentage=12.0, commit_count=130),
        FocusCategory(category="Cloud",    percentage=8.0,  commit_count=87),
    ]


def languages_sample() -> list[LanguageData]:
    return [
        LanguageData(language="Python",     percentage=41.0, loc=180_432),
        LanguageData(language="TypeScript", percentage=23.0, loc=102_310),
        LanguageData(language="Go",         percentage=15.0, loc=66_540),
        LanguageData(language="Rust",       percentage=11.0, loc=48_210),
        LanguageData(language="Shell",      percentage=6.0,  loc=27_004),
        LanguageData(language="Dockerfile", percentage=4.0,  loc=18_120),
    ]


def achievements_sample() -> list[AchievementData]:
    return [
        AchievementData(title="Hackathon winner",
                        subtitle="Y Combinator AI Hackathon",
                        event_date="2025-11",
                        icon="hackathon"),
        AchievementData(title="Speaker at PyCon",
                        subtitle="Async at scale",
                        event_date="2024-05",
                        icon="star"),
        AchievementData(title="Open Source Award",
                        subtitle="GitHub Stars program",
                        event_date="2024-01",
                        icon="trophy"),
        AchievementData(title="AWS Certified Solutions Architect",
                        subtitle="Professional",
                        event_date="2023-09",
                        icon="medal"),
    ]


def render_all(theme: str, widget_settings: dict | None = None) -> dict[str, str]:
    ws = widget_settings or {}
    widgets = {
        "grade":         render_grade_widget(grade_sample(), theme, settings=ws.get("grade")),
        "impact":        render_impact_widget(impact_sample(), theme, settings=ws.get("impact")),
        "streaks":       render_streaks_widget(streaks_sample(), theme, settings=ws.get("streaks")),
        "collaborators": render_collaborators_widget(collaborators_sample(), theme, settings=ws.get("collaborators")),
        "focus":         render_focus_widget(focus_sample(), theme, settings=ws.get("focus")),
        "languages":     render_languages_widget(languages_sample(), theme, settings=ws.get("languages")),
        "achievements":  render_achievements_widget(achievements_sample(), theme, settings=ws.get("achievements")),
    }
    return widgets


def write(name: str, svg: str) -> None:
    (OUT / name).write_text(svg)
    print(f"  wrote {name}  ({len(svg)}B)")


def main() -> None:
    print(f"generating into {OUT}")

    # Individual widgets in the default theme.
    default = render_all("dark")
    for key, svg in default.items():
        write(f"{key}.svg", svg)

    # Composite card in every theme.
    for theme in ("dark", "onyx", "nord", "light", "paper"):
        widgets = render_all(theme)
        svg = compose_widget(
            widgets=widgets,
            enabled=["grade", "impact", "streaks", "collaborators", "focus", "languages", "achievements"],
            theme_name=theme,
            username="demo",
            show_name=False,
        )
        label = {"dark": "midnight", "light": "clean"}.get(theme, theme)
        write(f"composite-{label}.svg", svg)

    # Customization demos.
    purple_impact = render_impact_widget(impact_sample(), "dark",
                                         settings={"line_color": "#a78bfa"})
    write("impact-purple.svg", purple_impact)

    green_streaks = render_streaks_widget(streaks_sample(), "dark",
                                          settings={"color": "#3fb950"})
    write("streaks-green.svg", green_streaks)

    compact_grade = render_grade_widget(grade_sample(), "dark",
                                        settings={"max_tags": 3})
    write("grade-compact.svg", compact_grade)

    hidden_langs = render_languages_widget(
        [l for l in languages_sample() if l.language not in {"Shell", "Dockerfile"}],
        "dark",
    )
    write("languages-hide.svg", hidden_langs)

    # Composite picking only a few widgets, onyx theme.
    onyx_widgets = render_all("onyx")
    svg = compose_widget(
        widgets={k: onyx_widgets[k] for k in ("grade", "streaks", "languages")},
        enabled=["grade", "streaks", "languages"],
        theme_name="onyx",
        username="demo",
        show_name=False,
    )
    write("composite-custom.svg", svg)

    print("done")


if __name__ == "__main__":
    main()
