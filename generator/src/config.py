"""Configuration for GitHub widget generator."""

import os

# Collaborator settings
COLLABORATOR_MAX_REPO_SIZE = int(os.getenv("COLLABORATOR_MAX_REPO_SIZE", "150"))
"""Maximum contributors in a repo to be included (filters out huge OSS projects)."""

COLLABORATOR_TOP_REPOS = int(os.getenv("COLLABORATOR_TOP_REPOS", "30"))
"""Safety cap on repos to scan for collaborators (ranked by user's own commit count)."""

SMALL_OWNED_REPO_SIZE = int(os.getenv("SMALL_OWNED_REPO_SIZE", "10"))
"""User-owned repos with at most this many contributors are treated as 'tight' projects —
single-repo collaborators in them bypass MIN_SHARED_REPOS (captures hackathon/side-project partners)."""

COLLABORATOR_LOOKBACK_DAYS = int(os.getenv("COLLABORATOR_LOOKBACK_DAYS", "365"))
"""How far back to look for the user's commit activity (GraphQL contributionsCollection is capped at 1 year)."""

MEANINGFUL_MIN_COMMITS = int(os.getenv("MEANINGFUL_MIN_COMMITS", "3"))
"""Minimum commits the user must have in a repo for it to count as 'meaningful' (kills drive-by commits)."""

FORK_MIN_COMMITS = int(os.getenv("FORK_MIN_COMMITS", "10"))
"""For forks, require at least this many user commits — kills the 'forked a huge repo, made one commit' problem."""

OWNER_BOOST = float(os.getenv("OWNER_BOOST", "1.5"))
"""Multiplier applied to collaborator scores in repos the user owns."""

MIN_SHARED_REPOS = int(os.getenv("MIN_SHARED_REPOS", "2"))
"""A collaborator must share at least this many repos with the user — unless DEEP_COLLAB_THRESHOLD is hit."""

DEEP_COLLAB_THRESHOLD = int(os.getenv("DEEP_COLLAB_THRESHOLD", "25"))
"""Single-repo escape hatch: a collaborator with raw_score above this qualifies even with only one shared repo."""

# Commit fetching settings
COMMIT_MAX_REPOS = int(os.getenv("COMMIT_MAX_REPOS", "10"))
"""Maximum number of repos to fetch commits from."""

COMMIT_PER_REPO = int(os.getenv("COMMIT_PER_REPO", "30"))
"""Number of commits to fetch per repository."""

# API settings
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "5"))
"""Timeout in seconds for API requests."""

# Data source
DATA_SOURCE_TYPE = os.getenv("DATA_SOURCE", "direct")
"""Data source type: 'direct' for immediate API calls, 'queued' for batch processing."""

# Widget settings
WIDGET_ORDER = ["grade", "impact", "collaborators", "focus", "languages", "achievements"]
"""Default order of widgets. Customize by reordering this list."""

ENABLED_WIDGETS = ["grade", "impact", "collaborators", "focus", "languages", "achievements"]
"""Which widgets to display. Remove any you don't want to show."""

# Language filtering
HIDDEN_LANGUAGES = []
"""Languages to exclude from stats (e.g., ["HTML", "CSS", "Makefile"])."""

# Tag settings
TAG_MAX_COUNT = int(os.getenv("TAG_MAX_COUNT", "6"))
"""Maximum number of tags to display (1-20)."""

TAG_LANGUAGE_MAP = {
    "Python": ["ML", "Backend"],
    "JavaScript": ["Frontend"],
    "TypeScript": ["Frontend"],
    "HTML": ["Frontend"],
    "CSS": ["Frontend"],
    "Go": ["Backend"],
    "Rust": ["Systems", "Backend"],
    "Java": ["Backend"],
    "C++": ["Systems"],
    "C": ["Systems"],
    "Swift": ["Mobile"],
    "Kotlin": ["Mobile", "Backend"],
    "Ruby": ["Backend"],
    "PHP": ["Backend"],
    "Shell": ["DevOps"],
    "Dockerfile": ["DevOps"],
    "HCL": ["DevOps", "Cloud"],
    "Jupyter Notebook": ["ML"],
}
"""Map programming languages to developer role categories."""

TAG_TOPIC_MAP = {
    "machine-learning": "ML",
    "deep-learning": "ML",
    "ai": "ML",
    "frontend": "Frontend",
    "react": "Frontend",
    "vue": "Frontend",
    "backend": "Backend",
    "api": "Backend",
    "database": "Database",
    "devops": "DevOps",
    "docker": "DevOps",
    "kubernetes": "DevOps",
    "security": "Security",
    "cloud": "Cloud",
    "aws": "Cloud",
    "azure": "Cloud",
    "gcp": "Cloud",
}
"""Map repository topics to developer role categories."""

# --- Service-specific additions (v2 of config) ---

PORT = int(os.getenv("GENERATOR_PORT", "5002"))
SETTINGS_DB_PATH = os.getenv("GENERATOR_SETTINGS_DB_PATH", "./data/settings.db")
WIDGETS_DB_PATH = os.getenv("GENERATOR_WIDGETS_DB_PATH", "./data/widgets.db")
FETCHER_URL = os.getenv("FETCHER_URL", "http://localhost:5001")
FETCHER_INTERNAL_TOKEN = os.getenv("FETCHER_INTERNAL_TOKEN", "")
REDIS_URL = os.getenv("REDIS_URL", "")
ENROLLMENT_DAILY_CAP = int(os.getenv("ENROLLMENT_DAILY_CAP", "50"))
WIDGET_LRU_PER_USER = int(os.getenv("WIDGET_LRU_PER_USER", "10"))
POLL_INTERVAL_MINUTES = int(os.getenv("GENERATOR_POLL_INTERVAL_MINUTES", "15"))

# --- Mini-PC capacity controls ---
# The generator runs on a single mini PC, so the constraining resources are
# CPU (SVG render) and the GitHub PAT (fetch). Everything here is tunable via
# env so the operator can loosen limits after measuring real load.

# Per-IP sliding-window rate limits: (max_hits, window_seconds). These are
# anti-abuse ceilings, not capacity controls — the mini PC is actually
# protected by the global semaphore + worker pool + queue cap below, so
# per-IP numbers stay lenient. Tighten via env only if you see a specific
# abuser.
RATE_LIMIT_READ_MAX    = int(os.getenv("RATE_LIMIT_READ_MAX", "3000"))
RATE_LIMIT_READ_WINDOW = int(os.getenv("RATE_LIMIT_READ_WINDOW", "60"))
RATE_LIMIT_MUTATE_MAX    = int(os.getenv("RATE_LIMIT_MUTATE_MAX", "120"))
RATE_LIMIT_MUTATE_WINDOW = int(os.getenv("RATE_LIMIT_MUTATE_WINDOW", "60"))
RATE_LIMIT_ENROLL_MAX    = int(os.getenv("RATE_LIMIT_ENROLL_MAX", "60"))
RATE_LIMIT_ENROLL_WINDOW = int(os.getenv("RATE_LIMIT_ENROLL_WINDOW", "300"))

# Global across-all-IPs caps. These are the mini-PC backstop: even a
# thousand-IP botnet can't induce more than this much work at once.
GENERATE_CONCURRENCY    = int(os.getenv("GENERATE_CONCURRENCY", "2"))
PREFETCH_MAX_WORKERS    = int(os.getenv("PREFETCH_MAX_WORKERS", "2"))
PENDING_JOB_QUEUE_CAP   = int(os.getenv("PENDING_JOB_QUEUE_CAP", "200"))
# How long a /generate caller will wait for the semaphore before giving up.
GENERATE_SEMAPHORE_WAIT_S = float(os.getenv("GENERATE_SEMAPHORE_WAIT_S", "15"))

# --- GitHub OAuth ---
GITHUB_OAUTH_CLIENT_ID = os.getenv("GITHUB_OAUTH_CLIENT_ID", "")
GITHUB_OAUTH_CLIENT_SECRET = os.getenv("GITHUB_OAUTH_CLIENT_SECRET", "")
GITHUB_OAUTH_REDIRECT_URI = os.getenv("GITHUB_OAUTH_REDIRECT_URI", "")

# Flask session secret. Generate once: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = os.getenv("GENERATOR_SECRET_KEY", "")

# Dev-only override; defaults to True so production HTTPS cookies work.
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() != "false"

# CSRF defense-in-depth: Origin/Referer allowlist for state-changing routes.
ALLOWED_ORIGINS = tuple(
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "https://gh-stats.com").split(",") if o.strip()
)

# Per-login rate limit on mutate routes, layered on top of per-IP limits.
RATE_LIMIT_MUTATE_PER_LOGIN_MAX    = int(os.getenv("RATE_LIMIT_MUTATE_PER_LOGIN_MAX", "120"))
RATE_LIMIT_MUTATE_PER_LOGIN_WINDOW = int(os.getenv("RATE_LIMIT_MUTATE_PER_LOGIN_WINDOW", "60"))
