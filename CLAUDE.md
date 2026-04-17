# CLAUDE.md

Guidance for Claude Code working in this repository.

## Layout

This is a monorepo of three independent Python services plus a Vite+React
frontend. Each service has its own `requirements.txt`, `pytest.ini`,
`Dockerfile`, and README:

- `fetcher/` — port 5001. Owns the GitHub PAT and `fetcher.db`. Refresh
  cron polls GitHub, upserts raw payloads, serves `/data/<u>` to internal
  callers only.
- `generator/` — port 5002. Owns settings + widgets SQLite DBs. Build
  worker renders SVGs from fetcher data. Serves the React SPA from
  `src/static/` and all `/api/*` routes. Frontend sources live in
  `generator/frontend/` and get built into `src/static/` by the
  multi-stage Dockerfile.
- `edge/` — port 5003. Cache-first SVG proxy in front of the generator;
  Flask-Caching + Flask-Compress, optional Redis.

Per-service READMEs cover run/test/Docker commands. The design and
implementation plan live in `docs/superpowers/`.

## Working on a single service

Each service is self-contained. `cd <service> && pytest` is the test
entry point; `cd <service> && pip install -r requirements.txt` is the
dependency install. Don't cross-import across services — they talk
over HTTP (generator → fetcher via `generator/src/fetcher_client.py`;
edge → generator via `edge/src/api.py::_fetch_origin`).

## Configuration

All runtime tuning is in each service's `src/config.py` and is
overridable via env vars:

- `fetcher/src/config.py` — `GITHUB_PAT`, `FETCHER_INTERNAL_TOKEN`,
  `COLLABORATOR_*`, `COMMIT_*`, `API_TIMEOUT`, refresh cadence.
- `generator/src/config.py` — `FETCHER_URL`, `FETCHER_INTERNAL_TOKEN`,
  `ENROLLMENT_DAILY_CAP`, `WIDGET_LRU_PER_USER`, `POLL_INTERVAL_MINUTES`,
  `TAG_MAX_COUNT`, `TAG_LANGUAGE_MAP`, `TAG_TOPIC_MAP`,
  `ENABLED_WIDGETS`, `WIDGET_ORDER`, `HIDDEN_LANGUAGES`.
- `edge/src/config.py` — `GENERATOR_URL`, `CACHE_TYPE`,
  `CACHE_REDIS_URL`, `CACHE_DEFAULT_TIMEOUT`, `CACHE_THRESHOLD`,
  `UPSTREAM_TIMEOUT`.

## Conventions

- Widget renderers return SVG strings; only `generator/src/worker.py`
  persists them (via `db.put_widgets`).
- The `X-Widget-Status` header (`ready | building | rate_limited |
  not_found`) is the contract between generator and edge for what to
  cache.
- Generator ↔ fetcher traffic uses the shared secret
  `FETCHER_INTERNAL_TOKEN` (HTTP header `X-Internal-Token`). Public
  routes on the generator don't require auth in v1.
- Adding a widget still means: new `generator/src/widgets/<name>.py`,
  export from `generator/src/widgets/__init__.py`, wire into
  `generator/src/processor.py::generate_widgets_from_github`, add the
  key to `WIDGET_ORDER` / `ENABLED_WIDGETS` in
  `generator/src/config.py`.
- Adding a theme: entry in `generator/src/themes/themes.py`.
