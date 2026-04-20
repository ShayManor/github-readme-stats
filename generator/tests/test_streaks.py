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
    assert "Current" in svg
    assert "Longest" in svg


def test_render_streaks_zero_values_render():
    data = StreakData(current=0, max=0)
    svg = render_streaks_widget(data, theme_name="dark")
    assert ">0<" in svg
    assert "Current" in svg
    assert "Longest" in svg


def test_render_streaks_hides_dates_when_disabled():
    data = StreakData(
        current=7, max=42,
        current_start="2026-04-13", last_active_date="2026-04-19",
        max_start="2024-03-01", max_end="2024-04-11",
    )
    svg = render_streaks_widget(data, theme_name="dark", settings={"show_dates": False})
    assert "2026-04-13" not in svg
    assert "2024-03-01" not in svg
