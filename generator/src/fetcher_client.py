"""HTTP client to the fetcher service. Used by api.py, worker.py, cron.py."""
import requests

from . import config


def _headers() -> dict:
    return {"X-Internal-Token": config.FETCHER_INTERNAL_TOKEN}


# Most calls hit the cache and return in <100ms; the only slow path is when
# the fetcher's /data endpoint falls back to a synchronous GitHub fetch
# (used by the /?username=X shortcut). 60s leaves headroom for the
# parallelized worst case (~15-25s) without poisoning the worker's job
# retry chain on a transient blip.
_TIMEOUT_S = 60


def get_data(username: str) -> dict:
    r = requests.get(f"{config.FETCHER_URL}/data/{username}", headers=_headers(),
                     timeout=_TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def force_fetch(username: str) -> dict:
    r = requests.post(f"{config.FETCHER_URL}/fetch", headers=_headers(),
                      json={"username": username}, timeout=_TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def start_fetch_async(username: str) -> dict:
    """Tell the fetcher to fetch this user in the background. Returns 202
    after the fetcher has accepted the job — does NOT wait for the GitHub
    fetch to complete. The fetcher will POST back to /internal/data-ready
    on this service when the data is persisted, which is what enqueues the
    build job. See fetcher.api.fetch_async for the other half."""
    r = requests.post(f"{config.FETCHER_URL}/fetch-async", headers=_headers(),
                      json={"username": username}, timeout=10)
    r.raise_for_status()
    return r.json()
