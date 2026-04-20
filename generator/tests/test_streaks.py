from datetime import date, timedelta
from unittest.mock import patch

import pytest

from src import processor
from src.models import StreakData


TODAY = date(2026, 4, 19)


@pytest.fixture
def freeze_today(monkeypatch):
    """Pin processor's notion of 'today' so the grace rule is testable."""
    class _FakeDatetime:
        @staticmethod
        def utcnow():
            from datetime import datetime
            return datetime(TODAY.year, TODAY.month, TODAY.day, 12, 0, 0)
    monkeypatch.setattr(processor, "datetime", _FakeDatetime)
    return TODAY


def _days(dates):
    """Turn a list of date objects into the fetcher's commits-array shape."""
    return [{"date": d.isoformat(), "count": 1} for d in dates]


def test_compute_streaks_empty_preserves_stored_max(freeze_today):
    stored = {
        "max_streak": 30, "max_start": "2024-06-01", "max_end": "2024-06-30",
        "current_streak": 0, "current_start": "",
        "last_active_date": "2024-06-30",
    }
    s = processor.compute_streaks({"commits": []}, stored)
    assert s.current == 0
    assert s.max == 30
    assert s.max_start == "2024-06-01"
    assert s.max_end == "2024-06-30"


def test_compute_streaks_current_today(freeze_today):
    dates = [freeze_today - timedelta(days=i) for i in range(5)]
    s = processor.compute_streaks({"commits": _days(dates)}, None)
    assert s.current == 5
    assert s.current_start == (freeze_today - timedelta(days=4)).isoformat()
    assert s.last_active_date == freeze_today.isoformat()


def test_compute_streaks_grace_day(freeze_today):
    yesterday = freeze_today - timedelta(days=1)
    dates = [yesterday - timedelta(days=i) for i in range(4)]
    s = processor.compute_streaks({"commits": _days(dates)}, None)
    assert s.current == 4
    assert s.current_start == (yesterday - timedelta(days=3)).isoformat()
    assert s.last_active_date == yesterday.isoformat()


def test_compute_streaks_current_broken(freeze_today):
    two_days_ago = freeze_today - timedelta(days=2)
    dates = [two_days_ago - timedelta(days=i) for i in range(10)]
    s = processor.compute_streaks({"commits": _days(dates)}, None)
    assert s.current == 0
    assert s.current_start == ""
    assert s.last_active_date == two_days_ago.isoformat()


def test_compute_streaks_max_within_window_beats_stored(freeze_today):
    start = freeze_today - timedelta(days=30)
    dates = [start + timedelta(days=i) for i in range(10)]
    stored = {
        "max_streak": 5, "max_start": "2020-01-01", "max_end": "2020-01-05",
        "current_streak": 0, "current_start": "", "last_active_date": "",
    }
    s = processor.compute_streaks({"commits": _days(dates)}, stored)
    assert s.max == 10
    assert s.max_start == start.isoformat()
    assert s.max_end == (start + timedelta(days=9)).isoformat()


def test_compute_streaks_stored_max_preserved(freeze_today):
    start = freeze_today - timedelta(days=10)
    dates = [start + timedelta(days=i) for i in range(3)]
    stored = {
        "max_streak": 50, "max_start": "2023-04-01", "max_end": "2023-05-20",
        "current_streak": 0, "current_start": "", "last_active_date": "",
    }
    s = processor.compute_streaks({"commits": _days(dates)}, stored)
    assert s.max == 50
    assert s.max_start == "2023-04-01"
    assert s.max_end == "2023-05-20"


def test_compute_streaks_current_equals_new_max(freeze_today):
    dates = [freeze_today - timedelta(days=i) for i in range(100)]
    s = processor.compute_streaks({"commits": _days(dates)}, None)
    assert s.current == 100
    assert s.max == 100
    assert s.max_end == freeze_today.isoformat()


def test_compute_streaks_ignores_zero_count_entries(freeze_today):
    dates = [freeze_today - timedelta(days=i) for i in range(3)]
    commits = _days(dates) + [{"date": (freeze_today - timedelta(days=5)).isoformat(), "count": 0}]
    s = processor.compute_streaks({"commits": commits}, None)
    assert s.current == 3
    assert s.max == 3


from src.widgets import render_streaks_widget


def test_render_streaks_contains_values():
    data = StreakData(
        current=7, max=42,
        current_start="2026-04-13", last_active_date="2026-04-19",
        max_start="2024-03-01", max_end="2024-04-11",
    )
    svg = render_streaks_widget(data, theme_name="dark")
    assert svg.startswith("<svg")
    assert "</svg>" in svg
    assert ">7<" in svg
    assert ">42<" in svg
    assert "CURRENT" in svg
    assert "LONGEST" in svg


def test_render_streaks_zero_values_render():
    data = StreakData(current=0, max=0)
    svg = render_streaks_widget(data, theme_name="dark")
    assert ">0<" in svg
    assert "CURRENT" in svg
    assert "LONGEST" in svg


def test_render_streaks_custom_color_applies_to_current_and_bar():
    data = StreakData(
        current=7, max=42,
        current_start="2026-04-13", last_active_date="2026-04-19",
        max_start="2024-03-01", max_end="2024-04-11",
    )
    svg = render_streaks_widget(data, theme_name="dark", settings={"color": "#ff00aa"})
    # Current number + bar fill + end-cap dot all use the override.
    assert svg.count("#ff00aa") >= 3
    # Theme accent (#58a6ff) must not leak through when overridden.
    assert "#58a6ff" not in svg


def test_render_streaks_invalid_color_falls_back_to_theme():
    data = StreakData(current=3, max=10, current_start="2026-04-18",
                      last_active_date="2026-04-20",
                      max_start="2025-01-01", max_end="2025-01-10")
    svg = render_streaks_widget(data, theme_name="dark",
                                settings={"color": "javascript:alert(1)"})
    assert "javascript" not in svg
    assert "#58a6ff" in svg  # theme accent fallback


def test_render_streaks_cross_year_longest_shows_both_years():
    data = StreakData(
        current=5, max=37,
        current_start="2026-04-16", last_active_date="2026-04-20",
        max_start="2024-12-20", max_end="2025-01-25",
    )
    svg = render_streaks_widget(data, theme_name="dark")
    assert "Dec 20, 2024" in svg
    assert "Jan 25, 2025" in svg


def test_render_streaks_same_year_longest_has_single_year_suffix():
    data = StreakData(
        current=5, max=37,
        current_start="2026-04-16", last_active_date="2026-04-20",
        max_start="2024-03-01", max_end="2024-04-11",
    )
    svg = render_streaks_widget(data, theme_name="dark")
    # Start has no year, end does.
    assert "Mar 1 – Apr 11, 2024" in svg


def test_render_streaks_current_caption_omits_year_when_same_year():
    data = StreakData(
        current=7, max=42,
        current_start="2026-04-13", last_active_date="2026-04-20",
        max_start="2024-03-01", max_end="2024-04-11",
    )
    svg = render_streaks_widget(data, theme_name="dark")
    assert "Apr 13 – Today" in svg


def test_render_streaks_current_caption_adds_year_across_year_boundary():
    data = StreakData(
        current=40, max=50,
        current_start="2025-12-20", last_active_date="2026-01-28",
        max_start="2024-03-01", max_end="2024-04-11",
    )
    svg = render_streaks_widget(data, theme_name="dark")
    assert "Dec 20, 2025 – Today" in svg


def test_generate_widgets_includes_streaks_when_enabled(freeze_today):
    from datetime import timedelta
    dates = [freeze_today - timedelta(days=i) for i in range(4)]
    payload = {
        "user": {"login": "alice"},
        "repos": [],
        "events": [],
        "commits": _days(dates),
        "total_commits": 4, "recent_commits": 4, "total_prs": 0,
        "collaborators_data": [],
    }
    widgets = processor.generate_widgets_from_github(
        payload, theme="dark", enabled=["streaks"],
    )
    assert "streaks" in widgets
    assert ">4<" in widgets["streaks"]


def test_generate_widgets_uses_stored_streak(freeze_today):
    payload = {
        "user": {"login": "alice"}, "repos": [], "events": [],
        "commits": [],
        "total_commits": 0, "recent_commits": 0, "total_prs": 0,
        "collaborators_data": [],
    }
    stored = {
        "max_streak": 99, "max_start": "2022-01-01", "max_end": "2022-04-09",
        "current_streak": 0, "current_start": "", "last_active_date": "",
    }
    widgets = processor.generate_widgets_from_github(
        payload, theme="dark", enabled=["streaks"], stored_streak=stored,
    )
    assert ">99<" in widgets["streaks"]
