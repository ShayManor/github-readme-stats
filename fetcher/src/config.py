"""Fetcher service configuration, overridable via env vars."""
import os

PORT = int(os.getenv("FETCHER_PORT", "5001"))
DB_PATH = os.getenv("FETCHER_DB_PATH", "./data/fetcher.db")
GITHUB_PAT = os.getenv("GITHUB_PAT", "")
INTERNAL_TOKEN = os.getenv("FETCHER_INTERNAL_TOKEN", "")
REFRESH_INTERVAL_HOURS = int(os.getenv("FETCHER_REFRESH_INTERVAL_HOURS", "24"))
TRIAL_GC_DAYS = int(os.getenv("FETCHER_TRIAL_GC_DAYS", "7"))
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "15"))

# Collaborator-detection tuning
COLLABORATOR_MAX_REPO_SIZE = int(os.getenv("COLLABORATOR_MAX_REPO_SIZE", "150"))
COLLABORATOR_TOP_REPOS = int(os.getenv("COLLABORATOR_TOP_REPOS", "30"))
SMALL_OWNED_REPO_SIZE = int(os.getenv("SMALL_OWNED_REPO_SIZE", "10"))
COLLABORATOR_LOOKBACK_DAYS = int(os.getenv("COLLABORATOR_LOOKBACK_DAYS", "365"))
MEANINGFUL_MIN_COMMITS = int(os.getenv("MEANINGFUL_MIN_COMMITS", "3"))
FORK_MIN_COMMITS = int(os.getenv("FORK_MIN_COMMITS", "10"))
OWNER_BOOST = float(os.getenv("OWNER_BOOST", "1.5"))
MIN_SHARED_REPOS = int(os.getenv("MIN_SHARED_REPOS", "2"))
DEEP_COLLAB_THRESHOLD = int(os.getenv("DEEP_COLLAB_THRESHOLD", "25"))

# Commit-fetching caps
COMMIT_MAX_REPOS = int(os.getenv("COMMIT_MAX_REPOS", "10"))
COMMIT_PER_REPO = int(os.getenv("COMMIT_PER_REPO", "30"))
