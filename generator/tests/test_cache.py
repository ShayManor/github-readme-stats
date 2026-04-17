from src import cache


def test_noop_when_redis_url_empty(monkeypatch):
    monkeypatch.setattr(cache.config, "REDIS_URL", "")
    c = cache.Cache()
    assert c.get("k") is None
    c.set("k", "v", 60)
    c.delete("k")
    assert c.get("k") is None  # still None because no-op


def test_enabled_flag_reflects_config(monkeypatch):
    monkeypatch.setattr(cache.config, "REDIS_URL", "")
    assert cache.Cache().enabled is False
