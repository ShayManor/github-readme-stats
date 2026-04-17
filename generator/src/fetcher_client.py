"""HTTP client to the fetcher service. Used by api.py, worker.py, cron.py."""
import requests

from . import config


def _headers() -> dict:
    return {"X-Internal-Token": config.FETCHER_INTERNAL_TOKEN}


def get_data(username: str) -> dict:
    r = requests.get(f"{config.FETCHER_URL}/data/{username}", headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def force_fetch(username: str) -> dict:
    r = requests.post(f"{config.FETCHER_URL}/fetch", headers=_headers(),
                      json={"username": username}, timeout=30)
    r.raise_for_status()
    return r.json()
