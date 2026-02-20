"""Configuration for GitHub widget generator."""

import os

# Collaborator settings
COLLABORATOR_MIN_COMMITS = int(os.getenv("COLLABORATOR_MIN_COMMITS", "5"))
"""Minimum commits in a shared repo to be considered a collaborator (lowered to 5 for better detection)."""

COLLABORATOR_MAX_REPO_SIZE = int(os.getenv("COLLABORATOR_MAX_REPO_SIZE", "150"))
"""Maximum contributors in a repo to be included (filters out huge OSS projects)."""

COLLABORATOR_TOP_REPOS = int(os.getenv("COLLABORATOR_TOP_REPOS", "8"))
"""Number of user's top repos to check for collaborators (increased to find more collaborators)."""

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
