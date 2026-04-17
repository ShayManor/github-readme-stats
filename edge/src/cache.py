"""Flask-Caching config. v1 = SimpleCache (in-process). Swap to RedisCache via env."""
from flask_caching import Cache
from . import config


def build_cache(app) -> Cache:
    cfg = {
        "CACHE_TYPE": config.CACHE_TYPE,
        "CACHE_DEFAULT_TIMEOUT": config.CACHE_DEFAULT_TIMEOUT,
        "CACHE_THRESHOLD": config.CACHE_THRESHOLD,
    }
    if config.CACHE_TYPE == "RedisCache" and config.CACHE_REDIS_URL:
        cfg["CACHE_REDIS_URL"] = config.CACHE_REDIS_URL
    c = Cache(config=cfg)
    c.init_app(app)
    return c
