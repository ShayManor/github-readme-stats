# Production Pipeline Design — github-readme-stats

**Date:** 2026-04-17
**Status:** Approved for planning
**Scope:** Restructure the repo into three independent Python services (fetcher, generator, edge), each with its own Docker image, tests, README, and API. The existing React/Vite frontend folds into the generator service (built and served by it, but kept as a decoupled React app with its own sources). Redis is designed for but not stood up in v1; the edge uses in-process Flask-Caching + Flask-Compress as free wins. Hosting/orchestration is explicitly out of scope.

## Goals

- A public, unauthenticated URL `GET /<github-username>` returns an SVG profile card suitable for embedding in a GitHub README.
- If the username is unknown at request time, return a clean "we're building your widget" placeholder immediately; fetch and build in the background.
- GitHub API calls are tightly rate-limited and live behind a single internal service (the fetcher) that holds the only GitHub PAT.
- The serving path is always a precomputed SVG lookup — never a render on the hot path.
- The three services must be genuinely independent so the generator can later be split into a build worker + a serverless edge serving layer without reshuffling the other services.

## Non-Goals (v1)

- No GitHub OAuth, no login, no per-user auth on the settings API. An auth stub is included so auth can be added later without touching call sites.
- No hosting, CI, cloud config, or docker-compose.
- No analytics, no metrics dashboard, no admin UI.
- No Postgres / remote DB. SQLite with WAL is sufficient for the v1 workload (one writer per DB, small volumes, mostly reads). All DB access lives behind one `db.py` per service so a swap to Postgres is a localized change.
- **No Redis deployment in v1.** Redis is designed in this spec so the integration points are correct, but v1 ships without Redis standing up. Edge uses in-process Flask-Caching; generator/fetcher skip the cache layer and talk directly over HTTP. Enabling Redis later is a config toggle — see the Redis section.

## Architecture

```
  GitHub README embed                Browser (user visits app)
          │                                      │
          ▼                                      ▼
  ┌───────────────┐                ┌─────────────────────────────┐
  │  Edge service │                │  Generator service          │
  │  (many nodes) │──── HTTP ─────►│  / + /assets/*  → React SPA │
  │  Flask-       │  origin fetch  │  /api/<u>       → widget    │
  │  Caching +    │  on miss       │  /api/enroll    → enroll    │
  │  Compress     │                │  /api/<u>/...   → settings  │
  │  - /<u>       │                │  + build worker container   │
  │  - /<u>/<w>   │                │  + poll cron container      │
  └───────────────┘                └──────┬──────────┬───────────┘
                                          │          │
                                  settings.db    widgets.db
                                                     ▲
                                                     │
                                             HTTP (internal,
                                             X-Internal-Token)
                                                     │
                                   ┌─────────────────▼───────┐
                                   │  Fetcher service        │
                                   │  - /data/<u>  (auto-    │
                                   │    fetches on miss)     │
                                   │  - /fetch (force)       │
                                   │  - /avatar              │
                                   │  + cron container       │
                                   └──────┬──────────────────┘
                                          ▼
                                      fetcher.db
                                          │
                                          ▼
                                      GitHub API

  (v2) Redis slots between edge↔generator and generator↔fetcher.
       cache.py is a no-op wrapper until REDIS_URL is set.
```

The edge has no DB of its own and no origin DB access — it's a cache-first proxy. The generator serves both the React SPA (static files at `/`) and the API (`/api/*`). Deploy as many edge instances around the world as you like.

## Redis (designed, not deployed in v1)

Specified here so the code knows the integration shape. v1 behavior: every `REDIS_URL` env var is unset → the cache wrapper short-circuits to a no-op, and every caller falls through to the underlying service. No code changes required to enable later — set `REDIS_URL` and it starts caching.

One Redis instance, accessible from fetcher, generator, and edge. Two key namespaces:

| Key | Value | TTL | Written by | Read by |
|---|---|---|---|---|
| `fetcher:data:<u>` | JSON payload from fetcher | 1h | fetcher (on miss-fill), generator cron on invalidation | generator API + worker |
| `fetcher:hash:<u>` | Current `payload_hash` | 1h | fetcher | generator cron (cheap change detection) |
| `widget:composite:<u>` | SVG string | 24h | edge (on miss-fill), generator (on rebuild invalidation) | edge |
| `widget:<name>:<u>` | SVG string per widget | 24h | same as composite | edge |
| `enroll:day:<YYYY-MM-DD>` | Counter | 48h | generator API | generator API (rate limit check) |

Rules:

- **Redis is a cache, never a source of truth.** Every key has a TTL. Losing Redis is a latency event, not a correctness event.
- **Invalidation on write, not just TTL.** When the build worker writes new widget rows, it immediately `DEL`s the matching `widget:*:<u>` keys so the next edge read re-populates. Same for fetcher on re-fetch.
- **Single Redis instance in v1.** If edge latency to a single Redis becomes a problem, swap to an edge-native KV (Cloudflare KV, Upstash) — only `edge/src/api.py` changes.

## Services

### 1. Fetcher

**Purpose:** Own every GitHub API interaction. Hold the PAT. Expose cached payloads to the generator.

**Endpoints** (all internal; not exposed to the public internet):

- `GET /data/<username>` — return stored payload JSON. If not stored, fetch from GitHub, store, return. This is the first-enrollment path. 502 on GitHub failure; 404 if GitHub says the user doesn't exist (fetcher stores a `{error: "not_found"}` marker so repeat calls are cheap).
- `POST /fetch {username}` — force re-fetch, ignoring any existing cache. Used by the fetcher's own cron and by manual admin action. Returns `{stored, payload_hash, changed}`.
- `GET /avatar/<username>` — return avatar bytes. GitHub's `https://github.com/<u>.png` is public and requires no PAT, so this is cheap. Used by the generator's placeholder renderer.
- `GET /health`

**Auth:** every request requires `X-Internal-Token: <shared-secret>` header. The generator holds the matching secret. The fetcher never listens on a public interface.

**Storage:** `fetcher.db` (SQLite), single table:

```sql
CREATE TABLE users (
    username            TEXT PRIMARY KEY,
    data_json           TEXT NOT NULL,       -- full GitHub payload OR {"error":"not_found"}
    payload_hash        TEXT NOT NULL,       -- sha256 of data_json
    fetched_at          TEXT NOT NULL,       -- UTC ISO 8601
    last_requested_at   TEXT NOT NULL        -- updated on every GET /data; drives GC
);
```

**Cron (`fetcher/src/cron.py`):** runs every hour. Each tick:

1. Select users with `fetched_at < now - 24h` AND `last_requested_at > now - 7d`. Stagger calls across the hour so we don't burst GitHub.
2. For each, call `POST /fetch` internally (or the equivalent function). Update `payload_hash`.
3. Delete rows where `last_requested_at < now - 7d` (trial GC — unused enrollments drop out automatically). `last_requested_at` is updated on every `GET /data/<u>`, so actively-embedded users are never dropped.

**Env vars:**

- `FETCHER_PORT` (default `5001`)
- `FETCHER_DB_PATH` (default `./data/fetcher.db` inside container)
- `GITHUB_PAT` (required)
- `FETCHER_INTERNAL_TOKEN` (required; the shared secret)
- `FETCHER_REFRESH_INTERVAL_HOURS` (default `24`)
- `FETCHER_TRIAL_GC_DAYS` (default `7`)
- `REDIS_URL` (optional; if set, writes to cache on fetch)

**DB pragmas:** on connection open, run `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;`.

### 2. Generator

**Purpose:** Serve precomputed SVGs to the public internet. Hold user settings. Build widgets in the background. Never call GitHub directly; only talk to the fetcher over HTTP.

All API endpoints are under the `/api/` prefix. Root `/` and `/assets/*` serve the React SPA built into `src/static/`.

**Public API endpoints:**

- `GET /api/<username>` — return composite SVG from `widgets.db`. Placeholder on miss. Sets `X-Widget-Status` header.
- `GET /api/<username>/<widget>.svg` — individual widget. Same behavior.
- `POST /api/enroll {username}` — explicit enrollment (SPA uses this). Also auto-invoked when `GET /api/<unknown>` arrives. Enforces daily rate limit. Returns `{enrolled, job_id}` or `{error: "rate_limited"}`.
- `GET /api/health`

**Auth-gated API endpoints** (auth stub in v1 — passes everything through; real auth later):

- `GET /api/<username>/settings` — current settings.
- `PATCH /api/<username>/settings` — update settings; enqueues a rebuild. Unlimited. Does NOT re-fetch GitHub.
- `POST /api/<username>/refresh` — one-shot manual re-fetch + rebuild. Calls fetcher's `POST /fetch`, then enqueues a rebuild. Gated by `manual_refresh_used` flag (allowed once per user, ever). Returns 409 `already_used` after the first call.

**Storage:**

**`settings.db`** (SQLite):

```sql
CREATE TABLE users (
    username                  TEXT PRIMARY KEY,
    settings_json             TEXT NOT NULL,       -- theme, enabled widgets, order, custom_tags, achievements, widget_settings
    settings_hash             TEXT NOT NULL,       -- sha256 of canonicalized settings_json
    enrolled_at               TEXT NOT NULL,
    last_fetcher_payload_hash TEXT,                -- last hash we rebuilt from; cron compares
    manual_refresh_used       INTEGER DEFAULT 0,   -- enforces one-shot user-triggered re-fetch
    last_requested_at         TEXT NOT NULL        -- updated on every GET /<u>; drives trial GC
);

CREATE TABLE enrollments_daily (
    day   TEXT PRIMARY KEY,                        -- YYYY-MM-DD, UTC
    count INTEGER NOT NULL
);

CREATE TABLE jobs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,                      -- "build"
    username   TEXT NOT NULL,
    status     TEXT NOT NULL,                      -- "pending" | "running" | "done" | "failed"
    attempts   INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_jobs_pending ON jobs(status, created_at);
```

**`widgets.db`** (SQLite in v1; designed for swap to remote backend later):

```sql
CREATE TABLE widgets (
    username      TEXT NOT NULL,
    settings_hash TEXT NOT NULL,
    widget_name   TEXT NOT NULL,                   -- "composite" | "grade" | "focus" | ...
    svg           TEXT NOT NULL,
    built_at      TEXT NOT NULL,
    PRIMARY KEY (username, settings_hash, widget_name)
);

CREATE TABLE current_widget (
    username      TEXT PRIMARY KEY,
    settings_hash TEXT NOT NULL,                   -- pointer to the "live" set
    updated_at    TEXT NOT NULL
);
CREATE INDEX idx_widgets_username ON widgets(username);
```

The `widgets_repo.py` module wraps all access. Future swap to Postgres / Turso / D1 / S3 changes only that one file.

**Build worker (`generator/src/build_worker.py`):**

- In-process thread polling `jobs` table every 500ms.
- For each pending job: mark `running`, load settings, `GET {fetcher}/data/<u>` (fetcher auto-fetches on miss), compute `settings_hash`, render all enabled widgets + composite, upsert into `widgets.db`, flip `current_widget` pointer atomically, LRU-trim to 10 rows per user, mark `done`.
- Failure: increment `attempts`, exponential backoff (1min, 5min, 15min); after 3 attempts mark `failed` and leave the existing widget (if any) in place. Placeholder continues to serve for un-built users.
- Extractable to a standalone process later (same DB, same code, separate entrypoint).

**Generator cron (`generator/src/cron.py`):** runs every 15 minutes.

1. For each enrolled user, `GET {fetcher}/data/<u>` (response includes `payload_hash`).
2. If `payload_hash != last_fetcher_payload_hash`, enqueue a build job and update `last_fetcher_payload_hash`.
3. LRU-trim widgets per user.

**Enrollment rate limit:** global cap of 50 new enrollments per UTC day (`ENROLLMENT_DAILY_CAP`). Over cap → `POST /enroll` returns `rate_limited`; `GET /<unknown>` returns a "try again tomorrow" placeholder. Enrollment counter increments only on *new* users, not on re-requests.

**Placeholder renderer (`generator/src/placeholder.py`):** produces SVGs matching the card wrapper and theme of real widgets. Three variants:

- **building**: "Building @username's widget... This usually takes under a minute." Shows avatar if fetched (generator calls `GET {fetcher}/avatar/<u>`). Serves when user is enrolled but widgets not yet built.
- **rate_limited**: "Too many new users today — try again tomorrow." Shown when enrollment cap is hit.
- **not_found**: "GitHub user @username doesn't exist." Shown when fetcher stored a `not_found` marker.

Placeholders are rendered on the fly (no DB lookup needed) and served with `Cache-Control: no-store`.

**Env vars:**

- `GENERATOR_PORT` (default `5002`)
- `GENERATOR_SETTINGS_DB_PATH` (default `./data/settings.db`)
- `GENERATOR_WIDGETS_DB_PATH` (default `./data/widgets.db`)
- `FETCHER_URL` (required, e.g. `http://mini-pc:5001`)
- `FETCHER_INTERNAL_TOKEN` (required, matches fetcher's)
- `REDIS_URL` (optional; if set, read-through to fetcher cache and invalidation on rebuild)
- `ENROLLMENT_DAILY_CAP` (default `50`)
- `WIDGET_LRU_PER_USER` (default `10`)
- `GENERATOR_POLL_INTERVAL_MINUTES` (default `15`)

**DB pragmas:** same as fetcher (WAL + NORMAL sync + 5s busy_timeout).

### 3. Edge

**Purpose:** Serve widget SVGs cache-first, with the generator as origin. Deploy many instances around the world (Cloud Run, Fly, Lambda container, etc.). No DB of its own.

**Endpoints:**

- `GET /<username>` — check cache; hit → return; miss → fetch generator `GET /api/<u>`, cache, return.
- `GET /<username>/<widget>.svg` — same pattern.
- `GET /health` — reports cache type + origin reachability.

**Caching (v1):** [Flask-Caching](https://flask-caching.readthedocs.io/) with `CACHE_TYPE=SimpleCache` — in-process LRU, per-instance, no external dependency. Wrapped by a thin `cache.py` so `CACHE_TYPE=RedisCache` + `CACHE_REDIS_URL` swaps in Redis later with no call-site changes. TTL: 24h. Max entries per instance: 10000.

**Compression:** [Flask-Compress](https://github.com/colour-science/flask-compress) on, default settings. SVG is text — gzip typically 70-80%% savings.

**HTTP cache headers on hits:**
- `Cache-Control: public, max-age=3600, s-maxage=86400, stale-while-revalidate=86400`

**Placeholder handling:** generator sets `X-Widget-Status: ready | building | rate_limited | not_found`. Edge only caches `ready` responses. Others are passed through with `Cache-Control: no-store` so a CDN in front doesn't memorize them.

**Implementation:** single `edge/src/api.py` Flask file (~100 lines) + `edge/src/cache.py` (~30 lines).

**Env vars:**
- `EDGE_PORT` (default `5003`)
- `GENERATOR_URL` (required — origin)
- `CACHE_TYPE` (default `SimpleCache`; later `RedisCache`)
- `CACHE_REDIS_URL` (optional)
- `CACHE_DEFAULT_TIMEOUT` (default `86400`)

### Frontend (served by the generator)

**Not a separate service.** The existing React/Vite frontend moves into `generator/frontend/` (source code) and is built by the generator's Dockerfile. The Flask app in `generator/src/api.py` serves the built static bundle from `/` (and `/assets/*`). The architecture stays decoupled — React sources live in their own folder, are built by their own toolchain, and only the static output is served by Flask.

**URL split on the generator:**

| Path | Served | Notes |
|---|---|---|
| `/` | `generator/frontend/dist/index.html` | React SPA entry |
| `/assets/*` | `generator/frontend/dist/assets/*` | JS/CSS bundles |
| `/api/<u>` | Flask route | widget origin (called by edge) |
| `/api/<u>/<w>.svg` | Flask route | individual widget origin |
| `/api/enroll` | Flask route | enrollment |
| `/api/<u>/settings` | Flask route | settings CRUD |
| `/api/<u>/refresh` | Flask route | one-shot re-fetch |
| `/api/health` | Flask route | health |

**Why `/api/` prefix:** keeps the frontend `/` clean for the SPA and keeps widget origin paths from colliding with React routes. The edge rewrites `GET /<u>` → `GET /api/<u>` when calling origin.

**Dockerfile (one, multi-stage):**

1. **Stage `frontend-build`** — `node:20-alpine`, `npm ci && npm run build` inside `/app/frontend`, produces `/app/frontend/dist`.
2. **Stage `runtime`** — `python:3.11-slim`, install `requirements.txt`, copy `src/` and the built `frontend/dist` from stage 1 into `src/static/`. Flask serves from there.

**Flow (v1, no auth):**

1. User opens `https://generator.example.com/` → React SPA loads.
2. User enters their GitHub username → calls `POST /api/enroll`.
3. UI polls `GET {EDGE_URL}/<username>` preview (placeholder until build completes).
4. Settings form edits go to `PATCH /api/<username>/settings`.
5. "Refresh from GitHub" button calls `POST /api/<username>/refresh`. Disabled after one use (server enforces 409).
6. UI displays the embeddable edge URL for pasting into their README.

**Vite env vars:** `VITE_GENERATOR_URL`, `VITE_EDGE_URL` (baked at build time by the Dockerfile).

## File Layout

Simplified — each Python service is ~4-6 files plus its rendering assets.

```
github-readme-stats/
├── fetcher/
│   ├── src/
│   │   ├── __init__.py
│   │   ├── api.py          # Flask app + all routes + auth header check
│   │   ├── github.py       # GitHub GraphQL/REST client (from src/data/fetcher.py)
│   │   ├── db.py           # SQLite repo, WAL setup, schema migrations
│   │   ├── cron.py         # scheduled refresh + GC; run as separate container
│   │   └── config.py
│   ├── tests/
│   │   ├── test_api.py
│   │   ├── test_github.py
│   │   ├── test_db.py
│   │   └── test_cron.py
│   ├── data/               # gitignored
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   └── README.md
│
├── generator/
│   ├── frontend/           # React+Vite sources (moved from top-level frontend/)
│   │   ├── src/
│   │   ├── package.json
│   │   ├── vite.config.ts
│   │   └── tsconfig.json
│   ├── src/
│   │   ├── __init__.py
│   │   ├── api.py          # Flask app + all /api/* routes + SPA static serve + fetcher HTTP client inline + auth stub inline
│   │   ├── worker.py       # build worker loop; run as separate container
│   │   ├── cron.py         # polls fetcher, enqueues rebuilds; run as separate container
│   │   ├── db.py           # settings_repo + widgets_repo together
│   │   ├── cache.py        # no-op in v1 (REDIS_URL unset); real wrapper otherwise
│   │   ├── placeholder.py  # three SVG variants
│   │   ├── processor.py    # widget rendering pipeline (from src/data/processor.py)
│   │   ├── config.py
│   │   ├── static/         # populated at Docker build time from frontend/dist
│   │   ├── widgets/        # (from src/widgets/)
│   │   ├── themes/         # (from src/themes/)
│   │   ├── models/         # (from src/models/)
│   │   └── utils/          # (from src/utils/)
│   ├── tests/
│   │   ├── test_api.py
│   │   ├── test_worker.py
│   │   ├── test_cron.py
│   │   ├── test_db.py
│   │   ├── test_placeholder.py
│   │   ├── test_processor.py
│   │   └── integration/
│   │       └── test_end_to_end.py
│   ├── data/               # gitignored
│   ├── Dockerfile          # multi-stage: node build → python runtime (api+worker+cron share image)
│   ├── requirements.txt
│   ├── pytest.ini
│   └── README.md
│
├── edge/
│   ├── src/
│   │   ├── __init__.py
│   │   ├── api.py          # Flask app + Flask-Caching + Flask-Compress + origin fetch
│   │   ├── cache.py        # Flask-Caching config (SimpleCache now, RedisCache later)
│   │   └── config.py
│   ├── tests/
│   │   └── test_api.py
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   └── README.md
│
├── docs/superpowers/specs/2026-04-17-production-pipeline-design.md
├── .gitignore              # **/data/*.db, built artifacts
└── README.md               # points to each service's README
```

**Independence rules:**

- No Python imports cross service folders. Communication only via HTTP + Redis.
- No shared package. Duplicate any trivial util (e.g., `payload_hash`) per service.
- Each service has its own `requirements.txt`, `pytest.ini`, `Dockerfile`, `README.md`.
- `docker build ./fetcher` etc. succeeds with no repo-root build context.
- Generator ships one Docker image; three containers run from it with different `CMD`s: `python -m src.api`, `python -m src.worker`, `python -m src.cron`.

## Code to Delete

The current `src/` layout is retired wholesale. Specifically:

- `run.py` — CLI entry point replaced by frontend + API.
- `src/generate.py` — replaced by the generator service.
- `src/fetcher_api.py`, `src/generator_api.py` — replaced by `fetcher/src/api.py` and `generator/src/api.py`.
- `src/db/` — schema moves to fetcher's `repository.py`; dummy user pattern replaced by placeholders.
- `src/data/ARCHITECTURE.md` — superseded by this spec.
- `widget_*.svg` at repo root — build artifacts, no longer produced.
- `data/ghstats.db` at repo root — replaced by per-service `data/*.db`.
- `REPORT.md`, `CHANGELOG.md` — stale; drop unless user wants them kept.
- `src/README.md` — superseded by per-service READMEs.

`CLAUDE.md` is updated to reflect the new layout (sections on commands, architecture, configuration). `CONFIGURATION.md` and `TAG_CUSTOMIZATION.md` move into the generator's `README.md` (or its own `docs/` under `generator/`).

Existing widget/theme/model code under `src/widgets/`, `src/themes/`, `src/models/`, `src/utils/`, and most of `src/data/processor.py` move into `generator/src/` and are kept. `src/data/fetcher.py` moves into `fetcher/src/github.py`. The top-level `frontend/` folder moves wholesale into `generator/frontend/`.

## Data Flow

### First-time `GET /shaymanor` (from a README embed, hitting the edge)

1. Edge: Flask-Caching lookup for `/shaymanor` → miss.
2. Edge: HTTP `GET {generator}/api/shaymanor` → origin.
3. Generator: `widgets_repo.get_current(shaymanor)` → miss.
4. Generator: `settings_repo.get(shaymanor)` → miss → user unenrolled.
5. Enrollment path:
   a. Check today's counter in `enrollments_daily`. If `>= 50`, return `rate_limited` placeholder with `X-Widget-Status: rate_limited` and `Cache-Control: no-store`.
   b. Insert default settings row. Increment counter.
   c. Insert `build` job.
6. Generator returns `building` placeholder with `X-Widget-Status: building`, `Cache-Control: no-store`.
7. Edge sees non-`ready` status header, returns SVG to the reader without caching.

### Build worker processing a job

1. Mark job `running`.
2. `cache.get("fetcher:data:<u>")` via the wrapper (v1 = no-op, always miss). Miss → `GET {fetcher}/data/<u>` with internal token (fetcher auto-fetches from GitHub on miss). Hit → use cached payload.
3. If payload is the `not_found` marker: upsert a `not_found` placeholder into widgets; flip `current_widget`; mark job `done`. No retries on this user.
4. Otherwise: load settings, compute `settings_hash`, render all enabled widgets + composite via the existing `processor.py` pipeline.
5. Transaction: insert widget rows, flip `current_widget`, update `settings.last_fetcher_payload_hash`.
6. `cache.delete("widget:composite:<u>")` and per-widget keys (v1 no-op; real invalidation once Redis is enabled).
7. LRU-trim widgets for this user to 10 hashes.
8. Mark job `done`.

The edge clears its own Flask-Caching entry via TTL expiry (24h) in v1. Users who want instant invalidation on rebuild can call the edge's `POST /admin/purge/<u>` (added in v2 when Redis comes online — not in v1).

### Cron-driven refresh

1. Fetcher cron (hourly) re-fetches due users; updates `payload_hash` on change.
2. Generator cron (15 min) calls fetcher `GET /data/<u>` per enrolled user (response includes `payload_hash`). Compares with `last_fetcher_payload_hash`. On mismatch, enqueues `build` job. (When Redis comes online in v2, this reads `fetcher:hash:<u>` from Redis — HTTP becomes the fallback.)
3. Trial users not requested in 7 days are GC'd by fetcher cron.

### Settings change from frontend

1. `PATCH /shaymanor/settings` (auth stub passes through).
2. Generator computes new `settings_hash`, updates `settings_json`.
3. Enqueue `build` job.
4. Old `(username, old_hash)` rows remain in `widgets` until LRU-trimmed. `current_widget` flips once the build completes — no user-visible flicker.

### Manual refresh (one-shot, user-triggered)

1. `POST /shaymanor/refresh`.
2. If `manual_refresh_used = 1`, return 409 `already_used`.
3. Otherwise: set `manual_refresh_used = 1`, call fetcher `POST /fetch {username: shaymanor}` (this burns one GitHub-quota hit), enqueue `build` job. The rebuild will pick up the freshly-fetched data on the next poll.

After this one-shot is spent, the user's data only changes via fetcher cron (every 24h). Settings edits continue to trigger unlimited rebuilds but never re-fetch.

## Error Handling

| Failure mode | Behavior |
|---|---|
| Fetcher unreachable from generator | Build job retries with backoff; placeholder continues to serve; `/health` reports degraded. |
| GitHub returns 5xx | Fetcher returns 502 to generator; build job retries. |
| GitHub returns 404 | Fetcher stores `{error: "not_found"}`; generator builds a `not_found` placeholder once, stops retrying. |
| GitHub rate-limit | Fetcher returns 429 to generator; build job retries with longer backoff. |
| Enrollment cap exceeded | `POST /enroll` → `rate_limited`. `GET /<unknown>` → `rate_limited` placeholder. Next day resets. |
| Settings DB or widgets DB corrupt | Generator serves 503. Intentional — this is a server bug, not a missing-user condition. |
| Build worker dies mid-job | On next start, any `running` job older than 10 minutes is reclaimed to `pending`. |
| Manual refresh reused | 409 `already_used`. |

## Testing

Each service has its own `tests/` and runs with `cd <service> && pytest`.

**Fetcher:**
- `test_repository.py`: upsert, payload_hash stability, last_requested_at update on read.
- `test_github_client.py`: mocked HTTP with the `responses` library; covers GraphQL + REST paths, 404, 429, 502.
- `test_api.py`: auth-header enforcement, auto-fetch on miss, 404 handling.
- `test_cron.py`: staggered refresh, GC of stale trial users.

**Generator:**
- `test_db.py`: settings + widgets CRUD, settings_hash canonicalization, LRU trimming, `current_widget` pointer atomicity, WAL pragma applied.
- `test_placeholder.py`: each of the three placeholder variants renders valid SVG and matches theme.
- `test_worker.py`: picks jobs, retries on fetcher failures, handles `not_found` marker, invalidates Redis on success.
- `test_api.py`: full surface — auth stub, rate limit, enrollment auto-trigger on `GET /api/<unknown>`, serves precomputed on hit, placeholder on miss, `X-Widget-Status` header correct per case, SPA served at `/`.
- `test_cron.py`: polls fetcher via HTTP, enqueues only on hash change.
- `test_processor.py`: carry-over tests for widget rendering (from existing code).

**Edge (`edge/tests/`):**
- `test_api.py`: SimpleCache hit returns cached SVG; miss fetches origin, caches, returns; `X-Widget-Status: ready` is cached, others pass through uncached; gzip content-encoding applied to responses > threshold.

**Integration (`generator/tests/integration/`):** spin up generator API + worker + cron + edge + a fake fetcher (responses/respx mock) in-process, drive `GET /<newuser>` end to end via the edge. Assert placeholder → build → real SVG transition and that the edge serves from cache on second request.

**Frontend:** Vitest smoke tests: form submit, preview fetch, settings save. No E2E required in v1.

## Security

- Fetcher's `X-Internal-Token` is required on every endpoint except `/health`. Constant-time comparison. 401 on mismatch.
- No endpoint on the fetcher is exposed to the public internet. Deployment guidance in the fetcher README: bind to `127.0.0.1` or a private interface.
- Generator does not echo stored data anywhere except via the widget SVG — no `/data/<u>` mirror. Prevents the generator from leaking raw GitHub payloads.
- Frontend talks to generator over HTTPS in production (user's responsibility).
- No secrets logged. No `GITHUB_PAT` in generator env at all.

## Observability

- Each service logs to stdout in a line-oriented format: `ts level service event key=val ...`.
- `/health` on each service returns `{status, service, db_ok, upstream_ok?}`.
- No metrics backend in v1.

## Migration Plan (executed by the implementation phase)

1. Create new folder scaffolding and move code wholesale. Do not keep the old `src/` in parallel — cut over in one branch.
2. Split `src/db/repository.py` into fetcher's `repository.py`.
3. Define new settings_repo and widgets_repo in `generator/src/`.
4. Write placeholder renderer using the existing card wrapper util (moved into `generator/src/utils/`).
5. Wire build worker + cron.
6. Update `.gitignore`; delete retired files and build artifacts.
7. Update the top-level `README.md` to point to the three service READMEs.
8. Update `CLAUDE.md` to reflect the new layout.

## Open Questions

None at time of writing. All design choices confirmed in brainstorming.

## Future Work (out of scope for this spec)

- GitHub OAuth on settings endpoints.
- Postgres migration (swap `db.py` per service; all call sites unchanged).
- Edge-native KV store (Cloudflare KV / Upstash) if single-Redis latency is a problem from far regions.
- Admin endpoints for cron pause / manual re-fetch / user purge.
- Metrics + alerting.
