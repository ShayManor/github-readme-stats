# github-readme-stats

[![tests](https://github.com/ShayManor/github-readme-stats/actions/workflows/tests.yml/badge.svg)](https://github.com/ShayManor/github-readme-stats/actions/workflows/tests.yml)
[![docker](https://github.com/ShayManor/github-readme-stats/actions/workflows/docker.yml/badge.svg)](https://github.com/ShayManor/github-readme-stats/actions/workflows/docker.yml)

A monorepo of three independent Python services plus a React frontend,
each self-contained. See each service's README for details.

## Services

| Folder | Port | Responsibility |
|---|---|---|
| [`fetcher/`](./fetcher/README.md) | 5001 | Owns GitHub PAT + `fetcher.db`; cron-refreshes data |
| [`generator/`](./generator/README.md) | 5002 | Settings + widgets DBs, build worker, serves React SPA + `/api/*` |
| [`edge/`](./edge/README.md) | 5003 | Cache-first SVG proxy; deploy globally |

## Design Docs

- Spec: [`docs/superpowers/specs/2026-04-17-production-pipeline-design.md`](docs/superpowers/specs/2026-04-17-production-pipeline-design.md)
- Plan: [`docs/superpowers/plans/2026-04-17-production-pipeline.md`](docs/superpowers/plans/2026-04-17-production-pipeline.md)

## Quick start (local dev, no Docker)

    # 1) fetcher
    (cd fetcher && pip install -r requirements.txt &&
     FETCHER_INTERNAL_TOKEN=dev GITHUB_PAT=<your-pat> python -m src.api) &

    # 2) generator API, worker, cron (three processes)
    cd generator && pip install -r requirements.txt
    FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.api &
    FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.worker &
    FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.cron &

    # 3) edge
    (cd ../edge && pip install -r requirements.txt &&
     GENERATOR_URL=http://localhost:5002 python -m src.api) &

    # 4) frontend (dev server)
    cd ../generator/frontend && npm install && npm run dev

Test everything:

    (cd fetcher && pytest) && (cd generator && pytest) && (cd edge && pytest)
