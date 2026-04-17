from src import placeholder


def test_building_contains_username_and_svg_tag():
    svg = placeholder.render("building", "alice", theme="dark")
    assert svg.startswith("<svg") and "</svg>" in svg
    assert "alice" in svg
    assert "Building" in svg or "building" in svg.lower()


def test_rate_limited_variant():
    svg = placeholder.render("rate_limited", "alice", theme="dark")
    assert "tomorrow" in svg.lower() or "try again" in svg.lower()


def test_not_found_variant():
    svg = placeholder.render("not_found", "ghost", theme="dark")
    assert "ghost" in svg
    assert "doesn't exist" in svg or "not found" in svg.lower()


def test_unknown_variant_raises():
    import pytest
    with pytest.raises(ValueError):
        placeholder.render("bogus", "alice", theme="dark")
