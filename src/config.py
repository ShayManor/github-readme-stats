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
