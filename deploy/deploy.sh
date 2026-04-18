#!/usr/bin/env bash
# Pulls the current image tag and brings up the compose stack.
# Expects GITHUB_PAT, FETCHER_INTERNAL_TOKEN, and IMAGE_TAG to be present in
# the environment (exported by the GitHub Actions deploy job).
set -euo pipefail

cd "$(dirname "$0")"

mkdir -p "$HOME/ghstats/data/fetcher" "$HOME/ghstats/data/generator"

docker compose pull
docker compose up -d --remove-orphans
docker compose ps
