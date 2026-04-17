"""Fetcher service configuration, overridable via env vars."""
import os

PORT = int(os.getenv("FETCHER_PORT", "5001"))
DB_PATH = os.getenv("FETCHER_DB_PATH", "./data/fetcher.db")
GITHUB_PAT = os.getenv("GITHUB_PAT", "")
INTERNAL_TOKEN = os.getenv("FETCHER_INTERNAL_TOKEN", "")
REFRESH_INTERVAL_HOURS = int(os.getenv("FETCHER_REFRESH_INTERVAL_HOURS", "24"))
TRIAL_GC_DAYS = int(os.getenv("FETCHER_TRIAL_GC_DAYS", "7"))
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "15"))
