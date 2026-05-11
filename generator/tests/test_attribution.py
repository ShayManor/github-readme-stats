"""Per-widget attribution behaves correctly in both contexts.

Standalone widget SVGs (served at /api/<u>/<widget>.svg) must show the
"Generated with gh-stats" footer; the composite (served at /api/<u>)
must strip the per-widget footer and only show its own bottom one.
"""
from src.models import GradeData, LanguageData, TagData
from src.widgets import (
    render_grade_widget,
    render_languages_widget,
    compose_widget,
)


def _grade_fixture() -> GradeData:
    return GradeData(
        grade="A", score=80,
        stats={"commits": 100, "prs": 10, "stars": 5, "repos": 3, "followers": 1},
        tags=[TagData(tag="builder", source="earned")],
        breakdown={"commits": 0.8, "consistency": 0.6, "stars": 0.4},
    )


def _languages_fixture() -> list[LanguageData]:
    return [
        LanguageData(language="Python", percentage=60.0, loc=0),
        LanguageData(language="TypeScript", percentage=40.0, loc=0),
    ]


def test_standalone_grade_widget_has_attribution():
    svg = render_grade_widget(_grade_fixture(), theme_name="dark")
    assert "Generated with gh-stats" in svg
    assert 'data-gh-attribution="1"' in svg


def test_standalone_languages_widget_has_attribution():
    svg = render_languages_widget(_languages_fixture(), theme_name="dark")
    assert "Generated with gh-stats" in svg
    assert 'data-gh-attribution="1"' in svg


def test_composite_strips_per_widget_attribution_from_grade():
    """Embedded inside the composite, the grade widget's per-widget
    attribution must be removed — the composite has its own footer at
    the bottom, showing both would be visually redundant."""
    grade_svg = render_grade_widget(_grade_fixture(), theme_name="dark")
    composite = compose_widget(
        widgets={"grade": grade_svg},
        enabled=["grade"],
        theme_name="dark",
        username="alice",
        avatar_b64="",
        show_name=False,
    )
    # The composite has exactly ONE attribution (its own). The widget's
    # footer attribution should be gone.
    assert composite.count("Generated with gh-stats") == 1
    # No leftover attribution markers leaked through.
    assert "data-gh-attribution" not in composite


def test_composite_strips_per_widget_attribution_from_languages():
    langs_svg = render_languages_widget(_languages_fixture(), theme_name="dark")
    composite = compose_widget(
        widgets={"languages": langs_svg},
        enabled=["languages"],
        theme_name="dark",
        username="alice",
        avatar_b64="",
        show_name=False,
    )
    assert composite.count("Generated with gh-stats") == 1
    assert "data-gh-attribution" not in composite


def test_composite_strips_attribution_from_multiple_widgets():
    """When several attribution-bearing widgets are inlined together,
    the composite still shows only its own single footer line."""
    grade_svg = render_grade_widget(_grade_fixture(), theme_name="dark")
    langs_svg = render_languages_widget(_languages_fixture(), theme_name="dark")
    composite = compose_widget(
        widgets={"grade": grade_svg, "languages": langs_svg},
        enabled=["grade", "languages"],
        theme_name="dark",
        username="alice",
        avatar_b64="",
        show_name=False,
    )
    # Each widget contributed an attribution; the composite contributes
    # one of its own — total visible attributions must be exactly 1.
    assert composite.count("Generated with gh-stats") == 1


def test_composite_reclaims_attribution_height():
    """Stripping the attribution from a per-widget SVG must also reduce
    the slot height the composite reserves — otherwise we'd leave 16px
    of empty space at the bottom of every embedded widget."""
    from src.widgets import composite as composite_mod

    grade_svg = render_grade_widget(_grade_fixture(), theme_name="dark")
    inner_with_attr, h_with_attr = composite_mod._extract_inner(grade_svg, "grade")
    # The standalone grade SVG declares its full height including the
    # 16px footer; the embed height should be 16 less.
    import re
    full_h = int(re.search(r'height="(\d+)"', grade_svg).group(1))
    assert h_with_attr == full_h - 16
    assert "data-gh-attribution" not in inner_with_attr
