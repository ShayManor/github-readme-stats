# Generator Service

Serves precomputed SVGs to the public internet. Holds user settings and
the widgets cache. Runs a build worker + cron in the background. Also
serves the React SPA (frontend sources live under `frontend/`).

## Run locally (3 processes)

    cd generator
    pip install -r requirements.txt

    # API
    FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.api
    # Build worker
    FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.worker
    # Poll cron
    FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.cron

## Frontend (dev)

    cd generator/frontend && npm install && npm run dev
    # Vite dev server proxies /api to the Flask app.

## Test

    cd generator && pytest

## Docker

Multi-stage (builds the frontend with node, serves everything from Python):

    docker build -t ghstats-generator .
    docker run --rm -e FETCHER_URL=http://fetcher:5001 -e FETCHER_INTERNAL_TOKEN=dev \
               -p 5002:5002 -v $(pwd)/data:/app/data ghstats-generator
    # Worker: override CMD to ["python","-m","src.worker"]
    # Cron:   override CMD to ["python","-m","src.cron"]

## Endpoints

All API endpoints are under `/api/`. The root and `/assets/*` serve the SPA.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /api/health | none | health |
| GET | /api/<u> | none | composite SVG; auto-enrolls unknown users |
| GET | /api/<u>/<w>.svg | none | individual widget SVG |
| POST | /api/enroll | none | explicit enroll (body: {username}) |
| GET | /api/<u>/settings | stub | current settings |
| PATCH | /api/<u>/settings | stub | update settings (enqueues rebuild) |
| POST | /api/<u>/refresh | stub | one-shot re-fetch + rebuild |

Responses carry `X-Widget-Status: ready | building | rate_limited | not_found`.

## Env

See `src/config.py`.
