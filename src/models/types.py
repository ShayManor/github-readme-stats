"""Data class definitions for widget components."""

from dataclasses import dataclass, field


@dataclass
class GradeData:
    grade: str          # e.g. "A++", "S+", "B-"
    score: float        # 0-100
    stats: dict         # {"commits": 1423, "prs": 87, "stars": 342, "repos": 28, "followers": 156}
    tags: list          # list of TagData
    breakdown: dict = field(default_factory=dict)  # optional bar breakdown


@dataclass
class TagData:
    tag: str
    source: str = "earned"    # "earned" | "chosen"
    confidence: float = 1.0


@dataclass
class ImpactWeek:
    week_start: str     # ISO date
    commits: int = 0
    additions: int = 0
    deletions: int = 0


@dataclass
class CollaboratorData:
    username: str
    avatar_b64: str = ""      # base64 encoded avatar
    shared_repos: int = 0
    shared_commits: int = 0


@dataclass
class FocusCategory:
    category: str
    percentage: float
    commit_count: int = 0


@dataclass
class LanguageData:
    language: str
    percentage: float
    loc: int = 0              # lines of code or repo count


@dataclass
class AchievementData:
    title: str
    subtitle: str = ""
    event_date: str = ""
    icon: str = "trophy"      # trophy, medal, star, hackathon
