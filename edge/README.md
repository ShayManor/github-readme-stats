# Edge Service

Cache-first SVG proxy in front of the generator. Deploy many instances
around the world. No DB of its own; optional Redis for shared cache.

## Run locally

    cd edge
    pip install -r requirements.txt
    GENERATOR_URL=http://localhost:5002 python -m src.api

## Test

    cd edge && pytest

## Docker

    docker build -t ghstats-edge .
    docker run --rm -e GENERATOR_URL=http://host.docker.internal:5002 -p 5003:5003 ghstats-edge

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /health | cache type + upstream reachability |
| GET | /<u> | composite SVG (cached on X-Widget-Status: ready) |
| GET | /<u>/<w>.svg | individual widget SVG |

## Env

- `GENERATOR_URL` — origin (required)
- `CACHE_TYPE` — `SimpleCache` (default) or `RedisCache`
- `CACHE_REDIS_URL` — if using RedisCache
- `CACHE_DEFAULT_TIMEOUT` — seconds, default 86400
- `CACHE_THRESHOLD` — max entries (SimpleCache only), default 10000
