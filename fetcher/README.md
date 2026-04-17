# Fetcher Service

Owns every GitHub API interaction. Holds the PAT. Exposes cached payloads
over an internal-only HTTP API protected by a shared secret.

## Run locally

    cd fetcher
    pip install -r requirements.txt
    FETCHER_INTERNAL_TOKEN=dev GITHUB_PAT=ghp_xxx python -m src.api

Cron (separate process):

    FETCHER_INTERNAL_TOKEN=dev GITHUB_PAT=ghp_xxx python -m src.cron

## Test

    cd fetcher && pytest

## Docker

    docker build -t ghstats-fetcher .
    docker run -e GITHUB_PAT=ghp_xxx -e FETCHER_INTERNAL_TOKEN=dev -p 5001:5001 -v $(pwd)/data:/app/data ghstats-fetcher
    # cron: override CMD to ["python","-m","src.cron"]

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /health | none | health check |
| GET | /data/<u> | X-Internal-Token | return stored payload; auto-fetches on miss |
| POST | /fetch | X-Internal-Token | force re-fetch (body: {username}) |
| GET | /avatar/<u> | X-Internal-Token | proxied avatar bytes |

## Env

See `src/config.py`.
